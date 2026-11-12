# Ask Dan (showcase)

Case study of a locally hosted, fact-grounded Q&A assistant for a personal site: Turnstile, Cloudflare Worker, tunnel, a Node gateway, and gemma4:e4b on Ollama.

- `CASE_STUDY.md`: problem, architecture, grounding approach, eval method and results, bugs and fixes (with per-item verification status).
- `example/factsheet.example.md`: placeholder fact sheet showing the structure (all facts invented).
- `example/system_prompt.example.txt`: the locked-down system prompt with a placeholder name. `<<FACTSHEET>>` is replaced at request time.
- `tests/tests.example.json`: 47 single-turn cases (in-scope, unknown, off-topic, injection) rewritten against the placeholder fact sheet.
- `tests/multi_turn.example.json`: 13 multi-turn cases.
- `tests/run_tests.example.py`: runner against a local Ollama (run from the `tests/` directory).

Not included on purpose: the real fact sheet, gateway keys, logs, conversation records, and the real result files. The pass counts in the case study come from those private result files.
