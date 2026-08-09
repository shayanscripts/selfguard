"""Provider-independent pre-generation prompt-injection plugin.

The plugin is a risk veto and review control.  An ``allow`` decision is never
authorization for tool use; route every model-proposed action through a
separate trusted boundary such as :class:`selfguard.boundary.ActionBoundary`.
"""

from __future__ import annotations

import functools
import hashlib
import io
import json
import math
import time
import uuid
import zipfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence, Union


class PromptAction(str, Enum):
    ALLOW = "allow"
    REVIEW = "review"
    BLOCK = "block"


@dataclass(frozen=True)
class PromptDecision:
    decision_id: str
    action: PromptAction
    score: Optional[float]
    reason_code: str
    reasons: tuple[str, ...]
    prompt_sha256: str
    prompt_length: int
    latency_ms: float

    @property
    def allowed(self) -> bool:
        return self.action is PromptAction.ALLOW


@dataclass(frozen=True)
class PromptAuditEvent:
    timestamp: float
    decision_id: str
    action: str
    score: Optional[float]
    reason_code: str
    prompt_sha256: str
    prompt_length: int


class PromptBlockedError(PermissionError):
    def __init__(self, decision: PromptDecision):
        super().__init__(f"Prompt blocked: {decision.reason_code}")
        self.decision = decision


class PromptReviewRequired(PermissionError):
    def __init__(self, decision: PromptDecision):
        super().__init__(f"Prompt requires review: {decision.reason_code}")
        self.decision = decision


class SupportsPromptScore(Protocol):
    def score(self, prompt: str) -> float: ...


Scorer = Union[Callable[[str], Any], SupportsPromptScore]
AuditSink = Callable[[PromptAuditEvent], None]
PromptExtractor = Callable[[Sequence[Any], Mapping[str, Any]], str]


class PromptInjectionPlugin:
    """Wrap an arbitrary LLM callable with fail-closed prompt inspection."""

    def __init__(
        self,
        scorer: Scorer,
        *,
        block_threshold: float,
        review_threshold: Optional[float] = None,
        audit_sink: Optional[AuditSink] = None,
        fail_closed: bool = True,
        fail_closed_on_audit_error: bool = True,
    ) -> None:
        if not any(
            callable(candidate)
            for candidate in (scorer, getattr(scorer, "score", None), getattr(scorer, "detect", None))
        ):
            raise TypeError("scorer must be callable or provide score/detect(prompt)")
        block = self._threshold(block_threshold, "block_threshold")
        review = block if review_threshold is None else self._threshold(
            review_threshold, "review_threshold"
        )
        if review > block:
            raise ValueError("review_threshold must be <= block_threshold")
        if audit_sink is not None and not callable(audit_sink):
            raise TypeError("audit_sink must be callable")
        self.scorer = scorer
        self.block_threshold = block
        self.review_threshold = review
        self.audit_sink = audit_sink
        self.fail_closed = bool(fail_closed)
        self.fail_closed_on_audit_error = bool(fail_closed_on_audit_error)

    @staticmethod
    def _threshold(value: float, name: str) -> float:
        threshold = float(value)
        if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
            raise ValueError(f"{name} must be finite and between 0 and 1")
        return threshold

    @staticmethod
    def _prompt(prompt: str) -> str:
        if not isinstance(prompt, str):
            raise TypeError("prompt must be a string")
        if not prompt.strip():
            raise ValueError("prompt must not be empty")
        return prompt

    def _score(self, prompt: str) -> tuple[float, tuple[str, ...]]:
        scorer_method = getattr(self.scorer, "score", None)
        detector_method = getattr(self.scorer, "detect", None)
        if callable(scorer_method):
            result = scorer_method(prompt)
        elif callable(detector_method):
            result = detector_method(prompt)
        else:
            result = self.scorer(prompt)  # type: ignore[misc]
        reasons = tuple(str(item) for item in getattr(result, "reasons", ()))
        score = getattr(result, "score", result)
        score = float(score)
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise ValueError("scorer returned a non-finite score outside [0, 1]")
        return score, reasons

    def inspect(self, prompt: str) -> PromptDecision:
        prompt = self._prompt(prompt)
        started = time.perf_counter()
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        try:
            score, reasons = self._score(prompt)
            if score >= self.block_threshold:
                action, reason_code = PromptAction.BLOCK, "score_at_or_above_block"
            elif score >= self.review_threshold:
                action, reason_code = PromptAction.REVIEW, "score_at_or_above_review"
            else:
                action, reason_code = PromptAction.ALLOW, "score_below_review"
        except Exception:
            if not self.fail_closed:
                raise
            score, reasons = None, ("detector failure",)
            action, reason_code = PromptAction.BLOCK, "detector_error_fail_closed"
        decision = PromptDecision(
            decision_id=str(uuid.uuid4()),
            action=action,
            score=score,
            reason_code=reason_code,
            reasons=reasons,
            prompt_sha256=digest,
            prompt_length=len(prompt),
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )
        if self.audit_sink is not None:
            event = PromptAuditEvent(
                timestamp=time.time(),
                decision_id=decision.decision_id,
                action=decision.action.value,
                score=decision.score,
                reason_code=decision.reason_code,
                prompt_sha256=digest,
                prompt_length=len(prompt),
            )
            try:
                self.audit_sink(event)
            except Exception:
                if self.fail_closed_on_audit_error:
                    return PromptDecision(
                        decision_id=decision.decision_id,
                        action=PromptAction.BLOCK,
                        score=decision.score,
                        reason_code="audit_error_fail_closed",
                        reasons=decision.reasons,
                        prompt_sha256=digest,
                        prompt_length=len(prompt),
                        latency_ms=decision.latency_ms,
                    )
        return decision

    def invoke(self, prompt: str, llm: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Inspect ``prompt`` before invoking an LLM callable."""

        if not callable(llm):
            raise TypeError("llm must be callable")
        decision = self.inspect(prompt)
        if decision.action is PromptAction.BLOCK:
            raise PromptBlockedError(decision)
        if decision.action is PromptAction.REVIEW:
            raise PromptReviewRequired(decision)
        return llm(prompt, *args, **kwargs)

    @staticmethod
    def default_prompt_extractor(args: Sequence[Any], kwargs: Mapping[str, Any]) -> str:
        if "prompt" in kwargs:
            return kwargs["prompt"]
        if args:
            return args[0]
        raise TypeError("wrapped call must provide a prompt positional argument or keyword")

    def wrap(
        self,
        llm: Callable[..., Any],
        *,
        prompt_extractor: Optional[PromptExtractor] = None,
    ) -> Callable[..., Any]:
        """Return an LLM callable that inspects before performing any model call."""

        if not callable(llm):
            raise TypeError("llm must be callable")
        extractor = prompt_extractor or self.default_prompt_extractor

        @functools.wraps(llm)
        def guarded(*args: Any, **kwargs: Any) -> Any:
            prompt = extractor(args, kwargs)
            decision = self.inspect(prompt)
            if decision.action is PromptAction.BLOCK:
                raise PromptBlockedError(decision)
            if decision.action is PromptAction.REVIEW:
                raise PromptReviewRequired(decision)
            return llm(*args, **kwargs)

        return guarded

    @classmethod
    def from_bundle(
        cls,
        path: Union[str, Path],
        *,
        expected_sha256: Optional[str] = None,
        audit_sink: Optional[AuditSink] = None,
        fail_closed: bool = True,
    ) -> "PromptInjectionPlugin":
        """Construct a plug-in from a hash-verified SELFGuard model bundle."""

        scorer, metadata = SkopsPromptScorer.from_bundle(
            path, expected_sha256=expected_sha256
        )
        return cls(
            scorer,
            block_threshold=metadata["block_threshold"],
            review_threshold=metadata.get("review_threshold"),
            audit_sink=audit_sink,
            fail_closed=fail_closed,
        )


class SkopsPromptScorer:
    """Load a hash-verified sklearn prompt model from a SELFGuard bundle.

    The optional ``skops`` dependency is used instead of pickle/joblib.  Only
    sklearn, numpy, and scipy types listed by the bundle and discovered by
    skops are trusted.
    """

    _ALLOWED_TYPE_PREFIXES = ("sklearn.", "numpy.", "scipy.")
    _MEMBERS = frozenset({"model.skops", "metadata.json", "sha256.json"})

    def __init__(self, model: Any, *, positive_class_index: int = 1) -> None:
        if not callable(getattr(model, "predict_proba", None)):
            raise TypeError("model must provide predict_proba")
        self.model = model
        self.positive_class_index = int(positive_class_index)

    def score(self, prompt: str) -> float:
        prompt = PromptInjectionPlugin._prompt(prompt)
        probabilities = self.model.predict_proba([prompt])
        return float(probabilities[0][self.positive_class_index])

    @classmethod
    def from_bundle(
        cls,
        path: Union[str, Path],
        *,
        expected_sha256: Optional[str] = None,
    ) -> tuple["SkopsPromptScorer", Mapping[str, Any]]:
        bundle = Path(path).read_bytes()
        digest = hashlib.sha256(bundle).hexdigest()
        if expected_sha256 is not None and digest != expected_sha256.casefold():
            raise ValueError("bundle SHA-256 mismatch")
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or set(names) != cls._MEMBERS:
                raise ValueError("bundle must contain exactly the expected flat members")
            manifest = json.loads(archive.read("sha256.json"))
            metadata = json.loads(archive.read("metadata.json"))
            if metadata.get("schema_version") != 1:
                raise ValueError("unsupported plugin model schema")
            expected_members = {"model.skops", "metadata.json"}
            hashes = manifest.get("sha256")
            if not isinstance(hashes, dict) or set(hashes) != expected_members:
                raise ValueError("invalid bundle hash coverage")
            for name in expected_members:
                if hashlib.sha256(archive.read(name)).hexdigest() != hashes[name]:
                    raise ValueError(f"bundle member hash mismatch: {name}")
            model_bytes = archive.read("model.skops")
        try:
            import skops.io as skops_io
        except ImportError as exc:
            raise RuntimeError(
                "Install SELFGuard with the 'plugin' extra to load model bundles"
            ) from exc
        unknown = set(skops_io.get_untrusted_types(data=model_bytes))
        declared = set(metadata.get("trusted_types", []))
        if unknown != declared:
            raise ValueError("bundle trusted-type declaration mismatch")
        if any(not item.startswith(cls._ALLOWED_TYPE_PREFIXES) for item in unknown):
            raise ValueError("bundle requests a type outside the safe allowlist")
        model = skops_io.loads(model_bytes, trusted=sorted(unknown))
        scorer = cls(model, positive_class_index=metadata.get("positive_class_index", 1))
        return scorer, metadata
