"""Small metadata-first registry for declarative skills."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from .models import Skill, SkillManifest, SkillStatus, SkillStep, SkillVersion
from ..events import Event, EventCategory, EventState


class SkillRegistry:
    """Registry metadata is cheap to list; full instructions load on demand."""

    def __init__(self, repository: object | None = None) -> None:
        self.repository = repository
        self._skills: dict[str, Skill] = {}
        self._versions: dict[str, list[SkillVersion]] = {}

    def register(self, skill: Skill) -> Skill:
        manifest = skill.manifest
        if not manifest.skill_id.strip() or not manifest.name.strip() or not manifest.description.strip():
            raise ValueError("skill identity and description are required")
        if manifest.estimated_duration <= 0 or manifest.estimated_duration > 3_600:
            raise ValueError("skill duration must be between 0 and 3600 seconds")
        if not 0 <= manifest.autonomy_level <= 3:
            raise ValueError("skill autonomy level must be between 0 and 3")
        if any(step.risk_level in {"critical", "forbidden_autonomous"} for step in skill.steps):
            raise ValueError("skill contains a forbidden autonomous step")
        self._skills[manifest.skill_id] = skill
        version = SkillVersion(f"skill-version-{manifest.skill_id}-{manifest.version}", manifest.skill_id, manifest.version, manifest, manifest.owner, "registered", None, datetime.now(UTC))
        self._versions.setdefault(manifest.skill_id, []).append(version)
        if self.repository is not None and hasattr(self.repository, "insert_skill"):
            self.repository.insert_skill(skill)
            self.repository.insert_skill_version(version)
            self._record("skill.registered", skill, EventState.COMPLETED)
        return skill

    def get(self, skill_id: str, *, include_disabled: bool = False) -> Skill | None:
        skill = self._skills.get(skill_id)
        if skill is None and self.repository is not None and hasattr(self.repository, "skill"):
            row = self.repository.skill(skill_id)
            if row:
                skill = self._from_row(row)
        if skill is None or (not include_disabled and skill.manifest.status is SkillStatus.DISABLED):
            return None
        return skill

    def list(self, *, include_disabled: bool = True) -> tuple[SkillManifest, ...]:
        if self.repository is not None and hasattr(self.repository, "skills"):
            for row in self.repository.skills():
                if str(row["id"]) not in self._skills:
                    self._from_row(row)
        values = (skill.manifest for skill in self._skills.values() if include_disabled or skill.manifest.status is not SkillStatus.DISABLED)
        return tuple(sorted(values, key=lambda item: item.skill_id))

    def set_enabled(self, skill_id: str, enabled: bool) -> Skill:
        skill = self.get(skill_id, include_disabled=True)
        if skill is None:
            raise KeyError(skill_id)
        manifest = replace(skill.manifest, status=SkillStatus.ACTIVE if enabled else SkillStatus.DISABLED)
        updated = Skill(manifest, skill.steps, skill.instructions_path, skill.instructions)
        self._skills[skill_id] = updated
        if self.repository is not None and hasattr(self.repository, "update_skill_status"):
            self.repository.update_skill_status(skill_id, manifest.status.value)
            self._record("skill.enabled" if enabled else "skill.disabled", updated, EventState.COMPLETED)
        return updated

    def version(self, skill: Skill, *, source: str, change_reason: str) -> Skill:
        previous = skill.manifest.version
        parts = previous.split(".")
        version = f"{int(parts[0])}.{int(parts[1])}.{int(parts[2]) + 1}" if len(parts) == 3 and all(part.isdigit() for part in parts) else previous + ".1"
        manifest = SkillManifest(skill.manifest.skill_id, skill.manifest.name, skill.manifest.description, version, skill.manifest.category, skill.manifest.inputs, skill.manifest.outputs, skill.manifest.required_capabilities, skill.manifest.risk_level, skill.manifest.autonomy_level, skill.manifest.estimated_duration, skill.manifest.workspace_scope, skill.manifest.network_requirement, skill.manifest.owner, skill.manifest.status)
        updated = Skill(manifest, skill.steps, skill.instructions_path, skill.instructions)
        self._skills[manifest.skill_id] = updated
        record = SkillVersion(f"skill-version-{manifest.skill_id}-{version}", manifest.skill_id, version, manifest, source, change_reason, previous, datetime.now(UTC))
        self._versions.setdefault(manifest.skill_id, []).append(record)
        if self.repository is not None and hasattr(self.repository, "insert_skill_version"):
            self.repository.insert_skill_version(record)
            self.repository.update_skill(updated)
            self._record("skill.versioned", updated, EventState.COMPLETED, {"previous_version": previous})
        return updated

    def _record(self, event_type: str, skill: Skill, state: EventState, extra: dict[str, object] | None = None) -> None:
        if self.repository is None or not hasattr(self.repository, "append_event"):
            return
        event = Event.create(event_type, EventCategory.SKILL, correlation_id=f"skill-{skill.manifest.skill_id}", actor_id=skill.manifest.owner, payload={"skill_id": skill.manifest.skill_id, "version": skill.manifest.version, "status": skill.manifest.status.value, **(extra or {})}, state=state)
        self.repository.append_event(event)

    def versions(self, skill_id: str) -> tuple[SkillVersion, ...]:
        if self.repository is not None and hasattr(self.repository, "skill_versions"):
            return tuple(self._version_from_row(row) for row in self.repository.skill_versions(skill_id))
        return tuple(self._versions.get(skill_id, ()))

    def _from_row(self, row: object) -> Skill:
        import json
        data = json.loads(str(row["manifest_json"]))
        for key in ("inputs", "outputs", "required_capabilities"):
            data[key] = tuple(data.get(key, ()))
        manifest = SkillManifest(**{**data, "status": SkillStatus(str(row["status"]))})
        skill = Skill(manifest, tuple())
        self._skills[manifest.skill_id] = skill
        return skill

    @staticmethod
    def _version_from_row(row: object) -> SkillVersion:
        import json
        data = json.loads(str(row["manifest_json"]))
        for key in ("inputs", "outputs", "required_capabilities"):
            data[key] = tuple(data.get(key, ()))
        data["status"] = SkillStatus(str(data.get("status", "active")))
        manifest = SkillManifest(**data)
        return SkillVersion(str(row["id"]), str(row["skill_id"]), str(row["version"]), manifest, str(row["source"]), str(row["change_reason"]), row["previous_version"], datetime.fromisoformat(str(row["created_at"])))


def builtin_skills() -> tuple[Skill, ...]:
    def item(skill_id: str, name: str, description: str, action: str, *, capability: str = "", risk: str = "read", approval: bool = False, category: str = "operations") -> Skill:
        manifest = SkillManifest(skill_id, name, description, category=category, inputs=("workspace_path",), outputs=("result",), required_capabilities=(capability,) if capability else (), risk_level=risk, autonomy_level=1 if not approval else 0)
        return Skill(manifest, (SkillStep(f"{skill_id}-step", name, action, required_capabilities=(capability,) if capability else (), risk_level=risk, requires_approval=approval),))
    return (
        item("project_status", "Project status", "Inspect a registered project without mutation.", "workspace.project_status", capability="workspace.read"),
        item("run_tests", "Run tests", "Run the existing bounded project test command.", "tool:project.tests.run", capability="project.tests.run", risk="safe"),
        item("debug_failed_build", "Debug failed build", "Prepare a bounded diagnostic mission for a failed build.", "mission.debug_project", capability="workspace.read", risk="consequential", approval=True),
        item("start_dev_environment", "Start development environment", "Request a scoped development environment start.", "workspace.start_dev", capability="workspace.dev", risk="consequential", approval=True),
        item("research_and_report", "Research and report", "Run bounded local-first research and preserve evidence.", "research.start", capability="research.local"),
        item("daily_brief", "Daily brief", "Generate an evidence-backed concise briefing.", "briefing.generate", category="briefing"),
        item("system_health_check", "System health check", "Read current JARVIS health and capability state.", "system.health", category="diagnostics"),
        item("backup_jarvis", "Backup JARVIS", "Create an explicit verified database backup.", "backup.create", capability="backup.create", risk="safe"),
    )
