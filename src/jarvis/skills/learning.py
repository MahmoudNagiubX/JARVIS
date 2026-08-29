"""Safe declarative procedure drafts; drafts never self-activate or add authority."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from .models import Skill, SkillDraft, SkillManifest, SkillStatus, SkillStep
from .policy import RISK_ORDER


class SkillLearningService:
    def propose(self, workflow_name: str, actions: tuple[str, ...], *, source: str = "successful_workflow") -> SkillDraft:
        if not workflow_name.strip() or not actions:
            raise ValueError("a named workflow and actions are required")
        skill_id = "draft_" + "_".join(item for item in workflow_name.casefold().split() if item.isalnum())[:48]
        manifest = SkillManifest(skill_id, workflow_name.strip(), "Draft declarative procedure proposed from a successful workflow.", version="0.1.0", category="learned", inputs=("context",), outputs=("result",), required_capabilities=(), risk_level="read", autonomy_level=0, owner=source, status=SkillStatus.DRAFT)
        steps = tuple(self._step(f"draft-step-{index}", action, manifest.risk_level) for index, action in enumerate(actions, 1))
        highest = max((RISK_ORDER.get(step.risk_level, RISK_ORDER["forbidden_autonomous"]) for step in steps), default=0)
        source_risk = max(RISK_ORDER[manifest.risk_level], highest)
        manifest = SkillManifest(manifest.skill_id, manifest.name, manifest.description, version=manifest.version, category=manifest.category, inputs=manifest.inputs, outputs=manifest.outputs, required_capabilities=manifest.required_capabilities, risk_level=max(RISK_ORDER, key=lambda key: RISK_ORDER[key]) if source_risk == RISK_ORDER["forbidden_autonomous"] else next(key for key, value in RISK_ORDER.items() if value == source_risk), autonomy_level=0, owner=manifest.owner, status=manifest.status)
        skill = Skill(manifest, steps)
        return SkillDraft(f"skill-draft-{uuid4()}", skill, source, ("human review required", "declarative actions only", "authority cannot increase"), datetime.now(UTC))

    def approve(self, draft: SkillDraft) -> Skill:
        source_risk = max((RISK_ORDER.get(draft.skill.manifest.risk_level, 5), *(RISK_ORDER.get(step.risk_level, 5) for step in draft.skill.steps)), default=5)
        risk = next(key for key, value in RISK_ORDER.items() if value == source_risk)
        steps = tuple(self._step(step.step_id, step.action, risk, step) for step in draft.skill.steps)
        manifest = SkillManifest(draft.skill.manifest.skill_id, draft.skill.manifest.name, draft.skill.manifest.description, version="1.0.0", category=draft.skill.manifest.category, inputs=draft.skill.manifest.inputs, outputs=draft.skill.manifest.outputs, required_capabilities=draft.skill.manifest.required_capabilities, risk_level=risk, autonomy_level=min(draft.skill.manifest.autonomy_level, 1), estimated_duration=draft.skill.manifest.estimated_duration, workspace_scope=draft.skill.manifest.workspace_scope, network_requirement=draft.skill.manifest.network_requirement, owner=draft.skill.manifest.owner, status=SkillStatus.ACTIVE)
        return Skill(manifest, steps, draft.skill.instructions_path, draft.skill.instructions)

    @staticmethod
    def _step(step_id: str, action: str, inherited_risk: str, source: SkillStep | None = None) -> SkillStep:
        lowered = action.casefold()
        action_risk = "consequential" if any(token in lowered for token in ("consequential", "send", "delete", "write", "start", "control")) else inherited_risk
        if source is not None:
            action_risk = max((action_risk, source.risk_level), key=lambda key: RISK_ORDER.get(key, 5))
        return SkillStep(step_id, source.title if source else action, action, source.arguments if source else {}, source.required_capabilities if source else (), action_risk, RISK_ORDER.get(action_risk, 5) >= RISK_ORDER["consequential"])
