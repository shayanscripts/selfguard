"""Auditable pre-generation prompt-risk signals.

These signals are intentionally transparent and model-agnostic.  They are
risk features, not authorization: quoted security text and legitimate role
instructions can activate them.  Use them as an input to a validated detector
or as a veto/escalation signal inside the deny-by-default action boundary.
"""

from __future__ import annotations

import math
import re
import time
import uuid
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional, Tuple

import numpy as np


_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
_OVERRIDE_RE = re.compile(
    r"\b(?:ignore|forget|disregard|override|bypass|supersede)\b.{0,48}"
    r"\b(?:previous|prior|above|system|developer|instruction|rule|policy|prompt)s?\b",
    re.IGNORECASE | re.DOTALL,
)
_ROLE_RE = re.compile(
    r"\b(?:act|behave|pretend|role\s*play)\s+(?:as|like)\b|"
    r"\byou\s+are\s+now\b|\bnew\s+(?:role|persona|task)\b",
    re.IGNORECASE,
)
_EXFILTRATION_RE = re.compile(
    r"\b(?:reveal|show|print|repeat|return|dump|expose|leak)\b.{0,48}"
    r"\b(?:system|developer|hidden|secret|credential|password|token|prompt|instruction|policy)s?\b",
    re.IGNORECASE | re.DOTALL,
)
_TOOL_RE = re.compile(
    r"\b(?:execute|run|call|invoke|open|download|upload|delete|remove|send|transfer|purchase)\b.{0,32}"
    r"\b(?:code|command|shell|terminal|tool|function|file|url|email|message|money|payment)\b",
    re.IGNORECASE,
)
_IMPERATIVE_RE = re.compile(
    r"\b(?:must|shall|immediately|instead|only|never|always|stop|begin|follow)\b",
    re.IGNORECASE,
)
_DELIMITER_RE = re.compile(r"(?:```|<\/?[A-Za-z][^>]{0,80}>|\[/?(?:system|assistant|user)\]|={3,}|-{3,})")


@dataclass(frozen=True)
class PromptRiskResult:
    """One pre-generation prompt-risk assessment."""

    id: str
    flagged: bool
    score: float
    signals: Mapping[str, float]
    reasons: Tuple[str, ...]
    latency_ms: float


class PromptRiskDetector:
    """Compute transparent lexical and optional semantic prompt-risk signals."""

    def __init__(
        self,
        system_prompt: str,
        *,
        threshold: float = 0.8,
        embedder: Optional[Any] = None,
    ) -> None:
        if not isinstance(system_prompt, str) or not system_prompt.strip():
            raise ValueError("system_prompt must be a non-empty string")
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be between 0 and 1")
        self.threshold = float(threshold)
        self.embedder = embedder
        self._system_words = self._words(system_prompt)
        self._system_embedding = None
        if embedder is not None:
            self._system_embedding = np.asarray(
                embedder.encode(system_prompt, convert_to_numpy=True), dtype=float
            )

    @staticmethod
    def _words(text: str) -> set[str]:
        return {word.casefold() for word in _WORD_RE.findall(text) if len(word) > 2}

    @staticmethod
    def _cosine(a: np.ndarray, b: np.ndarray) -> float:
        denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
        return float(np.dot(a, b) / denominator) if denominator else 0.0

    def compute_signals(self, prompt: str) -> Dict[str, float]:
        """Return stable numeric features without making an allow decision."""

        if not isinstance(prompt, str):
            raise TypeError("prompt must be a string")
        words = [word.casefold() for word in _WORD_RE.findall(prompt)]
        word_count = max(1, len(words))
        prompt_words = {word for word in words if len(word) > 2}
        overlap = (
            len(prompt_words & self._system_words) / len(prompt_words)
            if prompt_words
            else 0.0
        )
        alignment = math.nan
        if self.embedder is not None and self._system_embedding is not None and prompt.strip():
            embedding = np.asarray(
                self.embedder.encode(prompt, convert_to_numpy=True), dtype=float
            )
            alignment = self._cosine(embedding, self._system_embedding)
        return {
            "prompt_override_markers": float(len(_OVERRIDE_RE.findall(prompt))),
            "prompt_role_markers": float(len(_ROLE_RE.findall(prompt))),
            "prompt_exfiltration_markers": float(len(_EXFILTRATION_RE.findall(prompt))),
            "prompt_tool_markers": float(len(_TOOL_RE.findall(prompt))),
            "prompt_imperative_density": float(len(_IMPERATIVE_RE.findall(prompt)) / word_count),
            "prompt_delimiter_density": float(len(_DELIMITER_RE.findall(prompt)) / word_count),
            "prompt_system_overlap": float(overlap),
            "prompt_system_alignment": float(alignment),
            "prompt_log_length": float(math.log1p(len(prompt))),
        }

    def detect(self, prompt: str) -> PromptRiskResult:
        """Apply a conservative heuristic score to the transparent signals."""

        started = time.perf_counter()
        signals = self.compute_signals(prompt)
        alignment = signals["prompt_system_alignment"]
        semantic_risk = 0.0 if not math.isfinite(alignment) else float(
            np.clip((0.35 - alignment) / 0.70, 0.0, 1.0)
        )
        raw = (
            0.34 * min(1.0, signals["prompt_override_markers"])
            + 0.24 * min(1.0, signals["prompt_exfiltration_markers"])
            + 0.14 * min(1.0, signals["prompt_role_markers"])
            + 0.10 * min(1.0, signals["prompt_tool_markers"])
            + 0.08 * min(1.0, signals["prompt_imperative_density"] * 8.0)
            + 0.05 * min(1.0, signals["prompt_delimiter_density"] * 12.0)
            + 0.05 * semantic_risk
        )
        score = float(np.clip(raw, 0.0, 1.0))
        reasons = []
        for key, label in (
            ("prompt_override_markers", "instruction override language"),
            ("prompt_exfiltration_markers", "prompt or secret exfiltration language"),
            ("prompt_role_markers", "role-change language"),
            ("prompt_tool_markers", "tool or action language"),
        ):
            if signals[key] > 0:
                reasons.append(label)
        return PromptRiskResult(
            id=str(uuid.uuid4()),
            flagged=score >= self.threshold,
            score=score,
            signals=MappingProxyType(dict(signals)),
            reasons=tuple(reasons),
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )
