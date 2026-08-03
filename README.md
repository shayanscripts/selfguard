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
balanced test set of 300 clean plus 300 injected responses. The run used 1,000
clean calibration responses, 2,000 training pairs, and 300 validation pairs.

No single F1 describes every deployment tradeoff. The weighted baseline used
its fixed threshold of 0.8; each Random Forest threshold was selected on the
validation split and then evaluated on the fixed exploratory test split.
Historical Random Forest thresholds are displayed to six decimal places
because higher-precision values were not preserved in the frozen result record.

### Validation-selected Random Forest operating points

| Model | Operating point | Threshold | Precision | Recall | F1 | Clean FPR | TN | FP | FN | TP |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SELF-Light (RF3) | Maximum validation F1 | 0.390223 | 0.683333 | 0.820000 | 0.745455 | 0.380000 | 186 | 114 | 54 | 246 |
| SELF-Light (RF3) | Validation FPR ≤ 5% | 0.733778 | 0.880000 | 0.366667 | 0.517647 | 0.050000 | 285 | 15 | 190 | 110 |
| SELF-Full (RF4) | Maximum validation F1 | 0.299815 | 0.643541 | 0.896667 | 0.749304 | 0.496667 | 151 | 149 | 31 | 269 |
| SELF-Full (RF4) | Validation FPR ≤ 5% | 0.719706 | 0.902597 | 0.463333 | 0.612335 | 0.050000 | 285 | 15 | 161 | 139 |

Validation confusion counts are the integer counts implied by the stored
metrics and the 300-clean/300-injected validation design.

### Fixed exploratory test results

| Model | Operating point | Threshold | Precision | Recall | F1 | Clean FPR | TN | FP | FN | TP | ROC AUC | Average precision | Witness-proxy recall |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Weighted S1-S3 | Fixed threshold | 0.800000 | 0.767857 | 0.143333 | 0.241573 | 0.043333 | 287 | 13 | 257 | 43 | 0.736439 | 0.692157 | Not measured |
| SELF-Light (RF3) | Maximum validation F1 | 0.390223 | 0.739003 | 0.840000 | 0.786271 | 0.296667 | 211 | 89 | 48 | 252 | 0.853844 | 0.864318 | 170/173 (0.982659) |
| SELF-Light (RF3) | Validation FPR ≤ 5% | 0.733778 | 0.942857 | 0.440000 | 0.600000 | 0.026667 | 292 | 8 | 168 | 132 | 0.853844 | 0.864318 | 90/173 (0.520231) |
| SELF-Full (RF4) | Maximum validation F1 | 0.299815 | 0.666667 | 0.900000 | 0.765957 | 0.450000 | 165 | 135 | 30 | 270 | 0.862028 | 0.877253 | 172/173 (0.994220) |
| SELF-Full (RF4) | Validation FPR ≤ 5% | 0.719706 | 0.945205 | 0.460000 | 0.618834 | 0.026667 | 292 | 8 | 162 | 138 | 0.862028 | 0.877253 | 99/173 (0.572254) |

The weighted-baseline confusion counts are reconstructed exactly from the
reported metrics and balanced test-set size; historical row-level predictions
were not retained. ROC AUC and average precision do not depend on the displayed
operating threshold, so they repeat across the two rows for each forest.

### SELF-Full minus SELF-Light

| Operating point | Delta precision | Delta recall | Delta F1 | Delta clean FPR | Delta ROC AUC | Delta average precision | Delta witness-proxy recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| Maximum validation F1 | -0.072336 | +0.060000 | -0.020314 | +0.153333 | +0.008183 | +0.012935 | +0.011561 |
| Validation FPR ≤ 5% | +0.002348 | +0.020000 | +0.018834 | 0.000000 | +0.008183 | +0.012935 | +0.052023 |

Thus, the highest observed test F1 was 0.786271 for SELF-Light at the
maximum-validation-F1 point. At the low-FPR point, SELF-Full raised F1 from
0.600000 to 0.618834 and true positives from 132 to 138 while both models had
8 false positives. At the maximum-validation-F1 point, SELF-Full raised recall
but increased false positives from 89 to 135 and reduced test F1.

The RF4 impurity importances were S3 alignment 0.293859, S4 model NLL
0.254848, S1 vocabulary 0.245052, and S2 coherence 0.206242. In a separate
200-response smoke diagnostic, S4 used exact token IDs for every response,
had zero missing values, and added a median 142.555 ms forward-pass latency;
that timing is hardware-specific. Witness-proxy recall uses a case-insensitive
witness substring, not a human-confirmed attack-success judgment.

These results are exploratory: the test set was inspected during development,
the old smoke run overlapped the old paper split, attack prevalence was
artificially 50%, and only one small model/prompt/seed was evaluated. Read
[RESULTS.md](RESULTS.md) and the
[machine-readable result record](results/sep_fixed_system_paper_seed42.json) for
the complete evidence, and read
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
