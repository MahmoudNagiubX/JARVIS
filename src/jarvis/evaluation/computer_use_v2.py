"""Deterministic, product-owned Computer Use V2 evaluation suite.

Phase 18 Workstream A, Batch 02, Milestone 2. Reuses the existing
`EvaluationService`/`EvaluationCase`/`RegressionSuite` machinery (see
`jarvis.evaluation.service`) - this is **not** a second evaluation
authority. Every case exercises real product code (`ComputerActionService`,
`WindowsUIAutomationAdapter`, `WindowsNativeInputAdapter`) through
deterministic fakes at the OS/provider boundary; no GUI or live Windows
dependency is required to run this suite. Cases represent meaningful
product acceptance contracts (see Batch 02 task Section 8.1), not a
restatement of the unit test suite - keep each check short and focused.

`EvaluationResult.actual`/`detail` are durably persisted by
`EvaluationService` - every check here returns only booleans/short bounded
reason strings, never raw UI text/content (Section 8.8).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from ..authority.identity.service import EnrollmentGrant
from ..contracts import ComputerAction
from ..contracts.semantic_ui import SemanticBounds, SemanticElementSnapshot, SemanticResult
from .service import EvaluationCase, RegressionSuite

SUITE_NAME = "computer_use_v2"


def _snapshot(
    element_ref: str, window_ref: str = "window-1", *, name: str = "Target",
    actionable: bool = True, bounds: SemanticBounds | None = SemanticBounds(0, 0, 20, 20),
) -> SemanticElementSnapshot:
    return SemanticElementSnapshot(
        element_ref, window_ref, name, "ButtonControl", "targetButton",
        True, False, False, True, bounds, ("Invoke", "Toggle"), None, None, actionable=actionable,
    )


class _FakeSemanticAdapter:
    """Minimal, per-case-configurable stand-in for `SemanticDesktopAdapter`."""

    def __init__(self) -> None:
        self.available = True
        self.invoke_calls: list[str] = []
        self.toggle_calls: list[str] = []
        self.select_calls: list[str] = []
        self.get_element_calls: list[str] = []
        self.element_error: dict[str, str] = {}
        self.element_name: dict[str, str] = {}
        self.toggle_pre_post: tuple[int, int] = (0, 1)

    async def list_windows(self, device_id: str) -> SemanticResult:
        return SemanticResult("succeeded", {"windows": (), "filtered_count": 0})

    async def get_element(self, element_ref: str) -> SemanticResult:
        self.get_element_calls.append(element_ref)
        error = self.element_error.get(element_ref)
        if error is not None:
            return SemanticResult("failed", error_code=error)
        name = self.element_name.get(element_ref, "Target")
        return SemanticResult("succeeded", {"element": _snapshot(element_ref, name=name)})

    async def resolve_actionable_target(self, element_ref: str) -> SemanticResult:
        error = self.element_error.get(element_ref)
        if error is not None:
            status = "denied" if error in {
                "uia_element_identity_weak", "uia_target_not_interactable", "uia_sensitive_value_denied",
            } else "failed"
            return SemanticResult(status, error_code=error)
        name = self.element_name.get(element_ref, "Target")
        return SemanticResult("succeeded", {
            "element": _snapshot(element_ref, name=name),
            "reference_expires_at": datetime.now(UTC) + timedelta(seconds=45),
        })

    async def invoke(self, element_ref: str) -> SemanticResult:
        self.invoke_calls.append(element_ref)
        return SemanticResult("succeeded", {"element": _snapshot(element_ref), "verified": False, "verification_reason": "generic_invoke_no_postcondition"})

    async def toggle(self, element_ref: str) -> SemanticResult:
        self.toggle_calls.append(element_ref)
        pre, post = self.toggle_pre_post
        return SemanticResult("succeeded", {
            "element": _snapshot(element_ref), "verified": pre != post,
            "verification_reason": "fresh_state_confirmed_change" if pre != post else "fresh_state_unchanged",
            "pre_state": pre, "post_state": post,
        })

    async def select(self, element_ref: str) -> SemanticResult:
        self.select_calls.append(element_ref)
        return SemanticResult("succeeded", {"element": _snapshot(element_ref), "verified": True})


async def _new_runtime_context() -> SimpleNamespace:
    from ..bootstrap import create_runtime
    from ..config import JarvisConfig
    from ..contracts import ToolContext

    runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
    await runtime.start()
    identity = await runtime.identity.bootstrap_owner("Computer Use V2 Evaluation Owner")
    enrollment = await runtime.identity.create_enrollment(
        EnrollmentGrant(
            identity.owner_id, "Computer Use V2 Evaluation Device", "desktop", "windows",
            ("tool.request",), ("computer.observe", "computer.input"),
        )
    )
    issued = await runtime.identity.redeem_enrollment(enrollment.code)
    device = await runtime.identity.authenticate(issued.raw, issued.device_id)
    fake_semantic = _FakeSemanticAdapter()
    runtime.computer_actions.controller.local.semantic_adapter = fake_semantic
    session = runtime.repository.create_session(identity.owner_id, device.device_id)
    context = ToolContext(identity, device, session.id, "computer-use-v2-eval")
    return SimpleNamespace(runtime=runtime, identity=identity, device=device, context=context, semantic=fake_semantic)


# -- 1. semantic read uses canonical authority --

async def _case_semantic_read_canonical(_context: Any) -> bool:
    ctx = await _new_runtime_context()
    try:
        result = await ctx.runtime.tool_service.execute("computer.semantic.read", {"action": "list_windows"}, ctx.context)
        if result.status.value != "completed":
            return False
        audited = {row["event_type"] for row in ctx.runtime.repository.audit(ctx.context.correlation_id)}
        return "computer.permission_checked" in audited
    finally:
        await ctx.runtime.shutdown()


# -- 2. sensitive window does not leak --

async def _case_sensitive_window_filtered(_context: Any) -> bool:
    from ..computer.semantic_uia import WindowsUIAutomationAdapter
    from ..contracts import DesktopContextSnapshot, DesktopWindow, VisualRegion
    from datetime import UTC, datetime

    from ..perception.privacy import PerceptionPrivacyPolicy

    class _Provider:
        def __init__(self) -> None:
            self.privacy_policy = PerceptionPrivacyPolicy()

        def desktop_context(self, device_id: str) -> DesktopContextSnapshot:
            windows = (
                DesktopWindow("window-sensitive", "Sign in to your account", "chrome.exe", 1, "Cls", VisualRegion(0, 0, 1, 1), True, False),
                DesktopWindow("window-safe", "Notepad", "notepad.exe", 2, "Cls", VisualRegion(0, 0, 1, 1), True, False),
            )
            return DesktopContextSnapshot("snap", device_id, datetime.now(UTC), None, windows, 100, 100, "fake", 1.0)

    adapter = WindowsUIAutomationAdapter(_Provider(), control_from_handle=lambda hwnd: None, pattern_ids={})
    result = await adapter.list_windows("device-1")
    if result.status != "succeeded":
        return False
    refs = {w.window_ref for w in result.output["windows"]}
    return refs == {"window-safe"} and result.output.get("filtered_count") == 1


# -- 3. weak UIA identity cannot actuate --

async def _case_weak_identity_cannot_actuate(_context: Any) -> bool:
    from ..computer.semantic_uia import WindowsUIAutomationAdapter
    from .semantic_uia_fixtures import fake_control_tree

    root, provider, hwnd = fake_control_tree(weak=True)
    adapter = WindowsUIAutomationAdapter(provider, control_from_handle=lambda h: {hwnd: root}.get(h), pattern_ids={"Invoke": 1})
    found = await adapter.find_elements("window-1", control_type="ButtonControl")
    ref = found.output["matches"][0].element_ref
    result = await adapter.invoke(ref)
    return result.status == "denied" and result.error_code == "uia_element_identity_weak"


# -- 4. stale target cannot actuate --

async def _case_stale_target_cannot_actuate(_context: Any) -> bool:
    from datetime import UTC, datetime, timedelta
    from ..computer.semantic_uia import WindowsUIAutomationAdapter
    from .semantic_uia_fixtures import fake_control_tree

    root, provider, hwnd = fake_control_tree(weak=False)
    adapter = WindowsUIAutomationAdapter(provider, control_from_handle=lambda h: {hwnd: root}.get(h), pattern_ids={"Invoke": 1})
    found = await adapter.find_elements("window-1", control_type="ButtonControl")
    ref = found.output["matches"][0].element_ref
    adapter._element_refs[ref].expires_at = datetime.now(UTC) - timedelta(seconds=1)
    result = await adapter.invoke(ref)
    return result.status == "failed" and result.error_code == "uia_element_stale"


# -- 5. approval target-change binding works --

async def _case_approval_target_change_binding(_context: Any) -> bool:
    ctx = await _new_runtime_context()
    try:
        requested = await ctx.runtime.tool_service.execute(
            "computer.semantic.act", {"action": "invoke", "element_ref": "element-drift"}, ctx.context
        )
        if requested.status.value != "approval_required" or requested.approval_id is None:
            return False
        ctx.semantic.element_name["element-drift"] = "Changed Control"
        decided = await ctx.runtime.tool_service.decide_and_resume(
            requested.approval_id, True, ctx.identity.identity_id, ctx.context
        )
        return decided.status.value == "denied" and decided.error_code == "approval_target_changed" and ctx.semantic.invoke_calls == []
    finally:
        await ctx.runtime.shutdown()


# -- 6. semantic act requires approval --

async def _case_semantic_act_requires_approval(_context: Any) -> bool:
    ctx = await _new_runtime_context()
    try:
        result = await ctx.runtime.tool_service.execute(
            "computer.semantic.act", {"action": "invoke", "element_ref": "element-6"}, ctx.context
        )
        return result.status.value == "approval_required" and ctx.semantic.invoke_calls == []
    finally:
        await ctx.runtime.shutdown()


# -- 7. post-action verification never trusts only the stale original object --

async def _case_fresh_post_action_verification(_context: Any) -> bool:
    from ..computer.semantic_uia import WindowsUIAutomationAdapter
    from .semantic_uia_fixtures import fake_control_tree, FreezesAtFetchTogglePattern

    box = {"value": 0}
    root, provider, hwnd = fake_control_tree(weak=False, toggle_box=box)
    adapter = WindowsUIAutomationAdapter(provider, control_from_handle=lambda h: {hwnd: root}.get(h), pattern_ids={"Toggle": 2})
    found = await adapter.find_elements("window-1", control_type="CheckBoxControl")
    ref = found.output["matches"][0].element_ref
    result = await adapter.toggle(ref)
    # A frozen-at-fetch pattern proves the post-action read used a fresh
    # GetPattern() call, not the pre-action object - see fixture docstring.
    return result.status == "succeeded" and result.output["verified"] is True and result.output["post_state"] == 1


# -- 8. generic invoke remains unverified without postcondition --

async def _case_generic_invoke_unverified(_context: Any) -> bool:
    ctx = await _new_runtime_context()
    try:
        requested = await ctx.runtime.tool_service.execute(
            "computer.semantic.act", {"action": "invoke", "element_ref": "element-plain"}, ctx.context
        )
        decided = await ctx.runtime.tool_service.decide_and_resume(
            requested.approval_id, True, ctx.identity.identity_id, ctx.context
        )
        return decided.status.value == "completed" and decided.verified is False
    finally:
        await ctx.runtime.shutdown()


# -- 9. toggle/select use fresh evidence --

async def _case_toggle_select_fresh_evidence(_context: Any) -> bool:
    ctx = await _new_runtime_context()
    try:
        ctx.semantic.toggle_pre_post = (0, 1)
        toggle_requested = await ctx.runtime.tool_service.execute(
            "computer.semantic.act", {"action": "toggle", "element_ref": "element-toggle"}, ctx.context
        )
        toggle_decided = await ctx.runtime.tool_service.decide_and_resume(
            toggle_requested.approval_id, True, ctx.identity.identity_id, ctx.context
        )
        select_requested = await ctx.runtime.tool_service.execute(
            "computer.semantic.act", {"action": "select", "element_ref": "element-select"}, ctx.context
        )
        select_decided = await ctx.runtime.tool_service.decide_and_resume(
            select_requested.approval_id, True, ctx.identity.identity_id, ctx.context
        )
        return toggle_decided.verified is True and select_decided.verified is True
    finally:
        await ctx.runtime.shutdown()


# -- 10. native pointer requires grounded element --

async def _case_native_pointer_requires_grounded_element(_context: Any) -> bool:
    from ..computer.native_input import WindowsNativeInputAdapter

    class _Semantic:
        async def resolve_actionable_target(self, element_ref: str) -> SemanticResult:
            return SemanticResult("denied", error_code="uia_element_identity_weak")

    calls = {"count": 0}

    def counting_send(inputs: object) -> int:
        calls["count"] += 1
        return len(inputs)

    class _Provider:
        def validate_input_window(self, window_ref: str) -> int:
            return 1

        def focus_window(self, window_ref: str) -> bool:
            return True

        def is_foreground(self, hwnd: int) -> bool:
            return True

    adapter = WindowsNativeInputAdapter(
        _Provider(), _Semantic(),  # type: ignore[arg-type]
        metrics_provider=lambda: (0, 0, 1920, 1080), send_input=counting_send, get_cursor_pos=lambda: (0, 0),
    )
    result = await adapter.move_to_element("element-weak")
    return result.status == "denied" and result.error_code == "uia_element_identity_weak" and calls["count"] == 0


# -- 11. native key requires grounded foreground window --

async def _case_native_key_requires_foreground(_context: Any) -> bool:
    from ..computer.native_input import WindowsNativeInputAdapter

    class _Semantic:
        async def resolve_actionable_target(self, element_ref: str) -> SemanticResult:
            return SemanticResult("succeeded", {"element": _snapshot(element_ref)})

    class _Provider:
        def validate_input_window(self, window_ref: str) -> int:
            return 1

        def focus_window(self, window_ref: str) -> bool:
            return False  # focus cannot be established

        def is_foreground(self, hwnd: int) -> bool:
            return False

    adapter = WindowsNativeInputAdapter(_Provider(), _Semantic(), metrics_provider=lambda: (0, 0, 1920, 1080))  # type: ignore[arg-type]
    result = await adapter.press_key("window-1", "tab")
    return result.status == "failed" and result.error_code == "window_focus_not_verified"


# -- 12/13/14. bounded model-facing schemas --

async def _case_no_raw_coordinates_in_schema(_context: Any) -> bool:
    ctx = await _new_runtime_context()
    try:
        spec = ctx.runtime.tools.get("computer.pointer.act")
        if spec is None:
            return False
        properties = set(spec.parameters_schema.get("properties", {}))
        return not (properties & {"x", "y", "hwnd"}) and spec.parameters_schema.get("additionalProperties") is False
    finally:
        await ctx.runtime.shutdown()


async def _case_no_raw_vk_in_schema(_context: Any) -> bool:
    ctx = await _new_runtime_context()
    try:
        spec = ctx.runtime.tools.get("computer.keyboard.key")
        if spec is None:
            return False
        properties = spec.parameters_schema.get("properties", {})
        if set(properties) & {"vk", "code", "flags", "scan_code"}:
            return False
        key_schema = properties.get("key", {})
        from ..computer.native_input import NAMED_KEY_VK
        return key_schema.get("type") == "string" and set(key_schema.get("enum", [])) == set(NAMED_KEY_VK)
    finally:
        await ctx.runtime.shutdown()


async def _case_no_filesystem_parameter(_context: Any) -> bool:
    ctx = await _new_runtime_context()
    try:
        blocked = {"path", "root", "pattern", "file", "folder", "value"}
        for tool_name in ("computer.semantic.act", "computer.semantic.read", "computer.pointer.act", "computer.keyboard.key"):
            spec = ctx.runtime.tools.get(tool_name)
            if spec is None:
                return False
            if set(spec.parameters_schema.get("properties", {})) & blocked:
                return False
        return True
    finally:
        await ctx.runtime.shutdown()


# -- 15. model-visible `verified` survives the full pipeline --

async def _case_verified_field_survives_pipeline(_context: Any) -> bool:
    ctx = await _new_runtime_context()
    try:
        requested = await ctx.runtime.tool_service.execute(
            "computer.semantic.act", {"action": "invoke", "element_ref": "element-verify"}, ctx.context
        )
        decided = await ctx.runtime.tool_service.decide_and_resume(
            requested.approval_id, True, ctx.identity.identity_id, ctx.context
        )
        return decided.verified is False  # explicitly present and honest, not swallowed to None
    finally:
        await ctx.runtime.shutdown()


# -- 16. UI text cannot self-authorize an approval --

async def _case_ui_text_cannot_self_authorize(_context: Any) -> bool:
    ctx = await _new_runtime_context()
    try:
        spec = ctx.runtime.tools.get("computer.semantic.act")
        if spec is None:
            return False
        properties = set(spec.parameters_schema.get("properties", {}))
        # The schema has no free-text/preview/reason field at all - there is
        # no channel through which model-supplied text could ever reach an
        # approval preview; the preview is built server-side from a fresh
        # adapter read (R18B01-004), never from caller-supplied arguments.
        no_free_text_channel = properties == {"action", "element_ref", "target_device_id"}
        ctx.semantic.element_name["element-preview"] = "Observed Name"
        requested = await ctx.runtime.tool_service.execute(
            "computer.semantic.act", {"action": "invoke", "element_ref": "element-preview"}, ctx.context
        )
        assert requested.approval_id is not None
        row = ctx.runtime.repository.approval(requested.approval_id)
        import json
        preview = json.loads(row["preview_json"])
        return no_free_text_channel and preview.get("name") == "Observed Name"
    finally:
        await ctx.runtime.shutdown()


# -- 17. wrong-target execution count remains zero in fixture cases --

async def _case_wrong_target_execution_count_zero(_context: Any) -> bool:
    ctx = await _new_runtime_context()
    try:
        ctx.semantic.element_error["element-neg-weak"] = "uia_element_identity_weak"
        ctx.semantic.element_error["element-neg-stale"] = "uia_element_stale"
        ctx.semantic.element_error["element-neg-offscreen"] = "uia_target_not_interactable"
        for ref in ("element-neg-weak", "element-neg-stale", "element-neg-offscreen"):
            requested = await ctx.runtime.tool_service.execute(
                "computer.semantic.act", {"action": "invoke", "element_ref": ref}, ctx.context
            )
            # A denied-before-approval target never even reaches an
            # approval_id; a target that fails validation for another
            # reason must still never result in an actuation call below.
            if requested.approval_id is not None:
                await ctx.runtime.tool_service.decide_and_resume(
                    requested.approval_id, True, ctx.identity.identity_id, ctx.context
                )
        return ctx.semantic.invoke_calls == []
    finally:
        await ctx.runtime.shutdown()


def build_suite() -> RegressionSuite:
    cases = (
        EvaluationCase("cuv2-01", "semantic read uses canonical authority", "computer_use_v2", _case_semantic_read_canonical),
        EvaluationCase("cuv2-02", "sensitive window does not leak", "computer_use_v2", _case_sensitive_window_filtered),
        EvaluationCase("cuv2-03", "weak UIA identity cannot actuate", "computer_use_v2", _case_weak_identity_cannot_actuate),
        EvaluationCase("cuv2-04", "stale target cannot actuate", "computer_use_v2", _case_stale_target_cannot_actuate),
        EvaluationCase("cuv2-05", "approval target-change binding works", "computer_use_v2", _case_approval_target_change_binding),
        EvaluationCase("cuv2-06", "semantic act requires approval", "computer_use_v2", _case_semantic_act_requires_approval),
        EvaluationCase("cuv2-07", "post-action verification never trusts only the stale original object", "computer_use_v2", _case_fresh_post_action_verification),
        EvaluationCase("cuv2-08", "generic invoke remains unverified without postcondition", "computer_use_v2", _case_generic_invoke_unverified),
        EvaluationCase("cuv2-09", "toggle/select use fresh evidence", "computer_use_v2", _case_toggle_select_fresh_evidence),
        EvaluationCase("cuv2-10", "native pointer requires grounded element", "computer_use_v2", _case_native_pointer_requires_grounded_element),
        EvaluationCase("cuv2-11", "native key requires grounded foreground window", "computer_use_v2", _case_native_key_requires_foreground),
        EvaluationCase("cuv2-12", "raw coordinates rejected", "computer_use_v2", _case_no_raw_coordinates_in_schema),
        EvaluationCase("cuv2-13", "raw VK rejected", "computer_use_v2", _case_no_raw_vk_in_schema),
        EvaluationCase("cuv2-14", "no filesystem parameter introduced", "computer_use_v2", _case_no_filesystem_parameter),
        EvaluationCase("cuv2-15", "model-visible verified survives", "computer_use_v2", _case_verified_field_survives_pipeline),
        EvaluationCase("cuv2-16", "UI text cannot self-authorize", "computer_use_v2", _case_ui_text_cannot_self_authorize),
        EvaluationCase("cuv2-17", "wrong-target execution count remains zero in fixture cases", "computer_use_v2", _case_wrong_target_execution_count_zero),
    )
    return RegressionSuite(
        SUITE_NAME, cases,
        "Deterministic Computer Use V2 product acceptance contracts (Phase 18 Workstream A Batch 02 Milestone 2). "
        "No GUI/live Windows dependency; every case runs against fakes at the OS/provider boundary.",
    )
