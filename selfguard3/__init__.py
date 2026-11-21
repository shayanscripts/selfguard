"""SelfGuard v3: layered prompt-injection protection around any LLM.

  layout  - displaced / standard / routed (data in a low-authority turn)
  canary  - a random-code instruction planted in the data; the reply is withheld if obeyed
  checks  - Watchword's obedience, provenance and leak checks (vendored, frozen)
  M1-M4   - values, action locks + cashier, reply tripwire, support trace
No training of anything, no model internals, no extra LLM call. The only added prompt text
is the canary's one sentence inside the data (``canary=False`` removes it).
Standard library only: Watchword's engine is vendored in ``selfguard3/_watchword``.
"""
import json
import re
from dataclasses import dataclass, field

from .actions import ActionLock, Verdict
from .canary import Canary
from .checks import LAYOUTS, ReplyChecks, build_messages, route
from .reply import Tripwire
from .trace import SupportTrace
from .values import TrustSet, deobfuscate, values

__version__ = "3.2.0.dev0"

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


@dataclass
class Prepared:
    messages: list
    canary: Canary | None = None


class SelfGuard:
    def __init__(self, *, layout="displaced", trace_backend="lexical", allow_domains=(), approver=None,
                 obedience=True, obedience_threshold=0.8, canary=True, canary_positions=("end",),
                 canary_rng=None):
        """``canary``: plant a random-code instruction in the data and withhold the reply if the
        model follows it (see selfguard3/canary.py). ``canary_rng``: random.Random for
        reproducible experiments only; the default draws codes from the secrets module."""
        if layout not in LAYOUTS:
            raise ValueError(f"unknown layout {layout!r}; expected one of {LAYOUTS}")
        self.layout = layout
        self.trace = SupportTrace(trace_backend)
        self.allow_domains = allow_domains
        self.approver = approver
        self.obedience = obedience
        self.th = obedience_threshold
        self.checks = ReplyChecks(obedience_threshold) if obedience else None
        self.canary = canary
        self.canary_positions = tuple(canary_positions)
        self.canary_rng = canary_rng
        self.last_canary = None

    def prepare(self, task, data, system=None) -> Prepared:
        """Messages for one call, plus the canary to pass to ``inspect`` for its reply."""
        data = list(data)
        mode = route(data) if self.layout == "routed" else self.layout  # route on the real data
        if not (self.canary and data):
            return Prepared(build_messages(task, data, system, mode))
        c = Canary.new(self.canary_positions, self.canary_rng)
        return Prepared(build_messages(task, c.plant(data), system, mode), c)

    def messages(self, task, data, system=None):
        """Like ``prepare(...).messages``; the canary is kept in ``last_canary`` and used by the
        next ``inspect`` that is not given one (single-threaded use; prefer ``prepare``/``run``)."""
        p = self.prepare(task, data, system)
        self.last_canary = p.canary
        return p.messages

    def inspect(self, reply, *, task, data=(), system=None, canary="last") -> Outcome:
        """Checks for a reply. ``data`` is the original data (without the canary).
        ``canary``: the Prepared.canary of this call; "last" uses ``last_canary``; None: no check."""
        if canary == "last":
            canary = self.last_canary
        data_s = "\n\n".join(data)
        trust = TrustSet(system or "", task, allow_domains=self.allow_domains)
        out = Outcome(text=reply, raw=reply)
        fired = bool(canary and canary.fired(reply))
        if fired:
            reply = canary.strip(reply)
            out.safe = False
            out.findings.append(("canary", "the model followed an instruction planted in the data"))
        lock = ActionLock(trust, self.approver, task=task)
        for name, args in parse_actions(reply):
            v = Verdict("block", [], "model followed data instructions (canary)") if fired else lock.decide(name, args)
            out.actions.append((name, args, v))
        text, inj = self.trace.clean(reply, data_s)
        out.findings += [("injected_claim", r) for _, r in inj]
        tw = Tripwire(trust).clean(text, data_s)
        out.text, out.safe = tw.text, tw.safe and not fired
        out.findings += tw.findings
        if self.checks:
            r = self.checks(reply, task=task, data=data, system=system)
            if not r.allowed:
                out.safe = False
                out.findings += r.findings
        return out

    def run(self, llm, *, task, data=(), system=None, **params) -> Outcome:
        p = self.prepare(task, data, system)
        reply = llm(p.messages, **params)
        return self.inspect(reply, task=task, data=data, system=system, canary=p.canary)
