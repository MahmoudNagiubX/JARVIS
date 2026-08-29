"""Fail-closed autonomy levels for automatic actions."""

from __future__ import annotations

from collections.abc import Sequence

from ..contracts import AutonomyDecision, AutonomyLevel, AutonomyRule


class AutonomyPolicy:
    def __init__(self, rules: Sequence[AutonomyRule] = ()) -> None:
        self.rules = tuple(rules) or (
            AutonomyRule("project.tests.run", AutonomyLevel.SAFE_AUTO, "bounded local test runner"),
            AutonomyRule("workspace.inspect", AutonomyLevel.SAFE_AUTO, "read-only workspace inspection"),
            AutonomyRule("computer.open_application", AutonomyLevel.SAFE_AUTO, "allowlisted application launch"),
            AutonomyRule("computer.change_volume", AutonomyLevel.SAFE_AUTO, "local volume adjustment"),
            AutonomyRule("computer.mute", AutonomyLevel.SAFE_AUTO, "local mute toggle"),
            AutonomyRule("computer.unmute", AutonomyLevel.SAFE_AUTO, "local unmute toggle"),
            AutonomyRule("computer.open_file", AutonomyLevel.SAFE_AUTO, "open a selected local file"),
            AutonomyRule("computer.open_folder", AutonomyLevel.SAFE_AUTO, "open a selected local folder"),
            AutonomyRule("computer.list_processes", AutonomyLevel.OBSERVE, "bounded process observation"),
            AutonomyRule("computer.inspect_file", AutonomyLevel.OBSERVE, "bounded file observation"),
            AutonomyRule("computer.search_files", AutonomyLevel.SAFE_AUTO, "bounded local file search"),
            AutonomyRule("browser.open_url", AutonomyLevel.SAFE_AUTO, "open a web page"),
            AutonomyRule("browser.navigate", AutonomyLevel.SAFE_AUTO, "navigate a browser session"),
            AutonomyRule("browser.read_page", AutonomyLevel.OBSERVE, "read page content"),
            AutonomyRule("browser.inspect_accessibility_tree", AutonomyLevel.OBSERVE, "inspect accessibility metadata"),
            AutonomyRule("home.turn_on", AutonomyLevel.SAFE_AUTO, "safe room device control"),
            AutonomyRule("home.turn_off", AutonomyLevel.SAFE_AUTO, "safe room device control"),
            AutonomyRule("home.set_brightness", AutonomyLevel.SAFE_AUTO, "safe room brightness control"),
            AutonomyRule("home.set_color", AutonomyLevel.SAFE_AUTO, "safe room color control"),
            AutonomyRule("home.trigger_scene", AutonomyLevel.SAFE_AUTO, "safe room scene control"),
            AutonomyRule("home.set_temperature", AutonomyLevel.SAFE_AUTO, "safe room temperature control"),
            AutonomyRule("home.publish_mqtt", AutonomyLevel.SAFE_AUTO, "restricted MQTT publish"),
            AutonomyRule("communication.read", AutonomyLevel.OBSERVE, "read configured communications"),
            AutonomyRule("computer.observe", AutonomyLevel.OBSERVE, "observation only"),
            AutonomyRule("computer.input", AutonomyLevel.APPROVAL_REQUIRED, "computer input changes state"),
            AutonomyRule("message.send.scoped_auto", AutonomyLevel.AUTO_NOTIFY, "verified persisted scoped communication policy"),
            AutonomyRule("message.send", AutonomyLevel.APPROVAL_REQUIRED, "external communication requires approval"),
            AutonomyRule("files.delete", AutonomyLevel.BLOCKED, "destructive file operation"),
            AutonomyRule("account.", AutonomyLevel.BLOCKED, "account/security operation"),
        )

    def decide(self, action: str) -> AutonomyDecision:
        for rule in self.rules:
            if action == rule.action_prefix or action.startswith(rule.action_prefix + ".") or action.startswith(rule.action_prefix):
                return AutonomyDecision(
                    action,
                    rule.level,
                    rule.level in {AutonomyLevel.SAFE_AUTO, AutonomyLevel.AUTO_NOTIFY, AutonomyLevel.OBSERVE},
                    rule.level == AutonomyLevel.APPROVAL_REQUIRED,
                    rule.reason,
                )
        return AutonomyDecision(action, AutonomyLevel.APPROVAL_REQUIRED, False, True, "unknown action requires approval")
