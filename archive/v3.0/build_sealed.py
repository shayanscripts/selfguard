"""Carve a fresh sealed SEP split for SelfGuard v3 (smart routing).

Rows come from the SEP test pool (test probes x test subtasks, same seeded
partition as Watchword's split_sep.py), minus every row already in Watchword's
dev or sealed test. Stratified like the original (position x insistent).
Prints counts and hashes only, never row text. Refuses to overwrite.
"""
import hashlib
import json
import os
import random
import sys
import zipfile

WW = os.environ.get("WATCHWORD_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "watchword"))
sys.path.insert(0, WW)
from eval.split_sep import ARCHIVE_SHA256, MEMBER, DEFAULT_SEED, convert, partition, _sample, sha256_file  # noqa: E402

ZIP = os.environ.get("SEP_ZIP", "Should-It-Be-Executed-Or-Processed-main.zip")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "sealed_v3.jsonl")
SEED = 20261118
N = 600

if os.path.exists(OUT):
    sys.exit("refusing to overwrite " + OUT)
assert sha256_file(ZIP) == ARCHIVE_SHA256, "SEP archive hash mismatch"
with zipfile.ZipFile(ZIP) as z:
    rows = json.loads(z.read(MEMBER).decode("utf-8"))

used = set()
for name in ("dev.jsonl", "test_sealed.jsonl"):
    with open(os.path.join(WW, "data", "sep", name), encoding="utf-8") as f:
        used |= {json.loads(l)["id"] for l in f if l.strip()}

_, test_p, _, test_s = partition(rows, DEFAULT_SEED)
pool = [convert(r) for r in rows
        if r["info"]["appended_task_id"] in test_p and r["info"]["subtask"] in test_s]
fresh = [r for r in pool if r["id"] not in used]
sealed = _sample(fresh, N, random.Random(SEED), "sealed_v3")

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    for r in sealed:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
os.chmod(OUT, 0o444)
print(f"test pool {len(pool)}, already used {len(pool) - len(fresh)}, fresh {len(fresh)}, sealed {len(sealed)}")
print("overlap with Watchword splits:", len({r['id'] for r in sealed} & used))
print("sealed_v3.jsonl SHA-256:", sha256_file(OUT))
