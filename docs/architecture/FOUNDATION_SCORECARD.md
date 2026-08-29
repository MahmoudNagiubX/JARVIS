# Foundation scorecard

Scores are 0–10, where 10 is strongest for the target JARVIS authority-first
architecture. Each raw score is multiplied by its percentage weight. The
weighted total is normalized to 10.

| Area | Criterion | Weight | PersonalJarvis | aceFelix/jarvis | BMO/JARVIS |
|---|---|---:|---:|---:|---:|
| Architecture | Modularity | 10% | 6.5 | 7.0 | 8.5 |
| Architecture | Boundary clarity | 8% | 5.0 | 5.5 | 9.0 |
| Architecture | Events/protocols | 6% | 8.0 | 5.5 | 7.5 |
| Architecture | Testability | 5% | 8.0 | 7.5 | 8.0 |
| Agent runtime | Orchestrator | 8% | 9.0 | 8.0 | 4.0 |
| Agent runtime | Worker isolation | 5% | 8.0 | 6.5 | 2.0 |
| Agent runtime | Mission/task model | 4% | 8.0 | 5.5 | 2.0 |
| Agent runtime | Tool abstraction | 5% | 7.0 | 8.0 | 8.5 |
| Security/authority | Identity/device | 5% | 3.0 | 2.5 | 9.0 |
| Security/authority | Permissions | 6% | 7.0 | 8.0 | 8.5 |
| Security/authority | Approval | 5% | 7.0 | 5.5 | 8.5 |
| Security/authority | Audit | 4% | 7.0 | 6.0 | 8.5 |
| Voice | Realtime | 4% | 9.0 | 8.5 | 7.0 |
| Voice | Duplex/barge-in | 3% | 8.0 | 8.0 | 7.0 |
| Voice | Provider abstraction | 2% | 8.0 | 7.5 | 7.0 |
| Computer/devices | Windows | 4% | 8.0 | 7.5 | 8.5 |
| Computer/devices | Computer use | 3% | 8.0 | 7.5 | 5.0 |
| Computer/devices | Multi-device | 3% | 6.0 | 5.5 | 7.5 |
| Memory/context | Memory | 3% | 8.0 | 7.0 | 3.0 |
| Memory/context | Context/state | 3% | 8.0 | 7.0 | 5.0 |
| Engineering | Code quality | 3% | 6.0 | 7.5 | 8.0 |
| Engineering | Tests/CI | 3% | 8.5 | 8.0 | 8.5 |
| Engineering | Dependency simplicity | 2% | 3.0 | 6.0 | 7.0 |
| Engineering | Maintenance risk | 2% | 4.0 | 6.0 | 7.0 |
| **Total** | **Weighted score** | **100%** | **6.89/10** | **6.88/10** | **7.40/10** |

The score does not reward raw feature count as a substitute for ownership
boundaries. BMO wins because the target system needs one authority plane for
identity, permissions, approval, audit, model routing, tools, and devices.
PersonalJarvis and aceFelix/jarvis remain higher-value feature donors in the
agent, worker, voice, computer-use, and memory categories.
