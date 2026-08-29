from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from jarvis.attention.policy import AttentionContext
from jarvis.authority.identity.service import EnrollmentGrant
from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig
from jarvis.contracts import PersonalizationUpdate, VoiceSessionContext, VoiceTranscript
from jarvis.events import Event, EventCategory
from jarvis.time_windows import in_time_window


class PhaseEightFinalClosureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await self.runtime.start()
        self.identity = await self.runtime.identity.bootstrap_owner("Closure Owner")
        grant = await self.runtime.identity.create_enrollment(
            EnrollmentGrant(
                self.identity.owner_id,
                "Closure Device",
                "desktop",
                "windows",
                ("tool.request",),
                ("communication.send",),
            )
        )
        issued = await self.runtime.identity.redeem_enrollment(grant.code)
        self.device = await self.runtime.identity.authenticate(issued.raw, issued.device_id)

    async def asyncTearDown(self) -> None:
        await self.runtime.shutdown()

    async def test_queue_idempotency_voice_and_spoof_resistance(self) -> None:
        self.assertIs(self.runtime.notification_delivery.voice_core, self.runtime.voice)
        await self.runtime.operations.set_mode(self.identity.owner_id, "focus")
        item = await self.runtime.notifications.create(self.identity.owner_id, "Info", "queued", severity="info")
        first = await self.runtime.notification_delivery.deliver(self.identity.owner_id, item, mode="normal", active_voice=False)
        self.assertEqual(first.status, "queued")
        second = await self.runtime.notification_delivery.deliver(self.identity.owner_id, item)
        self.assertEqual(second.status, "queued")
        queue_attempts = [
            row
            for row in self.runtime.repository.delivery_attempts(self.identity.owner_id)
            if row["notification_id"] == item.notification_id and row["channel"] == "queue"
        ]
        self.assertEqual(len(queue_attempts), 1)
        await self.runtime.notification_delivery.reevaluate_queued(self.identity.owner_id)
        self.assertEqual(len(self.runtime.notification_delivery._queued[self.identity.owner_id]), 1)
        await self.runtime.operations.set_mode(self.identity.owner_id, "normal")
        await self.runtime.notification_delivery.reevaluate_queued(self.identity.owner_id)
        delivered = (await self.runtime.notifications.list(self.identity.owner_id))[0]
        self.assertIsNotNone(delivered.delivered_at)
        self.assertNotIn(item.notification_id, self.runtime.notification_delivery._queued[self.identity.owner_id])

        await self.runtime.voice.start(
            VoiceSessionContext("closure-voice", self.device.device_id, owner_id=self.identity.owner_id)
        )
        with self.assertRaisesRegex(ValueError, "voice owner does not match"):
            await self.runtime.voice.process_transcript(
                VoiceTranscript("spoof", True),
                self.identity,
                replace(self.device, owner_id="owner-spoof"),
            )
        await self.runtime.voice.stop()

    async def test_followup_owner_thread_and_timezone_auto_send(self) -> None:
        followup = await self.runtime.communication_followups.create(self.identity.owner_id, "thread-a")
        other_thread = await self.runtime.communication_followups.create(self.identity.owner_id, "thread-b")
        await self.runtime.event_bus.publish(
            Event.create(
                "communication.received",
                EventCategory.COMMUNICATION,
                correlation_id="c",
                actor_id="other",
                payload={"owner_id": "other", "thread_id": "thread-a"},
            )
        )
        self.assertTrue(all(item.status == "open" for item in await self.runtime.communication_followups.list(self.identity.owner_id)))
        await self.runtime.event_bus.publish(
            Event.create(
                "communication.received",
                EventCategory.COMMUNICATION,
                correlation_id="c",
                actor_id=self.identity.owner_id,
                payload={"owner_id": self.identity.owner_id, "thread_id": "wrong-thread"},
            )
        )
        self.assertTrue(all(item.status == "open" for item in await self.runtime.communication_followups.list(self.identity.owner_id)))
        await self.runtime.event_bus.publish(
            Event.create(
                "communication.received",
                EventCategory.COMMUNICATION,
                correlation_id="c",
                actor_id=self.identity.owner_id,
                payload={"owner_id": self.identity.owner_id, "thread_id": "thread-a"},
            )
        )
        statuses = {item.followup_id: item.status for item in await self.runtime.communication_followups.list(self.identity.owner_id)}
        self.assertEqual(statuses[followup.followup_id], "resolved")
        self.assertEqual(statuses[other_thread.followup_id], "open")

        await self.runtime.personalization.update(self.identity.owner_id, PersonalizationUpdate("timezone", "Africa/Cairo", "user"))
        rule = await self.runtime.communication_followups.create_rule(
            self.identity.owner_id,
            {
                "channel": "local",
                "recipient_allowlist": ["owner"],
                "message_class": "normal",
                "approval_requirement": "none",
                "allowed_time_start": "02:00",
                "allowed_time_end": "02:30",
            },
        )
        now = datetime(2026, 1, 1, 0, 15, tzinfo=UTC)
        result = await self.runtime.communication_followups.execute_scoped_auto_send(
            self.identity.owner_id,
            rule.rule_id,
            "local",
            "owner",
            "timezone",
            self.identity,
            self.device,
            now=now,
        )
        self.assertEqual(result.status, "sent")
        allowed, reason = self.runtime.communication_followups.can_auto_send_scoped(
            self.identity.owner_id,
            "local",
            "owner",
            "outside",
            now=datetime(2026, 1, 1, 1, 0, tzinfo=UTC),
            timezone_name="Africa/Cairo",
        )
        self.assertFalse(allowed)
        self.assertEqual(reason, "no_scoped_auto_send_policy")

    async def test_owner_timezone_drives_attention_quiet_hours_and_edge_windows(self) -> None:
        now = datetime(2026, 1, 1, 0, 15, tzinfo=UTC)
        self.assertTrue(in_time_window("02:00", "02:30", now=now, timezone_name="Africa/Cairo"))
        self.assertFalse(
            in_time_window(
                "02:00",
                "02:30",
                now=datetime(2026, 1, 1, 1, 0, tzinfo=UTC),
                timezone_name="Africa/Cairo",
            )
        )
        self.assertTrue(
            in_time_window(
                "23:00",
                "01:00",
                now=datetime(2026, 1, 1, 22, 30, tzinfo=UTC),
                timezone_name="Africa/Cairo",
            )
        )
        self.assertFalse(in_time_window("02:00", "02:30", now=now, timezone_name="Not/AZone"))
        await self.runtime.personalization.patch(
            self.identity.owner_id,
            {"timezone": "Africa/Cairo", "quiet_hours": ["02:00", "02:30"]},
        )
        item = await self.runtime.notifications.create(self.identity.owner_id, "Quiet", "owner-local quiet hour", severity="info")
        result = await self.runtime.notification_delivery.deliver(self.identity.owner_id, item, now=now)
        self.assertEqual(result.status, "queued")
        presence = await self.runtime.presence.snapshot(self.identity.owner_id, now=now)
        decision = self.runtime.attention.decide(
            item,
            presence,
            context=AttentionContext(quiet_hours=("02:00", "02:30"), timezone_name="Africa/Cairo"),
            now=now,
        )
        self.assertEqual(decision.reason, "quiet_hours")

    async def test_retention_preserves_latest_and_active(self) -> None:
        now = datetime.now(UTC)
        old = now - timedelta(days=120)
        await self.runtime.operations.set_mode(self.identity.owner_id, "work")
        active_focus = await self.runtime.operations.start_focus(self.identity.owner_id, duration_seconds=3600)
        active_followup = await self.runtime.communication_followups.create(
            self.identity.owner_id,
            "active-thread",
            due_at=now + timedelta(days=1),
        )
        resolved_followup = await self.runtime.communication_followups.create(
            self.identity.owner_id,
            "resolved-thread",
            due_at=old,
        )
        await self.runtime.communication_followups.acknowledge(self.identity.owner_id, resolved_followup.followup_id)
        rule = await self.runtime.communication_followups.create_rule(
            self.identity.owner_id,
            {"channel": "local", "recipient_allowlist": ["owner"], "approval_requirement": "none"},
        )
        item = await self.runtime.notifications.create(self.identity.owner_id, "Retention", "attempt")
        old_delivery = await self.runtime.notification_delivery._attempt(
            self.identity.owner_id, item, "hud", None, "delivered", None, "retention-old"
        )
        await self.runtime.notification_delivery._attempt(
            self.identity.owner_id, item, "hud", None, "delivered", None, "retention-current"
        )
        await self.runtime.communication_followups.record_auto_send_attempt(
            self.identity.owner_id, rule.rule_id, "local", "owner", "old", status="denied", now=old
        )
        await self.runtime.communication_followups.record_auto_send_attempt(
            self.identity.owner_id, rule.rule_id, "local", "owner", "current", status="denied", now=now
        )
        connection = self.runtime.repository.database.connection
        connection.execute(
            "UPDATE notification_delivery_attempts SET attempted_at = ? WHERE id = ?",
            (old.isoformat(), old_delivery.attempt_id),
        )
        mode_rows = self.runtime.repository.personal_modes(self.identity.owner_id)
        connection.execute("UPDATE personal_modes SET started_at = ? WHERE id = ?", (old.isoformat(), mode_rows[-1]["id"]))
        connection.execute(
            "UPDATE communication_followups SET resolved_at = ? WHERE id = ?",
            (old.isoformat(), resolved_followup.followup_id),
        )
        connection.execute(
            "INSERT INTO routine_runs(id, owner_id, routine_id, status, result_json, started_at, completed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("routine-old", self.identity.owner_id, "focus_lighting", "completed", "{}", old.isoformat(), old.isoformat()),
        )
        connection.execute(
            "INSERT INTO routine_runs(id, owner_id, routine_id, status, result_json, started_at, completed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("routine-current", self.identity.owner_id, "focus_lighting", "completed", "{}", now.isoformat(), now.isoformat()),
        )
        connection.execute(
            "INSERT INTO focus_sessions(id, owner_id, status, started_at, metadata_json) VALUES (?, ?, ?, ?, ?)",
            ("focus-old", self.identity.owner_id, "completed", old.isoformat(), "{}"),
        )
        connection.commit()
        audit_before = connection.execute("SELECT COUNT(*) FROM audit_records").fetchone()[0]
        credential_before = connection.execute(
            "SELECT COUNT(*) FROM credentials JOIN devices ON devices.id = credentials.device_id WHERE devices.owner_id = ?",
            (self.identity.owner_id,),
        ).fetchone()[0]

        result = self.runtime.repository.cleanup_phase08_operational_state(self.identity.owner_id, now=now)

        self.assertEqual(result["delivery_attempts"], 1)
        self.assertEqual(result["auto_send_attempts"], 1)
        self.assertEqual(result["routine_runs"], 1)
        self.assertEqual(result["focus_sessions"], 1)
        self.assertEqual(result["resolved_followups"], 1)
        self.assertGreaterEqual(result["personal_modes"], 1)
        self.assertEqual(
            connection.execute(
                "SELECT COUNT(*) FROM notification_delivery_attempts WHERE owner_id = ?",
                (self.identity.owner_id,),
            ).fetchone()[0],
            1,
        )
        self.assertEqual(
            connection.execute(
                "SELECT COUNT(*) FROM communication_auto_send_attempts WHERE owner_id = ?",
                (self.identity.owner_id,),
            ).fetchone()[0],
            1,
        )
        self.assertEqual(
            connection.execute(
                "SELECT COUNT(*) FROM routine_runs WHERE owner_id = ?", (self.identity.owner_id,)
            ).fetchone()[0],
            1,
        )
        self.assertIsNotNone(
            connection.execute(
                "SELECT id FROM focus_sessions WHERE id = ? AND status = 'active'", (active_focus.focus_id,)
            ).fetchone()
        )
        self.assertIsNotNone(
            connection.execute(
                "SELECT id FROM communication_followups WHERE id = ? AND status = 'open'",
                (active_followup.followup_id,),
            ).fetchone()
        )
        self.assertIsNotNone(
            connection.execute(
                "SELECT id FROM personal_modes WHERE owner_id = ? ORDER BY started_at DESC LIMIT 1",
                (self.identity.owner_id,),
            ).fetchone()
        )
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM audit_records").fetchone()[0], audit_before)
        self.assertEqual(
            connection.execute(
                "SELECT COUNT(*) FROM credentials JOIN devices ON devices.id = credentials.device_id WHERE devices.owner_id = ?",
                (self.identity.owner_id,),
            ).fetchone()[0],
            credential_before,
        )
