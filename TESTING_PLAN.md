# SelfGuard v3.4: testing plan

Everything to run, in order. Commands are for **PowerShell** in the repo folder on the GPU PC
(RTX 3060 Ti). Times are rough estimates for 7B models.

| Step | What | Model | Time | Output |
|---|---|---|---|---|
| 1 | Setup and unit tests | - | 20 min | test summary |
| 2 | Smoke test (24 items; none / v3.1 / v3.3 / v3.4) | Qwen2.5 7B | 15 min | `results/smoke_*` |
| 3 | SEP dev split (600 rows; none / v3.1 / v3.3 / routed / v3.4) | Mistral 7B | 4-5 h | `results/sep_v34_dev_*` |
| 4 | Choose the echo threshold and witness match on dev; build the fresh sealed split | - | 10 min | `data/sealed_v34.jsonl` + hash |
| 5 | Finish, commit and push the pre-registration | - | 15 min | `PREREGISTRATION_v3.4.md` |
| 6 | **SEP sealed, one shot** (none / v3.1 / routed / v3.4) | Mistral 7B | 3 h | `results/sep_v34_sealed_*` |
| 7 | BIPIA e-mail QA (50 e-mails; none / v3.1 / v3.3 / v3.4) | Qwen2.5 7B | 2-3 h | `results/bipia_v34_*` |
| 8 | AgentDojo banking + slack (regression check) | Qwen2.5 7B | 2-4 h | `results/agentdojo_*` |
| 9 | Own agent suite | Qwen2.5 7B | 15 min | `results/agent_suite.json` |
| 10 | Collect everything into one zip | - | 1 min | `Downloads\selfguard-v3.4-results-*.zip` |

**Ground rules**
- Never open `data/sealed_v34.jsonl` or the sealed cache; scripts print counts and metrics only.
- Step 6 runs **once**. If it fails, it failed: report it, do not change code and rerun.
- No code changes after step 5's commit. Any change goes in the pre-registration first.
- Run nothing else on the GPU during step 6. Keep the PC awake during long steps; every script
  resumes from its cache if stopped, except that the sealed scorer refuses to run twice.
- Results are not committed; step 10 collects them into a zip.

---

## 1. Setup and unit tests

Needs Git, Python 3.11+, and [Ollama](https://ollama.com).

```powershell
ollama pull mistral:7b-instruct
ollama pull qwen2.5:7b-instruct
ollama list                          # note both digests
python -m unittest discover -s tests
```
Expect `OK (skipped=2)` (the two skips need extra models).

BIPIA: from https://github.com/microsoft/BIPIA copy `benchmark\email\test.jsonl` and
`benchmark\text_attack_test.json` into `..\bipia`.

## 2. Smoke test

```powershell
python eval/smoke_test.py --model qwen2.5:7b-instruct
```
24 self-made items, to check the pipeline end to end. Not a result to report.

## 3. SEP dev split (not sealed)

Download https://github.com/egozverev/Should-It-Be-Executed-Or-Processed/archive/refs/heads/main.zip
and save it in this folder as `Should-It-Be-Executed-Or-Processed-main.zip`.

```powershell
python eval/sep_splits.py dev        # checks the archive hash and every earlier split's hash
python eval/sep_eval.py --rows data/sep/dev.jsonl --limit 30     # quick check
python eval/sep_eval.py --rows data/sep/dev.jsonl                # full dev
python eval/leak_analysis.py --rows data/sep/dev.jsonl --cache results/cache/sep_dev_mistral_7b-instruct.jsonl
```
If `sep_splits.py` reports a hash mismatch, stop: the archive changed since the freeze.
Generations resume from the cache if stopped. An older cache with identical prompts can be reused
with `--legacy-cache` (e.g. `results\cache\sep_v32_dev_mistral_7b-instruct.jsonl`).

## 4. Choose settings on dev, then build the fresh sealed split

From the dev report, choose and write into the pre-registration:
- the echo threshold (`ECHO_THRESHOLD` in `eval/sep_eval.py`; 0.3 now),
- the witness match for the criteria (`WITNESS_MATCH`: `substring`, SEP's grader, or
  `whole_word`).
Change the constants in `eval/sep_eval.py` to match, then:

```powershell
python eval/sep_splits.py sealed --dry-run
python eval/sep_splits.py sealed
```
It prints counts and a SHA-256 only. Copy the SHA-256.

## 5. Finish the pre-registration, then commit and push

Fill in every `FILL-IN` in `PREREGISTRATION_v3.4.md` (date, sealed SHA-256, Mistral digest,
chosen settings, changes after dev) and remove the DRAFT box.

```powershell
git add PREREGISTRATION_v3.4.md eval/sep_eval.py
git commit -m "Pre-register v3.4 sealed SEP test"
git push
```
The push time on GitHub is the proof it was written before the sealed run.

## 6. SEP sealed, one shot

```powershell
python eval/sep_eval.py --sealed
```
Checks the hash against the pre-registration and refuses if a sealed report already exists. If
interrupted during generation, run the same command again: it resumes from the cache.

## 7. BIPIA

```powershell
python eval/bipia_eval.py --bipia ..\bipia --model qwen2.5:7b-instruct --n 50
```
50 e-mails, each clean + 2 misinformation + 2 scam attacks. The judge is the same model; add
`--judge mistral:7b-instruct --out results\bipia_v34_judge_mistral.json` for an independent judge.

## 8. AgentDojo (regression check)

The agent pipeline uses the action lock only (no routing or echo strip), so v3.4 should match
v3.0 here; this checks nothing broke and shows run-to-run variation.

```powershell
pip install agentdojo openai
$env:AD_CONDITIONS = "none,sg3"
python eval/agentdojo_run.py banking
python eval/agentdojo_run.py slack
```

## 9. Own agent suite

```powershell
python eval/agent_suite.py
```

## 10. Collect and export

```powershell
python eval/collect_results.py
```
Writes `selfguard-v3.4-results-<date>-<time>.zip` to **Downloads**: `RESULTS.md`,
`environment.json` (GPU, Python, git commit, Ollama digests), every result file and the raw SEP
replies. Never includes `data\`. Use `--no-cache` if the zip is too big.

---

## What each result answers

| Result | Question |
|---|---|
| SEP sealed, v3.4 vs no defence (C1) | Does v3.4 cut attack success, with the 95% upper bound at or below 5%? |
| SEP sealed, v3.4 vs v3.1 (secondary) | Does echo strip + routing add protection on top of v3.1? |
| SEP grounding and withheld (C2, C3) | Does it cost answer quality or false alarms? |
| Clean replies echo-stripped | How often does echo strip remove a sentence from a correct answer? |
| SEP dev, v3.3 | The canary's false alarms (the dev finding) |
| BIPIA | Same questions on e-mail QA with lies and scams, and correct-answer rate |
| AgentDojo, agent suite | Did anything regress in agent tasks? |
