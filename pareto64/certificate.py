"""Restart-safe certificates for fail-closed prompt-cache routing."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

START_STATE = "start"
REQUIRED_IDENTITY_FIELDS = {
    "model_sha256",
    "server_sha256",
    "source_diff_sha256",
    "service_sha256",
}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode()


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def identity_sha256(identity: Mapping[str, Any]) -> str:
    if set(identity) != REQUIRED_IDENTITY_FIELDS or any(
        not isinstance(identity[name], str) or len(identity[name]) != 64
        for name in REQUIRED_IDENTITY_FIELDS
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
    """Route exact session transitions and periodically recheck successful ones."""

    def __init__(
        self,
        identity: Mapping[str, Any],
        *,
        minimum_cached_tokens: int,
        revalidate_every: int,
        registry: Mapping[str, Any] | None = None,
    ) -> None:
        if type(minimum_cached_tokens) is not int or minimum_cached_tokens <= 0:
            raise ValueError("minimum cached tokens must be positive")
        if type(revalidate_every) is not int or revalidate_every <= 0:
            raise ValueError("revalidation interval must be positive")
        self.identity = dict(identity)
        self.identity_digest = identity_sha256(identity)
        self.minimum_cached_tokens = minimum_cached_tokens
        self.revalidate_every = revalidate_every
        self.certified: dict[str, dict[str, Any]] = {}
        self.denied: dict[str, dict[str, Any]] = {}
        self.previous_prompt_sha256 = START_STATE
        self.previous_response_sha256 = START_STATE
        if registry is not None:
            self._restore(registry)

    def _restore(self, registry: Mapping[str, Any]) -> None:
        payload = registry.get("payload")
        if (
            registry.get("schema_version") != 2
            or registry.get("format") != "pareto64-online-transition-certificate"
            or not isinstance(payload, dict)
            or registry.get("payload_sha256") != sha256_value(payload)
            or payload.get("identity_sha256") != self.identity_digest
            or payload.get("minimum_cached_tokens") != self.minimum_cached_tokens
            or payload.get("revalidate_every") != self.revalidate_every
            or not isinstance(payload.get("certified"), dict)
            or not isinstance(payload.get("denied"), dict)
            or not _valid_state_digest(payload.get("previous_prompt_sha256"))
            or not _valid_state_digest(payload.get("previous_response_sha256"))
        ):
            raise ValueError("online certificate registry is corrupt or foreign")
        if set(payload["certified"]) & set(payload["denied"]):
            raise ValueError("online certificate registry sets overlap")
        for key, record in payload["certified"].items():
            if (
                not _sha256_string(key)
                or not isinstance(record, dict)
                or not _sha256_string(record.get("prompt_sha256"))
                or not _sha256_string(record.get("response_sha256"))
                or type(record.get("observed_cached_tokens")) is not int
                or record["observed_cached_tokens"] < self.minimum_cached_tokens
                or type(record.get("successful_uses")) is not int
                or record["successful_uses"] < 0
            ):
                raise ValueError("online certificate registry is corrupt or foreign")
        if any(
            not _sha256_string(key) or not isinstance(record, dict)
            for key, record in payload["denied"].items()
        ):
            raise ValueError("online certificate registry is corrupt or foreign")
        self.certified = json.loads(json.dumps(payload["certified"]))
        self.denied = json.loads(json.dumps(payload["denied"]))
        self.previous_prompt_sha256 = payload["previous_prompt_sha256"]
        self.previous_response_sha256 = payload["previous_response_sha256"]

    def reset_session(self) -> None:
        self.previous_prompt_sha256 = START_STATE
        self.previous_response_sha256 = START_STATE

    def plan(self, current_prompt_sha256: str) -> dict[str, Any]:
        if not _sha256_string(current_prompt_sha256):
            raise ValueError("current prompt fingerprint is invalid")
        key = transition_sha256(
            self.identity_digest,
            self.previous_prompt_sha256,
            self.previous_response_sha256,
            current_prompt_sha256,
        )
        if key in self.certified:
            successful_uses = self.certified[key]["successful_uses"]
            recheck = (
                successful_uses > 0 and successful_uses % self.revalidate_every == 0
            )
            route = "certified_revalidation" if recheck else "certified_cache"
            first_call_cache_prompt = True
            oracle_required = recheck
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
            exact = _calls_match(first_call, oracle_call)
            reused = (
                type(cached_tokens) is int
                and cached_tokens >= self.minimum_cached_tokens
            )
            if exact and reused:
                admission = "certified"
                self.certified[key] = {
                    "prompt_sha256": expected["current_prompt_sha256"],
                    "response_sha256": output_signature(oracle_call),
                    "observed_cached_tokens": cached_tokens,
                    "successful_uses": 0,
                }
            else:
                admission = "denied"
                self.denied[key] = {
                    "prompt_sha256": expected["current_prompt_sha256"],
                    "reason": _denial_reason(first_call, oracle_call, exact, reused),
                    "observed_cached_tokens": cached_tokens,
                }
            served_source = "uncached_oracle"
        elif route == "certified_revalidation":
            if oracle_call is None or not valid_call(oracle_call):
                raise ValueError("certified revalidation lacks a valid oracle")
            served = oracle_call
            if _calls_match(first_call, oracle_call):
                self.certified[key]["successful_uses"] += 1
                admission = "retained_revalidated"
            else:
                self.denied[key] = {
                    "prompt_sha256": expected["current_prompt_sha256"],
                    "reason": (
                        "successful_output_drift"
                        if valid_call(first_call)
                        else "certified_call_failed"
                    ),
                    "observed_cached_tokens": first_call.get("cached_tokens"),
                }
                self.certified.pop(key, None)
                admission = "revoked"
            served_source = "revalidation_oracle"
        elif route == "certified_cache":
            if valid_call(first_call):
                served = first_call
                self.certified[key]["successful_uses"] += 1
                admission = "retained"
                served_source = "certified_cache"
            else:
                if oracle_call is None or not valid_call(oracle_call):
                    raise ValueError(
                        "failed certified call lacks a valid oracle fallback"
                    )
                served = oracle_call
                self.denied[key] = {
                    "prompt_sha256": expected["current_prompt_sha256"],
                    "reason": "certified_call_failed",
                    "observed_cached_tokens": first_call.get("cached_tokens"),
                }
                self.certified.pop(key, None)
                admission = "revoked"
                served_source = "uncached_oracle"
        else:
            if oracle_call is not None or not valid_call(first_call):
                raise ValueError(
                    "denied transition did not use one valid uncached call"
                )
            served = first_call
            admission = "retained_denial"
            served_source = "denied_uncached"

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
            "shadow_cached_attempt_served": False,
            "served_response": served["response"],
            "served_response_sha256": response_digest,
            "served_call": dict(served),
        }

    def export_registry(self) -> dict[str, Any]:
        payload = {
            "identity_sha256": self.identity_digest,
            "minimum_cached_tokens": self.minimum_cached_tokens,
            "revalidate_every": self.revalidate_every,
            "previous_prompt_sha256": self.previous_prompt_sha256,
            "previous_response_sha256": self.previous_response_sha256,
            "certified": self.certified,
            "denied": self.denied,
        }
        return {
            "schema_version": 2,
            "format": "pareto64-online-transition-certificate",
            "payload": payload,
            "payload_sha256": sha256_value(payload),
        }


class CertificateStore:
    """Persist identity-bound, isolated session registries with atomic replacement."""

    def __init__(
        self,
        path: Path,
        identity: Mapping[str, Any],
        *,
        minimum_cached_tokens: int,
        revalidate_every: int,
        max_sessions: int = 1024,
    ) -> None:
        if type(max_sessions) is not int or max_sessions <= 0:
            raise ValueError("maximum sessions must be positive")
        self.path = path
        self.identity = dict(identity)
        self.identity_digest = identity_sha256(identity)
        self.minimum_cached_tokens = minimum_cached_tokens
        self.revalidate_every = revalidate_every
        self.max_sessions = max_sessions
        self.lock = threading.Lock()
        self.sessions: dict[str, dict[str, Any]] = {}
        if path.exists() or path.is_symlink():
            self._restore()

    def _restore(self) -> None:
        if self.path.is_symlink() or not self.path.is_file():
            raise ValueError("certificate store is not a regular file")
        value = json.loads(self.path.read_text(encoding="utf-8"))
        payload = value.get("payload") if isinstance(value, dict) else None
        if (
            value.get("schema_version") != 1
            or value.get("format") != "pareto64-session-certificate-store"
            or not isinstance(payload, dict)
            or value.get("payload_sha256") != sha256_value(payload)
            or payload.get("identity_sha256") != self.identity_digest
            or payload.get("minimum_cached_tokens") != self.minimum_cached_tokens
            or payload.get("revalidate_every") != self.revalidate_every
            or not isinstance(payload.get("sessions"), dict)
            or len(payload["sessions"]) > self.max_sessions
        ):
            raise ValueError("certificate store is corrupt or foreign")
        for session_digest, registry in payload["sessions"].items():
            if not _sha256_string(session_digest):
                raise ValueError("certificate store is corrupt or foreign")
            OnlineCertificate(
                self.identity,
                minimum_cached_tokens=self.minimum_cached_tokens,
                revalidate_every=self.revalidate_every,
                registry=registry,
            )
        self.sessions = payload["sessions"]

    def controller(self, session_id: str) -> tuple[str, OnlineCertificate]:
        if not isinstance(session_id, str) or not 1 <= len(session_id.encode()) <= 256:
            raise ValueError("session identity must contain 1 to 256 UTF-8 bytes")
        session_digest = hashlib.sha256(session_id.encode()).hexdigest()
        with self.lock:
            registry = self.sessions.get(session_digest)
            if registry is None and len(self.sessions) >= self.max_sessions:
                raise ValueError("certificate session capacity is exhausted")
        return session_digest, OnlineCertificate(
            self.identity,
            minimum_cached_tokens=self.minimum_cached_tokens,
            revalidate_every=self.revalidate_every,
            registry=registry,
        )

    def save(self, session_digest: str, controller: OnlineCertificate) -> None:
        if not _sha256_string(session_digest):
            raise ValueError("session digest is invalid")
        with self.lock:
            self.sessions[session_digest] = controller.export_registry()
            payload = {
                "identity_sha256": self.identity_digest,
                "minimum_cached_tokens": self.minimum_cached_tokens,
                "revalidate_every": self.revalidate_every,
                "sessions": self.sessions,
            }
            value = {
                "schema_version": 1,
                "format": "pareto64-session-certificate-store",
                "payload": payload,
                "payload_sha256": sha256_value(payload),
            }
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(
                prefix=f".{self.path.name}.", dir=self.path.parent
            )
            temporary_path = Path(temporary)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    json.dump(value, handle, indent=2, sort_keys=True)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                temporary_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
                os.replace(temporary_path, self.path)
            finally:
                if temporary_path.exists():
                    temporary_path.unlink()

    def counts(self) -> dict[str, int]:
        with self.lock:
            registries = list(self.sessions.values())
        return {
            "sessions": len(registries),
            "certified_transitions": sum(
                len(item["payload"]["certified"]) for item in registries
            ),
            "denied_transitions": sum(
                len(item["payload"]["denied"]) for item in registries
            ),
        }


def _sha256_string(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _valid_state_digest(value: Any) -> bool:
    return value == START_STATE or _sha256_string(value)


def _calls_match(first: Mapping[str, Any], oracle: Mapping[str, Any]) -> bool:
    return (
        valid_call(first)
        and valid_call(oracle)
        and output_signature(first) == output_signature(oracle)
    )


def _denial_reason(
    first: Mapping[str, Any],
    oracle: Mapping[str, Any],
    exact: bool,
    reused: bool,
) -> str:
    if not valid_call(first) or not valid_call(oracle):
        return "shadow_or_oracle_failure"
    if not exact:
        return "shadow_output_mismatch"
    if not reused:
        return "no_material_cache_reuse"
    raise AssertionError("admitted transition has no denial reason")
