# Changelog

## 3.4.0.dev0 (2026-11-23)

Not yet scored on a sealed split: see TESTING_PLAN.md.

### Why
On SEP dev rows (Mistral 7B) the displaced layout stops most attacks before the model writes
anything, but the reply checks caught **none** of the attacks that still got through (about 1 in
10). v3.4 targets those leaks.

### Added
- **Echo strip** (`selfguard3/echo.py`, on by default): removes reply sentences whose content
  words come mostly (>= `echo_threshold`, default 0.3) from words found only in the data's
  instruction-like sentences, i.e. sentences that carry out an injected instruction. It removes
  text, never withholds or allows. On 310 SEP dev rows it stops 14 attacks v3.1 lets through and
  none the other way (McNemar p = 0.0001), and removes a sentence from about 15% of clean replies.
- `eval/sep_splits.py`: rebuilds every SEP split (dev, the first sealed test, v3.0's sealed
  split, the new v3.4 sealed split) from the public archive and checks each earlier split against
  its published SHA-256. No other checkout is needed.
- `eval/sep_eval.py`: one SEP script for dev and the one-shot sealed run. Arms: none, v3.1, v3.3
  (dev), smart routing, v3.4. Routing and echo strip are scored from the none / v3.1 replies
  (prompts are byte-identical), so the sealed run needs 3,600 generations, not 5,400. Reports
  SEP's substring witness match and a whole-word match (the substring rule counts short witnesses
  inside other words, e.g. "pen" in "open").
- `eval/leak_analysis.py`: where attacks leak through an arm (counts by attack type, check score
  and witness position; never row text).
- `tests/test_echo.py`; `tests/test_engine.py` checks the engine against 406 decisions and 18
  layouts recorded from its original package (`tests/data/engine_decisions.json`).

### Changed
- `SelfGuard()` defaults are v3.4: `layout="routed"` (smart routing), `echo=True`.
  `SelfGuard(layout="displaced", echo=False)` is v3.1.
- The reply-check engine lives in `selfguard3/engine` (logic files byte-identical to the freeze;
  only two docstrings changed, hashes in `engine/frozen_config.json`).
- v3.0's pre-registration, sealed-test scripts and results moved unchanged to `archive/v3.0/`.
- `eval/canary_small.py` is now `eval/smoke_test.py` (arms none / v3.1 / v3.3 / v3.4);
  `eval/bipia_eval.py` compares none / v3.1 / v3.3 / v3.4.

### Fixes
- `eval/llm.py`: dropped connections (`ConnectionResetError`, `RemoteDisconnected`) are retried
  instead of ending a multi-hour run.

### Tried and dropped
- **Authority duel**: the user's request asks for code T, a note in the data asks for code D;
  withhold when D appears without T. On 30 SEP dev rows it fixed the canary's false alarms (3.3%
  clean withheld) but stopped exactly the attacks v3.1 stopped (McNemar b = 0, c = 0): no boost,
  so it was removed.
- Two filters meant to cut echo strip's clean removals (only instructions off-topic for the task;
  only instructions that stand alone in their document) did not separate clean replies from
  attacks on dev data and were not adopted.

## 3.3.0 (2026-11-22; built as 3.2.0.dev0)

**Canary layer** (`selfguard3/canary.py`, now opt-in): a harmless instruction with a fresh random
code is planted in the data; if the reply contains the code, the reply is withheld. Dropped at the
dev stage, before any sealed run: helpful models follow harmless notes, so it fired on clean data
(Mistral 7B: 44.6% of clean SEP dev replies withheld over 305 rows; Qwen2.5 7B: 92% on the smoke
test) and could not tell attacks from normal use. Kept for reproducing that finding.

## 3.1.0 (2026-11-21)

### Standalone
- The reply-check engine is included in the package (no `sys.path` edits, no other checkout).
  `selfguard3.checks` runs the checks directly and is built once per `SelfGuard`.
- `layout="routed"` (the pre-registered smart routing) is available in `SelfGuard`.
- `pyproject.toml`: `pip install .`, standard library only.
- Findings name the check that fired (`obedience`, `provenance`, `leak`).

### Fixes
- **Approver never saw the field labels.** `PerimeterApprover` computed the words before each
  value (`From:`, `IBAN:`) but `PROMPT` had no `{where}` slot, so `str.format` dropped them.
- **Support trace treated every word as a claim.** `CLAIM_TOKEN` was compiled with `re.I`, so
  `[A-Z][a-z]{2,}` matched any 3+ letter word and normal sentences could be removed. Only day and
  month names (and am/pm) ignore case now.
- **Nested tool arguments were dropped.** `parse_actions` used a non-greedy `\{.*?\}`; it now uses
  a real JSON decoder; unparseable calls keep their whole text so every value is checked.
- **Risky-verb rule was not implemented.** `ActionLock(..., task=...)` now holds actions whose
  name contains a risky verb (send, pay, delete, post, run, invite, ...) when the user's request
  asks for nothing of that kind.
- **Tests:** `unittest.main()` sat mid-file in `tests/test_modules.py`, so running the file
  directly skipped the approver and v4 tests. Regression tests added for every fix.
- `.gitattributes` forces LF so SHA-256-checked files hash the same on every OS.

### Integrity note: `archive/v3.0/results_freeze.sha256`
The hashes in that file do not match the committed v3.0 `PREREGISTRATION.md`, `score_v3.py` and
`build_sealed.py`. It is left unchanged as found. SHA-256 of the files as committed in `da4d868`:

```
5fa706294c2635f6dce505e2d96dca98dd3e150005dab4b4797068988823079e  PREREGISTRATION.md
f02130ae37d99c49935b7af571ee95bdeaa47bc0825695f11a58f89f125318a1  score_v3.py
e2e0c039bc9f60eac085059931c16de7329b5e748568ae59321501c99717d29d  build_sealed.py
```

## 3.0.0 (2026-11-20)

Smart routing, reply checks, action lock, approver, link tripwire, support trace, optional v4 lie
layer. Sealed, pre-registered SEP test PASS 3/3 (record in `archive/v3.0/`).
