"""Re-score our agent suite's saved replies with the perimeter approver (no regeneration)."""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "eval"))
from agent_suite import ATTACKS, SYSTEM, cases, harm  # noqa: E402
from selfguard3 import SelfGuard  # noqa: E402
from selfguard3.approver import PerimeterApprover  # noqa: E402

rows = json.load(open(os.path.join(HERE, "results", "agent_suite.json"), encoding="utf-8"))
pa = PerimeterApprover(os.environ.get("AD_APPROVER", "qwen2.5:3b-instruct"))
g = SelfGuard(trace_backend="lexical")
res = []
for row, (kind, task, data) in zip(rows, cases()):
    g.approver = lambda n, a, v, t=task, d=data: pa(t, n, a, v, d)
    o = g.inspect(row["ww_reply"], task=task, data=[data], system=SYSTEM)
    allowed = [a for _, a, v in o.actions if v.decision == "allow"]
    res.append({"kind": kind, "harm": harm(kind, o.text if o.safe else "", row["ww_reply"], allowed),
                "acts": [(a.get("to"), v.decision) for _, a, v in o.actions]})
total_actions = sum(len(r["acts"]) for r in res)
print(f"approver consulted {pa.calls} times out of {total_actions} actions in {len(res)} cases")
print("| case | n | harm: SG3 + approver |\n|---|---:|---:|")
for k in ["clean", *ATTACKS, "legit_trusted", "legit_from_doc"]:
    rs = [r for r in res if r["kind"] == k]
    h = f"{sum(1 for r in rs if r['harm'])}/{len(rs)}" if rs[0]["harm"] is not None else "-"
    print(f"| {k} | {len(rs)} | {h} |")
for k in ("exfil_action", "legit_trusted", "legit_from_doc"):
    print(k, [r["acts"] for r in res if r["kind"] == k])
json.dump(res, open(os.path.join(HERE, "results", "agent_suite_approver.json"), "w"), indent=1)
