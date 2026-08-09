"""
SELF Guard — Opt-in Telemetry Module

Collects pseudonymous signal data to improve detection accuracy over time.
- Opt-in only (default: disabled)
- JSON payloads exclude response text, user messages, and direct identifiers
- Endpoint operators can still receive ordinary network metadata
- Non-blocking — never slows down or crashes your application
"""

import uuid
import os
import threading
from typing import Optional
from datetime import datetime, timezone

__version__ = "0.2.0rc1"

# ------------------------------------------------------------------ #
#  Backend configuration                                               #
#  Replace TELEMETRY_ENDPOINT with your Firebase/Supabase URL         #
# ------------------------------------------------------------------ #
TELEMETRY_ENDPOINT = os.getenv("SELFGUARD_TELEMETRY_ENDPOINT", "")
FEEDBACK_ENDPOINT = os.getenv("SELFGUARD_FEEDBACK_ENDPOINT", "")


def _post_async(endpoint: str, payload: dict) -> bool:
    """Fire-and-forget POST request in background thread."""
    if not endpoint:
        return False
    def _send():
        try:
            import requests
            requests.post(endpoint, json=payload, timeout=2)
        except Exception:
            pass  # never crash the main app for telemetry

    thread = threading.Thread(target=_send, daemon=True)
    thread.start()
    return True


def log_detection(
    signal1: float,
    signal2: float,
    signal3: float,
    score: float,
    flagged: bool,
    model_type: str,
    threshold: float,
    latency_ms: float,
    opted_in: bool,
    session_id: Optional[str] = None
) -> bool:
    """
    Log a pseudonymous detection event.

    Args:
        signal1:     Vocabulary overlap score
        signal2:     Semantic coherence score
        signal3:     System alignment score
        score:       Combined normalized behavioral drift score
        flagged:     Whether injection was detected
        model_type:  LLM backend type (e.g. "openai", "anthropic")
        threshold:   Detection threshold used
        latency_ms:  Detection latency in milliseconds
        opted_in:    Whether user has opted into telemetry
        session_id:  Random session identifier
    """
    if not opted_in:
        return False

    payload = {
        "session_id":  session_id or str(uuid.uuid4()),
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "version":     __version__,
        "signal1":     round(signal1, 6),
        "signal2":     round(signal2, 6),
        "signal3":     round(signal3, 6),
        "score":       round(score, 6),
        "flagged":     flagged,
        "model_type":  model_type,
        "threshold":   threshold,
        "latency_ms":  round(latency_ms, 2),
    }

    return _post_async(TELEMETRY_ENDPOINT, payload)


def log_feedback(
    session_id: str,
    detection_id: str,
    was_correct: bool,
    opted_in: bool
) -> bool:
    """
    Log user feedback on a detection result.

    Args:
        session_id:   Random session identifier
        detection_id: ID of the detection being corrected
        was_correct:  True if detection was correct, False if false positive/negative
        opted_in:     Whether user has opted into telemetry
    """
    if not opted_in:
        return False

    payload = {
        "session_id":    session_id,
        "detection_id":  detection_id,
        "was_correct":   was_correct,
        "timestamp":     datetime.now(timezone.utc).isoformat(),
        "version":       __version__,
    }

    return _post_async(FEEDBACK_ENDPOINT, payload)
