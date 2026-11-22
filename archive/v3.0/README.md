# v3.0 sealed SEP test: frozen record

These files are the record of SelfGuard v3.0's pre-registered, sealed SEP test (commit
`da4d868`, result PASS 3/3). They are kept exactly as they were committed then, so they can be
compared with the hashes and dates of that commit; do not edit them.

- `PREREGISTRATION.md`: the pass bar, written before any generation on the sealed split.
- `build_sealed.py`, `score_v3.py`, `eval/sep_full.py`: the scripts that built and scored it.
  They need the SEP harness of the project they were written against and are not maintained;
  `eval/sep_splits.py` rebuilds the same sealed split (it checks its SHA-256,
  `f2a8adbe...0fc8`) without it.
- `results_freeze.sha256`: as found (see the integrity note in CHANGELOG.md).
- `results/`: v3.0's SEP, AgentDojo, BIPIA and agent-suite results, as cited in the README.
