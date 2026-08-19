#!/usr/bin/env python3
"""Run a content-safe Collector restart/idempotency soak on one native OS device."""

from __future__ import annotations

import argparse
import json
import platform
import secrets
import tempfile
import time
from pathlib import Path

from memova_collector.credentials import system_credential_store
from memova_collector.fixtures import FixtureThreadSource
from memova_collector.ledger import Ledger
from memova_collector.sinks import FailingSink, MockSink
from memova_collector.sync import SyncEngine

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def _run_engine(*, state_dir: Path, fixture: Path, device_id: str, sink) -> dict:
    with Ledger(state_dir / "collector.sqlite3") as ledger:
        return SyncEngine(
            source=FixtureThreadSource(fixture),
            ledger=ledger,
            sink=sink,
            consent_id=f"soak-consent-{device_id}",
            device_id=device_id,
        ).run_once()


def _native_credential_roundtrip(device_id: str) -> None:
    store = system_credential_store()
    account = f"soak:{device_id}:{secrets.token_hex(8)}"
    first = secrets.token_urlsafe(48)
    second = secrets.token_urlsafe(48)
    try:
        store.set(account, first)
        if store.get(account) != first:
            raise RuntimeError("native credential store did not return the first value")
        store.set(account, second)
        if store.get(account) != second:
            raise RuntimeError("native credential store did not return the rotated value")
    finally:
        store.delete(account)
    if store.get(account) is not None:
        raise RuntimeError("native credential store retained the deleted test credential")


def run_soak(*, cycles: int, interval_seconds: float, device_id: str) -> dict:
    if cycles < 4:
        raise ValueError("cycles must be at least 4")
    started = time.monotonic()
    _native_credential_roundtrip(device_id)
    changed_cycle = cycles // 2
    acknowledged_batches = 0
    no_op_cycles = 0
    with tempfile.TemporaryDirectory(prefix=f"memova-soak-{device_id}-") as temp_dir:
        state_dir = Path(temp_dir) / "state"
        state_dir.mkdir(parents=True)
        first = _run_engine(
            state_dir=state_dir,
            fixture=FIXTURES / "app-server-history-v1.json",
            device_id=device_id,
            sink=MockSink(),
        )
        if first["changed_message_count"] != 7 or first["acknowledged_batch_count"] != 1:
            raise RuntimeError("initial synthetic history was not fully acknowledged")
        acknowledged_batches += int(first["acknowledged_batch_count"])

        try:
            _run_engine(
                state_dir=state_dir,
                fixture=FIXTURES / "app-server-history-v2.json",
                device_id=device_id,
                sink=FailingSink("synthetic pre-restart interruption"),
            )
        except RuntimeError as exc:
            if "synthetic pre-restart interruption" not in str(exc):
                raise
        else:
            raise RuntimeError("synthetic interrupted delivery unexpectedly succeeded")

        recovered = _run_engine(
            state_dir=state_dir,
            fixture=FIXTURES / "app-server-history-v2.json",
            device_id=device_id,
            sink=MockSink(),
        )
        if recovered["acknowledged_batch_count"] != 1:
            raise RuntimeError("durable outbox did not recover after process restart")
        acknowledged_batches += int(recovered["acknowledged_batch_count"])

        for cycle in range(2, cycles):
            fixture = (
                FIXTURES / "app-server-history-v1.json"
                if cycle < changed_cycle
                else FIXTURES / "app-server-history-v2.json"
            )
            result = _run_engine(
                state_dir=state_dir,
                fixture=fixture,
                device_id=device_id,
                sink=MockSink(),
            )
            acknowledged_batches += int(result["acknowledged_batch_count"])
            if result["staged_batch_count"] == 0:
                no_op_cycles += 1
            if interval_seconds:
                time.sleep(interval_seconds)

        with Ledger(state_dir / "collector.sqlite3") as ledger:
            status = ledger.status()
        if status["pending_batch_count"] != 0:
            raise RuntimeError("soak ended with a pending durable outbox batch")
        if status["acknowledged_item_count"] != 7:
            raise RuntimeError("incremental edit/delete reconciliation changed the item cardinality")
        if no_op_cycles < 1:
            raise RuntimeError("soak did not prove an idempotent no-op cycle")

    return {
        "schema_version": "memova_collector_multiplatform_soak_v1",
        "status": "passed",
        "platform": platform.system().lower(),
        "device_id": device_id,
        "cycles": cycles,
        "no_op_cycles": no_op_cycles,
        "acknowledged_batches": acknowledged_batches,
        "native_credential_roundtrip": "passed",
        "synthetic_content_only": True,
        "remote_upload_performed": False,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycles", type=int, default=12)
    parser.add_argument("--interval-seconds", type=float, default=1.0)
    parser.add_argument("--device-id", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            run_soak(
                cycles=args.cycles,
                interval_seconds=args.interval_seconds,
                device_id=args.device_id,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
