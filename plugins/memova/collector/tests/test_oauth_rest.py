from __future__ import annotations

import json
import platform
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memova_collector.credentials import (
    MacOSCredentialStore,
    MemoryCredentialStore,
    system_credential_store,
)
from memova_collector.oauth import (
    TOKEN_SCHEMA_VERSION,
    CollectorOAuthClient,
    OAuthHttpError,
)
from memova_collector.sinks import RestSink


class OAuthAndRestTests(unittest.TestCase):
    def _oauth(self, store: MemoryCredentialStore, *, expires_at: float = 10_000) -> CollectorOAuthClient:
        oauth = CollectorOAuthClient(
            "https://api.memova.test",
            credential_store=store,
            clock=lambda: 100,
        )
        store.set(
            oauth.account,
            json.dumps(
                {
                    "schema_version": TOKEN_SCHEMA_VERSION,
                    "api_base": "https://api.memova.test",
                    "client_id": "collector-client",
                    "redirect_uri": "http://127.0.0.1:12345/oauth/callback",
                    "resource": "https://api.memova.test/v1/external-conversations",
                    "token_endpoint": "https://api.memova.test/v1/mcp/oauth/token",
                    "revocation_endpoint": "https://api.memova.test/v1/mcp/oauth/revoke",
                    "scope": "conversations.read conversations.write conversations.delete",
                    "access_token": "access-old",
                    "refresh_token": "refresh-old",
                    "expires_at": expires_at,
                }
            ),
        )
        return oauth

    def test_oauth_status_never_returns_token_material(self) -> None:
        oauth = self._oauth(MemoryCredentialStore())
        status = oauth.status()

        self.assertTrue(status["connected"])
        self.assertNotIn("access_token", status)
        self.assertNotIn("refresh_token", status)

    def test_prepare_pairing_keeps_verifier_secret_and_returns_only_public_fields(self) -> None:
        store = MemoryCredentialStore()
        oauth = CollectorOAuthClient(
            "https://api.memova.test",
            credential_store=store,
            clock=lambda: 100,
        )

        result = oauth.prepare_pairing(device_id="device-0001")

        self.assertEqual(result["status"], "pairing_prepared")
        self.assertEqual(result["retention_mode"], "until_user_or_account_deletion")
        self.assertTrue(result["archive_disclosure_confirmed"])
        self.assertEqual(len(result["code_challenge"]), 43)
        self.assertNotIn("pairing_verifier", result)
        stored = json.loads(store.get(oauth.account) or "{}")
        self.assertIn("pairing_verifier", stored)
        self.assertNotIn("access_token", stored)

    def test_pairing_exchange_stores_separate_device_bound_credential(self) -> None:
        store = MemoryCredentialStore()
        oauth = CollectorOAuthClient(
            "https://api.memova.test",
            credential_store=store,
            clock=lambda: 100,
        )
        prepared = oauth.prepare_pairing(device_id="device-0001")
        responses = [
            (
                200,
                {
                    "authorization_servers": ["https://api.memova.test"],
                    "resource": "https://api.memova.test/v1/external-conversations",
                },
            ),
            (
                200,
                {
                    "issuer": "https://api.memova.test",
                    "authorization_endpoint": "https://api.memova.test/v1/mcp/oauth/authorize",
                    "token_endpoint": "https://api.memova.test/v1/mcp/oauth/token",
                    "registration_endpoint": "https://api.memova.test/v1/mcp/oauth/register",
                    "revocation_endpoint": "https://api.memova.test/v1/mcp/oauth/revoke",
                },
            ),
            (
                200,
                {
                    "access_token": "collector-access",
                    "refresh_token": "collector-refresh",
                    "expires_in": 3600,
                    "scope": "conversations.read conversations.write conversations.delete",
                },
            ),
        ]
        with patch("memova_collector.oauth._json_request", side_effect=responses) as request:
            result = oauth.connect_with_pairing(
                pairing_grant="one-use-grant",
                device_id="device-0001",
            )

        self.assertTrue(result["paired_via_mcp"])
        exchange = request.call_args_list[2]
        self.assertTrue(exchange.args[0].endswith("/conversation-sync/pairing-token"))
        self.assertEqual(exchange.kwargs["payload"]["pairing_grant"], "one-use-grant")
        self.assertNotEqual(
            exchange.kwargs["payload"]["code_verifier"], prepared["code_challenge"]
        )
        stored = json.loads(store.get(oauth.account) or "{}")
        self.assertEqual(stored["access_token"], "collector-access")
        self.assertEqual(stored["device_id"], "device-0001")
        self.assertNotIn("pairing_grant", stored)
        self.assertNotIn("pairing_verifier", stored)

    def test_connect_reuses_existing_secure_authorization_without_browser(self) -> None:
        oauth = self._oauth(MemoryCredentialStore())
        with patch("memova_collector.oauth._json_request") as request:
            result = oauth.connect()

        self.assertEqual(result["status"], "already_connected")
        self.assertIsNone(result["authorization_url"])
        request.assert_not_called()

    def test_expired_access_token_refreshes_and_rotates_stored_refresh_token(self) -> None:
        store = MemoryCredentialStore()
        oauth = self._oauth(store, expires_at=100)
        with patch(
            "memova_collector.oauth._json_request",
            return_value=(
                200,
                {
                    "access_token": "access-new",
                    "refresh_token": "refresh-new",
                    "expires_in": 3600,
                    "scope": "conversations.read conversations.write conversations.delete",
                },
            ),
        ) as request:
            token = oauth.access_token()

        self.assertEqual(token, "access-new")
        stored = json.loads(store.get(oauth.account) or "{}")
        self.assertEqual(stored["refresh_token"], "refresh-new")
        self.assertEqual(request.call_args.kwargs["form"]["resource"], stored["resource"])

    def test_refresh_revokes_new_tokens_if_secure_storage_fails(self) -> None:
        class FailingStore(MemoryCredentialStore):
            fail_writes = False

            def set(self, account: str, secret: str) -> None:
                if self.fail_writes:
                    raise RuntimeError("synthetic credential-store failure")
                super().set(account, secret)

        store = FailingStore()
        oauth = self._oauth(store, expires_at=100)
        store.fail_writes = True
        with patch(
            "memova_collector.oauth._json_request",
            side_effect=[
                (
                    200,
                    {
                        "access_token": "access-new",
                        "refresh_token": "refresh-new",
                        "expires_in": 3600,
                    },
                ),
                (200, {}),
                (200, {}),
            ],
        ) as request:
            with self.assertRaisesRegex(RuntimeError, "could not be stored securely"):
                oauth.access_token()

        self.assertIsNone(store.get(oauth.account))
        self.assertEqual(request.call_count, 3)

    def test_disconnect_retains_credential_when_server_revocation_fails(self) -> None:
        store = MemoryCredentialStore()
        oauth = self._oauth(store)

        with patch(
            "memova_collector.oauth._json_request",
            side_effect=OSError("synthetic offline"),
        ):
            with self.assertRaisesRegex(RuntimeError, "retained securely"):
                oauth.disconnect()

        self.assertIsNotNone(store.get(oauth.account))

    def test_disconnect_deletes_credential_only_after_all_tokens_are_revoked(self) -> None:
        store = MemoryCredentialStore()
        oauth = self._oauth(store)

        with patch(
            "memova_collector.oauth._json_request",
            side_effect=[(200, {}), (200, {})],
        ) as request:
            result = oauth.disconnect()

        self.assertEqual(request.call_count, 2)
        self.assertTrue(result["server_token_revocation_completed"])
        self.assertIsNone(store.get(oauth.account))

    def test_rest_sink_registers_consent_and_requires_matching_server_ack(self) -> None:
        oauth = self._oauth(MemoryCredentialStore())
        consent = {
            "schema_version": "memova_conversation_sync_consent_v1",
            "consent_id": "consent-0001",
            "device_id": "device-0001",
            "accepted_at": "2026-08-11T00:00:00Z",
            "status": "active",
            "memova_account_hint": None,
            "policy": {"schema_version": "memova_conversation_collection_policy_v1"},
            "retention_mode": "until_user_or_account_deletion",
        }
        batch = {
            "batch_id": "codex-batch-0001",
            "idempotency_key": "codex-conversations:" + "a" * 64,
        }
        responses = [
            (200, {"consent_id": "consent-0001", "status": "active"}),
            (
                202,
                {
                    "status": "accepted",
                    "batch_id": batch["batch_id"],
                    "idempotency_key": batch["idempotency_key"],
                    "archive_status": "durable",
                },
            ),
        ]
        with patch("memova_collector.sinks._json_request", side_effect=responses) as request:
            ack = RestSink(
                api_base="https://api.memova.test",
                oauth=oauth,
                consent=consent,
            ).send(batch)

        self.assertEqual(ack["status"], "accepted")
        self.assertEqual(request.call_count, 2)
        self.assertTrue(request.call_args_list[0].args[0].endswith("/consents"))
        self.assertTrue(request.call_args_list[1].args[0].endswith("/batches"))

    def test_rest_sink_refreshes_once_after_401(self) -> None:
        oauth = self._oauth(MemoryCredentialStore())
        consent = {"status": "active"}
        sink = RestSink(
            api_base="https://api.memova.test",
            oauth=oauth,
            consent=consent,
        )
        sink._consent_registered = True
        batch = {"batch_id": "batch", "idempotency_key": "key"}
        accepted = {
            "status": "accepted",
            "batch_id": "batch",
            "idempotency_key": "key",
            "archive_status": "durable",
        }
        with (
            patch.object(oauth, "access_token", side_effect=["old", "new"]) as token,
            patch(
                "memova_collector.sinks._json_request",
                side_effect=[OAuthHttpError(401, {}), (202, accepted)],
            ),
        ):
            self.assertEqual(sink.send(batch), accepted)
        token.assert_called_with(force_refresh=True)

    def test_rest_sink_rejects_ack_without_durable_archive_confirmation(self) -> None:
        oauth = self._oauth(MemoryCredentialStore())
        sink = RestSink(
            api_base="https://api.memova.test",
            oauth=oauth,
            consent={"status": "active"},
        )
        sink._consent_registered = True
        batch = {"batch_id": "batch", "idempotency_key": "key"}
        with patch(
            "memova_collector.sinks._json_request",
            return_value=(
                202,
                {"status": "accepted", "batch_id": "batch", "idempotency_key": "key"},
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "durable raw-archive"):
                sink.send(batch)

    def test_unknown_platform_has_no_plaintext_credential_fallback(self) -> None:
        with self.assertRaises(RuntimeError):
            system_credential_store("plan9")

    @unittest.skipUnless(platform.system() == "Darwin", "macOS Keychain test")
    def test_macos_keychain_uses_framework_without_token_in_process_arguments(self) -> None:
        with tempfile.TemporaryDirectory(prefix="memova-keychain-test-") as temp_dir:
            keychain_path = Path(temp_dir) / "collector-test.keychain-db"
            subprocess.run(
                [
                    "/usr/bin/security",
                    "create-keychain",
                    "-p",
                    "temporary-test-only",
                    str(keychain_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "/usr/bin/security",
                    "unlock-keychain",
                    "-p",
                    "temporary-test-only",
                    str(keychain_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            try:
                store = MacOSCredentialStore(keychain_path=str(keychain_path))
                secret = "token-material-never-passed-to-a-child-process"
                with patch("memova_collector.credentials.subprocess.run") as child_process:
                    store.set("collector-test-account", secret)
                    self.assertEqual(store.get("collector-test-account"), secret)
                    store.set("collector-test-account", f"{secret}-rotated")
                    self.assertEqual(
                        store.get("collector-test-account"), f"{secret}-rotated"
                    )
                    store.delete("collector-test-account")
                    self.assertIsNone(store.get("collector-test-account"))
                child_process.assert_not_called()
            finally:
                subprocess.run(
                    ["/usr/bin/security", "delete-keychain", str(keychain_path)],
                    check=False,
                    capture_output=True,
                    text=True,
                )


if __name__ == "__main__":
    unittest.main()
