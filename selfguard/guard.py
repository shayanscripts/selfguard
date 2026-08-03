"""Post-generation behavioral-drift wrapper for supported LLM backends."""

import time
import uuid
from dataclasses import dataclass, replace
from typing import Any, Callable, List, Optional, Union

from .core import SELFDetector, DetectionResult
from . import telemetry as _telemetry


TELEMETRY_NOTICE = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SELF Guard — Opt-in Telemetry (telemetry=True)

Telemetry is sent only when you both opt in and configure
an endpoint. The endpoint operator may receive ordinary
network metadata such as an IP address.

What IS collected:
  ✓ Signal scores (3 numbers)
  ✓ Detection outcome (flagged: True/False)
  ✓ Model type (e.g. "openai")
  ✓ Latency
  ✓ Random session ID

What is NEVER collected:
  ✗ Your system prompt
  ✗ User messages
  ✗ LLM response text
  ✗ Direct identifiers in the JSON payload

Disable anytime: SELFGuard(..., telemetry=False)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""


@dataclass
class GuardedResponse:
    """Response text plus SELF's post-generation detection metadata."""
    text:              str    # LLM response text (or block message)
    flagged:           bool   # True if the configured threshold was exceeded
    injection_score:   float  # normalized 0-1 behavioral drift score
    detection:         DetectionResult  # full detection details
    blocked:           bool   # generated response was suppressed
    total_latency_ms:  float  # total call latency in ms

    def __str__(self):
        return self.text

    def __repr__(self):
        status = "FLAGGED" if self.flagged else "PASS"
        return (
            f"GuardedResponse({status}, "
            f"score={self.injection_score:.3f}, "
            f"latency={self.total_latency_ms:.0f}ms)"
        )


class SELFGuard:
    """Wrap an LLM call with experimental post-generation drift detection.

    Detection happens after the model has generated its response. Suppression
    therefore cannot prevent tool calls or other side effects that occurred
    during generation.

    Supports:
        - OpenAI  (GPT-4, GPT-3.5, etc.)
        - Anthropic (Claude)
        - HuggingFace (any open model)
        - Custom LLM functions

    Basic usage:
        guard = SELFGuard(
            system_prompt="You are a helpful assistant.",
            llm="openai",
            model="gpt-4"
        )
        response = guard.chat("User message")
        if response.flagged:
            print("Behavioral drift flagged:", response.detection.reason)
        else:
            print(response.text)
    """

    def __init__(
        self,
        system_prompt:    str,
        llm:              Union[str, Callable] = "openai",
        model:            str = "gpt-4",
        threshold:        float = 0.8,
        block_injections: bool = True,
        auto_calibrate:   bool = False,
        calibration_prompts: Optional[List[str]] = None,
        clean_examples:   Optional[List[str]] = None,
        verbose:          bool = True,
        api_key:          Optional[str] = None,
        telemetry:        bool = False,   # opt-in, default OFF
        embedder:         Optional[Any] = None,
        embedder_model:   str = "all-MiniLM-L6-v2",
        embedder_revision: Optional[str] = None,
    ):
        """
        Args:
            system_prompt:    Your deployment system prompt
            llm:              "openai", "anthropic", "huggingface", or callable
            model:            Model name (e.g. "gpt-4", "claude-sonnet-4-6")
            threshold:        Heuristic detection threshold from 0 to 1
            block_injections: Block detected injections (default True)
            auto_calibrate:   Generate calibration responses on initialization
            calibration_prompts: At least 10 known-clean, domain-specific prompts
            clean_examples:   Optional clean responses for manual calibration
            verbose:          Print detection results (default True)
            api_key:          API key (or set via env variable)
            telemetry:        Send pseudonymous signal data to configured endpoints
                              (default False — must explicitly opt in)
            embedder:         Optional compatible embedder instance (advanced/testing)
            embedder_model:   Sentence-transformer model name
            embedder_revision: Optional immutable model revision for reproducibility
        """
        self.system_prompt     = system_prompt
        self.llm_type          = llm if isinstance(llm, str) else "custom"
        self.model             = model
        self.block_injections  = block_injections
        self.verbose           = verbose
        self.api_key           = api_key
        self.telemetry_enabled = telemetry
        self.calibration_prompts = calibration_prompts
        self._session_id       = str(uuid.uuid4())  # random session ID

        # show telemetry notice if enabled
        if telemetry and verbose:
            print(TELEMETRY_NOTICE)

        # initialize detector
        self.detector = SELFDetector(
            system_prompt=system_prompt,
            threshold=threshold,
            embedder_model=embedder_model,
            embedder_revision=embedder_revision,
            embedder=embedder,
        )

        # Auto-calibration calls the backend, so configure it first.
        self._setup_llm(llm)

        # calibrate
        if clean_examples:
            # option B — manual calibration with user examples
            self.detector.calibrate(clean_examples)
        elif auto_calibrate:
            if not calibration_prompts or len(calibration_prompts) < 10:
                raise ValueError(
                    "auto_calibrate=True requires at least 10 domain-specific "
                    "calibration_prompts"
                )
            if self.llm_type == "huggingface":
                self._pending_auto_calibration = True
            else:
                self._auto_calibrate()

    # ------------------------------------------------------------------ #
    #  Setup                                                               #
    # ------------------------------------------------------------------ #

    def _setup_llm(self, llm):
        if callable(llm):
            self._llm_call = llm
        elif llm == "openai":
            self._llm_call = self._call_openai
        elif llm == "anthropic":
            self._llm_call = self._call_anthropic
        elif llm == "huggingface":
            self._llm_call = self._call_huggingface
        else:
            raise ValueError(
                f"Unknown llm: '{llm}'. "
                "Use 'openai', 'anthropic', 'huggingface', or a callable."
            )

    def _auto_calibrate(self):
        """Generate clean responses from caller-supplied calibration prompts."""
        if self.verbose:
            print("Auto-calibrating SELF Guard...")
            print("(Pass clean_examples= to skip, or auto_calibrate=False)")

        clean_responses = []
        for prompt in self.calibration_prompts or []:
            try:
                response = self._llm_call(prompt)
                if response and len(response.strip()) > 5:
                    clean_responses.append(response)
            except Exception as e:
                if self.verbose:
                    print(f"  Skipping prompt ({e})")
                continue

        if len(clean_responses) < 10:
            raise RuntimeError(
                f"Auto-calibration failed — only {len(clean_responses)} "
                "valid responses. Check your LLM config."
            )

        self.detector.calibrate(clean_responses)

    def calibrate_manual(self, clean_responses: List[str]):
        """
        Manually calibrate with domain-specific clean responses.
        More accurate than auto-calibration for specialized deployments.
        """
        self.detector.calibrate(clean_responses)

    # ------------------------------------------------------------------ #
    #  LLM Backends                                                        #
    # ------------------------------------------------------------------ #

    def _call_openai(self, user_message: str) -> str:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            resp = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user",   "content": user_message}
                ],
                max_tokens=300
            )
            return resp.choices[0].message.content
        except ImportError as exc:
            raise ImportError("Run: pip install 'selfguard[openai]'") from exc

    def _call_anthropic(self, user_message: str) -> str:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key)
            resp = client.messages.create(
                model=self.model,
                max_tokens=300,
                system=self.system_prompt,
                messages=[{"role": "user", "content": user_message}]
            )
            return resp.content[0].text
        except ImportError as exc:
            raise ImportError("Run: pip install 'selfguard[anthropic]'") from exc

    def _call_huggingface(self, user_message: str) -> str:
        if not hasattr(self, '_hf_model'):
            raise RuntimeError(
                "Attach your model first:\n"
                "  guard.attach_hf_model(model, tokenizer)"
            )
        import torch
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user",   "content": user_message}
        ]
        formatted = self._hf_tok.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True)
        inputs = self._hf_tok(
            formatted, return_tensors="pt",
            add_special_tokens=False, truncation=True, max_length=768)
        inputs = {k: v.to(self._hf_model.device) for k, v in inputs.items()}
        with torch.inference_mode():
            out = self._hf_model.generate(
                **inputs,
                max_new_tokens=150,
                do_sample=False,
                pad_token_id=self._hf_tok.eos_token_id
            )
        new_tokens = out[0][inputs['input_ids'].shape[1]:]
        return self._hf_tok.decode(new_tokens, skip_special_tokens=True).strip()

    def attach_hf_model(self, model, tokenizer):
        """Attach a HuggingFace model and tokenizer."""
        self._hf_model = model
        self._hf_tok   = tokenizer
        self._hf_model.eval()
        if getattr(self, "_pending_auto_calibration", False):
            self._auto_calibrate()
            self._pending_auto_calibration = False
        if self.verbose:
            print("✅ HuggingFace model attached.")

    # ------------------------------------------------------------------ #
    #  Main interface                                                      #
    # ------------------------------------------------------------------ #

    def chat(self, user_message: str) -> GuardedResponse:
        """
        Send a message to the LLM with post-generation drift scoring.

        Args:
            user_message: The user's input message

        Returns:
            GuardedResponse — .text for response, .flagged for detection status
        """
        if not self.detector.is_calibrated:
            raise RuntimeError(
                "SELFGuard is not calibrated. Supply clean_examples, enable "
                "auto_calibrate with calibration_prompts, or call calibrate_manual()."
            )
        if not isinstance(user_message, str) or not user_message.strip():
            raise ValueError("user_message must be a non-empty string")

        t0 = time.perf_counter()

        # call LLM
        response_text = self._llm_call(user_message)
        if not isinstance(response_text, str):
            raise TypeError("The LLM backend must return response text as a string")

        # run SELF detection
        detection = self.detector.detect(response_text)

        total_latency = (time.perf_counter() - t0) * 1000

        # Log pseudonymous numeric metadata only when explicitly enabled.
        _telemetry.log_detection(
            signal1=detection.signal1_vocab,
            signal2=detection.signal2_coherence,
            signal3=detection.signal3_alignment,
            score=detection.score,
            flagged=detection.flagged,
            model_type=self.llm_type,
            threshold=self.detector.threshold,
            latency_ms=detection.latency_ms,
            opted_in=self.telemetry_enabled,
            session_id=self._session_id
        )

        # handle blocked responses
        blocked = detection.flagged and self.block_injections
        if blocked:
            # A suppressed response must not remain reachable through the
            # nested DetectionResult object.
            detection = replace(detection, response="[suppressed]")
            response_text = (
                "This response was suppressed by SELF Guard because its "
                "behavioral signals exceeded the configured threshold. "
                f"[Detection ID: {detection.id}]"
            )

        if self.verbose:
            status = "FLAGGED" if detection.flagged else "PASS"
            print(
                f"[SELF Guard] {status} | "
                f"score={detection.score:.3f} | "
                f"S1={detection.signal1_vocab:.3f} | "
                f"S2={detection.signal2_coherence:.3f} | "
                f"S3={detection.signal3_alignment:.3f} | "
                f"detection={detection.latency_ms:.0f}ms | "
                f"total={total_latency:.0f}ms"
            )
            if detection.flagged and detection.reason:
                print(f"[SELF Guard] Reason: {detection.reason}")

        return GuardedResponse(
            text=response_text,
            flagged=detection.flagged,
            injection_score=detection.score,
            detection=detection,
            blocked=blocked,
            total_latency_ms=total_latency
        )

    def report(
        self,
        response: GuardedResponse,
        correct: bool
    ) -> bool:
        """
        Report whether a detection was correct.
        Helps improve SELF Guard's accuracy over time.

        Args:
            response: The GuardedResponse to report on
            correct:  True if detection was correct,
                      False if false positive or false negative

        Example:
            response = guard.chat("message")
            if response.flagged:
                # user says "actually this was fine"
                guard.report(response, correct=False)
        """
        if not self.telemetry_enabled:
            if self.verbose:
                print(
                    "[SELF Guard] Feedback was not sent because telemetry is disabled."
                )
            return False

        accepted = _telemetry.log_feedback(
            session_id=self._session_id,
            detection_id=response.detection.id,
            was_correct=correct,
            opted_in=self.telemetry_enabled
        )

        if self.verbose:
            if accepted:
                print("[SELF Guard] Feedback queued for best-effort delivery.")
            else:
                print("[SELF Guard] Feedback was not sent: no endpoint is configured.")
        return accepted

    def batch_check(self, responses: List[str]) -> List[DetectionResult]:
        """
        Check a batch of pre-generated LLM responses.
        Use when you already have responses and just want detection.

        Args:
            responses: List of LLM response strings

        Returns:
            List of DetectionResult objects
        """
        results = []
        for r in responses:
            result = self.detector.detect(r)
            _telemetry.log_detection(
                signal1=result.signal1_vocab,
                signal2=result.signal2_coherence,
                signal3=result.signal3_alignment,
                score=result.score,
                flagged=result.flagged,
                model_type=self.llm_type,
                threshold=self.detector.threshold,
                latency_ms=result.latency_ms,
                opted_in=self.telemetry_enabled,
                session_id=self._session_id
            )
            results.append(result)
        return results

    def stats(self) -> dict:
        """Return fingerprint stats for the current deployment."""
        if not self.detector.is_calibrated:
            return {"status": "not calibrated"}
        return {
            "status":    "calibrated",
            "threshold": self.detector.threshold,
            "fingerprint": {
                "signal1_mean": self.detector.fingerprint["signal1"]["mean"],
                "signal1_std":  self.detector.fingerprint["signal1"]["std"],
                "signal2_mean": self.detector.fingerprint["signal2"]["mean"],
                "signal2_std":  self.detector.fingerprint["signal2"]["std"],
                "signal3_mean": self.detector.fingerprint["signal3"]["mean"],
                "signal3_std":  self.detector.fingerprint["signal3"]["std"],
            },
            "telemetry":  self.telemetry_enabled,
            "session_id": self._session_id,
        }
