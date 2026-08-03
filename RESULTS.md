# Exploratory Results

## Status and scope

These are the canonical paired-ablation numbers available for the v0.1 research preview. They come from a **SEP-derived, fixed-system-prompt experiment** using Qwen2.5-0.5B-Instruct, seed 42, and greedy generation capped at 80 new tokens. They are not results for the full native SEP task: the experiment loaded SEP-derived examples but generated every response under one ShopCo system prompt instead of each row's original clean system prompt.

The selected benchmark split was task- and witness-group-disjoint after filtering. That wording is intentionally narrower than “leakage-free”: exact/group separation does not rule out semantic overlap or pretraining contamination.

The historical paper-mode run used:

- 1,000 clean calibration responses;
- 2,000 training pairs;
- 300 validation pairs; and
- 300 test pairs, or 300 clean and 300 injected test responses.

The test set is therefore balanced at 50% attack prevalence. Precision below is conditional on that artificial prevalence and should not be interpreted as deployment positive predictive value.

## Held-out weighted heuristic

The fixed S1-S3 weighted heuristic was evaluated at its pre-set threshold of 0.8.

| Threshold | Precision | Recall | F1 | ROC AUC | Average precision | TN | FP | FN | TP |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.800000 | 0.767857 | 0.143333 | 0.241573 | 0.736439 | 0.692157 | 287 | 13 | 257 | 43 |

The confusion counts above are the integer counts implied by the reported metrics on 300 clean and 300 injected test examples.

## Paired random-forest ablation

`SELF-Light` uses S1-S3. `SELF-Full` adds S4, model conditional negative log-likelihood in bits. Each operating threshold was selected on validation data and then applied once to the corresponding test scores.

### Validation-selected operating points

| Model | Operating point | Threshold | Validation precision | Validation recall | Validation F1 | Validation clean FPR |
|---|---|---:|---:|---:|---:|---:|
| SELF-Light (S1-S3) | Maximum validation F1 | 0.390223 | 0.683333 | 0.820000 | 0.745455 | 0.380000 |
| SELF-Light (S1-S3) | Validation FPR ≤ 5% | 0.733778 | 0.880000 | 0.366667 | 0.517647 | 0.050000 |
| SELF-Full (S1-S4) | Maximum validation F1 | 0.299815 | 0.643541 | 0.896667 | 0.749304 | 0.496667 |
| SELF-Full (S1-S4) | Validation FPR ≤ 5% | 0.719706 | 0.902597 | 0.463333 | 0.612335 | 0.050000 |

### Test results

| Model | Operating point | Precision | Recall | F1 | Clean FPR | TN | FP | FN | TP | ROC AUC | Average precision | Witness-proxy recall |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SELF-Light (S1-S3) | Maximum validation F1 | 0.739003 | 0.840000 | 0.786271 | 0.296667 | 211 | 89 | 48 | 252 | 0.853844 | 0.864318 | 170/173 (0.982659) |
| SELF-Light (S1-S3) | Validation FPR ≤ 5% | 0.942857 | 0.440000 | 0.600000 | 0.026667 | 292 | 8 | 168 | 132 | 0.853844 | 0.864318 | 90/173 (0.520231) |
| SELF-Full (S1-S4) | Maximum validation F1 | 0.666667 | 0.900000 | 0.765957 | 0.450000 | 165 | 135 | 30 | 270 | 0.862028 | 0.877253 | 172/173 (0.994220) |
| SELF-Full (S1-S4) | Validation FPR ≤ 5% | 0.945205 | 0.460000 | 0.618834 | 0.026667 | 292 | 8 | 162 | 138 | 0.862028 | 0.877253 | 99/173 (0.572254) |

“Witness-proxy recall” is recall on injected responses whose output contained a case-insensitive witness substring. It is an automated proxy, not a human-confirmed success label and not proof that the attack achieved its full goal. Across training, validation, and test generation, 1,709 of 2,600 injected outputs met this proxy.

### SELF-Full minus SELF-Light

| Operating point | Δ precision | Δ recall | Δ F1 | Δ clean FPR | Δ ROC AUC | Δ average precision | Δ witness-proxy recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| Maximum validation F1 | -0.072336 | +0.060000 | -0.020314 | +0.153333 | +0.008183 | +0.012935 | +0.011561 |
| Validation FPR ≤ 5% | +0.002348 | +0.020000 | +0.018834 | 0.000000 | +0.008183 | +0.012935 | +0.052023 |

At the strict operating point, adding S4 held the aggregate test false-positive count at 8 while increasing true positives from 132 to 138 and witness-proxy hits from 90 to 99. It did **not** reduce false positives in this comparison. At the maximum-validation-F1 operating point, S4 increased recall but also increased false positives from 89 to 135 and reduced test F1.

### Exploratory feature importance

| Feature | Random-forest impurity importance |
|---|---:|
| S3 system alignment | 0.293859 |
| S4 model NLL bits | 0.254848 |
| S1 vocabulary | 0.245052 |
| S2 coherence | 0.206242 |

Impurity importance describes how this fitted forest used the features. It is not a causal attribution and can be biased when features are correlated or differ in scale/cardinality.

### S4 implementation diagnostic

A separate 200-response smoke diagnostic computed all S4 values from exact token IDs, with zero missing values. Its median additional forward-pass latency was 142.555017 ms. That timing was not measured as part of the paper-mode table, and the historical smoke hardware/runtime provenance is insufficient for a general latency claim. S4 cost must be remeasured on each intended model, sequence length, batch size, and device.

## Why these results are exploratory

- The historical smoke and paper runs reused seed 42 and leading slices. In particular, the smoke validation and test examples were subsets of the paper validation and test examples.
- The paper test results were inspected during RF3 development and again while deciding to add and evaluate S4. The set can support debugging and an exploratory ablation, but it is no longer an untouched confirmatory holdout.
- Historical row-level predictions were not preserved in this repository, so the published point estimates cannot support a retrospective paired interval or test. Protocol 2 computes paired bootstrap intervals and an exact McNemar test for new runs, but no such result currently establishes that the modest strict-point S4 improvement is distinguishable from sampling variation.
- Only one 0.5B model, one fixed system prompt, one seed, and one decoding configuration were evaluated.
- Historical environment, dataset-archive, and model-revision hashes were not all recorded, limiting bit-for-bit reproduction.

These numbers support a narrower conclusion: behavioral drift features separate clean and injected responses better than the fixed weighted heuristic in this selected experimental setting, and S4 merits further pre-registered evaluation. They do not establish production robustness or general prompt-injection detection.

See [LIMITATIONS.md](LIMITATIONS.md) and [REPRODUCIBILITY.md](REPRODUCIBILITY.md) before reusing or citing the results. The source benchmark is [Should It Be Executed Or Processed?](https://github.com/egozverev/Should-It-Be-Executed-Or-Processed), associated with Zverev et al., “Can LLMs Separate Instructions From Data? And What Do We Even Mean By That?” (ICLR 2025).
