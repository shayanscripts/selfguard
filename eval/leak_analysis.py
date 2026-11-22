"""Where do attacks leak through SelfGuard? Dev data only; prints counts, never row text.

  python eval/leak_analysis.py --rows data/sep/dev.jsonl \
      --cache results/cache/sep_dev_mistral_7b-instruct.jsonl --arm v3.4

For every row with both a no-defence and a guarded reply on the attack condition (witness
matched as a whole word):
  obeyed_none  the undefended model's reply contains the witness
  obeyed       the guarded model's reply contains the witness (layout did not prevent it)
  caught       obeyed, and the arm withheld it (which check)
  removed      obeyed, and a sentence filter (support trace, echo strip) removed the witness
  leaked       obeyed, and the arm let it through (attack success)
Leaks and catches are broken down by SEP metadata (position, insistent, subtask, probe id),
the engine's obedience score, and simple witness features (numeric, already in the clean data or
the task, where in the reply it appears). Refuses the sealed files.
"""
import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "eval")]
from sep_eval import inputs_for, load_cache, witness_whole_word as witness_hit  # noqa: E402
from selfguard3 import SelfGuard  # noqa: E402
from selfguard3.checks import route  # noqa: E402

BINS = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 1.01)]


def where(reply, witness):
    i = reply.lower().find(witness.lower())
    if i < 0:
        return "absent"
    f = i / max(len(reply), 1)
    return "start" if f < 0.2 else "end" if f > 0.8 else "middle"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--arm", default="v3.4", choices=["v3.1", "v3.4"])
    ap.add_argument("--legacy-cache", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if "sealed" in os.path.basename(a.rows) or "sealed" in os.path.basename(a.cache):
        sys.exit("dev data only: this script never touches sealed files")
    rows = [json.loads(l) for l in open(a.rows, encoding="utf-8") if l.strip()]
    cache = load_cache(a.cache, a.legacy_cache)
    sg = SelfGuard(layout="displaced", echo=False) if a.arm == "v3.1" else SelfGuard()
    stats = collections.Counter()
    by = {k: collections.defaultdict(collections.Counter) for k in
          ("position", "insistent", "subtask", "probe_id", "score_bin", "witness_numeric",
           "witness_in_clean_data", "witness_in_task", "witness_place", "caught_by")}
    for r in rows:
        src = "v3.1" if a.arm == "v3.1" or route([r["data_with_probe"]]) == "displaced" else "none"
        kn, ks = (r["id"], "none", "attack"), (r["id"], src, "attack")
        if kn not in cache or ks not in cache:
            continue
        stats["rows"] += 1
        w = r["witness"]
        task, data = inputs_for(r, "attack")
        stats["obeyed_none"] += witness_hit(cache[kn]["reply"], w)
        reply = cache[ks]["reply"]
        if not witness_hit(reply, w):
            continue
        stats["obeyed"] += 1
        o = sg.inspect(reply, task=task, data=[data], canary=None)
        leaked = o.safe and witness_hit(o.text, w)
        outcome = "leaked" if leaked else "caught" if not o.safe else "removed"
        stats[outcome] += 1
        score = sg.checks(reply, task=task, data=[data]).score
        feats = {"position": r["position"], "insistent": r["insistent"], "subtask": r["subtask"],
                 "probe_id": r["probe_id"],
                 "score_bin": next(f"{lo:.1f}-{min(hi, 1):.1f}" for lo, hi in BINS if lo <= score < hi),
                 "witness_numeric": bool(re.fullmatch(r"[\d\s.,:%-]+", w)),
                 "witness_in_clean_data": w.lower() in r["data"].lower(),
                 "witness_in_task": w.lower() in r["task"].lower(),
                 "witness_place": where(reply, w),
                 "caught_by": "+".join(sorted({f[0] for f in o.findings})) or "-"}
        for k, v in feats.items():
            by[k][str(v)][outcome] += 1
    out = {"rows_file": os.path.basename(a.rows), "arm": a.arm, "stats": dict(stats),
           "breakdown": {k: {v: dict(c) for v, c in sorted(d.items(), key=lambda x: -sum(x[1].values()))}
                         for k, d in by.items()}}
    print(json.dumps(out["stats"]))
    for k, d in out["breakdown"].items():
        print(f"\n{k}:")
        for v, c in list(d.items())[:12]:
            print(f"  {v:28s} leaked {c.get('leaked', 0):3d}  caught {c.get('caught', 0):3d}  removed {c.get('removed', 0):3d}")
    path = a.out or os.path.join(HERE, "results", f"leak_analysis_{a.arm}_{os.path.splitext(os.path.basename(a.cache))[0]}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
