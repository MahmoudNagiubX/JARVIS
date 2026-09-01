# Phase 16: Durable Memory Specification

## 1. Core Principles
1. **Product-Owned Authority**: `DurableMemoryService` is the sole authority for persistent memory in JARVIS.
2. **Deterministic Extraction**: In addition to explicit owner entry, deterministic regex extractors parse Egyptian Arabic, Standard Arabic, and English patterns without probabilistic hallucinations.
3. **Strict Policy Gate**: Memory candidates are evaluated before persistence. Credentials, bearer tokens, API keys, private keys, cookies, raw media, and prompt injections from untrusted sources are unconditionally rejected.
4. **Structured Key Conflicts & Superseding**: Memory candidates with structured keys (e.g., `preferred_editor`, `project_phoenix_tech`) supersede previous records with matching keys. Old records are marked `status="superseded"` and linked via `supersedes=previous_id`.
5. **Inspectable & Deletable**: Owners can view, edit, pin, archive, or permanently delete any memory through the HTTP API and desktop UI.

## 2. Memory Contract & Schema

```python
@dataclass(frozen=True, slots=True)
class MemoryRecord:
    memory_id: str
    owner_id: str
    content: str
    created_at: datetime
    kind: str
    metadata: Mapping[str, object]
    category: str
    structured_data: Mapping[str, object]
    source: str
    source_reference: str | None
    updated_at: datetime
    last_accessed_at: datetime | None = None
    confidence: float = 1.0
    sensitivity: str = "personal"
    scope: str = "owner"
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    retention_policy: str = "permanent"
    status: str = "active"
    supersedes: str | None = None
    tags: tuple[str, ...] = ()
    pinned: bool = False
    archived: bool = False
    embedding: tuple[float, ...] | None = None
```

## 3. Categories & Semantics
- `fact`: Factual statement verified by owner or local system.
- `preference`: Owner preferences regarding editor, verbosity, language, or tooling.
- `project`: Architecture, technology stack, and repo configurations.
- `task`: Action items, milestones, deadlines, and deliverables.
- `goal`: Strategic objectives and desired outcomes.
- `profile`: Identity attributes, preferred display name, role, and pronouns.
- `decision`: Recorded architectural or operational choices.

## 4. Policy Guardrails

```
Blocked Patterns:
- API Keys: sk-[a-zA-Z0-9]{20,}, ghp_[a-zA-Z0-9]{20,}, glpat-[a-zA-Z0-9]{20,}
- Tokens: Bearer tokens, refresh tokens, auth tokens, session tokens
- Secrets: AWS secret access keys, private keys (BEGIN ... PRIVATE KEY)
- Passwords & Passcodes
- Raw media: Audio streams, video streams, raw screenshots
- Untrusted Source Firewall: Browser, web, or research sources cannot inject "SYSTEM:", "override policy", "remember permanently", or "disable approvals".
```

## 5. Keyword Retrieval with Arabic Normalization

Retrieval ranking computes relevance via:
1. Exact substring matching (+5.0)
2. Normalized term overlap in content (+2.0 per term)
3. Normalized term overlap in structured data values (+2.0 per term)
4. Normalized term overlap in tags (+2.0 per term)
5. Pinned boost (+1.0)
6. Confidence weighting (+0.5 * confidence)

Arabic text normalization automatically:
- Strips diacritics (tashkeel `[\u064b-\u0652\u0670\u0640]`)
- Normalizes alef forms (`أ`, `إ`, `آ`, `ٱ` -> `ا`)
- Normalizes teh marbuta (`ة` -> `ه`)
- Normalizes alef maksura / yaa (`ى` -> `ي`)
