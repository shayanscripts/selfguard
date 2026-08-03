import unittest

from test_core import FakeEmbedder, clean_examples
from selfguard import SELFGuard


class GuardTests(unittest.TestCase):
    def test_manual_calibration_and_custom_backend(self):
        guard = SELFGuard(
            system_prompt="You provide order support.",
            llm=lambda _: "Your order will arrive tomorrow. Contact support if needed.",
            clean_examples=clean_examples(),
            embedder=FakeEmbedder(),
            verbose=False,
        )
        response = guard.chat("Where is my order?")
        self.assertIsInstance(response.text, str)
        self.assertEqual(guard.stats()["status"], "calibrated")

    def test_auto_calibration_configures_backend_first(self):
        calls = []

        def backend(prompt):
            calls.append(prompt)
            return f"Clean response. Details for {prompt}."

        prompts = [f"Known clean request {index}" for index in range(10)]
        guard = SELFGuard(
            system_prompt="You provide support.",
            llm=backend,
            auto_calibrate=True,
            calibration_prompts=prompts,
            embedder=FakeEmbedder(),
            verbose=False,
        )
        self.assertEqual(guard.stats()["status"], "calibrated")
        self.assertEqual(calls, prompts)

    def test_uncalibrated_chat_fails_clearly(self):
        guard = SELFGuard(
            system_prompt="You provide support.",
            llm=lambda _: "response",
            embedder=FakeEmbedder(),
            verbose=False,
        )
        with self.assertRaisesRegex(RuntimeError, "not calibrated"):
            guard.chat("hello")

    def test_blocking_redacts_nested_detection_response(self):
        raw_response = "sensitive generated output"
        guard = SELFGuard(
            system_prompt="You provide support.",
            llm=lambda _: raw_response,
            threshold=0.0,
            block_injections=True,
            clean_examples=clean_examples(),
            embedder=FakeEmbedder(),
            verbose=False,
        )
        response = guard.chat("hello")
        self.assertTrue(response.blocked)
        self.assertNotIn(raw_response, response.text)
        self.assertEqual(response.detection.response, "[suppressed]")

    def test_huggingface_auto_calibration_is_deferred(self):
        prompts = [f"Known clean request {index}" for index in range(10)]
        guard = SELFGuard(
            system_prompt="You provide support.",
            llm="huggingface",
            auto_calibrate=True,
            calibration_prompts=prompts,
            embedder=FakeEmbedder(),
            verbose=False,
        )
        self.assertTrue(guard._pending_auto_calibration)

        def fake_calibration():
            guard.detector.calibrate(clean_examples())

        guard._auto_calibrate = fake_calibration
        class FakeModel:
            def eval(self):
                return self

        guard.attach_hf_model(FakeModel(), object())
        self.assertTrue(guard.detector.is_calibrated)
        self.assertFalse(guard._pending_auto_calibration)


if __name__ == "__main__":
    unittest.main()
