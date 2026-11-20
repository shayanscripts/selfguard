"""Module 2: value locks on actions + the 'cashier' (human approval).

An action may run only if every sensitive value in its arguments comes from
trusted text. Anything else is held for a human, or refused if none is there.
Risky verbs (send, pay, delete, ...) driven by a document always ask.
"""
import re
from dataclasses import dataclass, field
from .values import TrustSet, values

# actions that are dangerous even without any outside value in them
SENSITIVE_ACTION = re.compile(r"password|passcode|credential|secret|token|2fa|permission|role|admin|update_user", re.I)

RISKY = ("send", "forward", "email", "mail", "pay", "transfer", "delete", "remove", "post", "share", "upload", "exec", "run")


@dataclass
class Verdict:
    decision: str                      # "allow" | "confirm" | "block"
    untrusted: list = field(default_factory=list)
    reason: str = ""


class ActionLock:
    def __init__(self, trust: TrustSet, approver=None):
        self.trust = trust
        self.approver = approver  # callable(name, args, verdict) -> bool, or None

    def check(self, name: str, args: dict) -> Verdict:
        found = set()
        for v in (args or {}).values():
            found |= values(str(v))
        bad = sorted(v for v in found if v not in self.trust)
        if bad:
            return Verdict("confirm", bad, "uses values not found in trusted text")
        if SENSITIVE_ACTION.search(name or ""):
            return Verdict("confirm", [], "changes credentials, access or settings")
        return Verdict("allow")

    def decide(self, name: str, args: dict) -> Verdict:
        """check() and, when a human is needed, ask the approver (no approver = block)."""
        v = self.check(name, args)
        if v.decision == "confirm":
            ok = bool(self.approver and self.approver(name, args, v))
            return Verdict("allow" if ok else "block", v.untrusted, v.reason + (" (approved)" if ok else ""))
        return v
