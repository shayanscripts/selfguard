# Colab guide

## Start a run

1. Open `SELFGuard_SEP_Benchmark.ipynb` in a fresh GPU runtime.
2. Leave `MODE = 'smoke'` for the first run.
3. Upload the current SELFGuard source ZIP and the upstream SEP ZIP when asked.
4. Authorize Google Drive.
5. Run every cell in order.
6. Use `MODE = 'paper'` only after the smoke pipeline finishes.

Protocol-2 outputs are stored under:

- `MyDrive/SELFGuard/qwen2.5-0.5b_smoke_seed42_protocol2/`
- `MyDrive/SELFGuard/qwen2.5-0.5b_paper_seed42_protocol2/`

Future smoke and paper selections do not overlap. Historical results remain
exploratory because the earlier test set was inspected and the old protocol
overlapped.

## Resume after a disconnect

Reopen the notebook, choose the same mode and seed, upload the same source and
dataset archives, mount the same Drive, and rerun from the top. Generation and
Signal 4 save every 25 completed items and skip matching records.

The notebook stops if the split protocol, model revision, archives, extracted
dataset digest, prompt, or checkpoint configuration differs. Do not copy or
rename an old protocol-1 directory to bypass these checks, and do not execute
isolated cells from an older notebook.
