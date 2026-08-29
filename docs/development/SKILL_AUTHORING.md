# Skill authoring

Add a manifest and declarative `SkillStep` actions. Use existing capability
names, keep inputs/outputs explicit, set the smallest risk and autonomy, and
route tools through `ToolExecutionService`. Keep instructions in a bounded
Markdown file when progressive loading is useful. Do not add shell snippets,
arbitrary code bundles, hidden credentials, or authority-changing steps.

Register a version with a source and change reason. Learned workflows must
remain drafts until a human reviews and activates them.
