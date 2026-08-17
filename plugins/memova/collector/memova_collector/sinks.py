from __future__ import annotations

import http.client
import json
import time
from pathlib import Path
from typing import Any, Callable, Protocol

from .contracts import build_ack
from .oauth import CollectorOAuthClient, OAuthHttpError, _json_request


class BatchSink(Protocol):
    def send(self, batch: dict[str, Any]) -> dict[str, Any]: ...


class MockSink:
    """A local sink used by M2. It never performs a network request."""

    target = "mock"

    def __init__(self, output: str | Path | None = None) -> None:
        self.output = Path(output).expanduser() if output else None
        self.received: list[dict[str, Any]] = []

    def send(self, batch: dict[str, Any]) -> dict[str, Any]:
        self.received.append(batch)
        if self.output is not None:
            self.output.parent.mkdir(parents=True, exist_ok=True)
            with self.output.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(batch, ensure_ascii=False, sort_keys=True) + "\n")
            try:
                self.output.chmod(0o600)
            except OSError:
                pass
        return build_ack(batch)


class FailingSink:
    target = "mock"

    def __init__(self, message: str = "synthetic sink failure") -> None:
        self.message = message

    def send(self, batch: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError(self.message)


class RestSink:
    """Authenticated archive sink with server ACK; tokens remain in the OS credential store."""

    target = "rest"

    def __init__(
        self,
        *,
        api_base: str,
        oauth: CollectorOAuthClient,
        consent: dict[str, Any],
        retry_attempts: int = 4,
        retry_backoff_seconds: float = 1.0,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if retry_attempts < 1:
            raise ValueError("retry_attempts must be at least 1")
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds cannot be negative")
        self.api_base = api_base.rstrip("/")
        self.oauth = oauth
        self.consent = consent
        self.retry_attempts = retry_attempts
        self.retry_backoff_seconds = retry_backoff_seconds
        self.sleeper = sleeper
        self._consent_registered = False

    def register_consent(self) -> dict[str, Any]:
        payload = {**self.consent, "status": "active"}
        result = self._request("PUT", "/v1/external-conversations/consents", payload)
        self._consent_registered = True
        return result

    def send(self, batch: dict[str, Any]) -> dict[str, Any]:
        if not self._consent_registered:
            self.register_consent()
        ack = self._request("POST", "/v1/external-conversations/batches", batch)
        if ack.get("status") != "accepted":
            raise RuntimeError("Memova REST did not return an accepted batch ACK.")
        if ack.get("batch_id") != batch.get("batch_id"):
            raise RuntimeError("Memova REST ACK batch_id does not match the sent batch.")
        if ack.get("idempotency_key") != batch.get("idempotency_key"):
            raise RuntimeError("Memova REST ACK idempotency_key does not match the sent batch.")
        if ack.get("archive_status") != "durable":
            raise RuntimeError(
                "Memova REST did not confirm durable raw-archive storage; checkpoint unchanged."
            )
        return ack

    def status(self, *, device_id: str) -> dict[str, Any]:
        from urllib.parse import urlencode

        return self._request(
            "GET",
            "/v1/external-conversations/status?" + urlencode({"device_id": device_id}),
            None,
        )

    def delete(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/v1/external-conversations/deletions", payload)

    def repository_fingerprint_key(self) -> str | None:
        return self.oauth.repository_fingerprint_key()

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        token = self.oauth.access_token()
        try:
            return self._request_with_retries(method, path, payload, token=token)
        except OAuthHttpError as exc:
            if exc.status_code != 401:
                raise
        token = self.oauth.access_token(force_refresh=True)
        return self._request_with_retries(method, path, payload, token=token)

    def _request_with_retries(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
        *,
        token: str,
    ) -> dict[str, Any]:
        transient_statuses = frozenset({408, 429, 500, 502, 503, 504})
        for attempt in range(self.retry_attempts):
            try:
                _, response = _json_request(
                    f"{self.api_base}{path}",
                    method=method,
                    payload=payload,
                    token=token,
                )
                return response
            except OAuthHttpError as exc:
                if exc.status_code not in transient_statuses:
                    raise
                error: BaseException = exc
            except (OSError, http.client.HTTPException) as exc:
                error = exc

            if attempt + 1 >= self.retry_attempts:
                raise error
            self.sleeper(self.retry_backoff_seconds * (2**attempt))

        raise AssertionError("REST retry loop exited without a response")
