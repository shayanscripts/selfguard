# Production-oriented evaluation

This protocol is designed to reduce false-positive rate without hiding the
corresponding detection-rate tradeoff. It keeps threshold selection separate
from final testing, fails on known split leakage, reports uncertainty, and
makes hard negatives visible instead of averaging them into one headline F1.

It does not turn SELFGuard's prompt or post-generation response detectors into
an authorization boundary. Tool permissions, sandboxing, schema validation,
and approval remain separate controls.

## Primary release metrics

Choose the clean-FPR budget before training. Report at least:

- injected recall (detection rate) at the fixed clean-FPR budget;
- clean FPR with a confidence interval;
- precision, recall, and F1 on the untouched test distribution;
- ROC AUC and average precision as threshold-independent diagnostics;
- projected precision at a realistic deployment attack prevalence;
- conservative projected precision using recall's Wilson lower bound and clean
  FPR's Wilson upper bound; and
- recall and clean FPR for every declared stratum and the hard-negative subset.

For production gates, constrain the confidence-interval upper bound rather than
only the observed FPR. A small clean set cannot establish a very low FPR: even
zero observed false positives has a non-zero upper confidence bound.

With the evaluator's 95% two-sided Wilson interval, zero false positives needs
at least 73 clean examples to put the upper bound at or below 5%, and at least
381 clean examples to put it at or below 1%. Validation and final test must
each independently meet the chosen evidence requirement. Use
`minimum_clean_samples_for_zero_false_positives()` to calculate other targets.

Never interpret projected precision from an observed zero false-positive count
as certainty. `conservative_precision_at_deployment_prevalence` combines the
recall lower bound and clean-FPR upper bound to expose this uncertainty. It is a
conservative marginal calculation, not a joint confidence interval.

## Split contract

Every scored row must contain a non-empty `group_id`. A group should identify
the largest correlated source that could leak behavior across splits, such as:

- source task or attack template;
- source document or retrieved page;
- conversation or user/session scenario; or
- paired clean/injected example family.

The evaluator rejects any `example_id`, `group_id`, or available `content_hash`
that crosses train, validation, and test. Freeze the manifest before modeling.
Do not tune features, models, prompts, or thresholds after revealing test
results; a reused test set is exploratory.

## Score-file schema

Use UTF-8 CSV or JSON Lines. Required fields are:

| Field | Type | Meaning |
| --- | --- | --- |
| `example_id` | string | Stable unique row identifier |
| `label` | integer | `0` for clean, `1` for injected |
| `score` | number | Detector score; larger means higher risk |
| `group_id` | string | Cross-split leakage group |

Optional fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `stratum` | string | Domain, model, language, attack family, or clean subtype |
| `is_hard_negative` | boolean | Clean example intentionally resembling an attack |
| `content_hash` | string | Stable hash for exact cross-split duplicate checks |

An `is_hard_negative=true` row must have `label=0`.

## Hard-negative suite

Build hard negatives from known-clean deployment traffic and reviewed synthetic
cases. Keep their categories in `stratum`. The minimum useful suite includes:

- quoted or analyzed prompt-injection text;
- security-policy and incident-response discussions;
- code, logs, markup, and structured data containing imperative language;
- benign instructions inside documents and retrieved content;
- role-play, translations, and multilingual requests;
- long, short, truncated, and refusal responses;
- domain jargon and responses with low system-prompt vocabulary overlap; and
- legitimate tool-use explanations that mention sensitive actions.

Do not create hard negatives by lightly editing test attacks. That creates a
new leakage path and inflates apparent generalization.

## Command-line evaluation

Select a threshold on validation data and apply it once to the untouched test:

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

`--fpr-constraint upper` is the default. Pass `--fpr-constraint point` only for
an explicitly exploratory diagnostic; a point estimate is not a release gate.

The output contains the validation-selected threshold, validation and test
confusion counts, Wilson intervals, ranking metrics, realistic-prevalence
precision, each test stratum, and the hard-negative subset.

## Promotion gate

Define the exact values from deployment risk and traffic volume. A starting
contract might require:

- clean-FPR 95% upper bound at or below 1%;
- minimum overall and worst-stratum injected recall;
- no unresolved split overlap;
- enough clean examples to support the FPR claim;
- latency and availability budgets measured on deployment hardware; and
- shadow-mode evidence before enforcement is enabled.

If any required stratum is missing, treat the evaluation as incomplete rather
than silently substituting the aggregate metric.
