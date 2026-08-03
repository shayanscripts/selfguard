"""Token-surprisal signal for causal language models with accessible logits.

This module deliberately keeps PyTorch optional: importing :mod:`selfguard`
does not require it, while computing Signal 4 does.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Integral
from typing import Any, Sequence


@dataclass(frozen=True)
class TokenSurprise:
    """Mean teacher-forced response surprise and its token denominator."""

    mean_bits: float
    token_count: int


def token_surprise_bits(
    model: Any,
    tokenizer: Any,
    system_prompt: str,
    user_message: str,
    response: str,
    *,
    max_prompt_tokens: int = 768,
    device: Any = None,
) -> TokenSurprise:
    """Return response-token negative log likelihood in bits per token.

    The response is teacher-forced under the exact system/user chat context.
    Prompt tokens are masked out, so the causal-language-model loss is averaged
    over response tokens only. The model must be in evaluation mode. This
    helper requires direct access to model logits.

    Retokenizing stored text measures its likelihood faithfully, although an
    exact replay of generation should persist the originally sampled token IDs.
    """

    if not isinstance(system_prompt, str) or not system_prompt.strip():
        raise ValueError("system_prompt must be a non-empty string")
    if not isinstance(user_message, str):
        raise TypeError("user_message must be a string")
    if not isinstance(response, str):
        raise TypeError("response must be a string")
    if not isinstance(max_prompt_tokens, int) or max_prompt_tokens <= 0:
        raise ValueError("max_prompt_tokens must be a positive integer")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    rendered_prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    prompt_ids = tokenizer(
        rendered_prompt,
        # The chat template already supplies model control tokens. Adding
        # another BOS/control token can change the likelihood context.
        add_special_tokens=False,
        truncation=True,
        max_length=max_prompt_tokens,
    )["input_ids"]
    response_ids = tokenizer(response, add_special_tokens=False)["input_ids"]

    # Some custom tokenizers return a one-row nested list without tensors.
    if prompt_ids and isinstance(prompt_ids[0], (list, tuple)):
        prompt_ids = prompt_ids[0]
    if response_ids and isinstance(response_ids[0], (list, tuple)):
        response_ids = response_ids[0]
    prompt_ids = list(prompt_ids)
    response_ids = list(response_ids)

    return token_surprise_bits_from_ids(
        model,
        prompt_ids,
        response_ids,
        device=device,
    )


def token_surprise_bits_from_ids(
    model: Any,
    prompt_token_ids: Sequence[int],
    response_token_ids: Sequence[int],
    *,
    device: Any = None,
) -> TokenSurprise:
    """Compute exact Signal 4 from token IDs retained during generation."""

    prompt_ids = list(prompt_token_ids)
    response_ids = list(response_token_ids)
    if not prompt_ids:
        raise ValueError("prompt_token_ids must contain at least one token")
    if any(
        not isinstance(item, Integral) or isinstance(item, bool) or item < 0
        for item in prompt_ids
    ):
        raise ValueError("prompt_token_ids must contain non-negative integers")
    if any(
        not isinstance(item, Integral) or isinstance(item, bool) or item < 0
        for item in response_ids
    ):
        raise ValueError("response_token_ids must contain non-negative integers")
    if not response_ids:
        return TokenSurprise(mean_bits=math.nan, token_count=0)

    try:
        import torch
        import torch.nn.functional as functional
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ImportError(
            "Signal 4 requires PyTorch. Install selfguard[huggingface]."
        ) from exc

    if device is None:
        device = getattr(model, "device", None)
        if device is None:
            try:
                device = next(model.parameters()).device
            except (AttributeError, StopIteration) as exc:
                raise ValueError("Could not infer model device; pass device explicitly") from exc

    # The shifted logit at P-1 predicts the first response token at P.
    combined_ids = prompt_ids + response_ids
    input_ids = torch.tensor([combined_ids], dtype=torch.long, device=device)
    attention_mask = torch.ones_like(input_ids)
    response_mask = torch.zeros_like(input_ids, dtype=torch.bool)
    response_mask[:, len(prompt_ids):] = True

    with torch.inference_mode():
        output = model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            use_cache=False,
        )
        shifted_logits = output.logits[:, :-1, :].float()
        shifted_targets = input_ids[:, 1:]
        shifted_mask = response_mask[:, 1:]
        mean_nll = functional.cross_entropy(
            shifted_logits[shifted_mask],
            shifted_targets[shifted_mask],
            reduction="mean",
        )

    mean_bits = float(mean_nll.detach().cpu().item()) / math.log(2.0)
    if not math.isfinite(mean_bits):
        mean_bits = math.nan
    return TokenSurprise(mean_bits=mean_bits, token_count=len(response_ids))
