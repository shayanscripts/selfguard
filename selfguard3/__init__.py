"""SelfGuard v3: layered prompt-injection protection around any LLM.

  layout  - displaced / standard / routed (data in a low-authority turn)
  checks  - Watchword's obedience, provenance and leak checks (vendored, frozen)
  M1-M4   - values, action locks + cashier, reply tripwire, support trace
No training of anything, no model internals, no extra LLM call, no added prompt text.
Standard library only: Watchword's engine is vendored in ``selfguard3/_watchword``.
"""
import json
import re
from dataclasses import dataclass, field

from .actions import ActionLock, Verdict
from .checks import LAYOUTS, ReplyChecks, build_messages
from .reply import Tripwire
from .trace import SupportTrace
from .values import TrustSet, deobfuscate, values

__version__ = "3.1.0"

ACTION_RE = re.compile(r"ACTION\s+(\w+)\s+(?=\{)")
_JSON = json.JSONDecoder()


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
            args, _ = _JSON.raw_decode(reply, m.end())  # full JSON, nested objects included
            if not isinstance(args, dict):
                raise ValueError
        except ValueError:
            # Unparseable: keep everything up to the next ACTION so the lock checks every value
            # in it (fail closed), instead of guessing at one field.
            nxt = ACTION_RE.search(reply, m.end())
            args = {"raw": reply[m.end():nxt.start() if nxt else len(reply)]}
        out.append((m.group(1), args))
    return out


class SelfGuard:
    def __init__(self, *, layout="displaced", trace_backend="lexical", allow_domains=(), approver=None,
                 obedience=True, obedience_threshold=0.8):
        if layout not in LAYOUTS:
            raise ValueError(f"unknown layout {layout!r}; expected one of {LAYOUTS}")
        self.layout = layout
        self.trace = SupportTrace(trace_backend)
        self.allow_domains = allow_domains
        self.approver = approver
        self.obedience = obedience
        self.th = obedience_threshold
        self.checks = ReplyChecks(obedience_threshold) if obedience else None

    def messages(self, task, data, system=None):
        return build_messages(task, list(data), system, self.layout)

    def inspect(self, reply, *, task, data=(), system=None) -> Outcome:
        data_s = "\n\n".join(data)
        trust = TrustSet(system or "", task, allow_domains=self.allow_domains)
        out = Outcome(text=reply, raw=reply)
        lock = ActionLock(trust, self.approver, task=task)
        for name, args in parse_actions(reply):
            out.actions.append((name, args, lock.decide(name, args)))
        text, inj = self.trace.clean(reply, data_s)
        out.findings += [("injected_claim", r) for _, r in inj]
        tw = Tripwire(trust).clean(text, data_s)
        out.text, out.safe = tw.text, tw.safe
        out.findings += tw.findings
        if self.checks:
            r = self.checks(reply, task=task, data=data, system=system)
            if not r.allowed:
                out.safe = False
                out.findings += r.findings
        return out

    def run(self, llm, *, task, data=(), system=None, **params) -> Outcome:
        reply = llm(self.messages(task, data, system), **params)
        return self.inspect(reply, task=task, data=data, system=system)
