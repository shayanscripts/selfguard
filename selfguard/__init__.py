"""
SELF Guard — Prompt Injection Detection via Behavioral Fingerprinting

Experimental, model-agnostic behavioral drift signals for LLM responses.
The bundled weighted scorer is a baseline and is not the trained Random Forest
evaluated in the accompanying research.

Usage:
    from selfguard import SELFGuard

    guard = SELFGuard(
        system_prompt="You are a helpful customer support assistant.",
        llm="openai",
        model="gpt-4.1-mini",
        clean_examples=[...],
        telemetry=False  # opt-in; may send pseudonymous numeric metadata
    )

    response = guard.chat("User message here")

    if response.flagged:
        print("Behavioral drift flagged!", response.detection.reason)
    else:
        print(response.text)
"""

from .guard import SELFGuard, GuardedResponse
from .core  import SELFDetector, DetectionResult
from .surprise import TokenSurprise, token_surprise_bits, token_surprise_bits_from_ids

__version__ = "0.1.0"
__all__ = [
    "SELFGuard",
    "GuardedResponse",
    "SELFDetector",
    "DetectionResult",
    "TokenSurprise",
    "token_surprise_bits",
    "token_surprise_bits_from_ids",
]
