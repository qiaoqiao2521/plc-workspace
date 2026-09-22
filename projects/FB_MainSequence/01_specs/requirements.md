# Requirements — implemented scan contract v0.3

The authoritative invocation/lifecycle contract is `scan-contract.md`. Interface 0.2.0 changes behavior and instance layout. This is the abstract 303翻转 main sequence, not the missing original machine project, physical I/O or child FB implementation.

| ID | Requirement | Assertions |
|---|---|---|
| REQ-START-001 | Enabled healthy Init exits only on fresh Start and InitDone, without stop/reset inhibition. Ignored edges are consumed. | P8 |
| REQ-SEQ-001 | TransportDone advances 1→2. | P9 |
| REQ-SEQ-002 | FlipDone advances 2→3. | P10 |
| REQ-SEQ-003 | OutputDone advances 3→1 and marks the completed cycle. | P11, P18 |
| REQ-SAFETY-001 | EStop feedback inhibits actions; it does not acknowledge block errors. | P3, P4, P7 |
| REQ-SAFETY-002 | Stop cancels a healthy sequence to Init; existing errors remain Error. | P3, P4, P5 |
| REQ-SAFETY-003 | Belt forward/reverse never overlap; reverse is constant FALSE in this abstraction. | P1 |
| REQ-SAFETY-004 | Uncompleted busy step expires at the specified call count, committing error and timeout reason together. | P13, P14, P17, P24 |
| REQ-SAFETY-005 | Enabled block error persists through Stop/EStop/Reset; disable clears current error. | P2, P7, P25 |
| REQ-ENABLE-001 | Disable ends execution and clears Valid/Busy; re-enable alone never starts motion. | P2, P3, P8, P21 |
| REQ-DIAG-001 | Timeout history survives stop/reset/disable; a new enable session clears old history. | P19, P20, P26 |
| REQ-RESET-001 | Healthy business Reset returns Init and cannot start in the same call; it does not clear block errors. | P6, P7, P8 |
| REQ-COMMAND-001 | CommandBusy distinguishes active sequence from continuous FB Busy; canceled commands report CommandAborted. | P22, P23 |
| REQ-OWNERSHIP-001 | Internals own persistent state; outputs are written once and never read by the FB. | Native output-poison test and source ownership check |

Completion/timeout and simultaneous command boundaries are verified with compiled ST, supplemented by source-derived formal assertions and projection drift checks. Native checks cannot establish F safety, full PLCopen conformance, TIA compilation, retention or real-machine acceptance. Legacy PLCreX/full-service gates remain separate; a missing dependency is not a pass.
