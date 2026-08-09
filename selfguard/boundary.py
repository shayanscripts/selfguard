"""Deny-by-default authorization boundary for LLM-proposed tool actions.

SELFGuard is a risk sensor in this design.  It can deny or escalate an action,
but a low detector score never grants permission.  Authorization comes from
trusted application scopes, explicit tool policy, argument validation, and
verified human approval where required.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Callable, Dict, FrozenSet, Mapping, Optional, Sequence


def _freeze_json(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


class RiskLevel(str, Enum):
    READ_ONLY = "read_only"
    WRITE = "write"
    DESTRUCTIVE = "destructive"


@dataclass(frozen=True)
class ActionRequest:
    """Trusted application context plus an LLM-proposed action.

    ``granted_scopes`` and approval tokens must come from trusted application
    state, never from model-generated text or tool arguments.
    """

    action_id: str
    principal_id: str
    tool_name: str
    arguments: Mapping[str, Any]
    granted_scopes: FrozenSet[str] = field(default_factory=frozenset)
    detector_flagged: Optional[bool] = None
    detector_score: Optional[float] = None
    _canonical_arguments: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        for name, value in (
            ("action_id", self.action_id),
            ("principal_id", self.principal_id),
            ("tool_name", self.tool_name),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.arguments, Mapping):
            raise TypeError("arguments must be a mapping")
        if not isinstance(self.granted_scopes, frozenset):
            object.__setattr__(self, "granted_scopes", frozenset(self.granted_scopes))
        if any(not isinstance(scope, str) or not scope.strip() for scope in self.granted_scopes):
            raise ValueError("granted_scopes must contain non-empty strings")
        if self.detector_flagged is not None and not isinstance(self.detector_flagged, bool):
            raise TypeError("detector_flagged must be bool or None")
        if self.detector_score is not None:
            score = float(self.detector_score)
            if not math.isfinite(score) or not 0.0 <= score <= 1.0:
                raise ValueError("detector_score must be finite and between 0 and 1")
            object.__setattr__(self, "detector_score", score)
        try:
            canonical_arguments = json.dumps(
                dict(self.arguments),
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("arguments must be strict JSON-serializable data") from exc
        copied_arguments = json.loads(canonical_arguments)
        object.__setattr__(self, "arguments", _freeze_json(copied_arguments))
        object.__setattr__(self, "_canonical_arguments", canonical_arguments)

    def arguments_copy(self) -> Dict[str, Any]:
        """Return a fresh mutable JSON copy for a validator or tool handler."""

        return json.loads(self._canonical_arguments)

    @property
    def digest(self) -> str:
        """Hash the exact principal, tool, and parameters for approval binding."""

        canonical = json.dumps(
            {
                "action_id": self.action_id,
                "principal_id": self.principal_id,
                "tool_name": self.tool_name,
                "arguments": json.loads(self._canonical_arguments),
            },
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()


ArgumentValidator = Callable[[Mapping[str, Any]], bool]
ToolHandler = Callable[..., Any]
ApprovalVerifier = Callable[[ActionRequest, str], bool]


@dataclass(frozen=True)
class ToolPolicy:
    """Policy registered by trusted application code for exactly one tool."""

    tool_name: str
    required_scopes: FrozenSet[str] = field(default_factory=frozenset)
    risk_level: RiskLevel = RiskLevel.READ_ONLY
    require_human_approval: bool = False
    require_detector: bool = True
    deny_at_or_above_score: Optional[float] = None
    allowed_argument_names: FrozenSet[str] = field(default_factory=frozenset)
    argument_validator: Optional[ArgumentValidator] = None

    def __post_init__(self) -> None:
        if not isinstance(self.tool_name, str) or not self.tool_name.strip():
            raise ValueError("tool_name must be a non-empty string")
        if not isinstance(self.risk_level, RiskLevel):
            object.__setattr__(self, "risk_level", RiskLevel(self.risk_level))
        if not isinstance(self.required_scopes, frozenset):
            object.__setattr__(self, "required_scopes", frozenset(self.required_scopes))
        if any(
            not isinstance(scope, str) or not scope.strip()
            for scope in self.required_scopes
        ):
            raise ValueError("required_scopes must contain non-empty strings")
        if not isinstance(self.allowed_argument_names, frozenset):
            object.__setattr__(
                self, "allowed_argument_names", frozenset(self.allowed_argument_names)
            )
        if any(
            not isinstance(name, str) or not name.strip()
            for name in self.allowed_argument_names
        ):
            raise ValueError("allowed_argument_names must contain non-empty strings")
        if self.allowed_argument_names and self.argument_validator is None:
            raise ValueError(
                "argument_validator is required when a tool accepts arguments"
            )
        if self.argument_validator is not None and not callable(self.argument_validator):
            raise TypeError("argument_validator must be callable")
        if self.deny_at_or_above_score is not None:
            threshold = float(self.deny_at_or_above_score)
            if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
                raise ValueError("deny_at_or_above_score must be between 0 and 1")
            object.__setattr__(self, "deny_at_or_above_score", threshold)

    @property
    def approval_required(self) -> bool:
        return self.require_human_approval or self.risk_level in {
            RiskLevel.WRITE,
            RiskLevel.DESTRUCTIVE,
        }


@dataclass(frozen=True)
class AuthorizationDecision:
    decision_id: str
    action_id: str
    request_digest: str
    decision: Decision
    reason_code: str
    missing_scopes: FrozenSet[str] = field(default_factory=frozenset)

    @property
    def allowed(self) -> bool:
        return self.decision is Decision.ALLOW


@dataclass(frozen=True)
class AuditEvent:
    timestamp: float
    decision_id: str
    action_id: str
    request_digest: str
    principal_id: str
    tool_name: str
    argument_names: tuple[str, ...]
    decision: str
    reason_code: str
    detector_flagged: Optional[bool]
    detector_score: Optional[float]


AuditSink = Callable[[AuditEvent], None]


class AuthorizationError(PermissionError):
    """Raised when an action reaches execution without an allow decision."""

    def __init__(self, decision: AuthorizationDecision):
        super().__init__(
            f"Action {decision.action_id!r} was not authorized: {decision.reason_code}"
        )
        self.decision = decision


class ActionBoundary:
    """Authorize and execute registered tool handlers under fail-closed policy."""

    def __init__(
        self,
        *,
        approval_verifier: Optional[ApprovalVerifier] = None,
        audit_sink: Optional[AuditSink] = None,
        fail_closed_on_audit_error: bool = True,
    ) -> None:
        self._approval_verifier = approval_verifier
        self._audit_sink = audit_sink
        self._fail_closed_on_audit_error = fail_closed_on_audit_error
        self._policies: Dict[str, ToolPolicy] = {}
        self._handlers: Dict[str, ToolHandler] = {}

    def register_tool(self, policy: ToolPolicy, handler: ToolHandler) -> None:
        """Register a policy and handler from trusted startup code."""

        if not callable(handler):
            raise TypeError("handler must be callable")
        if policy.tool_name in self._policies:
            raise ValueError(f"Tool already registered: {policy.tool_name}")
        self._policies[policy.tool_name] = policy
        self._handlers[policy.tool_name] = handler

    def _decision(
        self,
        request: ActionRequest,
        decision: Decision,
        reason_code: str,
        missing_scopes: Sequence[str] = (),
    ) -> AuthorizationDecision:
        return AuthorizationDecision(
            decision_id=str(uuid.uuid4()),
            action_id=request.action_id,
            request_digest=request.digest,
            decision=decision,
            reason_code=reason_code,
            missing_scopes=frozenset(missing_scopes),
        )

    def _emit(self, request: ActionRequest, decision: AuthorizationDecision) -> bool:
        if self._audit_sink is None:
            return True
        event = AuditEvent(
            timestamp=time.time(),
            decision_id=decision.decision_id,
            action_id=request.action_id,
            request_digest=decision.request_digest,
            principal_id=request.principal_id,
            tool_name=request.tool_name,
            argument_names=tuple(sorted(request.arguments)),
            decision=decision.decision.value,
            reason_code=decision.reason_code,
            detector_flagged=request.detector_flagged,
            detector_score=request.detector_score,
        )
        try:
            self._audit_sink(event)
            return True
        except Exception:
            if self._fail_closed_on_audit_error:
                return False
            return True

    def authorize(
        self,
        request: ActionRequest,
        *,
        approval_token: Optional[str] = None,
    ) -> AuthorizationDecision:
        """Return an auditable decision without executing the action."""

        policy = self._policies.get(request.tool_name)
        if policy is None:
            decision = self._decision(request, Decision.DENY, "tool_not_registered")
        elif not set(request.arguments).issubset(policy.allowed_argument_names):
            decision = self._decision(request, Decision.DENY, "argument_not_allowed")
        else:
            missing_scopes = policy.required_scopes - request.granted_scopes
            if missing_scopes:
                decision = self._decision(
                    request, Decision.DENY, "missing_scope", sorted(missing_scopes)
                )
            elif policy.require_detector and (
                request.detector_flagged is None or request.detector_score is None
            ):
                decision = self._decision(request, Decision.DENY, "detector_result_missing")
            elif request.detector_flagged:
                decision = self._decision(request, Decision.DENY, "detector_flagged")
            elif (
                policy.deny_at_or_above_score is not None
                and request.detector_score is not None
                and request.detector_score >= policy.deny_at_or_above_score
            ):
                decision = self._decision(request, Decision.DENY, "detector_score_too_high")
            elif policy.argument_validator is not None:
                try:
                    valid_arguments = bool(
                        policy.argument_validator(request.arguments_copy())
                    )
                except Exception:
                    valid_arguments = False
                if not valid_arguments:
                    decision = self._decision(request, Decision.DENY, "argument_validation_failed")
                else:
                    decision = self._approval_decision(request, policy, approval_token)
            else:
                decision = self._approval_decision(request, policy, approval_token)

        if not self._emit(request, decision):
            return self._decision(request, Decision.DENY, "audit_unavailable")
        return decision

    def _approval_decision(
        self,
        request: ActionRequest,
        policy: ToolPolicy,
        approval_token: Optional[str],
    ) -> AuthorizationDecision:
        if not policy.approval_required:
            return self._decision(request, Decision.ALLOW, "policy_satisfied")
        if approval_token is None:
            return self._decision(request, Decision.REQUIRE_APPROVAL, "approval_required")
        if self._approval_verifier is None:
            return self._decision(request, Decision.DENY, "approval_verifier_unavailable")
        try:
            approved = bool(self._approval_verifier(request, approval_token))
        except Exception:
            approved = False
        return self._decision(
            request,
            Decision.ALLOW if approved else Decision.DENY,
            "approval_verified" if approved else "approval_invalid",
        )

    def execute(
        self,
        request: ActionRequest,
        *,
        approval_token: Optional[str] = None,
    ) -> Any:
        """Authorize immediately before calling the registered handler."""

        decision = self.authorize(request, approval_token=approval_token)
        if not decision.allowed:
            raise AuthorizationError(decision)
        handler = self._handlers[request.tool_name]
        return handler(**request.arguments_copy())
