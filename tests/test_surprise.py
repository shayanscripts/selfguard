import builtins
import importlib.util
import math
import types
import unittest
from unittest import mock

from selfguard import token_surprise_bits, token_surprise_bits_from_ids


TORCH_AVAILABLE = importlib.util.find_spec("torch") is not None


class FakeTokenizer:
    def apply_chat_template(self, messages, tokenize, add_generation_prompt):
        return "rendered prompt"

    def __call__(self, text, **kwargs):
        if not hasattr(self, "calls"):
            self.calls = []
        self.calls.append((text, kwargs))
        if text == "rendered prompt":
            return {"input_ids": [0, 0]}
        if not text:
            return {"input_ids": []}
        return {"input_ids": [1, 1]}


@unittest.skipUnless(TORCH_AVAILABLE, "PyTorch is an optional dependency")
class TokenSurpriseTests(unittest.TestCase):
    def test_converts_mean_nll_from_nats_to_bits(self):
        import torch

        class FakeModel:
            device = torch.device("cpu")

            def __call__(self, **kwargs):
                self.kwargs = kwargs
                length = kwargs["input_ids"].shape[1]
                return types.SimpleNamespace(logits=torch.zeros((1, length, 2)))

        model = FakeModel()
        tokenizer = FakeTokenizer()
        result = token_surprise_bits(
            model,
            tokenizer,
            "system",
            "user",
            "response",
        )

        self.assertAlmostEqual(result.mean_bits, 1.0, places=6)
        self.assertEqual(result.token_count, 2)
        self.assertEqual(model.kwargs["input_ids"].tolist(), [[0, 0, 1, 1]])
        self.assertFalse(model.kwargs["use_cache"])
        self.assertFalse(tokenizer.calls[0][1]["add_special_tokens"])

    def test_empty_response_is_a_missing_signal(self):
        result = token_surprise_bits(
            object(),
            FakeTokenizer(),
            "system",
            "user",
            "",
            device="cpu",
        )
        self.assertTrue(math.isnan(result.mean_bits))
        self.assertEqual(result.token_count, 0)

    def test_exact_id_api_uses_the_same_definition(self):
        import torch

        class FakeModel:
            device = torch.device("cpu")

            def __call__(self, **kwargs):
                length = kwargs["input_ids"].shape[1]
                return types.SimpleNamespace(logits=torch.zeros((1, length, 2)))

        result = token_surprise_bits_from_ids(FakeModel(), [0, 0], [1, 1])
        self.assertAlmostEqual(result.mean_bits, 1.0, places=6)
        self.assertEqual(result.token_count, 2)

    def test_first_response_token_uses_last_prompt_logit(self):
        """Catch an off-by-one mask at the prompt/response boundary."""
        import torch

        class BoundaryModel:
            device = torch.device("cpu")

            def __call__(self, **kwargs):
                length = kwargs["input_ids"].shape[1]
                logits = torch.zeros((1, length, 4))
                # Position 0 predicts the second prompt token almost perfectly.
                # It must not contribute to response NLL. Position 1, the final
                # prompt position, is uniform and predicts response token 2.
                logits[0, 0, :] = -20.0
                logits[0, 0, 1] = 20.0
                return types.SimpleNamespace(logits=logits)

        result = token_surprise_bits_from_ids(BoundaryModel(), [0, 1], [2])
        self.assertAlmostEqual(result.mean_bits, 2.0, places=6)
        self.assertEqual(result.token_count, 1)

    def test_all_response_transitions_are_averaged(self):
        """Ensure Signal 4 includes both the first and later response tokens."""
        import torch

        class DistinctLossModel:
            device = torch.device("cpu")

            def __call__(self, **kwargs):
                length = kwargs["input_ids"].shape[1]
                logits = torch.zeros((1, length, 4))
                # The first response token has uniform probability: 2 bits.
                # For the second response token, logit ln(3) makes its
                # probability exactly 1/2 among four classes: 1 bit.
                logits[0, 2, 3] = math.log(3.0)
                return types.SimpleNamespace(logits=logits)

        result = token_surprise_bits_from_ids(
            DistinctLossModel(),
            [0, 1],
            [2, 3],
        )
        self.assertAlmostEqual(result.mean_bits, 1.5, places=6)
        self.assertEqual(result.token_count, 2)


class TokenSurpriseValidationTests(unittest.TestCase):
    def test_rejects_invalid_context(self):
        with self.assertRaises(ValueError):
            token_surprise_bits(object(), object(), "", "user", "response")
        with self.assertRaises(TypeError):
            token_surprise_bits(object(), object(), "system", None, "response")

    def test_empty_response_short_circuits_without_torch(self):
        result = token_surprise_bits_from_ids(object(), [0], [])
        self.assertTrue(math.isnan(result.mean_bits))
        self.assertEqual(result.token_count, 0)

    def test_rejects_invalid_token_ids_before_importing_torch(self):
        invalid_cases = [
            ([], [1]),
            ([0], [-1]),
            ([0], [True]),
            (["0"], [1]),
        ]
        for prompt_ids, response_ids in invalid_cases:
            with self.subTest(prompt_ids=prompt_ids, response_ids=response_ids):
                with self.assertRaises(ValueError):
                    token_surprise_bits_from_ids(
                        object(),
                        prompt_ids,
                        response_ids,
                    )

    def test_missing_torch_error_names_the_install_extra(self):
        real_import = builtins.__import__

        def import_without_torch(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "torch" or name.startswith("torch."):
                raise ImportError("PyTorch intentionally unavailable in this test")
            return real_import(name, globals, locals, fromlist, level)

        with mock.patch.object(
            builtins,
            "__import__",
            side_effect=import_without_torch,
        ):
            with self.assertRaisesRegex(ImportError, r"selfguard\[huggingface\]"):
                token_surprise_bits_from_ids(object(), [0], [1])


if __name__ == "__main__":
    unittest.main()
