"""Core behavioral-signal computation for SELF Guard."""

from __future__ import annotations

import math
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

import numpy as np


_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class DetectionResult:
    """Result of one detection pass."""

    id: str
    flagged: bool
    score: float
    signal1_vocab: float
    signal2_coherence: float
    signal2_missing: bool
    signal3_alignment: float
    latency_ms: float
    response: str
    reason: Optional[str] = None


class SELFDetector:
    """Compute behavioral drift signals against a clean-response fingerprint.

    The bundled scorer is a transparent weighted z-score heuristic. It is not
    the trained Random Forest used in the research experiment.
    """

    def __init__(
        self,
        system_prompt: str,
        threshold: float = 0.8,
        embedder_model: str = "all-MiniLM-L6-v2",
        embedder_revision: Optional[str] = None,
        embedder: Optional[Any] = None,
    ):
        if not isinstance(system_prompt, str) or not system_prompt.strip():
            raise ValueError("system_prompt must be a non-empty string")
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be between 0 and 1")

        self.threshold = float(threshold)
        self.fingerprint: Optional[Dict[str, Dict[str, float]]] = None
        self.is_calibrated = False

        if embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise ImportError(
                    "Missing dependency 'sentence-transformers'. Install selfguard."
                ) from exc
            embedder = SentenceTransformer(
                embedder_model,
                revision=embedder_revision,
            )
        self.embedder = embedder

        self._system_words = self._extract_words(system_prompt)
        self._system_embedding = np.asarray(
            self.embedder.encode(system_prompt, convert_to_numpy=True), dtype=float
        )

    @staticmethod
    def _extract_words(text: str) -> Set[str]:
        return {word.casefold() for word in _WORD_RE.findall(text) if len(word) > 2}

    @staticmethod
    def _sentences(text: str) -> List[str]:
        return [part.strip() for part in _SENTENCE_RE.split(text.strip()) if part.strip()]

    @staticmethod
    def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
        denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
        if denominator == 0.0:
            return 0.0
        return float(np.dot(a, b) / denominator)

    def _signal1_vocab_overlap(self, response: str) -> float:
        words = [word.casefold() for word in _WORD_RE.findall(response) if len(word) > 2]
        if not words:
            return 0.0
        return sum(word in self._system_words for word in words) / len(words)

    def _signal2_semantic_coherence(self, response: str) -> float:
        sentences = self._sentences(response)
        if len(sentences) < 2:
            return math.nan
        embeddings = np.asarray(
            self.embedder.encode(sentences, convert_to_numpy=True), dtype=float
        )
        similarities = [
            self._cosine_sim(embeddings[index], embeddings[index + 1])
            for index in range(len(embeddings) - 1)
        ]
        return float(np.mean(similarities))

    def _signal3_system_alignment(self, response: str) -> float:
        if not response.strip():
            return 0.0
        embedding = np.asarray(
            self.embedder.encode(response, convert_to_numpy=True), dtype=float
        )
        return self._cosine_sim(embedding, self._system_embedding)

    def compute_signals(self, response: str) -> Dict[str, float]:
        if not isinstance(response, str):
            raise TypeError("response must be a string")
        return {
            "signal1_vocab": self._signal1_vocab_overlap(response),
            "signal2_coherence": self._signal2_semantic_coherence(response),
            "signal3_alignment": self._signal3_system_alignment(response),
        }

    @staticmethod
    def _summary(values: np.ndarray) -> Dict[str, float]:
        finite = values[np.isfinite(values)]
        if finite.size == 0:
            return {"mean": 0.0, "std": 1.0}
        return {"mean": float(finite.mean()), "std": float(finite.std())}

    def calibrate(self, clean_responses: List[str]) -> None:
        """Build a fingerprint from at least ten known-clean responses."""
        if len(clean_responses) < 10:
            raise ValueError(f"Need at least 10 clean responses. Got {len(clean_responses)}.")
        if any(not isinstance(item, str) or not item.strip() for item in clean_responses):
            raise ValueError("clean_responses must contain non-empty strings")

        signals = [self.compute_signals(response) for response in clean_responses]
        self.fingerprint = {
            "signal1": self._summary(np.array([s["signal1_vocab"] for s in signals])),
            "signal2": self._summary(np.array([s["signal2_coherence"] for s in signals])),
            "signal3": self._summary(np.array([s["signal3_alignment"] for s in signals])),
        }
        self.is_calibrated = True

    def detect(self, response: str) -> DetectionResult:
        """Score one generated response after calibration."""
        if not self.is_calibrated or self.fingerprint is None:
            raise RuntimeError("Detector is not calibrated. Call calibrate() first.")

        started = time.perf_counter()
        signals = self.compute_signals(response)
        s1 = signals["signal1_vocab"]
        s2 = signals["signal2_coherence"]
        s3 = signals["signal3_alignment"]
        s2_missing = not math.isfinite(s2)
        if s2_missing:
            s2 = self.fingerprint["signal2"]["mean"]

        def z_score(value: float, signal: str) -> float:
            stats = self.fingerprint[signal]
            std = stats["std"]
            return 0.0 if std < 1e-8 else (value - stats["mean"]) / std

        z1, z2, z3 = z_score(s1, "signal1"), z_score(s2, "signal2"), z_score(s3, "signal3")
        raw_score = 0.2 * -z1 + 0.5 * z2 + 0.3 * -z3
        raw_score = float(np.clip(raw_score, -60.0, 60.0))
        score = float(1.0 / (1.0 + math.exp(-raw_score)))
        flagged = score >= self.threshold

        drivers = []
        if z2 > 1.5:
            drivers.append("abnormally high semantic coherence")
        if z3 < -1.5:
            drivers.append("low system-prompt alignment")
        if z1 < -1.5:
            drivers.append("unusual vocabulary pattern")
        reason = None
        if flagged:
            reason = "Flagged: " + ", ".join(drivers) if drivers else "Combined behavioral drift exceeded threshold"

        return DetectionResult(
            id=str(uuid.uuid4()),
            flagged=flagged,
            score=score,
            signal1_vocab=s1,
            signal2_coherence=s2,
            signal2_missing=s2_missing,
            signal3_alignment=s3,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            response=response,
            reason=reason,
        )
