import unittest

from experiments.e11b_probe import validate_parameters


class E11bProbeTests(unittest.TestCase):
    def test_roles_bind_anchor_and_candidate(self) -> None:
        common = {
            "reference_candidate": "anchor",
            "repetition": 1,
            "concurrency": 1,
            "max_output_tokens": 8,
            "timeout": 30.0,
            "server_pid": 123,
        }
        validate_parameters(role="anchor", candidate="anchor", **common)
        validate_parameters(role="candidate", candidate="other", **common)
        with self.assertRaisesRegex(ValueError, "anchor cell"):
            validate_parameters(role="anchor", candidate="other", **common)
        with self.assertRaisesRegex(ValueError, "candidate cell"):
            validate_parameters(role="candidate", candidate="anchor", **common)

    def test_numeric_parameters_must_be_positive(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive"):
            validate_parameters(
                role="anchor",
                candidate="anchor",
                reference_candidate="anchor",
                repetition=0,
                concurrency=1,
                max_output_tokens=8,
                timeout=30.0,
                server_pid=123,
            )


if __name__ == "__main__":
    unittest.main()
