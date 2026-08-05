import json
import unittest

from experiments.e21a_online_policy import (
    OnlineCertificate,
    identity_sha256,
    synthetic_replay,
)


IDENTITY = {
    "model_sha256": "1" * 64,
    "server_sha256": "2" * 64,
    "source_diff_sha256": "3" * 64,
    "service_sha256": "4" * 64,
}


def call(response="A", cached_tokens=16, status=200):
    return {
        "http_status": status,
        "error": None if status == 200 else "failure",
        "response": response if status == 200 else None,
        "stop_type": "eos",
        "generated_tokens": 1,
        "cached_tokens": cached_tokens,
    }


class OnlineCertificateTests(unittest.TestCase):
    def test_unknown_cached_attempt_is_never_served(self) -> None:
        controller = OnlineCertificate(IDENTITY, minimum_cached_tokens=8)
        plan = controller.plan("a" * 64)
        result = controller.complete(plan, call("B", 0), call("A", 0))
        self.assertEqual(result["served_response"], "A")
        self.assertEqual(result["served_source"], "uncached_oracle")
        self.assertFalse(result["shadow_cached_attempt_served"])
        self.assertEqual(result["admission"], "denied")

    def test_exact_reused_transition_is_certified_then_cached(self) -> None:
        controller = OnlineCertificate(IDENTITY, minimum_cached_tokens=8)
        first = controller.plan("a" * 64)
        controller.complete(first, call("A", 0), call("A", 0))
        second = controller.plan("b" * 64)
        admitted = controller.complete(second, call("B", 16), call("B", 0))
        self.assertEqual(admitted["admission"], "certified")
        third = controller.plan("a" * 64)
        controller.complete(third, call("A", 16), call("A", 0))
        fourth = controller.plan("b" * 64)
        self.assertEqual(fourth["route"], "certified_cache")
        served = controller.complete(fourth, call("B", 16))
        self.assertEqual(served["served_source"], "certified_cache")

    def test_registry_is_identity_bound_and_corruption_fails(self) -> None:
        controller = OnlineCertificate(IDENTITY, minimum_cached_tokens=8)
        registry = controller.export_registry()
        restored = OnlineCertificate(
            IDENTITY, minimum_cached_tokens=8, registry=registry
        )
        self.assertEqual(restored.export_registry(), registry)
        foreign = dict(IDENTITY)
        foreign["model_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "corrupt or foreign"):
            OnlineCertificate(foreign, minimum_cached_tokens=8, registry=registry)
        damaged = json.loads(json.dumps(registry))
        damaged["payload"]["denied"]["x"] = {}
        with self.assertRaisesRegex(ValueError, "corrupt or foreign"):
            OnlineCertificate(IDENTITY, minimum_cached_tokens=8, registry=damaged)

    def test_identity_requires_the_complete_closure(self) -> None:
        self.assertEqual(len(identity_sha256(IDENTITY)), 64)
        incomplete = dict(IDENTITY)
        incomplete.pop("server_sha256")
        with self.assertRaisesRegex(ValueError, "identity differs"):
            identity_sha256(incomplete)

    def test_synthetic_replay_is_complete_and_byte_stable(self) -> None:
        first = synthetic_replay()
        second = synthetic_replay()
        self.assertEqual(first, second)
        self.assertEqual(first["decision_counts"]["unknown_shadow_then_oracle"], 3)
        self.assertEqual(first["decision_counts"]["certified_cache"], 3)
        self.assertEqual(first["certified_transitions"], 2)
        self.assertEqual(first["denied_transitions"], 1)
        self.assertEqual(first["unknown_cached_attempts_served"], 0)


if __name__ == "__main__":
    unittest.main()
