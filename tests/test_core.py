import hashlib
import unittest

import numpy as np

from selfguard import SELFDetector


class FakeEmbedder:
    def _one(self, text):
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return np.array([byte / 255 for byte in digest[:8]], dtype=float)

    def encode(self, value, convert_to_numpy=True):
        if isinstance(value, str):
            return self._one(value)
        return np.vstack([self._one(item) for item in value])


def clean_examples():
    return [f"Your order number {index} will arrive tomorrow. Please contact support." for index in range(10)]


class DetectorTests(unittest.TestCase):
    def test_requires_calibration(self):
        detector = SELFDetector("You provide order support.", embedder=FakeEmbedder())
        with self.assertRaisesRegex(RuntimeError, "not calibrated"):
            detector.detect("Your order is ready.")

    def test_short_response_uses_neutral_coherence(self):
        detector = SELFDetector("You provide order support.", embedder=FakeEmbedder())
        detector.calibrate(clean_examples())
        result = detector.detect("Okay")
        self.assertEqual(result.signal2_coherence, detector.fingerprint["signal2"]["mean"])
        self.assertTrue(result.signal2_missing)
        self.assertTrue(np.isfinite(result.score))

    def test_input_validation(self):
        detector = SELFDetector("You provide order support.", embedder=FakeEmbedder())
        with self.assertRaises(ValueError):
            detector.calibrate(["valid"] * 9)
        with self.assertRaises(TypeError):
            detector.compute_signals(None)


if __name__ == "__main__":
    unittest.main()
