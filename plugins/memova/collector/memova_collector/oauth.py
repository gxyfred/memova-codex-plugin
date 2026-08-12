from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

from .credentials import CredentialStore, decode_secret, encode_secret, system_credential_store

TOKEN_SCHEMA_VERSION = "memova_collector_oauth_token_v1"
DEFAULT_SCOPES = "conversations.read conversations.write conversations.delete"
COLLECTOR_CLIENT_ID = "memova-codex-collector-1.1.0"
PAIRING_DISCLOSURE_VERSION = "codex-full-history-archive-v1"


def _json_request(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    form: dict[str, str] | None = None,
    token: str | None = None,
    timeout: float = 30,
) -> tuple[int, dict[str, Any]]:
    headers = {"Accept": "application/json", "User-Agent": "memova-codex-collector/1.1.0"}
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif form is not None:
        data = urllib.parse.urlencode(form).encode("ascii")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        hostname = urllib.parse.urlsplit(url).hostname or ""
        bypass_proxy = hostname.lower() == "localhost"
        if not bypass_proxy:
            try:
                bypass_proxy = ipaddress.ip_address(hostname).is_loopback
            except ValueError:
                pass
        opener = (
            urllib.request.build_opener(urllib.request.ProxyHandler({}))
            if bypass_proxy
            else urllib.request.build_opener()
        )
        with opener.open(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return int(response.status), json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            details = json.loads(body) if body else {}
        except json.JSONDecodeError:
            details = {"message": body[:1000]}
        raise OAuthHttpError(exc.code, details) from exc


class OAuthHttpError(RuntimeError):
    def __init__(self, status_code: int, details: dict[str, Any]) -> None:
        super().__init__(f"Memova OAuth request failed with HTTP {status_code}.")
        self.status_code = status_code
        self.details = details


@dataclass(frozen=True)
class OAuthMetadata:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str
    revocation_endpoint: str
    resource: str


class _CallbackHandler(BaseHTTPRequestHandler):
    callback: dict[str, str] = {}

    def do_GET(self) -> None:  # noqa: N802
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        type(self).callback = {key: values[0] for key, values in query.items() if values}
        body = "Memova authorization received. You may close this window."
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *_: object) -> None:
        return


class CollectorOAuthClient:
    def __init__(
        self,
        api_base: str,
        *,
        credential_store: CredentialStore | None = None,
        opener: Callable[[str], bool] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self.store = credential_store or system_credential_store()
        self.opener = opener or webbrowser.open
        self.clock = clock
        self.account = "oauth:" + hashlib.sha256(self.api_base.encode("utf-8")).hexdigest()[:32]

    def metadata(self) -> OAuthMetadata:
        _, resource = _json_request(
            f"{self.api_base}/.well-known/oauth-protected-resource/v1/external-conversations"
        )
        authorization_server = str(resource["authorization_servers"][0]).rstrip("/")
        _, server = _json_request(
            f"{authorization_server}/.well-known/oauth-authorization-server"
        )
        return OAuthMetadata(
            issuer=str(server["issuer"]),
            authorization_endpoint=str(server["authorization_endpoint"]),
            token_endpoint=str(server["token_endpoint"]),
            registration_endpoint=str(server["registration_endpoint"]),
            revocation_endpoint=str(server["revocation_endpoint"]),
            resource=str(resource["resource"]),
        )

    def connect(self, *, timeout_seconds: int = 300) -> dict[str, Any]:
        existing = self._load(required=False)
        if existing and existing.get("refresh_token"):
            return {
                "status": "already_connected",
                "authorization_url": None,
                "browser_opened": False,
                "resource": existing.get("resource"),
                "scopes": str(existing.get("scope") or "").split(),
                "credential_store": type(self.store).__name__,
            }
        if existing:
            self._revoke_values(existing, [existing.get("access_token")])
            self.store.delete(self.account)
        metadata = self.metadata()
        _CallbackHandler.callback = {}
        server = ThreadingHTTPServer(("127.0.0.1", 0), _CallbackHandler)
        server.timeout = 1
        redirect_uri = f"http://127.0.0.1:{server.server_port}/oauth/callback"
        _, registration = _json_request(
            metadata.registration_endpoint,
            method="POST",
            payload={
                "redirect_uris": [redirect_uri],
                "client_name": "Memova Codex Collector",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
                "scope": DEFAULT_SCOPES,
            },
        )
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        state = secrets.token_urlsafe(32)
        authorization_url = metadata.authorization_endpoint + "?" + urllib.parse.urlencode(
            {
                "response_type": "code",
                "client_id": str(registration["client_id"]),
                "redirect_uri": redirect_uri,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "resource": metadata.resource,
                "scope": DEFAULT_SCOPES,
                "state": state,
            }
        )
        opened = bool(self.opener(authorization_url))
        if not opened:
            print(
                "Open this Memova authorization URL in a browser:\n" + authorization_url,
                file=sys.stderr,
                flush=True,
            )
        deadline = self.clock() + timeout_seconds
        try:
            while self.clock() < deadline and not _CallbackHandler.callback:
                server.handle_request()
        finally:
            server.server_close()
        callback = dict(_CallbackHandler.callback)
        if not callback:
            raise RuntimeError(
                "Memova authorization timed out. Open the authorization URL and approve access."
            )
        if callback.get("state") != state:
            raise RuntimeError("OAuth callback state did not match; refusing the authorization.")
        if callback.get("error"):
            raise RuntimeError(f"Memova authorization was denied: {callback['error']}")
        code = callback.get("code")
        if not code:
            raise RuntimeError("OAuth callback did not include an authorization code.")
        _, issued = _json_request(
            metadata.token_endpoint,
            method="POST",
            form={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": str(registration["client_id"]),
                "redirect_uri": redirect_uri,
                "code_verifier": verifier,
                "resource": metadata.resource,
            },
        )
        token_record = {
            "schema_version": TOKEN_SCHEMA_VERSION,
            "api_base": self.api_base,
            "client_id": str(registration["client_id"]),
            "redirect_uri": redirect_uri,
            "resource": metadata.resource,
            "token_endpoint": metadata.token_endpoint,
            "revocation_endpoint": metadata.revocation_endpoint,
            "scope": str(issued.get("scope") or DEFAULT_SCOPES),
            "access_token": str(issued["access_token"]),
            "refresh_token": issued.get("refresh_token"),
            "expires_at": self.clock() + int(issued.get("expires_in") or 3600),
        }
        try:
            self.store.set(self.account, encode_secret(token_record))
        except Exception:
            self._revoke_values(
                token_record,
                [token_record.get("refresh_token"), token_record.get("access_token")],
            )
            raise
        return {
            "status": "connected",
            "authorization_url": authorization_url,
            "browser_opened": opened,
            "resource": metadata.resource,
            "scopes": token_record["scope"].split(),
            "credential_store": type(self.store).__name__,
        }

    def prepare_pairing(self, *, device_id: str) -> dict[str, Any]:
        existing = self._load(required=False)
        if existing.get("refresh_token"):
            return {
                "status": "already_connected",
                "device_id": device_id,
                "collector_client_id": str(existing.get("client_id") or COLLECTOR_CLIENT_ID),
                "credential_store": type(self.store).__name__,
            }
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        pending = {
            "schema_version": TOKEN_SCHEMA_VERSION,
            "api_base": self.api_base,
            "pairing_status": "pending",
            "pairing_verifier": verifier,
            "pairing_challenge": challenge,
            "pairing_device_id": device_id,
            "client_id": COLLECTOR_CLIENT_ID,
            "disclosure_version": PAIRING_DISCLOSURE_VERSION,
            "retention_mode": "until_user_or_account_deletion",
            "prepared_at": self.clock(),
        }
        self.store.set(self.account, encode_secret(pending))
        return {
            "status": "pairing_prepared",
            "collector_client_id": COLLECTOR_CLIENT_ID,
            "device_id": device_id,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "disclosure_version": PAIRING_DISCLOSURE_VERSION,
            "retention_mode": "until_user_or_account_deletion",
            "archive_disclosure_confirmed": True,
            "mcp_tool": "create_conversation_sync_pairing_grant",
            "credential_store": type(self.store).__name__,
        }

    def connect_with_pairing(
        self,
        *,
        pairing_grant: str,
        device_id: str,
    ) -> dict[str, Any]:
        pending = self._load(required=True)
        if pending.get("refresh_token"):
            return {
                "status": "already_connected",
                "resource": pending.get("resource"),
                "scopes": str(pending.get("scope") or "").split(),
                "credential_store": type(self.store).__name__,
            }
        if pending.get("pairing_status") != "pending":
            raise RuntimeError("Prepare an MCP pairing request before connecting.")
        if pending.get("pairing_device_id") != device_id:
            raise RuntimeError("Prepared pairing request is bound to another device.")
        metadata = self.metadata()
        _, issued = _json_request(
            f"{self.api_base}/v1/mcp/oauth/conversation-sync/pairing-token",
            method="POST",
            payload={
                "pairing_grant": pairing_grant,
                "collector_client_id": str(pending["client_id"]),
                "device_id": device_id,
                "code_verifier": str(pending["pairing_verifier"]),
            },
        )
        token_record = {
            "schema_version": TOKEN_SCHEMA_VERSION,
            "api_base": self.api_base,
            "client_id": str(pending["client_id"]),
            "redirect_uri": None,
            "resource": metadata.resource,
            "token_endpoint": metadata.token_endpoint,
            "revocation_endpoint": metadata.revocation_endpoint,
            "scope": str(issued.get("scope") or DEFAULT_SCOPES),
            "access_token": str(issued["access_token"]),
            "refresh_token": issued.get("refresh_token"),
            "expires_at": self.clock() + int(issued.get("expires_in") or 3600),
            "device_id": device_id,
            "paired_via_mcp": True,
        }
        try:
            self.store.set(self.account, encode_secret(token_record))
        except Exception:
            self._revoke_values(
                token_record,
                [token_record.get("refresh_token"), token_record.get("access_token")],
            )
            self.store.delete(self.account)
            raise
        return {
            "status": "connected",
            "paired_via_mcp": True,
            "resource": metadata.resource,
            "scopes": token_record["scope"].split(),
            "credential_store": type(self.store).__name__,
        }

    def status(self) -> dict[str, Any]:
        record = self._load(required=False)
        return {
            "connected": bool(record and record.get("refresh_token")),
            "resource": record.get("resource") if record else None,
            "scopes": str(record.get("scope") or "").split() if record else [],
            "access_token_expired": (
                self.clock() >= float(record.get("expires_at") or 0) if record else None
            ),
            "credential_store": type(self.store).__name__,
        }

    def access_token(self, *, force_refresh: bool = False) -> str:
        record = self._load(required=True)
        if force_refresh or self.clock() >= float(record.get("expires_at") or 0) - 60:
            record = self._refresh(record)
        token = record.get("access_token")
        if not token:
            raise RuntimeError("Stored Collector authorization has no access token.")
        return str(token)

    def disconnect(self) -> dict[str, Any]:
        record = self._load(required=False)
        revoked = True
        if record:
            revoked = self._revoke_values(
                record,
                [record.get("refresh_token"), record.get("access_token")],
            )
            if not revoked:
                raise RuntimeError(
                    "Memova token revocation did not complete; the credential was retained "
                    "securely so disconnect can be retried."
                )
        self.store.delete(self.account)
        return {
            "oauth_credential_deleted": True,
            "server_token_revocation_completed": revoked,
        }

    def _load(self, *, required: bool) -> dict[str, Any]:
        value = self.store.get(self.account)
        if value is None:
            if required:
                raise RuntimeError("Collector is not connected to Memova. Run `connect` first.")
            return {}
        record = decode_secret(value)
        if record.get("schema_version") != TOKEN_SCHEMA_VERSION:
            raise RuntimeError("Stored Collector authorization has an unsupported version.")
        return record

    def _refresh(self, record: dict[str, Any]) -> dict[str, Any]:
        refresh_token = record.get("refresh_token")
        if not refresh_token:
            raise RuntimeError("Collector authorization cannot be refreshed; reconnect Memova.")
        _, issued = _json_request(
            str(record["token_endpoint"]),
            method="POST",
            form={
                "grant_type": "refresh_token",
                "refresh_token": str(refresh_token),
                "client_id": str(record["client_id"]),
                "resource": str(record["resource"]),
            },
        )
        updated = {
            **record,
            "access_token": str(issued["access_token"]),
            "refresh_token": issued.get("refresh_token") or refresh_token,
            "scope": str(issued.get("scope") or record.get("scope") or DEFAULT_SCOPES),
            "expires_at": self.clock() + int(issued.get("expires_in") or 3600),
        }
        try:
            self.store.set(self.account, encode_secret(updated))
        except Exception as exc:
            self._revoke_values(
                updated,
                [updated.get("refresh_token"), updated.get("access_token")],
            )
            self.store.delete(self.account)
            raise RuntimeError(
                "Refreshed OAuth tokens could not be stored securely; reconnect Memova."
            ) from exc
        return updated

    def _revoke_values(self, record: dict[str, Any], tokens: list[Any]) -> bool:
        values = [token for token in tokens if token]
        revoked = bool(values)
        for token in values:
            try:
                _json_request(
                    str(record["revocation_endpoint"]),
                    method="POST",
                    form={
                        "token": str(token),
                        "client_id": str(record["client_id"]),
                    },
                )
            except (OAuthHttpError, OSError):
                revoked = False
        return revoked
