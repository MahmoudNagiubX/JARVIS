# Phase 15 Capability Selection and Context Budget

`ToolSchemaSelector` remains the single model-facing selector. It selects from
the existing native registry, including namespaced MCP and browser tools, using
normalized user intent and a maximum of eight tools. MCP schemas are also
bounded by a 32,000-byte aggregate budget.

Selection is based on trusted user intent only. English, Arabic, Egyptian Arabic,
and mixed technical requests use the same bounded path; the implementation does
not inject the complete catalog. `select_with_metadata()` records the selected
names, schema byte count, and a safe selection reason for observability. Remote
MCP schema annotations and instructions are removed before this selector sees
the schema.

MCP server startup is lazy for stdio servers. This keeps discovery and schema
cost out of ordinary requests unless a relevant capability is selected.
