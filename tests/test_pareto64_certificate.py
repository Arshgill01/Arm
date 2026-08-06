from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pareto64.certificate import CertificateStore, OnlineCertificate

IDENTITY = {
    "model_sha256": "1" * 64,
    "server_sha256": "2" * 64,
    "source_diff_sha256": "3" * 64,
    "service_sha256": "4" * 64,
}


def call(response: str = "A", cached_tokens: int = 16, status: int = 200):
    return {
        "http_status": status,
        "error": None if status == 200 else "failure",
        "response": response if status == 200 else None,
        "stop_type": "eos",
        "generated_tokens": 1 if status == 200 else None,
        "cached_tokens": cached_tokens,
    }


class ProductCertificateTests(unittest.TestCase):
    def controller(self) -> OnlineCertificate:
        return OnlineCertificate(IDENTITY, minimum_cached_tokens=8, revalidate_every=1)

    def certify_transition(self, controller: OnlineCertificate) -> None:
        first = controller.plan("a" * 64)
        controller.complete(first, call(cached_tokens=0), call(cached_tokens=0))
        second = controller.plan("b" * 64)
        result = controller.complete(second, call("B"), call("B", 0))
        self.assertEqual("certified", result["admission"])
        third = controller.plan("a" * 64)
        controller.complete(third, call(cached_tokens=16), call(cached_tokens=0))

    def test_unknown_shadow_is_never_served(self) -> None:
        controller = self.controller()
        plan = controller.plan("a" * 64)
        result = controller.complete(plan, call("wrong", 0), call("oracle", 0))
        self.assertEqual("oracle", result["served_response"])
        self.assertEqual("uncached_oracle", result["served_source"])
        self.assertFalse(result["shadow_cached_attempt_served"])

    def test_certified_use_is_periodically_revalidated(self) -> None:
        controller = self.controller()
        self.certify_transition(controller)
        cached = controller.plan("b" * 64)
        self.assertEqual("certified_cache", cached["route"])
        controller.complete(cached, call("B"))
        recheck = controller.plan("a" * 64)
        controller.complete(recheck, call("A"), call("A", 0))
        recheck = controller.plan("b" * 64)
        self.assertEqual("certified_revalidation", recheck["route"])
        result = controller.complete(recheck, call("B"), call("B", 0))
        self.assertEqual("retained_revalidated", result["admission"])
        self.assertEqual("revalidation_oracle", result["served_source"])

    def test_successful_output_drift_revokes_and_serves_oracle(self) -> None:
        controller = self.controller()
        self.certify_transition(controller)
        cached = controller.plan("b" * 64)
        controller.complete(cached, call("B"))
        controller.complete(controller.plan("a" * 64), call("A"), call("A", 0))
        recheck = controller.plan("b" * 64)
        result = controller.complete(recheck, call("drift"), call("B", 0))
        self.assertEqual("revoked", result["admission"])
        self.assertEqual("B", result["served_response"])
        self.assertEqual("revalidation_oracle", result["served_source"])
        back_to_a = controller.plan("a" * 64)
        controller.complete(back_to_a, call("A"), call("A", 0))
        self.assertEqual("denied_fallback", controller.plan("b" * 64)["route"])

    def test_store_is_restart_safe_and_session_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "certificates.json"
            store = CertificateStore(
                path,
                IDENTITY,
                minimum_cached_tokens=8,
                revalidate_every=4,
            )
            first_digest, first = store.controller("user-a")
            first.complete(first.plan("a" * 64), call("A", 0), call("A", 0))
            store.save(first_digest, first)
            second_digest, second = store.controller("user-b")
            self.assertNotEqual(first_digest, second_digest)
            self.assertEqual("start", second.previous_prompt_sha256)
            restored = CertificateStore(
                path,
                IDENTITY,
                minimum_cached_tokens=8,
                revalidate_every=4,
            )
            _, resumed = restored.controller("user-a")
            self.assertEqual("a" * 64, resumed.previous_prompt_sha256)
            self.assertEqual(0o600, path.stat().st_mode & 0o777)

    def test_corrupt_or_foreign_store_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "certificates.json"
            store = CertificateStore(
                path,
                IDENTITY,
                minimum_cached_tokens=8,
                revalidate_every=4,
            )
            digest, controller = store.controller("user-a")
            store.save(digest, controller)
            value = json.loads(path.read_text())
            value["payload"]["identity_sha256"] = "0" * 64
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "corrupt or foreign"):
                CertificateStore(
                    path,
                    IDENTITY,
                    minimum_cached_tokens=8,
                    revalidate_every=4,
                )


if __name__ == "__main__":
    unittest.main()
