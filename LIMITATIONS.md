# Limitations

SELFGuard v0.1 is an exploratory research preview. It is not a certified security control, and its scores should not be treated as probabilities that a response is malicious.

## Experimental evidence

- **Derived, fixed-system task.** The reported experiment uses SEP-derived examples with one ShopCo system prompt. It does not reproduce the full native SEP setup or each example's original clean system prompt.
- **Selected split, not a pristine holdout.** The selected data are task- and witness-group-disjoint after filtering, but the paper test set was inspected during iterative development. Earlier smoke validation/test slices also overlapped the leading paper slices. The reported RF3/RF4 comparison is exploratory, not confirmatory.
- **Narrow model coverage.** Results come from Qwen2.5-0.5B-Instruct with one prompt, seed 42, greedy decoding, and an 80-token generation limit. There is no evidence yet for other model sizes, providers, languages, domains, prompts, sampling settings, or longer responses.
- **Historical uncertainty is unresolved.** The stored v0.1 record has point estimates but no row-level historical predictions from which to verify a paired interval or significance result. Protocol 2 computes descriptive paired bootstrap intervals and an exact McNemar test for new runs. Random-forest impurity importance is descriptive, not causal.
- **Historical provenance is incomplete.** The original paper-mode run did not pin and record every package version, accelerator detail, dataset hash, and model revision. Exact bit-for-bit reconstruction may be impossible.

## Labels and metrics

- **Witness matching is a proxy.** An injected response is called “effective” only when a case-insensitive witness substring is found. This can miss paraphrases and can count incidental matches; it is not a human-confirmed judgment that the attack achieved its objective.
- **Balanced prevalence changes precision.** The test set contains 50% clean and 50% injected examples. Real deployments may have far fewer attacks, causing many more false alarms per true alarm even when sensitivity and specificity transfer. As an illustration only, a 46% true-positive rate and 2.667% false-positive rate imply roughly 15% positive predictive value at 1% attack prevalence.
- **Thresholds are deployment-specific.** The reported thresholds were selected on one validation distribution. They should be recalibrated on representative clean data and evaluated against the costs of misses and false alarms before use elsewhere.
- **Dataset separation is limited.** Task/witness grouping and exact duplicate checks do not rule out semantic overlap, benchmark contamination in model pretraining, or memorization.

## Security boundary

- **Detection is post-generation.** SELFGuard analyzes a response after the model has produced it. Suppressing displayed text cannot undo tool calls, network requests, file writes, purchases, messages, or other side effects that occurred during generation.
- **No guarantee against adaptive attacks.** The benchmark does not cover a determined attacker who knows the detector, probes thresholds, optimizes against the signals, or targets the embedding/model dependencies.
- **Outputs remain untrusted.** A clean score is not authorization to execute code, call tools, reveal secrets, or bypass normal sandboxing, allowlists, validation, and human approval.
- **Calibration can be poisoned.** Clean calibration responses define the reference behavior. Contaminated, unrepresentative, or too-small calibration data can shift scores and thresholds.

## Implementation and cost

- **The packaged default is not the reported RF model.** The public detector defaults to a weighted S1-S3 heuristic. The experimental RF3/RF4 artifacts are not bundled as a production model.
- **S4 needs model logits.** It is unavailable for ordinary text-only APIs unless the provider exposes suitable token-level logits. Computing it requires another model forward pass and adds hardware-, sequence-, and model-dependent latency and memory use.
- **Embedding dependence.** S2/S3 behavior depends on the embedding model and its version. Package or model updates can change calibration and scores.
- **Long and unusual responses.** Truncation, multilingual content, code, structured data, domain jargon, very short output, or distribution shifts may produce unmeasured error rates.

The next credible evidence should come from a newly frozen, untouched test protocol; multiple seeds, system prompts, models, and domains; paired uncertainty estimates; adaptive attacks; and latency/memory measurements on documented hardware.
