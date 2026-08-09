# SELFGuard

[![CI](https://github.com/shayanscripts/selfguard/actions/workflows/ci.yml/badge.svg)](https://github.com/shayanscripts/selfguard/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status: Release candidate](https://img.shields.io/badge/status-release%20candidate-orange.svg)](LIMITATIONS.md)

SELFGuard is an experimental Python toolkit for measuring prompt risk before
generation and behavioral drift in language-model responses after generation.
Its current research question is whether those signals can help identify
prompt-injected inputs and their resulting responses.

> [!IMPORTANT]
> This is a **v0.2.0 release candidate**, not a production security boundary.
> Prompt checks can run before generation, but response detection happens after
> output exists and neither score is authorization. A response check cannot undo
> tool calls, network requests, file writes, or other side effects. Keep
> least-privilege tools, sandboxing, validation, and human approval in place.

## What is included

SELF-Light computes three text-level signals:

1. vocabulary overlap with the configured system prompt;
2. semantic coherence between adjacent response sentences; and
3. semantic alignment between the response and system prompt.

`PromptRiskDetector` adds transparent pre-generation features for instruction
override, role-change, prompt/secret exfiltration, tool-action language,
delimiter density, vocabulary overlap, and optional semantic alignment. These
are detector inputs and veto signals, never authorization.

SELF-Full adds Signal 4: mean teacher-forced negative log likelihood in bits per
response content token. Signal 4 requires direct model logits and an additional
forward pass. Higher surprise is not inherently malicious; the research
Random Forest learns its interaction with the other signals.

The installable API uses a transparent weighted S1-S3 heuristic. That score is
not a probability and is not the Random Forest reported in the experiment. The
repository contains the RF3/RF4 training workflow, but it deliberately does not
distribute fitted `joblib` artifacts as a stable production detector.

### Release posture

No detector is currently promotion-eligible. The v5 development run fixed
exact top-k hard-negative mining and exported a hash-verified prompt-model
bundle. The overall meta-model passed the descriptive SEP operating gate, while
the portable prompt-only plug-in missed the 1% clean-FPR confidence-bound gate
by one false positive. SEP and deepset test results have already been inspected,
so they cannot promote the model.

### Latest development results

| Candidate | Precision | Recall | F1 | Clean FP / N | FPR 95% upper | ROC AUC | AP |
|---|---:|---:|---:|---:|---:|---:|---:|
| V5 overall meta-model | 1.0000 | 0.6400 | 0.7805 | 0 / 400 | 0.9512% | 0.9790 | 0.9815 |
| V5 portable prompt plug-in | 0.9963 | 0.6700 | 0.8012 | 1 / 400 | 1.4023% | 0.9761 | 0.9789 |
| V4 stacked text | 0.9962 | 0.6625 | 0.7958 | 1 / 400 | 1.4023% | 0.9624 | 0.9672 |
| Protocol-4 RF3 | 1.0000 | 0.0950 | 0.1735 | 0 / 400 | 0.9512% | 0.8499 | 0.8508 |

These are descriptive results on an already-inspected, balanced SEP-derived
test. The v5 meta-model uses post-generation response signals and is not the
portable pre-generation plug-in. At 1% assumed deployment attack prevalence,
the plug-in's conservative precision estimate was 30.96%, illustrating why
balanced-test precision must not be presented as deployment precision.

## Historical v0.1 evidence

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
python -m pip install ".[plugin]"       # verified plug-in model bundles
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

## Evaluate at a fixed false-positive rate

Use the production-oriented evaluator to select a threshold on validation data
and apply it once to an untouched test set. It reports Wilson confidence
intervals, realistic-prevalence precision, per-stratum metrics, and a dedicated
hard-negative result. It also fails when example IDs, source groups, or known
content hashes cross split boundaries.

```bash
selfguard-evaluate \
  --train scores/train.jsonl \
  --validation scores/validation.jsonl \
  --test scores/test.jsonl \
  --max-clean-fpr 0.01 \
  --fpr-constraint upper \
  --deployment-attack-prevalence 0.01 \
  --output results/fixed_fpr_report.json
```

For the score-file schema, hard-negative taxonomy, split rules, and suggested
release gates, read [EVALUATION.md](EVALUATION.md).

## Gate tool actions before execution

`ActionBoundary` provides a deny-by-default dispatch layer for LLM-proposed
tool calls. It requires registered tools, trusted principal scopes, argument
allowlists and validation, detector results, verified approval for every write
or destructive action, and auditable decisions. SELFGuard can veto an action;
a low score never authorizes one.

Keep the planner isolated from executable tools and place the boundary directly
in front of handlers that hold narrowly scoped credentials. See
[SECURITY_BOUNDARY.md](SECURITY_BOUNDARY.md) for the trust model and integration
example.

## Wrap an LLM with the prompt plug-in

`PromptInjectionPlugin` provides provider-independent allow/review/block
inspection before an LLM callable runs. Hash-verified model bundles use `skops`
instead of unsafe pickle/joblib loading.

```python
from selfguard import PromptInjectionPlugin

plugin = PromptInjectionPlugin.from_bundle(
    "selfguard_prompt_plugin.sgplugin",
    expected_sha256="<release hash>",
)
safe_generate = plugin.wrap(generate)
answer = safe_generate("Where is my order?")
```

Read [PLUGIN.md](PLUGIN.md) for custom provider extractors, indirect-injection
coverage, audit handling, and the security limitations. An allow decision is a
risk signal, never permission to execute a tool.

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
python -m pip install -e ".[huggingface,plugin,dev]"
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
