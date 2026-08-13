from __future__ import annotations

from collections import Counter
from typing import Any

from .contracts import ALLOWED_ITEM_TYPES, EXCLUDED_ITEM_TYPES, sha256_json
from .project_context import build_project_context


def _thread_source_kind(thread: dict[str, Any]) -> str:
    source = thread.get("source")
    if isinstance(source, dict):
        kind = source.get("kind")
        if isinstance(kind, str):
            return kind
    for key in ("sourceKind", "source_kind"):
        if isinstance(thread.get(key), str):
            return str(thread[key])
    return "unknown"


def _user_text_blocks(item: dict[str, Any], diagnostics: Counter[str]) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    content = item.get("content")
    if not isinstance(content, list):
        diagnostics["malformed_user_message"] += 1
        return blocks
    for part in content:
        if not isinstance(part, dict):
            diagnostics["excluded_non_text_part"] += 1
            continue
        if part.get("type") == "text" and isinstance(part.get("text"), str):
            blocks.append({"type": "text", "text": part["text"]})
        else:
            diagnostics["excluded_non_text_part"] += 1
    return blocks


def _agent_text_blocks(item: dict[str, Any], diagnostics: Counter[str]) -> list[dict[str, str]]:
    text = item.get("text")
    if not isinstance(text, str):
        diagnostics["malformed_agent_message"] += 1
        return []
    return [{"type": "text", "text": text}]


def extract_thread(
    thread: dict[str, Any],
    *,
    archived: bool | None = None,
    project_fingerprint_secret: str | None = None,
    workspace_repository_fingerprint_key: str | None = None,
    project_context_mode: str = "disabled",
) -> tuple[dict[str, Any], dict[str, int]]:
    """Extract only user-visible text messages from a ThreadRead response."""

    diagnostics: Counter[str] = Counter()
    messages: list[dict[str, Any]] = []
    turns = thread.get("turns")
    if not isinstance(turns, list):
        turns = []
        diagnostics["missing_turns"] += 1

    sequence = 0
    for turn_index, turn in enumerate(turns):
        if not isinstance(turn, dict):
            diagnostics["malformed_turn"] += 1
            continue
        turn_id = str(turn.get("id") or f"turn-{turn_index}")
        items = turn.get("items")
        if not isinstance(items, list):
            diagnostics["malformed_turn_items"] += 1
            continue
        for item_index, item in enumerate(items):
            if not isinstance(item, dict):
                diagnostics["malformed_item"] += 1
                continue
            item_type = item.get("type")
            if item_type not in ALLOWED_ITEM_TYPES:
                if item_type in EXCLUDED_ITEM_TYPES:
                    diagnostics[f"excluded_{item_type}"] += 1
                else:
                    diagnostics["excluded_unknown_item_type"] += 1
                continue
            item_id = str(item.get("id") or f"{turn_id}-item-{item_index}")
            if item_type == "userMessage":
                role = "user"
                phase = None
                blocks = _user_text_blocks(item, diagnostics)
            else:
                role = "assistant"
                raw_phase = item.get("phase")
                phase = raw_phase if raw_phase in {"commentary", "final_answer"} else "unknown"
                blocks = _agent_text_blocks(item, diagnostics)
            if not blocks:
                diagnostics["excluded_empty_message"] += 1
                continue
            message_identity = {
                "turn_id": turn_id,
                "item_id": item_id,
                "role": role,
                "phase": phase,
                "content": blocks,
            }
            messages.append(
                {
                    "operation": "upsert",
                    "external_item_id": item_id,
                    "external_turn_id": turn_id,
                    "sequence": sequence,
                    "turn_sequence": turn_index,
                    "item_sequence": item_index,
                    "role": role,
                    "phase": phase,
                    "content": blocks,
                    "content_hash": sha256_json(message_identity),
                },
            )
            sequence += 1

    thread_id = str(thread.get("id") or thread.get("threadId") or "")
    result = {
        "external_thread_id": thread_id,
        "title": thread.get("title") or thread.get("name"),
        "source_kind": _thread_source_kind(thread),
        "created_at": thread.get("createdAt") or thread.get("created_at"),
        "updated_at": thread.get("updatedAt") or thread.get("updated_at"),
        "archived": bool(thread.get("archived") if archived is None else archived),
        "messages": messages,
    }
    project_context = build_project_context(
        thread,
        fingerprint_secret=(
            project_fingerprint_secret if project_context_mode != "disabled" else None
        ),
        workspace_fingerprint_key=(
            workspace_repository_fingerprint_key
            if project_context_mode != "disabled"
            else None
        ),
        include_observations=project_context_mode == "full",
    )
    if project_context is not None:
        result["project_context"] = project_context
    result["thread_hash"] = sha256_json(
        {
            "external_thread_id": thread_id,
            "title": result["title"],
            "updated_at": result["updated_at"],
            "archived": result["archived"],
            "project_context": project_context,
            "messages": messages,
        },
    )
    return result, dict(diagnostics)
