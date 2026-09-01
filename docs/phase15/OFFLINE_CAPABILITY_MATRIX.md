# Phase 15 Offline Capability Matrix

| Capability | Offline behavior | Authority |
| --- | --- | --- |
| Local MCP providers | available when runtime is ready | MCPRegistry + existing executor |
| Registered workspace | available | WorkspaceIntelligenceService |
| Registered repository inspection | available | WorkspaceIntelligenceService |
| Local skills | available | SkillRegistry/SkillExecutor |
| Local research | available | ResearchService/LocalDocumentProvider |
| Deterministic local browser | available for injected/local fixtures | BrowserActionService |
| External stdio MCP server | available if configured and healthy; otherwise isolated/degraded | MCPStdioClient |
| Web research | unavailable or degraded without network | ResearchService |
| GitHub/external services | unavailable or degraded without network | existing integration seams |

The Command Center reports the backend health state it receives. It must not
display a connected server, installed skill, or available browser adapter unless
the corresponding backend state confirms it.
