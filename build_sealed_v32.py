"""Carve a fresh sealed SEP split for SelfGuard v3.2 (canary).

Same pool and stratification as build_sealed.py (SEP test probes x test subtasks of
Watchword's seeded partition), minus every row already used: Watchword's dev and sealed test,
and v3's sealed split (data/sealed_v3.jsonl; rebuild it first with build_sealed.py if it is
missing, it is deterministic). Prints counts and hashes only, never row text. Refuses to
overwrite.

  python build_sealed_v32.py            # needs SEP_ZIP and a Watchword checkout (WATCHWORD_PATH)
  python build_sealed_v32.py --dry-run  # counts only, writes nothing
"""
import json
import os
import random
import sys
import zipfile

WW = os.environ.get("WATCHWORD_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "watchword"))
sys.path.insert(0, WW)
from eval.split_sep import ARCHIVE_SHA256, DEFAULT_SEED, MEMBER, _sample, convert, partition, sha256_file  # noqa: E402

ZIP = os.environ.get("SEP_ZIP", "Should-It-Be-Executed-Or-Processed-main.zip")
HERE = os.path.dirname(os.path.abspath(__file__))
V3 = os.path.join(HERE, "data", "sealed_v3.jsonl")
OUT = os.path.join(HERE, "data", "sealed_v32.jsonl")
SEED = 20261122
N = 600
dry = "--dry-run" in sys.argv

if os.path.exists(OUT) and not dry:
    sys.exit("refusing to overwrite " + OUT)
if not os.path.exists(V3):
    sys.exit(f"{V3} missing: run build_sealed.py first (deterministic), so its rows can be excluded")
assert sha256_file(ZIP) == ARCHIVE_SHA256, "SEP archive hash mismatch"
with zipfile.ZipFile(ZIP) as z:
    rows = json.loads(z.read(MEMBER).decode("utf-8"))

used = set()
for path in (os.path.join(WW, "data", "sep", "dev.jsonl"), os.path.join(WW, "data", "sep", "test_sealed.jsonl"), V3):
    with open(path, encoding="utf-8") as f:
        used |= {json.loads(l)["id"] for l in f if l.strip()}

_, test_p, _, test_s = partition(rows, DEFAULT_SEED)
pool = [convert(r) for r in rows if r["info"]["appended_task_id"] in test_p and r["info"]["subtask"] in test_s]
fresh = [r for r in pool if r["id"] not in used]
strata = {}
for r in fresh:
    strata[(r["position"], r["insistent"])] = strata.get((r["position"], r["insistent"]), 0) + 1
print(f"test pool {len(pool)}, already used {len(pool) - len(fresh)}, fresh {len(fresh)}")
print("fresh rows per stratum (position, insistent):", dict(sorted(strata.items(), key=str)))
if dry:
    sys.exit(0)
sealed = _sample(fresh, N, random.Random(SEED), "sealed_v32")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    for r in sealed:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
os.chmod(OUT, 0o444)
print(f"sealed {len(sealed)}; overlap with used rows: {len({r['id'] for r in sealed} & used)}")
print("sealed_v32.jsonl SHA-256:", sha256_file(OUT))
