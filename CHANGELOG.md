# Changelog

All notable project changes will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project intends to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0-rc.1] - 2026-08-09

### Added

- Fixed-clean-FPR evaluation API and CLI with validation-only threshold
  selection, Wilson confidence intervals, realistic-prevalence precision,
  per-stratum and hard-negative metrics.
- Fail-closed cross-split checks for example IDs, source groups, and available
  content hashes.
- Production-oriented evaluation protocol and hard-negative taxonomy.
- Deny-by-default pre-action tool boundary with scope checks, argument policy,
  detector vetoes, verified approval for side effects, privacy-conscious audit
  events, and fail-closed execution.
- Protocol-4 release evaluation with 400 clean validation and test examples
  and 1% Wilson-upper-bound FPR selection; both candidates failed the recall
  gate and remain development-only.
- Auditable pre-generation `PromptRiskDetector` signals and a v3 development
  workflow combining prompt and response features with hard-negative mining.
- V4 development workflow with character/word TF-IDF prompt modeling,
  group-safe out-of-fold stacking, separate external-domain calibration, exact
  cross-dataset overlap rejection, and privacy-safe row-level score exports.
- Provider-independent `PromptInjectionPlugin` with allow/review/block states,
  fail-closed detector and audit behavior, pre-call wrapping, privacy-conscious
  audit events, and hash-verified `skops` model-bundle loading.
- V5 development workflow with four text learners, soft-vote and stacked
  candidates, exact stable top-k hard-negative selection, and plug-in bundle
  export.

### Changed

- Made confidence-bound FPR selection the evaluator and CLI default; point-FPR
  selection now requires an explicit exploratory opt-in.
- Moved analytics hashing after all exports are written and verify the archive
  member set, so fixed-FPR, runtime, and score files are covered.
- Kept Signal 4 ablation-only: the protocol-4 run improved ranking AUC/AP but
  reduced recall, F1, and effective-attack recall at the 1% confidence-bound
  operating point while adding substantially higher latency.
- Added conservative prevalence-adjusted precision based on recall's Wilson
  lower bound and clean-FPR's Wilson upper bound.

## [0.1.0] - 2026-08-03

### Added

- Machine-readable record of the canonical SEP-derived fixed-system exploratory results.
- Reproducibility, limitations, contribution, security, and citation documentation.
- Research workflow for paired SELF-Light (S1-S3) and SELF-Full (S1-S4) random-forest ablation.
- S4 model conditional negative-log-likelihood computation from causal-model logits.
- Protocol-2 split selection with non-overlapping future smoke/paper slices, pinned model revisions, provenance manifests, artifact hashes, and paired uncertainty code.
- PyTorch-enabled Python 3.10/3.12 continuous integration, notebook validation, and distribution checks.
- Initial experimental SELFGuard package with vocabulary, coherence, and system-alignment drift signals.
- Calibration, post-generation response suppression, supported backend wrappers, batch checking, and optional telemetry.
- Fixed weighted baseline and Colab benchmark notebooks.

### Changed

- Clarified that runtime detection is post-generation and cannot prevent generation-time side effects.
- Clarified that telemetry is opt-in and that endpoint operators can receive ordinary network metadata.
- Reframed historical paper-mode numbers as exploratory because the test set was inspected during development and old smoke/paper slices overlapped.
- Replaced broad “leakage-free” language with the supported “task- and witness-group-disjoint selected split” description.
- Redacted blocked raw responses from nested detection metadata and made telemetry delivery messages reflect actual endpoint configuration.
- Expanded the README evidence section to report the weighted baseline and both Random Forest operating points with complete validation, test, confusion-count, ranking, and witness-proxy metrics.
