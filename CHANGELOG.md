# Changelog

All notable project changes will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project intends to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
