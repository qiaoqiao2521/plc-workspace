# Multiple executable PLC process scenes

Owner: root Codex. User selected conveyor, dual-cylinder clamp and sorting, each with its own PLC logic. Environment-only dressing is not the requested outcome.

Plan: confirm demonstration process choices; analyze/review/freeze/generate via existing mcode/CM controller; compile fixed source snapshots; execute source-bound boundary tests; expose per-scene independent sessions, I/O, trace and 3D views; verify browser interactions and frozen source/assets; commit and push verified work.

Scope: logical demonstration fixtures, deterministic scan-driven simplified equipment; no physical valve selection, device writes, arbitrary source upload, Siemens or safety acceptance. Existing conveyor behavior must remain unchanged. New process generation remains blocked until the requested action order and branch choices are answered.

Adopted lesson: acceptance must bind observable behavior and delivery to the corresponding source (Obsidian `Wiki/自动化开发范式与智能体协作.md`, acceptance evidence section); a 3D display or reviewer approval alone is not execution evidence.
