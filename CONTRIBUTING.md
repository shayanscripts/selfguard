# Contributing

SELFGuard is an exploratory research project. Contributions that improve correctness, reproducibility, evaluation breadth, documentation, privacy, and safe deployment boundaries are welcome.

## Before making a change

- Open an issue before a major API, signal, benchmark, or dependency change so the scope and evidence standard can be agreed.
- Keep changes focused. Do not mix refactors with metric-changing research modifications.
- Never commit API keys, private prompts, raw sensitive outputs, downloaded datasets, model checkpoints, fitted pickle/joblib artifacts, or notebook credentials.
- Follow the upstream dataset's license and citation requirements. This repository does not grant permission to redistribute SEP data.

## Development setup

Use Python 3.10 or newer:

```bash
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
```

Changes to Hugging Face/S4 behavior must also be tested with the Hugging Face dependencies installed so torch-dependent tests run instead of being skipped.

## Pull-request checklist

- Add or update tests for changed behavior, including failure paths and edge cases.
- Run the full test suite and notebook validation.
- Keep public interfaces documented and backwards-compatible unless the change is explicitly breaking.
- Update `CHANGELOG.md`, limitations, and reproducibility notes when behavior or evidence changes.
- Explain any change to thresholds, splits, feature definitions, generation settings, or metrics.
- Report the exact environment, seeds, data/model revisions, and artifact hashes for new benchmark claims.
- Avoid unsupported language such as “leakage-free,” “proved,” “secure,” or “production-ready.”
- Confirm telemetry remains opt-in and that no prompt or response text is transmitted.

## Research-result requirements

New benchmark results should:

1. use a frozen, versioned split manifest;
2. keep smoke/development data disjoint from the final test set;
3. select features and operating points without inspecting final-test outcomes;
4. distinguish native benchmarks from derived or fixed-system variants;
5. define automated success proxies and validate them where possible;
6. report class prevalence, confusion counts, ROC AUC, average precision, and operating-point metrics;
7. include paired uncertainty when comparing models on the same examples;
8. measure runtime and memory costs; and
9. separate exploratory findings from untouched confirmatory results.

If a final test set is inspected and further tuning follows, retain the result but relabel it exploratory and create a new untouched evaluation for confirmation.

## Security reports

Do not publish vulnerability details in an ordinary issue. Follow [SECURITY.md](SECURITY.md).
