"""SelfGuard v3: layered prompt-injection protection around any LLM.

  layout  - Watchword displaced layout (data in a low-authority turn)
  M1-M4   - values, action locks + cashier, reply tripwire, support trace
No training of anything, no model internals, no extra LLM call, no added prompt text.
"""
import json
import os
import re
import sys
from dataclasses import dataclass, field

from .actions import ActionLock, Verdict
from .reply import Tripwire
from .trace import SupportTrace
from .values import TrustSet, deobfuscate, values

WW = os.environ.get("WATCHWORD_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "watchword"))
if WW not in sys.path:
    sys.path.insert(0, WW)

ACTION_RE = re.compile(r"ACTION\s+(\w+)\s+(\{.*?\})", re.S)


@dataclass
class Outcome:
    text: str
    raw: str
    actions: list = field(default_factory=list)   # [(name, args, Verdict)]
    findings: list = field(default_factory=list)
    safe: bool = True


def parse_actions(reply: str):
    for ch in "_{}<>[]*":  # undo markdown escapes (send\_email, \{)
        reply = reply.replace("\\" + ch, ch)
    out = []
    for m in ACTION_RE.finditer(reply):
        try:
            out.append((m.group(1), json.loads(m.group(2))))
        except Exception:
            to = re.search(r'"to"\s*:\s*"([^"]+)"', m.group(2))
            out.append((m.group(1), {"to": to.group(1).strip("<> ")} if to else {"raw": m.group(2)}))
    return out


class SelfGuard:
    def __init__(self, *, layout="displaced", trace_backend="lexical", allow_domains=(), approver=None,
                 obedience=True, obedience_threshold=0.8):
        self.layout = layout
        self.trace = SupportTrace(trace_backend)
        self.allow_domains = allow_domains
        self.approver = approver
        self.obedience = obedience
        self.th = obedience_threshold

    def messages(self, task, data, system=None):
        from watchword.layout import build
        return build(task, list(data), system, self.layout)

    def inspect(self, reply, *, task, data=(), system=None) -> Outcome:
        data_s = "\n\n".join(data)
        trust = TrustSet(system or "", task, allow_domains=self.allow_domains)
        out = Outcome(text=reply, raw=reply)
        lock = ActionLock(trust, self.approver)
        for name, args in parse_actions(reply):
            out.actions.append((name, args, lock.decide(name, args)))
        text, inj = self.trace.clean(reply, data_s)
        out.findings += [("injected_claim", r) for _, r in inj]
        tw = Tripwire(trust).clean(text, data_s)
        out.text, out.safe = tw.text, tw.safe
        out.findings += tw.findings
        if self.obedience:
            from watchword import Watchword
            ww = Watchword(layout=self.layout, obedience_threshold=self.th)
            r = ww.inspect(reply, task=task, data=list(data), system=system)
            if not r.allowed:
                out.safe = False
                out.findings.append(("obedience", getattr(r, "score", None)))
        return out

    def run(self, llm, *, task, data=(), system=None, **params) -> Outcome:
        reply = llm(self.messages(task, data, system), **params)
        return self.inspect(reply, task=task, data=data, system=system)
