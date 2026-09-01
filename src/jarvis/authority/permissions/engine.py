"""Explicit, fail-closed permission evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ...contracts import DeviceIdentity, Identity, PermissionDecision, PermissionEffect


@dataclass(frozen=True, slots=True)
class PermissionRule:
    action_prefix: str
    effect: PermissionEffect
    reason_code: str


class PolicyPermissionEngine:
    """Evaluate actor, device, capability, scope, risk, and policy together."""

    def __init__(self, rules: tuple[PermissionRule, ...] = ()) -> None:
        self.rules = rules or (
            PermissionRule("tool.status.read", PermissionEffect.ALLOW, "safe_read_tool"),
            PermissionRule("tool.echo.reversible", PermissionEffect.ALLOW, "reversible_tool"),
            PermissionRule("tool.project.tests.run", PermissionEffect.ALLOW, "safe_test_runner"),
            PermissionRule("tool.desktop.context.read", PermissionEffect.ALLOW, "safe_desktop_context_read"),
            PermissionRule("tool.screen.observe", PermissionEffect.ALLOW, "on_demand_screen_read"),
            PermissionRule("tool.screen.latest", PermissionEffect.ALLOW, "cached_screen_read"),
            PermissionRule("tool.computer.audio.adjust", PermissionEffect.ALLOW, "computer_audio_boundary"),
            PermissionRule("tool.computer.window.control", PermissionEffect.ALLOW, "computer_window_boundary"),
            PermissionRule("tool.computer.clipboard.read", PermissionEffect.ALLOW, "computer_clipboard_boundary"),
            PermissionRule("tool.computer.clipboard.write", PermissionEffect.ALLOW, "computer_clipboard_boundary"),
            PermissionRule("tool.computer.keyboard.type", PermissionEffect.ALLOW, "computer_keyboard_boundary"),
            PermissionRule("tool.mcp.", PermissionEffect.ALLOW, "mcp_capability_boundary"),
            PermissionRule("mission.start", PermissionEffect.ALLOW, "bounded_mission_start"),
            PermissionRule("skill.", PermissionEffect.ALLOW, "registered_skill_execution"),
            PermissionRule("computer.open_application", PermissionEffect.ALLOW, "safe_application_open"),
            PermissionRule("computer.change_volume", PermissionEffect.ALLOW, "safe_volume_change"),
            PermissionRule("computer.mute", PermissionEffect.ALLOW, "safe_audio_control"),
            PermissionRule("computer.unmute", PermissionEffect.ALLOW, "safe_audio_control"),
            PermissionRule("computer.open_file", PermissionEffect.ALLOW, "safe_file_open"),
            PermissionRule("computer.open_folder", PermissionEffect.ALLOW, "safe_folder_open"),
            PermissionRule("computer.stop_safe_process", PermissionEffect.ALLOW, "safe_process_stop"),
            PermissionRule("computer.list_processes", PermissionEffect.ALLOW, "safe_process_read"),
            PermissionRule("computer.inspect_file", PermissionEffect.ALLOW, "safe_file_read"),
            PermissionRule("computer.search_files", PermissionEffect.ALLOW, "safe_file_search"),
            PermissionRule("computer.focus_window", PermissionEffect.ALLOW, "safe_window_focus"),
            PermissionRule("computer.screen_snapshot_on_demand", PermissionEffect.ALLOW, "on_demand_screen_read"),
            PermissionRule("browser.open_url", PermissionEffect.ALLOW, "safe_browser_navigation"),
            PermissionRule("browser.navigate", PermissionEffect.ALLOW, "safe_browser_navigation"),
            PermissionRule("browser.back", PermissionEffect.ALLOW, "safe_browser_navigation"),
            PermissionRule("browser.forward", PermissionEffect.ALLOW, "safe_browser_navigation"),
            PermissionRule("browser.read_page", PermissionEffect.ALLOW, "safe_browser_read"),
            PermissionRule("browser.inspect_accessibility_tree", PermissionEffect.ALLOW, "safe_browser_read"),
            PermissionRule("browser.find_element", PermissionEffect.ALLOW, "safe_browser_read"),
            PermissionRule("browser.extract_text", PermissionEffect.ALLOW, "safe_browser_read"),
            PermissionRule("browser.tabs", PermissionEffect.ALLOW, "safe_browser_read"),
            PermissionRule("home.read", PermissionEffect.ALLOW, "safe_home_read"),
            PermissionRule("home.read_state", PermissionEffect.ALLOW, "safe_home_read"),
            PermissionRule("home.read_sensor", PermissionEffect.ALLOW, "safe_home_read"),
            PermissionRule("home.turn_on", PermissionEffect.ALLOW, "safe_home_control"),
            PermissionRule("home.turn_off", PermissionEffect.ALLOW, "safe_home_control"),
            PermissionRule("home.set_brightness", PermissionEffect.ALLOW, "safe_home_control"),
            PermissionRule("home.set_color", PermissionEffect.ALLOW, "safe_home_control"),
            PermissionRule("home.trigger_scene", PermissionEffect.ALLOW, "safe_home_control"),
            PermissionRule("home.set_temperature", PermissionEffect.ALLOW, "safe_home_control"),
            PermissionRule("home.publish_mqtt", PermissionEffect.ALLOW, "restricted_mqtt_publish"),
            PermissionRule("communication.read", PermissionEffect.ALLOW, "safe_communication_read"),
            PermissionRule("communication.send", PermissionEffect.ALLOW, "configured_communication"),
            PermissionRule("engineering.", PermissionEffect.ALLOW, "bounded_engineering"),
            PermissionRule("research.", PermissionEffect.ALLOW, "bounded_research"),
            PermissionRule("perception.", PermissionEffect.ALLOW, "on_demand_perception"),
            PermissionRule("system.", PermissionEffect.ALLOW, "bounded_system_read"),
            PermissionRule("workspace.", PermissionEffect.ALLOW, "bounded_workspace_action"),
            PermissionRule("briefing.", PermissionEffect.ALLOW, "bounded_briefing_action"),
            PermissionRule("backup.", PermissionEffect.ALLOW, "scoped_backup_action"),
            PermissionRule("tool.", PermissionEffect.REQUIRE_APPROVAL, "tool_policy_requires_approval"),
            PermissionRule("computer.", PermissionEffect.REQUIRE_APPROVAL, "computer_action_requires_approval"),
        )

    async def evaluate(
        self,
        identity: Identity | None,
        device: DeviceIdentity | None,
        action: str,
        resource: Mapping[str, object] | None = None,
    ) -> PermissionDecision:
        resource = resource or {}
        if identity is None or device is None:
            return PermissionDecision(PermissionEffect.DENY, "identity_or_device_missing")
        if identity.owner_id != device.owner_id:
            return PermissionDecision(PermissionEffect.DENY, "owner_binding_mismatch")
        required_scope = resource.get("required_scope")
        if isinstance(required_scope, str) and required_scope not in device.scopes:
            return PermissionDecision(PermissionEffect.DENY, "scope_missing")
        required_capabilities = resource.get("required_capabilities", ())
        if any(capability not in device.capabilities for capability in required_capabilities):
            return PermissionDecision(PermissionEffect.DENY, "device_capability_missing")
        risk = str(resource.get("risk_level", "read"))
        if risk not in {"read", "safe", "reversible", "consequential", "critical", "forbidden_autonomous"}:
            return PermissionDecision(PermissionEffect.DENY, "unknown_risk_level")
        if risk in {"critical", "forbidden_autonomous"}:
            return PermissionDecision(PermissionEffect.DENY, "risk_forbidden_by_default")
        if bool(resource.get("requires_approval", False)) or risk == "consequential":
            return PermissionDecision(PermissionEffect.REQUIRE_APPROVAL, "risk_requires_approval")
        for rule in self.rules:
            if action.startswith(rule.action_prefix):
                return PermissionDecision(rule.effect, rule.reason_code)
        return PermissionDecision(PermissionEffect.DENY, "no_allow_rule")
