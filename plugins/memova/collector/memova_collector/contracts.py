from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

COLLECTOR_VERSION = "1.2.0"
BATCH_SCHEMA_VERSION = "memova_external_conversation_batch_v2"
ACK_SCHEMA_VERSION = "memova_external_conversation_batch_ack_v1"
CONSENT_SCHEMA_VERSION = "memova_conversation_sync_consent_v1"
STATUS_SCHEMA_VERSION = "memova_conversation_sync_status_v1"
DELETE_SCHEMA_VERSION = "memova_external_conversation_delete_v1"
HOOK_HINT_SCHEMA_VERSION = "memova_codex_hook_hint_v1"

ALLOWED_ITEM_TYPES = frozenset({"userMessage", "agentMessage"})
EXCLUDED_ITEM_TYPES = frozenset(
    {
        "reasoning",
        "commandExecution",
        "fileChange",
        "mcpToolCall",
        "dynamicToolCall",
        "collabAgentToolCall",
        "plan",
        "contextCompaction",
        "hookPrompt",
    },
)
ALLOWED_SOURCE_KINDS = ("cli", "vscode", "exec", "appServer", "unknown")


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def default_collection_policy(*, include_project_context: bool = False) -> dict[str, Any]:
    """The fail-closed M0 policy shown during consent and enforced locally."""

    return {
        "schema_version": "memova_conversation_collection_policy_v1",
        "purpose": "private_memova_archive_and_user_requested_knowledge_derivation",
        "included": {
            "item_types": sorted(ALLOWED_ITEM_TYPES),
            "agent_message_phases": ["commentary", "final_answer", "unknown"],
            "thread_sets": ["active", "archived"],
            "content": ["user_visible_text"],
            "project_context": (
                "privacy_safe_repository_context_v1"
                if include_project_context
                else "disabled"
            ),
        },
        "excluded": {
            "item_types": sorted(EXCLUDED_ITEM_TYPES),
            "content": [
                "system_messages",
                "developer_messages",
                "hidden_reasoning",
                "tool_calls_and_results",
                "terminal_output",
                "file_change_payloads",
                "file_bodies",
                "binary_attachments",
                "subagent_traces",
                "secrets_detected_outside_user_visible_messages",
                "absolute_working_paths",
                "repository_remote_urls",
                "repository_commit_shas",
            ],
        },
        "controls": [
            "explicit_full_history_opt_in",
            "retention_until_user_or_account_deletion",
            "preview_before_first_sync",
            "pause",
            "resume",
            "disconnect",
            "delete_by_thread",
            "delete_by_device",
            "delete_all",
        ],
        "transport": {
            "codex_app_server": "local_stdio_only",
            "hooks": "content_free_latency_hints_only",
            "scheduler": "optional_user_scoped_incremental_rest_sync",
            "remote_upload": "oauth_pkce_with_server_ack",
        },
    }


def build_consent_record(
    *,
    consent_id: str,
    device_id: str,
    memova_account_hint: str | None = None,
    accepted_at: str | None = None,
    include_project_context: bool = False,
) -> dict[str, Any]:
    return {
        "schema_version": CONSENT_SCHEMA_VERSION,
        "consent_id": consent_id,
        "device_id": device_id,
        "accepted_at": accepted_at or utc_now(),
        "status": "active",
        "memova_account_hint": memova_account_hint,
        "policy": default_collection_policy(
            include_project_context=include_project_context,
        ),
        "retention_mode": "until_user_or_account_deletion",
    }


def build_batch(
    *,
    consent_id: str,
    device_id: str,
    delivery_target: str,
    threads: list[dict[str, Any]],
    diagnostics: dict[str, int] | None = None,
) -> dict[str, Any]:
    identity_material = {
        "schema_version": BATCH_SCHEMA_VERSION,
        "consent_id": consent_id,
        "device_id": device_id,
        "delivery_target": delivery_target,
        "threads": threads,
    }
    digest = sha256_json(identity_material)
    return {
        **identity_material,
        "batch_id": f"codex-{digest[:32]}",
        "idempotency_key": f"codex-conversations:{digest}",
        "collector_version": COLLECTOR_VERSION,
        "generated_at": utc_now(),
        "diagnostics": diagnostics or {},
    }


def build_ack(batch: dict[str, Any]) -> dict[str, Any]:
    messages = [
        message
        for thread in batch.get("threads", [])
        for message in thread.get("messages", [])
    ]
    return {
        "schema_version": ACK_SCHEMA_VERSION,
        "batch_id": batch["batch_id"],
        "idempotency_key": batch["idempotency_key"],
        "status": "accepted",
        "accepted_item_count": len(messages),
        "rejected_items": [],
        "acknowledged_at": utc_now(),
        "archive_status": "durable",
    }
