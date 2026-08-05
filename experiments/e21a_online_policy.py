#!/usr/bin/env python3
"""Identity-bound online transition certificates for fail-closed prompt reuse."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


START_STATE = "start"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode()


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def identity_sha256(identity: Mapping[str, Any]) -> str:
    required = {
        "model_sha256",
        "server_sha256",
        "source_diff_sha256",
        "service_sha256",
    }
    if set(identity) != required or any(
        not isinstance(identity[name], str) or len(identity[name]) != 64
        for name in required
    ):
        raise ValueError("online certificate identity differs")
    return sha256_value(dict(identity))


def output_signature(call: Mapping[str, Any]) -> str:
    return sha256_value(
        {
            "response": call.get("response"),
            "stop_type": call.get("stop_type"),
            "generated_tokens": call.get("generated_tokens"),
        }
    )


def valid_call(call: Mapping[str, Any]) -> bool:
    return (
        call.get("http_status") == 200
        and call.get("error") is None
        and isinstance(call.get("response"), str)
        and isinstance(call.get("generated_tokens"), int)
        and call["generated_tokens"] >= 0
    )


def transition_sha256(
    identity_digest: str,
    previous_prompt_sha256: str,
    previous_response_sha256: str,
    current_prompt_sha256: str,
) -> str:
    values = (
        identity_digest,
        previous_prompt_sha256,
        previous_response_sha256,
        current_prompt_sha256,
    )
    if any(not isinstance(value, str) or not value for value in values):
        raise ValueError("transition identity is incomplete")
    return sha256_value(
        {
            "identity_sha256": identity_digest,
            "previous_prompt_sha256": previous_prompt_sha256,
            "previous_response_sha256": previous_response_sha256,
            "current_prompt_sha256": current_prompt_sha256,
        }
    )


class OnlineCertificate:
    """Route exact transitions while never serving an unknown cached attempt."""

    def __init__(
        self,
        identity: Mapping[str, Any],
        *,
        minimum_cached_tokens: int,
        registry: Mapping[str, Any] | None = None,
    ) -> None:
        if type(minimum_cached_tokens) is not int or minimum_cached_tokens <= 0:
            raise ValueError("minimum cached tokens must be positive")
        self.identity = dict(identity)
        self.identity_digest = identity_sha256(identity)
        self.minimum_cached_tokens = minimum_cached_tokens
        self.certified: dict[str, dict[str, Any]] = {}
        self.denied: dict[str, dict[str, Any]] = {}
        self.previous_prompt_sha256 = START_STATE
        self.previous_response_sha256 = START_STATE
        if registry is not None:
            self._restore(registry)

    def _restore(self, registry: Mapping[str, Any]) -> None:
        payload = registry.get("payload")
        if (
            registry.get("schema_version") != 1
            or not isinstance(payload, dict)
            or registry.get("payload_sha256") != sha256_value(payload)
            or payload.get("identity_sha256") != self.identity_digest
            or payload.get("minimum_cached_tokens") != self.minimum_cached_tokens
            or not isinstance(payload.get("certified"), dict)
            or not isinstance(payload.get("denied"), dict)
        ):
            raise ValueError("online certificate registry is corrupt or foreign")
        if set(payload["certified"]) & set(payload["denied"]):
            raise ValueError("online certificate registry sets overlap")
        self.certified = dict(payload["certified"])
        self.denied = dict(payload["denied"])

    def reset_session(self) -> None:
        self.previous_prompt_sha256 = START_STATE
        self.previous_response_sha256 = START_STATE

    def plan(self, current_prompt_sha256: str) -> dict[str, Any]:
        if not isinstance(current_prompt_sha256, str) or len(current_prompt_sha256) != 64:
            raise ValueError("current prompt fingerprint is invalid")
        key = transition_sha256(
            self.identity_digest,
            self.previous_prompt_sha256,
            self.previous_response_sha256,
            current_prompt_sha256,
        )
        if key in self.certified:
            route = "certified_cache"
            first_call_cache_prompt = True
            oracle_required = False
        elif key in self.denied:
            route = "denied_fallback"
            first_call_cache_prompt = False
            oracle_required = False
        else:
            route = "unknown_shadow_then_oracle"
            first_call_cache_prompt = True
            oracle_required = True
        return {
            "transition_sha256": key,
            "previous_prompt_sha256": self.previous_prompt_sha256,
            "previous_response_sha256": self.previous_response_sha256,
            "current_prompt_sha256": current_prompt_sha256,
            "route": route,
            "first_call_cache_prompt": first_call_cache_prompt,
            "oracle_required": oracle_required,
        }

    def complete(
        self,
        plan: Mapping[str, Any],
        first_call: Mapping[str, Any],
        oracle_call: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        expected = self.plan(str(plan.get("current_prompt_sha256")))
        if dict(plan) != expected:
            raise ValueError("online certificate plan is stale")
        route = expected["route"]
        key = expected["transition_sha256"]
        if route == "unknown_shadow_then_oracle":
            if oracle_call is None:
                raise ValueError("unknown transition lacks uncached oracle")
            served = oracle_call
            cached_tokens = first_call.get("cached_tokens")
            exact = (
                valid_call(first_call)
                and valid_call(oracle_call)
                and output_signature(first_call) == output_signature(oracle_call)
            )
            reused = (
                isinstance(cached_tokens, int)
                and not isinstance(cached_tokens, bool)
                and cached_tokens >= self.minimum_cached_tokens
            )
            if exact and reused:
                admission = "certified"
                self.certified[key] = {
                    "prompt_sha256": expected["current_prompt_sha256"],
                    "response_sha256": output_signature(oracle_call),
                    "observed_cached_tokens": cached_tokens,
                }
            else:
                admission = "denied"
                self.denied[key] = {
                    "prompt_sha256": expected["current_prompt_sha256"],
                    "reason": (
                        "shadow_or_oracle_failure"
                        if not valid_call(first_call) or not valid_call(oracle_call)
                        else "shadow_output_mismatch"
                        if not exact
                        else "no_material_cache_reuse"
                    ),
                    "observed_cached_tokens": cached_tokens,
                }
            served_source = "uncached_oracle"
            shadow_served = False
        elif route == "certified_cache":
            if valid_call(first_call):
                served = first_call
                admission = "retained"
                served_source = "certified_cache"
                shadow_served = False
            else:
                if oracle_call is None or not valid_call(oracle_call):
                    raise ValueError("failed certified call lacks a valid oracle fallback")
                served = oracle_call
                self.denied[key] = {
                    "prompt_sha256": expected["current_prompt_sha256"],
                    "reason": "certified_call_failed",
                    "observed_cached_tokens": first_call.get("cached_tokens"),
                }
                self.certified.pop(key, None)
                admission = "revoked"
                served_source = "uncached_oracle"
                shadow_served = False
        else:
            if oracle_call is not None or not valid_call(first_call):
                raise ValueError("denied transition did not use one valid uncached call")
            served = first_call
            admission = "retained_denial"
            served_source = "denied_uncached"
            shadow_served = False

        if not valid_call(served):
            self.reset_session()
            raise ValueError("served online certificate response is invalid")
        response_digest = output_signature(served)
        self.previous_prompt_sha256 = expected["current_prompt_sha256"]
        self.previous_response_sha256 = response_digest
        return {
            **expected,
            "admission": admission,
            "served_source": served_source,
            "shadow_cached_attempt_served": shadow_served,
            "served_response": served["response"],
            "served_response_sha256": response_digest,
            "served_call": dict(served),
        }

    def export_registry(self) -> dict[str, Any]:
        payload = {
            "identity_sha256": self.identity_digest,
            "minimum_cached_tokens": self.minimum_cached_tokens,
            "certified": self.certified,
            "denied": self.denied,
        }
        return {
            "schema_version": 1,
            "format": "pareto64-online-transition-certificate",
            "payload": payload,
            "payload_sha256": sha256_value(payload),
        }


def synthetic_replay() -> dict[str, Any]:
    identity = {name: character * 64 for name, character in zip(
        (
            "model_sha256",
            "server_sha256",
            "source_diff_sha256",
            "service_sha256",
        ),
        "1234",
        strict=True,
    )}
    controller = OnlineCertificate(identity, minimum_cached_tokens=8)
    prompts = ["a" * 64, "b" * 64, "a" * 64, "b" * 64, "a" * 64, "b" * 64]
    answers = {"a" * 64: "A", "b" * 64: "B"}
    records = []
    for index, prompt in enumerate(prompts):
        plan = controller.plan(prompt)
        cached_tokens = 0 if plan["previous_prompt_sha256"] == START_STATE else 16
        first = {
            "http_status": 200,
            "error": None,
            "response": answers[prompt],
            "stop_type": "eos",
            "generated_tokens": 1,
            "cached_tokens": cached_tokens if plan["first_call_cache_prompt"] else 0,
        }
        oracle = None
        if plan["oracle_required"]:
            oracle = {**first, "cached_tokens": 0}
        record = controller.complete(plan, first, oracle)
        records.append(
            {
                "index": index,
                "prompt_sha256": prompt,
                "route": record["route"],
                "admission": record["admission"],
                "served_source": record["served_source"],
                "served_response": record["served_response"],
                "shadow_cached_attempt_served": record[
                    "shadow_cached_attempt_served"
                ],
            }
        )
    registry = controller.export_registry()
    return {
        "schema_version": 1,
        "status": "valid_online_transition_certificate_synthetic_replay",
        "records": records,
        "decision_counts": {
            route: sum(record["route"] == route for record in records)
            for route in (
                "unknown_shadow_then_oracle",
                "certified_cache",
                "denied_fallback",
            )
        },
        "certified_transitions": len(registry["payload"]["certified"]),
        "denied_transitions": len(registry["payload"]["denied"]),
        "unknown_cached_attempts_served": sum(
            record["shadow_cached_attempt_served"] for record in records
        ),
        "registry": registry,
    }
