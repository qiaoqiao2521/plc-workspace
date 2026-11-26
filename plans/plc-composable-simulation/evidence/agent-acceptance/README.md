# Actual Agent acceptance

A fresh subagent read only the public project entry, Skill and protocol, chose its own scene edits and CLI payloads, and completed 40 actual calls. It did not read implementation files, regression tests or existing acceptance answers. No product code, PLC source or oracle was edited by this agent.

`summary.json` and `AGENT_ACCEPTANCE_REPORT.txt` describe the run. The selected standalone requests and reports beside them make the final correct scene and deliberate Stop bypass directly reviewable and rerunnable. `commands.sh` records the actual command history with original machine paths; its old sessions/project IDs are provenance and must be recreated for a new run.

`raw-evidence.zip` preserves the complete 185-file handoff, including all requests, stdout/stderr, command metadata, operations.jsonl, normal/jam/repaired cases, interactive traces, OIP catalog/assembly/native/self-test responses, expected unsupported-profile failure and file-sha256.json. It contains no compiler products, dependencies or third-party checkout. ZIP member content has not been rewritten.

The service was restarted after the batch timeout boundary was added to the contract document. `final-normal-case.report.json` and `final-stop-bypass.report.json` bind the current contract SHA-256. Earlier reports retain the previous document hash; their histories were not rewritten. The program and the corresponding good/bad scene hashes stayed identical across the restart. Both services and all explicitly created sessions were closed.

The expected failing Stop case is a successful negative control, not an unexplained regression. Its scan 2 shows PLC Motor=0 and actual motor/belt running=true because Enable bypassed the PLC command. Restoring only the connection made the same Stop case pass. The positive result grants only the documented finite simulation-case scope.
