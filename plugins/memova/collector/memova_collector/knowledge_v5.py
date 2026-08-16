from __future__ import annotations

import hashlib
import io
import ipaddress
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from .ledger import Ledger
from .oauth import CollectorOAuthClient, OAuthHttpError, _json_request

SYNC_PLAN_REQUEST_SCHEMA = "knowledge-sync-plan-request/v1"
SYNC_PLAN_SCHEMA = "knowledge-sync-plan/v1"
LEASE_SCHEMA = "knowledge-analyzer-lease/v1"
RUN_SCHEMA = "knowledge-analyzer-run/v1"
CHANGESET_SCHEMA = "knowledge-changeset/v1"
ACK_SCHEMA = "knowledge-changeset-ack/v1"

_MARKDOWN_DOCUMENT_HEADER_RE = re.compile(
    r"\A---\r?\n.*?\r?\n---(?:\r?\n|\Z)",
    re.DOTALL,
)


def analyzer_workspace_root(state_dir: Path) -> Path:
    return state_dir / "knowledge-v5" / "analyzer-workspaces"


def _open_request(request: urllib.request.Request, *, timeout: float):
    hostname = urllib.parse.urlsplit(request.full_url).hostname or ""
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
    return opener.open(request, timeout=timeout)


def _bytes_request(
    url: str,
    *,
    token: str,
    timeout: float = 60,
) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/zip",
            "Authorization": f"Bearer {token}",
        },
        method="GET",
    )
    try:
        with _open_request(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            details = json.loads(body) if body else {}
        except json.JSONDecodeError:
            details = {"message": body[:1000]}
        raise OAuthHttpError(exc.code, details) from exc


class KnowledgeV5ApiClient:
    def __init__(
        self,
        *,
        api_base: str,
        oauth: CollectorOAuthClient,
        json_request: Callable[..., tuple[int, dict[str, Any]]] = _json_request,
        bytes_request: Callable[..., bytes] = _bytes_request,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self.oauth = oauth
        self.json_request = json_request
        self.bytes_request = bytes_request

    def create_sync_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._json("POST", "/v1/knowledge-v5/sync-plans", payload)

    def acquire_lease(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._json("POST", "/v1/knowledge-v5/analyzer-leases", payload)

    def submit_changeset(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._json("POST", "/v1/knowledge-v5/changesets", payload)

    def get_run(self, analyzer_run_id: str) -> dict[str, Any]:
        return self._json("GET", f"/v1/knowledge-v5/runs/{analyzer_run_id}", None)

    def download_bundle(self, *, plan: dict[str, Any], lease_id: str) -> bytes:
        path = str(plan.get("bundle_download_path") or "")
        expected_prefix = f"/v1/knowledge-v5/bundles/{plan['bundle_revision']}"
        if path != expected_prefix:
            raise RuntimeError("Memova returned an unexpected Knowledge V5 Bundle path.")
        query = urllib.parse.urlencode(
            {"plan_id": plan["plan_id"], "lease_id": lease_id}
        )
        url = f"{self.api_base}{path}?{query}"
        token = self.oauth.access_token()
        try:
            return self.bytes_request(url, token=token)
        except OAuthHttpError as exc:
            if exc.status_code != 401:
                raise
        return self.bytes_request(
            url,
            token=self.oauth.access_token(force_refresh=True),
        )

    def _json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        token = self.oauth.access_token()
        try:
            _, response = self.json_request(
                f"{self.api_base}{path}",
                method=method,
                payload=payload,
                token=token,
            )
            return response
        except OAuthHttpError as exc:
            if exc.status_code != 401:
                raise
        _, response = self.json_request(
            f"{self.api_base}{path}",
            method=method,
            payload=payload,
            token=self.oauth.access_token(force_refresh=True),
        )
        return response


class KnowledgeV5StateStore:
    def __init__(self, state_dir: Path) -> None:
        self.root = state_dir / "knowledge-v5"
        self.path = self.root / "current-run.json"

    def load(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("state_schema") != 1:
            raise RuntimeError("Knowledge V5 local recovery state is unsupported.")
        return payload

    def save(self, payload: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            self.root.chmod(0o700)
        except OSError:
            pass
        handle, temporary_name = tempfile.mkstemp(
            prefix="current-run-",
            suffix=".tmp",
            dir=self.root,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as output:
                json.dump(payload, output, ensure_ascii=False, sort_keys=True)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            try:
                temporary.chmod(0o600)
            except OSError:
                pass
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)


class CodexKnowledgeV5Runner:
    def __init__(
        self,
        *,
        state_dir: Path,
        codex_path: str | None = None,
        process_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        timeout_seconds: int = 25 * 60,
    ) -> None:
        self.workspace_root = analyzer_workspace_root(state_dir)
        self.codex_path = codex_path or "codex"
        self.process_runner = process_runner
        self.timeout_seconds = timeout_seconds

    def analyze(
        self,
        *,
        bundle: bytes,
        plan: dict[str, Any],
        lease_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._verify_bundle_bytes(bundle, plan)
        run_id = str(plan["analyzer_run_id"])
        workspace = self.workspace_root / run_id
        self._prepare_workspace(workspace)
        try:
            self._extract_bundle(bundle, workspace)
            output_path = workspace / "changeset.json"
            schema_path = workspace / "contracts" / "changeset-v1.schema.json"
            command = [
                self.codex_path,
                "exec",
                "--ephemeral",
                "--ignore-user-config",
                "--ignore-rules",
                "--disable",
                "plugins",
                "--disable",
                "remote_plugin",
                "--disable",
                "recommended_plugins",
                "--disable",
                "apps",
                "--disable",
                "enable_mcp_apps",
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "--color",
                "never",
                "--cd",
                str(workspace),
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
                "-",
            ]
            prompt = self._prompt(
                plan=plan,
                lease_id=lease_id,
                idempotency_key=idempotency_key,
            )
            completed = self.process_runner(
                command,
                input=prompt,
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    f"Local Codex Knowledge V5 analysis failed with exit code "
                    f"{completed.returncode}; it will be retried."
                )
            if not output_path.exists():
                raise RuntimeError("Local Codex analysis did not produce a changeset.")
            changeset = json.loads(output_path.read_text(encoding="utf-8"))
            _normalize_changeset_content_hashes(changeset)
            _validate_changeset(
                changeset,
                plan=plan,
                lease_id=lease_id,
                idempotency_key=idempotency_key,
            )
            return changeset
        finally:
            self._remove_workspace(workspace)

    @staticmethod
    def _verify_bundle_bytes(bundle: bytes, plan: dict[str, Any]) -> None:
        if len(bundle) != int(plan["bundle_byte_size"]):
            raise RuntimeError("Knowledge V5 Bundle byte size does not match the sync plan.")
        actual_hash = hashlib.sha256(bundle).hexdigest()
        if actual_hash != plan["bundle_sha256"]:
            raise RuntimeError("Knowledge V5 Bundle hash does not match the sync plan.")

    def _prepare_workspace(self, workspace: Path) -> None:
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        try:
            self.workspace_root.chmod(0o700)
        except OSError:
            pass
        self._remove_workspace(workspace)
        workspace.mkdir(mode=0o700)

    def _remove_workspace(self, workspace: Path) -> None:
        if workspace.parent != self.workspace_root:
            raise RuntimeError("Refused to remove a path outside the analyzer workspace root.")
        if workspace.exists():
            shutil.rmtree(workspace)

    @staticmethod
    def _extract_bundle(bundle: bytes, workspace: Path) -> None:
        required = {
            "SKILL.md",
            "bundle.json",
            "contracts/changeset-v1.schema.json",
            "wiki-index.md",
        }
        extracted: set[str] = set()
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            for info in archive.infolist():
                path = PurePosixPath(info.filename)
                if path.is_absolute() or ".." in path.parts or not path.parts:
                    raise RuntimeError("Knowledge V5 Bundle contains an unsafe path.")
                if info.compress_type != zipfile.ZIP_STORED:
                    raise RuntimeError(
                        "Knowledge V5 Bundle must use the server's stored ZIP format."
                    )
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise RuntimeError("Knowledge V5 Bundle cannot contain symbolic links.")
                destination = workspace.joinpath(*path.parts)
                if info.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                if path.as_posix() in extracted:
                    raise RuntimeError("Knowledge V5 Bundle contains a duplicate file path.")
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.read(info))
                extracted.add(path.as_posix())
        missing = sorted(required - extracted)
        if missing:
            raise RuntimeError(f"Knowledge V5 Bundle is incomplete: {missing}")

    @staticmethod
    def _prompt(
        *,
        plan: dict[str, Any],
        lease_id: str,
        idempotency_key: str,
    ) -> str:
        return (
            "Analyze this authorized Memova Knowledge V5 Wiki Bundle. Read SKILL.md, "
            "bundle.json, wiki-index.md, and the declared changed-thread inputs. Do not use "
            "the network and do not modify Bundle files. Return only one JSON changeset that "
            "matches contracts/changeset-v1.schema.json. Use these exact envelope values:\n"
            f"analyzer_run_id={plan['analyzer_run_id']}\n"
            f"plan_id={plan['plan_id']}\n"
            f"lease_id={lease_id}\n"
            f"idempotency_key={idempotency_key}\n"
            f"base_bundle_revision={plan['bundle_revision']}\n"
            "Authorized work_items="
            + json.dumps(plan.get("work_items", []), ensure_ascii=False, sort_keys=True)
        )


class KnowledgeV5AnalyzerLoop:
    def __init__(
        self,
        *,
        client: KnowledgeV5ApiClient,
        runner: CodexKnowledgeV5Runner,
        ledger: Ledger,
        state_dir: Path,
        device_id: str,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.client = client
        self.runner = runner
        self.ledger = ledger
        self.store = KnowledgeV5StateStore(state_dir)
        self.device_id = device_id
        self.clock = clock

    def has_pending_run(self) -> bool:
        return self.store.path.exists()

    def run_once(self, *, trigger: bool) -> dict[str, Any]:
        try:
            return self._run_once(trigger=trigger)
        except OAuthHttpError as exc:
            if exc.status_code != 404:
                raise
            return {
                "status": "unavailable",
                "reason": "server_rollout_disabled_or_not_deployed",
                "retry_required": True,
                "resume_pending": self.has_pending_run(),
            }

    def _run_once(self, *, trigger: bool) -> dict[str, Any]:
        state = self.store.load()
        if state is None:
            if not trigger:
                return {"status": "skipped", "reason": "no_archived_changes"}
            state = {
                "state_schema": 1,
                "plan_request": {
                    "schema_version": SYNC_PLAN_REQUEST_SCHEMA,
                    "device_id": self.device_id,
                    "idempotency_key": f"knowledge-v5-plan:{uuid.uuid4()}",
                    "checkpoint": self.ledger.get_metadata(
                        "knowledge_v5_server_checkpoint"
                    ),
                    "known_thread_revisions": [],
                },
            }
            self.store.save(state)

        plan = state.get("plan")
        if plan is None:
            plan = self.client.create_sync_plan(state["plan_request"])
            _validate_plan(plan, device_id=self.device_id)
            state["plan"] = plan
            self.store.save(state)

        if plan["status"] == "no_work":
            return self._finalize_no_work(plan)

        run = self.client.get_run(str(plan["analyzer_run_id"]))
        _validate_run(run, plan=plan)
        if run["status"] == "completed":
            ack = run.get("ack")
            if not isinstance(ack, dict):
                raise RuntimeError("Completed Knowledge V5 analyzer run has no durable ACK.")
            return self._finalize_ack(plan=plan, ack=ack)
        if run["status"] in {"failed", "expired"}:
            self.store.clear()
            raise RuntimeError(
                f"Knowledge V5 analyzer run became {run['status']}; the next sync will create "
                "a fresh plan."
            )
        if run["status"] == "committing" and not _is_expired(
            run.get("lease_expires_at"), self.clock()
        ):
            return {"status": "in_progress", "analyzer_run_id": plan["analyzer_run_id"]}

        lease = state.get("lease")
        lease = self._ensure_lease(plan=plan, lease=lease)
        state["lease"] = lease
        self.store.save(state)

        changeset = state.get("changeset")
        if changeset is None:
            changeset_idempotency_key = state.get("changeset_idempotency_key")
            if changeset_idempotency_key is None:
                changeset_idempotency_key = f"knowledge-v5-changeset:{uuid.uuid4()}"
                state["changeset_idempotency_key"] = changeset_idempotency_key
                self.store.save(state)
            bundle = self.client.download_bundle(
                plan=plan,
                lease_id=str(lease["lease_id"]),
            )
            changeset = self.runner.analyze(
                bundle=bundle,
                plan=plan,
                lease_id=str(lease["lease_id"]),
                idempotency_key=str(changeset_idempotency_key),
            )
            state["changeset"] = changeset
            self.store.save(state)

        lease = self._ensure_lease(plan=plan, lease=state.get("lease"))
        state["lease"] = lease
        changeset["lease_id"] = lease["lease_id"]
        _normalize_changeset_content_hashes(changeset)
        _validate_changeset(
            changeset,
            plan=plan,
            lease_id=str(lease["lease_id"]),
            idempotency_key=str(state["changeset_idempotency_key"]),
        )
        state["changeset"] = changeset
        self.store.save(state)
        ack = self.client.submit_changeset(changeset)
        return self._finalize_ack(plan=plan, ack=ack)

    def _ensure_lease(
        self,
        *,
        plan: dict[str, Any],
        lease: dict[str, Any] | None,
    ) -> dict[str, Any]:
        lease_id = None
        if isinstance(lease, dict) and not _is_expired(lease.get("expires_at"), self.clock()):
            lease_id = lease.get("lease_id")
        payload = {
            "schema_version": LEASE_SCHEMA,
            "device_id": self.device_id,
            "plan_id": plan["plan_id"],
            "lease_id": lease_id,
        }
        response = self.client.acquire_lease(payload)
        _validate_lease(response, plan=plan)
        return response

    def _finalize_no_work(self, plan: dict[str, Any]) -> dict[str, Any]:
        self.ledger.set_metadata("knowledge_v5_initialized", "true")
        self.ledger.set_metadata("knowledge_v5_last_analyzer_run_id", plan["analyzer_run_id"])
        self.ledger.set_metadata("knowledge_v5_retry_required", "false")
        self.store.clear()
        return {
            "status": "no_work",
            "analyzer_run_id": plan["analyzer_run_id"],
            "work_item_count": 0,
        }

    def _finalize_ack(
        self,
        *,
        plan: dict[str, Any],
        ack: dict[str, Any],
    ) -> dict[str, Any]:
        _validate_ack(
            ack,
            plan=plan,
            idempotency_key=str(self.store.load()["changeset_idempotency_key"]),
        )
        self.ledger.set_metadata("knowledge_v5_initialized", "true")
        self.ledger.set_metadata("knowledge_v5_server_checkpoint", ack["server_checkpoint"])
        self.ledger.set_metadata("knowledge_v5_last_analyzer_run_id", plan["analyzer_run_id"])
        counts: dict[str, int] = {"accepted": 0, "conflict": 0, "rejected": 0}
        for result in ack["results"]:
            counts[str(result["status"])] += 1
        self.ledger.set_metadata(
            "knowledge_v5_retry_required",
            "true" if counts["conflict"] else "false",
        )
        self.store.clear()
        return {
            "status": "completed",
            "analyzer_run_id": plan["analyzer_run_id"],
            "server_checkpoint": ack["server_checkpoint"],
            "results": counts,
        }


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise RuntimeError("Knowledge V5 server timestamp must include a timezone.")
    return parsed.astimezone(UTC)


def _is_expired(value: object, now: datetime) -> bool:
    parsed = _parse_datetime(value)
    return parsed is None or parsed <= now.astimezone(UTC)


def _require_uuid(value: object, field: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise RuntimeError(f"Knowledge V5 {field} must be a UUID.") from exc


def _validate_plan(plan: dict[str, Any], *, device_id: str) -> None:
    if plan.get("schema_version") != SYNC_PLAN_SCHEMA:
        raise RuntimeError("Memova returned an unsupported Knowledge V5 sync plan.")
    for field in ("analyzer_run_id", "plan_id", "bundle_revision"):
        _require_uuid(plan.get(field), field)
    if plan.get("status") not in {"planned", "no_work"}:
        raise RuntimeError("Memova returned an invalid Knowledge V5 plan status.")
    if not isinstance(plan.get("work_items"), list):
        raise RuntimeError("Memova returned invalid Knowledge V5 work items.")
    if plan["status"] == "no_work" and plan["work_items"]:
        raise RuntimeError("A no-work Knowledge V5 plan cannot contain work items.")
    _parse_datetime(plan.get("bundle_expires_at"))
    if not device_id:
        raise RuntimeError("Knowledge V5 requires a Collector device identity.")


def _validate_lease(lease: dict[str, Any], *, plan: dict[str, Any]) -> None:
    if lease.get("schema_version") != LEASE_SCHEMA:
        raise RuntimeError("Memova returned an unsupported Knowledge V5 analyzer lease.")
    if str(lease.get("analyzer_run_id")) != str(plan["analyzer_run_id"]):
        raise RuntimeError("Knowledge V5 lease analyzer_run_id does not match its plan.")
    if str(lease.get("plan_id")) != str(plan["plan_id"]):
        raise RuntimeError("Knowledge V5 lease plan_id does not match its plan.")
    _require_uuid(lease.get("lease_id"), "lease_id")
    _parse_datetime(lease.get("expires_at"))


def _validate_run(run: dict[str, Any], *, plan: dict[str, Any]) -> None:
    if run.get("schema_version") != RUN_SCHEMA:
        raise RuntimeError("Memova returned an unsupported Knowledge V5 analyzer run.")
    if str(run.get("analyzer_run_id")) != str(plan["analyzer_run_id"]):
        raise RuntimeError("Knowledge V5 analyzer run does not match its plan.")
    if str(run.get("plan_id")) != str(plan["plan_id"]):
        raise RuntimeError("Knowledge V5 analyzer run plan_id does not match its plan.")


def _normalize_changeset_content_hashes(changeset: object) -> None:
    """Own deterministic Markdown identity and transport hashes."""
    if not isinstance(changeset, dict):
        return
    object_changes = changeset.get("object_changes")
    if not isinstance(object_changes, list):
        return
    for change in object_changes:
        if not isinstance(change, dict):
            continue
        content = change.get("content")
        if isinstance(content, str):
            if change.get("canonical_format") == "markdown":
                identity_values = (
                    change.get("object_id"),
                    change.get("object_type"),
                    change.get("change_id")
                    if change.get("operation") == "create"
                    else change.get("expected_revision"),
                )
                if all(isinstance(value, str) and value for value in identity_values):
                    object_id, object_type, revision = identity_values
                    body = _MARKDOWN_DOCUMENT_HEADER_RE.sub("", content, count=1)
                    content = (
                        "---\n"
                        "memova_schema: knowledge-object/v1\n"
                        f"object_id: {object_id}\n"
                        f"object_type: {object_type}\n"
                        f"revision: {revision}\n"
                        "---\n"
                        f"{body}"
                    )
                    change["content"] = content
            change["content_sha256"] = hashlib.sha256(content.encode("utf-8")).hexdigest()


def _validate_changeset(
    changeset: dict[str, Any],
    *,
    plan: dict[str, Any],
    lease_id: str,
    idempotency_key: str,
) -> None:
    if not isinstance(changeset, dict) or changeset.get("schema_version") != CHANGESET_SCHEMA:
        raise RuntimeError("Local Codex returned an unsupported Knowledge V5 changeset.")
    expected = {
        "analyzer_run_id": plan["analyzer_run_id"],
        "plan_id": plan["plan_id"],
        "lease_id": lease_id,
        "idempotency_key": idempotency_key,
        "base_bundle_revision": plan["bundle_revision"],
    }
    for field, value in expected.items():
        if str(changeset.get(field)) != str(value):
            raise RuntimeError(f"Knowledge V5 changeset {field} does not match its plan.")
    object_changes = changeset.get("object_changes")
    if not isinstance(object_changes, list):
        raise RuntimeError("Knowledge V5 changeset object_changes must be a list.")
    change_ids: set[str] = set()
    object_ids: set[str] = set()
    for change in object_changes:
        if not isinstance(change, dict):
            raise RuntimeError("Knowledge V5 object change must be an object.")
        change_id = _require_uuid(change.get("change_id"), "change_id")
        object_id = _require_uuid(change.get("object_id"), "object_id")
        if change_id in change_ids or object_id in object_ids:
            raise RuntimeError("Knowledge V5 changeset contains duplicate changes.")
        change_ids.add(change_id)
        object_ids.add(object_id)
        content = change.get("content")
        if not isinstance(content, str):
            raise RuntimeError("Knowledge V5 object change content must be text.")
        if hashlib.sha256(content.encode("utf-8")).hexdigest() != change.get(
            "content_sha256"
        ):
            raise RuntimeError("Knowledge V5 object change content hash is invalid.")


def _validate_ack(
    ack: dict[str, Any],
    *,
    plan: dict[str, Any],
    idempotency_key: str,
) -> None:
    if ack.get("schema_version") != ACK_SCHEMA:
        raise RuntimeError("Memova returned an unsupported Knowledge V5 ACK.")
    if str(ack.get("analyzer_run_id")) != str(plan["analyzer_run_id"]):
        raise RuntimeError("Knowledge V5 ACK analyzer_run_id does not match its plan.")
    bundle_revision = _require_uuid(ack.get("bundle_revision"), "ACK bundle_revision")
    if str(ack.get("idempotency_key")) != idempotency_key:
        raise RuntimeError("Knowledge V5 ACK idempotency key does not match its changeset.")
    expected_checkpoint = f"v5:{plan['analyzer_run_id']}:{bundle_revision}"
    if ack.get("server_checkpoint") != expected_checkpoint:
        raise RuntimeError(
            "Knowledge V5 ACK checkpoint does not match its new Bundle revision."
        )
    if not isinstance(ack.get("results"), list):
        raise RuntimeError("Knowledge V5 ACK results must be a list.")
    for result in ack["results"]:
        if not isinstance(result, dict) or result.get("status") not in {
            "accepted",
            "conflict",
            "rejected",
        }:
            raise RuntimeError("Knowledge V5 ACK contains an invalid object result.")
