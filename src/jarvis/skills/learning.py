"""Safe declarative procedure drafts; drafts never self-activate or add authority."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from .models import Skill, SkillDraft, SkillManifest, SkillStatus, SkillStep


class SkillLearningService:
    def propose(self, workflow_name: str, actions: tuple[str, ...], *, source: str = "successful_workflow") -> SkillDraft:
        if not workflow_name.strip() or not actions:
            raise ValueError("a named workflow and actions are required")
        skill_id = "draft_" + "_".join(item for item in workflow_name.casefold().split() if item.isalnum())[:48]
        manifest = SkillManifest(skill_id, workflow_name.strip(), "Draft declarative procedure proposed from a successful workflow.", version="0.1.0", category="learned", inputs=("context",), outputs=("result",), required_capabilities=(), risk_level="read", autonomy_level=0, owner=source, status=SkillStatus.DRAFT)
        skill = Skill(manifest, tuple(SkillStep(f"draft-step-{index}", action, action) for index, action in enumerate(actions, 1)))
        return SkillDraft(f"skill-draft-{uuid4()}", skill, source, ("human review required", "declarative actions only", "authority cannot increase"), datetime.now(UTC))

    def approve(self, draft: SkillDraft) -> Skill:
        manifest = SkillManifest(draft.skill.manifest.skill_id, draft.skill.manifest.name, draft.skill.manifest.description, version="1.0.0", category=draft.skill.manifest.category, inputs=draft.skill.manifest.inputs, outputs=draft.skill.manifest.outputs, required_capabilities=draft.skill.manifest.required_capabilities, risk_level=draft.skill.manifest.risk_level, autonomy_level=min(draft.skill.manifest.autonomy_level, 1), estimated_duration=draft.skill.manifest.estimated_duration, workspace_scope=draft.skill.manifest.workspace_scope, network_requirement=draft.skill.manifest.network_requirement, owner=draft.skill.manifest.owner, status=SkillStatus.ACTIVE)
        return Skill(manifest, draft.skill.steps, draft.skill.instructions_path, draft.skill.instructions)
