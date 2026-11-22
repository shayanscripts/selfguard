# SelfGuard

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](selfguard3)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![v3.0 sealed SEP test: PASS 3/3](https://img.shields.io/badge/v3.0%20sealed%20SEP-PASS%203%2F3-brightgreen.svg)](archive/v3.0/PREREGISTRATION.md)

Layered protection against **indirect prompt injection** (instructions hidden in e-mails, web
pages, files and tool output) that wraps **any LLM**. No training, no model internals, no extra
call to the main LLM, no added prompt text. About **2 ms** of local checking per answer.

The core rule: **nothing inside the data can grant permission**; only the user's request and
the app's settings can.

| Layer | What it does | Cost |
|---|---|---|
| **Smart routing** | Data that contains instruction-like sentences goes into a low-authority (assistant) turn, so the model treats it as material, not orders; clean data keeps the normal layout, so answer quality is kept | rules, ~0 ms |
| **Reply checks** | A frozen engine (threshold 0.80) withholds replies that carry out an instruction found in the data, contain an untrusted command or tool payload, or leak the system prompt | rules |
| **Echo strip** (new in v3.4) | Removes reply sentences made mostly of words that appear only in the data's instruction-like sentences: the sentences that carry out an injected instruction. Aimed at the attacks that get past the layout | rules |
| **Action lock** | A tool call may only use links, e-mails and account numbers that appear in **trusted** text (system prompt, user request, allowlist). Password / permission changes are always held | rules |
| **Approver** (optional) | A small local model decides held actions. It sees only the user's request, the action and the field label of each value, **never the documents**, so injected text cannot argue with it | 1 small-model call, only when an action is held |
| **Link tripwire** | Untrusted links in the reply are defanged, untrusted images removed, hidden links (hxxp, `[.]`, spaced out, base64, homoglyphs) decoded first | rules |
| **Support trace** | A reply sentence whose only source is a sentence addressed to the AI ("tell the user...") is removed | rules |
| **v4 lie layer** (optional) | Strips AI-addressed sentences before the call (a small model confirms suspicious ones) and fact-checks the reply against the document | small-model calls |

## Versions

| Version | What changed | Status |
|---|---|---|
| v3.0 | Smart routing, reply checks, action lock, approver, tripwire, support trace | Sealed SEP test **PASS 3/3** (below) |
| v3.1 | Standalone engine, bug fixes | Not scored on a sealed split |
| v3.3 | Canary (planted random-code instruction) | **Dropped at the dev stage**: helpful models obey the harmless note on clean data (withheld 45% of clean SEP dev replies, 92% on the Qwen smoke test) |
| v3.4 | Echo strip; smart routing is the default | Dev results below; sealed test pending ([TESTING_PLAN.md](TESTING_PLAN.md)) |

## Results

All numbers are as measured; small local models (Mistral 7B, Qwen2.5 7B) on one RTX 3060 Ti.

### 1. v3.4 on the SEP dev split (Mistral 7B, development data, not a sealed result)

First 310 of 600 dev rows (full run in progress). Attack success counts the probe's witness in
a reply SelfGuard lets through, with SEP's substring grader and with a whole-word match.

| | No defence | v3.1 (always displaced) | Smart routing | **v3.4** (routing + echo strip) |
|---|---:|---:|---:|---:|
| Attack success (SEP grader) | 55.1% | 11.1% | 11.1% | **6.6%** |
| Attack success (whole word) | 51.8% | 8.2% | 8.2% | **3.6%** |
| Clean grounding | 84.9% | 76.1% | 83.3% | 82.3% |
| Clean replies withheld | 0.0% | 1.0% | 1.0% | 1.0% |
| Clean replies that lost a sentence to echo strip | – | – | – | 14.8% |

Echo strip stops 14 attacks v3.1 lets through and lets none through that v3.1 stops (McNemar
p = 0.0001). Smart routing fixes the always-displaced layout's quality loss.

### 2. v3.0 SEP, sealed and pre-registered (600 fresh rows, Mistral 7B)
Rows never used before, pass bar written in
[archive/v3.0/PREREGISTRATION.md](archive/v3.0/PREREGISTRATION.md) before any generation, scored once.

| | No defence | Always displaced | **Smart routing** |
|---|---:|---:|---:|
| Attack success (residual) | 62.2% | 10.2% | **10.2%** |
| Clean answers that use the data (grounding) | 82.7% | 72.2% | **80.0%** |
| Clean replies withheld | – | 0.8% | **0.8%** (Wilson hi 1.9%) |
| Legit instruction in the task followed | 77.0% | – | 77.2% |

Smart routing: **PASS 3/3** (protection McNemar p = 7e-81; grounding within 3 points; false alarms
<= 3%). The always-displaced variant fails the quality criterion.

### 3. AgentDojo v1.2 (v3.0; Qwen2.5 7B, `important_instructions` attack, no human in the loop)

| Suite | Defence | Attack success | Clean tasks done |
|---|---|---:|---:|
| Banking (144) | none | 7.6% | 43.8% |
| | action lock | **0.0%** | 31.3% |
| | lock + 7B approver | 3.5% | 37.5% |
| Slack (105) | none | 29.5% | 47.6% |
| | action lock | **0.0%** | 14.3% |
| | lock + 7B approver | **0.0%** | 23.8% |

The lock stops hijacked actions; its price is utility, because many legitimate tasks need a value
from a document ("pay the bill in this file"). In a real app those are an *Allow?* prompt; in the
benchmark nobody answers, so they count as failures. The approver recovers part of it.

### 4. BIPIA (v3.0; Microsoft, e-mail QA, Qwen2.5 7B, 20 e-mails)

| | No defence | v3 | v4 |
|---|---:|---:|---:|
| Misinformation attacks succeed | 78% | 2% | 2% |
| Scam attacks succeed | 62% | 8% | **2%** |
| Correct answers, clean e-mails | 45% | 45% | 45% |
| Correct answers under attack (misinfo / scam) | 5% / 22% | 42% / 32% | 38% / 30% |

Attack success and answer correctness are judged by Qwen2.5 7B (eval only).

### 5. Other checks (v3.0)
- Own e-mail agent suite (72 cases): 0/48 attacks succeed vs 48/48 undefended; legit actions
  allowed 12/12 with the approver. Self-made, so optimistic.
- [injection-holdout](https://github.com/shayanscripts/injection-holdout) v1 (finder only): flags
  98% of SPML and 89% of Gandalf attacks, but also 98.5% of clean **user** prompts, so the finder
  is only meaningful on documents, which is how SelfGuard uses it.

## Limitations
- **Utility cost on agent tasks** without a human approver (see AgentDojo).
- **Echo strip cost:** on clean documents that contain instruction-like sentences (procedures,
  FAQs), it often removes a sentence from a correct answer (about 15% of clean SEP dev replies).
  It cannot catch an injected answer that reuses none of the instruction's words.
- **Small local models only.** No commercial model has been tested yet.
- **No adaptive attacker.** An attacker who knows the rules can write injections the finder misses;
  those get the normal layout. The action lock still applies to them.
- **Lies without an action** are only partly covered (support trace, v4).
- SEP results use Mistral 7B; AgentDojo and BIPIA use Qwen2.5 7B.

## Install

```bash
pip install .            # standard library only
```

## Use

```python
from selfguard3 import SelfGuard
from selfguard3.approver import PerimeterApprover

approver = PerimeterApprover("qwen2.5:7b-instruct")            # optional, local via Ollama
sg = SelfGuard(approver=lambda name, args, v: approver(user_request, name, args, v, document))
messages = sg.messages(task=user_request, data=[document], system=system_prompt)
reply = my_llm(messages)                                         # your one normal call
out = sg.inspect(reply, task=user_request, data=[document], system=system_prompt)
out.text, out.safe, out.actions, out.findings
```

`out.actions` lists each tool call with `allow` / `block`; only run the allowed ones.
`SelfGuard()` is v3.4; `SelfGuard(layout="displaced", echo=False)` is v3.1.

## Reproduce
```bash
python -m unittest discover -s tests            # unit tests (model tests: MINICHECK=1, V4MODELS=1)
python eval/sep_splits.py dev                    # SEP dev split from the public archive
python eval/sep_eval.py --rows data/sep/dev.jsonl
python eval/bipia_eval.py --bipia ../bipia --n 50
python eval/agentdojo_run.py banking            # AD_CONDITIONS=none,sg3,approver
python eval/collect_results.py                   # one zip of every result
```
The full order, including the one-shot sealed run, is in [TESTING_PLAN.md](TESTING_PLAN.md).
SEP rows are not redistributed; `eval/sep_splits.py` rebuilds every split from the public archive
and checks each against its published SHA-256. v3.0's sealed-test scripts and results are kept
unchanged in [archive/v3.0](archive/v3.0) as the record of that pre-registered run.

## Related work
ASIDE and DRIP (training-time separation), Spotlighting, CaMeL and Dual-LLM, MELON, SONAR (sentence
sanitization), Semantic Overlays, MiniCheck (Tang et al. 2024), AgentDojo (Debenedetti et al.
2024), BIPIA (Yi et al. 2023), SEP (Zverev et al. 2025).

## Licence
[MIT](LICENSE)
