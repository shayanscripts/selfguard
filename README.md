# SELFGuard

[![CI](https://github.com/shayanscripts/selfguard/actions/workflows/ci.yml/badge.svg)](https://github.com/shayanscripts/selfguard/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

SELFGuard is an experimental Python toolkit for measuring behavioral drift in
language-model responses after generation. Its current research question is
whether those signals can help identify responses associated with
prompt-injected inputs.

> [!IMPORTANT]
> This is a **v0.1 research preview**, not a production security boundary.
> Detection happens after the model has generated its response, so it cannot
> undo tool calls, network requests, file writes, or other side effects. Keep
> least-privilege tools, sandboxing, validation, and human approval in place.

## What is included

SELF-Light computes three text-level signals:

1. vocabulary overlap with the configured system prompt;
2. semantic coherence between adjacent response sentences; and
3. semantic alignment between the response and system prompt.

SELF-Full adds Signal 4: mean teacher-forced negative log likelihood in bits per
response content token. Signal 4 requires direct model logits and an additional
forward pass. Higher surprise is not inherently malicious; the research
Random Forest learns its interaction with the other signals.

The installable API uses a transparent weighted S1-S3 heuristic. That score is
not a probability and is not the Random Forest reported in the experiment. The
repository contains the RF3/RF4 training workflow, but it deliberately does not
distribute fitted `joblib` artifacts as a stable production detector.

## Current evidence

The reported evaluation is a **SEP-derived, fixed-system-prompt experiment**:
Qwen2.5-0.5B-Instruct, one ShopCo policy, seed 42, greedy generation, and a
balanced test set of 300 clean plus 300 injected responses.

At the validation-FPR-at-most-5% operating point:

| Model | Precision | Recall | F1 | Observed clean FPR | TP / FP |
|---|---:|---:|---:|---:|---:|
| SELF-Light (RF3) | 0.9429 | 0.4400 | 0.6000 | 0.0267 | 132 / 8 |
| SELF-Full (RF4) | 0.9452 | 0.4600 | 0.6188 | 0.0267 | 138 / 8 |

Signal 4 recorded six additional injected detections at the same aggregate
false-positive count in this operating-point comparison. It did **not** reduce
false positives. At the maximum-validation-F1 point, RF4 raised recall but also
raised false positives from 89 to 135 and lowered test F1.

These results are exploratory: the test set was inspected during development,
the old smoke run overlapped the old paper split, attack prevalence was
artificially 50%, and only one small model/prompt/seed was evaluated. Read
[RESULTS.md](RESULTS.md) for the complete table and
[LIMITATIONS.md](LIMITATIONS.md) before citing it.

## Install

```bash
python -m pip install .
python -m pip install ".[openai]"       # optional OpenAI adapter
python -m pip install ".[anthropic]"    # optional Anthropic adapter
python -m pip install ".[huggingface]"  # local models and Signal 4
```

Python 3.10 or newer is required. Constructing the default detector may
download its sentence-transformer model.

## Use the post-generation guard

Calibration is mandatory. Use clean responses produced by the same model,
system prompt, domain, and generation settings you intend to evaluate.
Ten responses are the enforced minimum; larger representative calibration sets
are strongly preferred.

```python
from selfguard import SELFGuard

clean_responses = [
    "Your order is being prepared and will ship soon.",
    # Add at least nine more representative, known-clean model responses.
]

guard = SELFGuard(
    system_prompt="You are a customer-support assistant.",
    llm=lambda message: call_your_model(message),
    clean_examples=clean_responses,
    threshold=0.8,
    telemetry=False,
)

result = guard.chat("Where is my order?")
print(result.flagged, result.injection_score, result.text)
```

`threshold=0.8` is only a heuristic starting point. Select a threshold on
deployment-representative validation data and report both false-positive and
false-negative rates. With `block_injections=True`, flagged text is replaced
after generation and also redacted from the nested `DetectionResult`.

Automatic calibration is opt-in and may incur one model call per prompt:

```python
guard = SELFGuard(
    system_prompt="You are a customer-support assistant.",
    llm="openai",
    model="your-model",
    auto_calibrate=True,
    calibration_prompts=known_clean_prompts,  # at least 10
)
```

For Hugging Face, attach the model before deferred automatic calibration runs:

```python
guard = SELFGuard(
    system_prompt="You are a support assistant.",
    llm="huggingface",
    auto_calibrate=True,
    calibration_prompts=known_clean_prompts,
)
guard.attach_hf_model(model, tokenizer)
```

## Compute Signal 4

Retaining token IDs during generation gives the most faithful replay:

```python
from selfguard import token_surprise_bits_from_ids

s4 = token_surprise_bits_from_ids(
    model,
    prompt_token_ids=stored_prompt_ids,
    response_token_ids=stored_response_content_ids,
)
print(s4.mean_bits, s4.token_count)
```

`token_surprise_bits(...)` can instead retokenize stored text under a
system/user chat context. That remains a likelihood measurement, but it may not
exactly reconstruct the sequence originally generated.

## Reproduce the research workflow

[![Open benchmark in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/shayanscripts/selfguard/blob/main/SELFGuard_SEP_Benchmark.ipynb)
[![Open smoke test in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/shayanscripts/selfguard/blob/main/SELFGuard_Colab_Smoke_Test.ipynb)

[SELFGuard_SEP_Benchmark.ipynb](SELFGuard_SEP_Benchmark.ipynb) trains the paired
RF3/RF4 ablation, selects thresholds on validation scores, performs descriptive
paired bootstrap and McNemar analyses, and saves:

- aggregate signal/score tables without prompt, witness, or response text;
- split manifests with hashed group identifiers;
- comparison, delta, feature-importance, and uncertainty tables;
- model/data/environment metadata; and
- SHA-256 hashes for generated artifacts.

Protocol 2 gives future smoke and paper runs non-overlapping selected slices.
It does not make the historical, already-inspected paper result confirmatory.
See [REPRODUCIBILITY.md](REPRODUCIBILITY.md) for the exact procedure.
For upload and checkpoint-resume instructions, see [COLAB.md](COLAB.md).

The source data come from
[Should It Be Executed Or Processed?](https://github.com/egozverev/Should-It-Be-Executed-Or-Processed),
associated with Zverev et al., *Can LLMs Separate Instructions From Data? And
What Do We Even Mean By That?* (ICLR 2025). The dataset is not redistributed
here. Obtain it upstream and independently confirm its terms before use.

## Privacy and telemetry

Telemetry is off by default and sends nothing unless the caller opts in and
configures an endpoint. When active, JSON payloads exclude prompts, user
messages, and response text, but include a random session ID and numeric
metadata. Endpoint and network operators can still observe ordinary network
metadata such as IP addresses and timing. See [SECURITY.md](SECURITY.md).

## Development

```bash
python -m pip install -e ".[huggingface,dev]"
python -m unittest discover -s tests -v
python scripts/validate_notebooks.py
python -m build
python -m twine check dist/*
```

GitHub Actions runs the full PyTorch-enabled suite on Python 3.10 and 3.12,
validates source notebooks, and checks built distributions.

## Citation and license

Use [CITATION.cff](CITATION.cff) and identify the exact release or commit.
SELFGuard code is released under the [MIT License](LICENSE).
