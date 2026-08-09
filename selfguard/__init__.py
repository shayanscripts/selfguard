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
from .evaluation import (
    BinaryMetrics,
    EvaluationRecord,
    FixedFPRReport,
    RateInterval,
    ThresholdSelection,
    assert_disjoint_splits,
    binary_metrics,
    evaluate_fixed_fpr,
    load_evaluation_records,
    minimum_clean_samples_for_zero_false_positives,
    precision_at_prevalence,
    select_threshold_at_fpr,
    wilson_interval,
)
from .boundary import (
    ActionBoundary,
    ActionRequest,
    AuditEvent,
    AuthorizationDecision,
    AuthorizationError,
    Decision,
    RiskLevel,
    ToolPolicy,
)
from .prompt_risk import PromptRiskDetector, PromptRiskResult
from .plugin import (
    PromptAction,
    PromptAuditEvent,
    PromptBlockedError,
    PromptDecision,
    PromptInjectionPlugin,
    PromptReviewRequired,
    SkopsPromptScorer,
)

__version__ = "0.2.0rc1"
__all__ = [
    "SELFGuard",
    "GuardedResponse",
    "SELFDetector",
    "DetectionResult",
    "TokenSurprise",
    "token_surprise_bits",
    "token_surprise_bits_from_ids",
    "BinaryMetrics",
    "EvaluationRecord",
    "FixedFPRReport",
    "RateInterval",
    "ThresholdSelection",
    "assert_disjoint_splits",
    "binary_metrics",
    "evaluate_fixed_fpr",
    "load_evaluation_records",
    "minimum_clean_samples_for_zero_false_positives",
    "precision_at_prevalence",
    "select_threshold_at_fpr",
    "wilson_interval",
    "ActionBoundary",
    "ActionRequest",
    "AuditEvent",
    "AuthorizationDecision",
    "AuthorizationError",
    "Decision",
    "RiskLevel",
    "ToolPolicy",
    "PromptRiskDetector",
    "PromptRiskResult",
    "PromptAction",
    "PromptAuditEvent",
    "PromptBlockedError",
    "PromptDecision",
    "PromptInjectionPlugin",
    "PromptReviewRequired",
    "SkopsPromptScorer",
]
