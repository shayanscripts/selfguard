# Reproducibility

This guide distinguishes reproduction of the historical exploratory run from a new confirmatory evaluation.

## Historical experiment specification

The canonical v0.1 record is [results/sep_fixed_system_paper_seed42.json](results/sep_fixed_system_paper_seed42.json). The executable workflow is [SELFGuard_SEP_Benchmark.ipynb](SELFGuard_SEP_Benchmark.ipynb).

The reported run used:

- the SEP-derived archive from [Should It Be Executed Or Processed?](https://github.com/egozverev/Should-It-Be-Executed-Or-Processed);
- Qwen2.5-0.5B-Instruct;
- one fixed ShopCo system prompt;
- random seed 42;
- greedy decoding with at most 80 new tokens;
- 1,000 clean calibration responses;
- 2,000 training pairs;
- 300 validation pairs; and
- 300 test pairs.

Protocol 2 verifies the extracted `datasets/SEP_dataset.json` used for this
project as 12,089,182 bytes with SHA-256
`9f81a52ba089073251793f8499fbb79bb4112e94cf48d31b7f8805e8b44fa3ce`.
It pins Qwen revision
`7ae557604adf67be50417f59c2c2f167def9a775` and all-MiniLM-L6-v2 revision
`1110a243fdf4706b3f48f1d95db1a4f5529b4d41`. These controls define new
protocol-2 runs; they do not retroactively prove that the historical run used
identical upstream bytes or package builds.

Do not commit or redistribute the upstream dataset archive from this repository unless its licensing terms independently permit that use. Download it from its source and retain its citation.

## Run the notebook

1. Start a fresh Google Colab runtime with a GPU.
2. Open `SELFGuard_SEP_Benchmark.ipynb` and install the repository and research/Hugging Face dependencies when prompted.
3. Upload the upstream SEP archive when the notebook requests it.
4. Select paper mode and seed 42.
5. Run cells in order without changing the split, model, generation, or threshold-selection configuration.
6. Keep checkpoints in the new `*_protocol2` output directory. Do not silently reuse an older checkpoint with a different configuration.
7. Compare generated aggregate metrics with the JSON record. Floating-point values and generated text may differ across model revisions, package versions, accelerators, and kernels.

For a local editable environment, use:

```bash
python -m pip install -e ".[research,huggingface]"
```

The historical run did not record enough provenance to promise bit-for-bit reproduction. A matching headline table is a computational reproduction; it does not restore an untouched holdout or turn the result into confirmatory evidence.

## Record provenance for every new run

Before generation, save:

- the exact repository commit;
- SHA-256 of the uploaded dataset archive and extracted canonical data file;
- model identifier and immutable model revision/commit;
- tokenizer identifier and revision;
- Python, package, PyTorch, CUDA, driver, GPU, and operating-system versions;
- all seeds and determinism settings;
- the full fixed system prompt or its hash when disclosure is unsafe;
- generation settings, including maximum length and sampling parameters;
- calibration/training/validation/test pair identifiers or stable hashes;
- split-protocol version and grouping fields;
- fitted artifact hashes and selected thresholds; and
- raw per-example scores in access-controlled storage when licensing/privacy allows.

Useful environment captures include `python -m pip freeze`, `nvidia-smi`, the notebook runtime metadata, and SHA-256 checksums. A checksum identifies bytes; it does not grant permission to redistribute them.

## Avoid repeating the historical evaluation leak

The old smoke and paper workflows reused the same seed and leading slices, so smoke validation/test examples overlapped the paper sets. In addition, paper test metrics were viewed before S4 was finalized.

For future work:

1. Freeze a versioned split manifest before modeling.
2. Give smoke runs separate, non-overlapping examples.
3. Use training data for fitting and validation data for feature/threshold decisions.
4. Keep the new confirmatory test labels and metrics inaccessible until the complete protocol is frozen.
5. Do not tune after test release; label any follow-up on that set exploratory.
6. Report paired confidence intervals and a paired test such as McNemar's test for thresholded predictions.
7. Repeat across seeds, prompts, models, domains, and attack families.

“Task- and witness-group-disjoint selected split” is the appropriate description of the current grouping claim. Do not call it fully leakage-free.

## Expected comparisons

A reproduction should report, at minimum:

- the fixed weighted S1-S3 baseline at threshold 0.8;
- SELF-Light (RF3) and SELF-Full (RF4);
- maximum-validation-F1 and validation-FPR-at-most-5% operating points;
- precision, recall, F1, clean FPR, confusion counts, ROC AUC, and average precision;
- witness-substring-proxy recall, with the proxy definition stated;
- S4 latency and missing-value/source counts; and
- paired uncertainty for RF4 minus RF3.

Keep development findings separate from a future untouched confirmatory result.
