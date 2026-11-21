# SelfGuard v3.2: testing plan

Everything to run on the GPU PC (RTX 3060 Ti), in order, and how to send the results back.
Commands are for **PowerShell** in the repo folder. Times are rough estimates for 7B models.

| Step | What | Model | Time | Output |
|---|---|---|---|---|
| 1 | Setup and unit tests | - | 20 min | test summary |
| 2 | Smoke test (canary_small, 24 items) | Qwen2.5 7B | 10 min | `results/canary_small_*` |
| 3 | SEP dev split (600 rows, not sealed) | Mistral 7B | 3-5 h | `results/sep_v32_dev_*` |
| 4 | Build the fresh sealed split | - | 5 min | `data/sealed_v32.jsonl` + hash |
| 5 | Finish and commit the pre-registration | - | 15 min | `PREREGISTRATION_v3.2.md` |
| 6 | **SEP sealed, one shot** | Mistral 7B | 3-5 h | `results/sep_v32_sealed_*` |
| 7 | BIPIA e-mail QA (50 e-mails) | Qwen2.5 7B | 1-2 h | `results/bipia_v32_*` |
| 8 | AgentDojo banking + slack (regression check) | Qwen2.5 7B | 2-4 h | `results/agentdojo_*` |
| 9 | Collect everything into one zip | - | 1 min | `Downloads\selfguard-v3.2-results-*.zip` |

**Ground rules**
- Do steps 3 and 4-6 in this order. Never open `data/sealed_v32.jsonl` or the sealed cache.
- Step 6 runs **once**. If it fails, it failed: report it, do not change code and rerun.
- No code changes after step 5's commit. If you must change something, it goes in the
  pre-registration first.
- Leave the PC on and awake during long steps; every script resumes if stopped, except that the
  sealed scorer must not be restarted after it has written its report.

---

## 1. Setup and unit tests

Needs Git, Python 3.11+, and [Ollama](https://ollama.com).

```powershell
ollama pull mistral:7b-instruct
ollama pull qwen2.5:7b-instruct
ollama list                          # note both digests
```

Folder layout (Watchword is needed for its SEP data scripts, and BIPIA for its e-mails):

```
<parent>\selfguard-v3.2   (this repo)
<parent>\watchword        git clone https://github.com/shayanscripts/watchword
<parent>\bipia            from https://github.com/microsoft/BIPIA: copy benchmark\email\test.jsonl
                          and benchmark\text_attack_test.json into this folder
```

```powershell
python -m unittest tests.test_modules tests.test_vendored tests.test_canary
```
Expect `OK (skipped=2)`. Anything else: stop and send me the output.

## 2. Smoke test (10 min)

```powershell
python eval/canary_small.py --model qwen2.5:7b-instruct
```
24 self-made items, to check the whole pipeline works with Ollama before the long runs. Not a
result to report.

## 3. SEP dev split (not sealed)

Get the SEP archive and rebuild Watchword's dev split (deterministic; rows are not in git):

```powershell
# download https://github.com/egozverev/Should-It-Be-Executed-Or-Processed/archive/refs/heads/main.zip
# save it as Should-It-Be-Executed-Or-Processed-main.zip in <parent>\watchword and in this repo
(Get-FileHash .\Should-It-Be-Executed-Or-Processed-main.zip).Hash
```
The hash must be `275F3536FC89D0AA99D10E14D6B7313A3258092F002B966E2BDFB951CC66CC19`. If it is
not, the SEP repo has changed since the freeze: stop and tell me (do not continue with a
different archive).

```powershell
cd ..\watchword
python eval/split_sep.py --zip Should-It-Be-Executed-Or-Processed-main.zip
cd ..\selfguard-v3.2
python eval/sep_v32.py --rows ..\watchword\data\sep\dev.jsonl --limit 30     # quick check first
python eval/sep_v32.py --rows ..\watchword\data\sep\dev.jsonl                # full dev, 600 rows
```
9 replies per row (3 conditions x no defence / v3.1 / v3.2), 5,400 in total; it resumes if
stopped. This tells us what to expect, and is where any problem should show up. If the dev
result makes you want to change something, change it now and write it in the pre-registration.

## 4. Build the fresh sealed split

```powershell
$env:WATCHWORD_PATH = (Resolve-Path ..\watchword).Path
$env:SEP_ZIP = ".\Should-It-Be-Executed-Or-Processed-main.zip"
python build_sealed.py          # only if data\sealed_v3.jsonl is missing; deterministic
python build_sealed_v32.py --dry-run
python build_sealed_v32.py
```
It prints counts and a SHA-256 only. Copy the SHA-256.

## 5. Finish the pre-registration, then commit and push

Open `PREREGISTRATION_v3.2.md` and fill in every `FILL-IN`:
the date, the sealed SHA-256 (replace `FILL-IN-AFTER-BUILD`), the Mistral digest from
`ollama list`, and any change made after the dev run ("none" if none). Remove the DRAFT box.

```powershell
git add PREREGISTRATION_v3.2.md
git commit -m "Pre-register v3.2 sealed SEP test"
git push
```
The push time on GitHub is the proof it was written before the sealed run.

## 6. SEP sealed, one shot

```powershell
python eval/sep_v32.py --sealed
```
It checks the hash against the pre-registration and refuses if a sealed report already exists.
If it is interrupted during generation, run the same command again: it resumes from the cache.

## 7. BIPIA

```powershell
python eval/bipia_eval.py --bipia ..\bipia --model qwen2.5:7b-instruct --n 50
```
50 e-mails, each clean + 2 misinformation + 2 scam attacks (100 attacks per category). The
judge is the same model; add `--judge mistral:7b-instruct` for an independent judge if time
allows (a second run, same command plus that flag and `--out results\bipia_v32_judge_mistral.json`).

## 8. AgentDojo (regression check)

The canary is not used in the agent pipeline, so v3.2 should match v3.1 here; this checks
nothing broke and shows run-to-run variation.

```powershell
pip install agentdojo openai
$env:AD_CONDITIONS = "none,sg3"
python eval/agentdojo_run.py banking
python eval/agentdojo_run.py slack
```

## 9. Collect and export

```powershell
python eval/collect_results.py
```
Writes `selfguard-v3.2-results-<date>-<time>.zip` to your **Downloads** folder: a combined
`RESULTS.md`, `environment.json` (GPU, Python, git commit, Ollama model digests), every result
file, and the raw SEP replies. It never includes `data\` (SEP rows stay private). If the zip is
too big to send, run `python eval/collect_results.py --no-cache`.

Send me the zip (and the output of any step that failed).

---

## What each result answers

| Result | Question |
|---|---|
| SEP sealed, v3.2 vs no defence (C1) | Does v3.2 cut attack success, with the 95% upper bound at or below 5%? |
| SEP sealed, v3.2 vs v3.1 (secondary) | Does the canary add protection on top of v3.1? |
| SEP grounding and withheld (C2, C3) | Does it cost answer quality or false alarms? |
| Canary fire rates | Does the canary fire on clean data (false alarms) and when the model obeys? |
| BIPIA | Same questions on e-mail QA with lies and scams, and correct-answer rate |
| AgentDojo | Did anything regress in agent tasks? |
