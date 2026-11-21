# Changelog

## 3.2.0.dev0 (2026-11-22)

Not yet evaluated: see TESTING_PLAN.md. README results are still v3.0's.

### Added
- **Canary layer** (`selfguard3/canary.py`): a harmless instruction with a fresh random code is
  planted in the untrusted data; if the reply contains the code, the model followed data
  instructions during this call, so the reply is withheld and every action blocked. It watches
  the model's behaviour, not the attacker's wording; no extra model call; it can only withhold.
  On by default (`SelfGuard(canary=False)` turns it off). Adds one sentence to the data.
- `SelfGuard.prepare()` returns the messages and that call's canary; `inspect(..., canary=...)`
  checks it; `run()` wires both. `messages()` keeps the canary in `last_canary` for
  single-threaded use. Smart routing is decided on the real data, before the canary is planted.
- Evaluation: `eval/sep_v32.py` (SEP, no defence vs v3.1 vs v3.2, resumable, one-shot sealed
  mode tied to `PREREGISTRATION_v3.2.md`), `build_sealed_v32.py` (fresh sealed split excluding
  Watchword's and v3's rows), `eval/canary_small.py` (24-item smoke test), `eval/llm.py` (Ollama
  or OpenAI-compatible calls, records model digests), `eval/collect_results.py` (one zip of all
  results in Downloads). `eval/bipia_eval.py` now compares none / v3.1 / v3.2 (v4 optional).
- `TESTING_PLAN.md`, `PREREGISTRATION_v3.2.md` (draft, finished before the sealed run).

### Changed
- `eval/agent_suite.py` passes each call's canary to both guards it checks with.

## 3.1.0 (2026-11-21)

All results in the README were measured with **v3.0** (commit `da4d868`). The fixes below change
behaviour and have not been re-scored; the sealed SEP split is already used, so v3.1 must be
evaluated on the non-sealed benchmarks or a new pre-registered split.

### Independent of Watchword
- Watchword's engine is vendored in `selfguard3/_watchword` (byte-identical to its freeze,
  commit `b51be8bf`; hashes checked by `tests/test_vendored.py`). No `sys.path` edits, no
  Watchword checkout needed. `selfguard3.checks` runs the reply checks directly and is built
  once per `SelfGuard`. Decisions match the original on 205 cases in both layouts.
- `layout="routed"` (the pre-registered smart routing) is now available in `SelfGuard`.
- `pyproject.toml`: `pip install .`, standard library only.
- Findings name the check that fired (`obedience`, `provenance`, `leak`); v3.0 labelled every
  Watchword withholding `obedience`.

### Fixes
- **Approver never saw the field labels.** `PerimeterApprover` computed the words before each
  value (`From:`, `IBAN:`) but `PROMPT` had no `{where}` slot, so `str.format` dropped them.
- **Support trace treated every word as a claim.** `CLAIM_TOKEN` was compiled with `re.I`, so
  `[A-Z][a-z]{2,}` matched any 3+ letter word and normal sentences could be removed. Only day and
  month names (and am/pm) ignore case now.
- **Nested tool arguments were dropped.** `parse_actions` used a non-greedy `\{.*?\}`; nested
  JSON failed to parse and only a `"to"` field was kept, so values in other fields skipped the
  lock. It now uses a real JSON decoder; unparseable calls keep their whole text so every value
  in them is checked (fail closed).
- **Risky-verb rule was not implemented.** `RISKY` was defined but unused. `ActionLock(...,
  task=...)` now holds actions whose name contains a risky verb (send, pay, delete, post, run,
  invite, ...) when the user's request asks for nothing of that kind. `SelfGuard` and
  `eval/agentdojo_run.py` pass the request; `task=None` keeps v3.0 behaviour.
- **Tests:** `unittest.main()` sat mid-file in `tests/test_modules.py`, so running the file
  directly skipped the approver and v4 tests. Regression tests added for every fix.
- `.gitattributes` forces LF so SHA-256-checked files hash the same on every OS.

### Integrity note: `results_freeze.sha256`
The hashes in `results_freeze.sha256` do not match the committed `PREREGISTRATION.md`,
`score_v3.py` and `build_sealed.py` (neither the LF bytes in git nor CRLF checkouts). The file is
left unchanged as found. SHA-256 of the files as committed in `da4d868`:

```
5fa706294c2635f6dce505e2d96dca98dd3e150005dab4b4797068988823079e  PREREGISTRATION.md
f02130ae37d99c49935b7af571ee95bdeaa47bc0825695f11a58f89f125318a1  score_v3.py
e2e0c039bc9f60eac085059931c16de7329b5e748568ae59321501c99717d29d  build_sealed.py
```
