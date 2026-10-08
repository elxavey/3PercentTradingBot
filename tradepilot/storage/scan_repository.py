"""Persist and recover completed scanner outcomes without Streamlit.

Each scan and its candidate/telemetry rows commit atomically. No raw price
history, credentials or executable broker orders are stored.
"""
from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from tradepilot.core.scanner_service import ScanOutcome
from .database import DEFAULT_DB_PATH, database_connection, initialize_database


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _json_default(value):
    # Support numpy/pandas scalar values produced by indicator calculations.
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise TypeError("Naive datetime cannot be serialized as an observation")
        return value.astimezone(timezone.utc).isoformat()
    raise TypeError(f"Not JSON serializable: {type(value).__name__}")


def _json(value) -> str:
    return json.dumps(value, default=_json_default, allow_nan=False, sort_keys=True)


def _finite(value):
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


@dataclass(frozen=True)
class StoredScan:
    id: str
    universe_name: str
    started_at_utc: str
    finished_at_utc: str | None
    status: str
    discovered_count: int
    pre_screen_count: int
    quality_pass_count: int
    elapsed_seconds: float
    config_snapshot: dict
    results: list[dict]
    discovery: dict | None
    pre_screen: dict
    timing: dict
    excluded: list


def save_scan(
    outcome: ScanOutcome,
    *,
    universe_name: str,
    config_snapshot: dict,
    db_path: str | Path = DEFAULT_DB_PATH,
    scan_id: str | None = None,
    job_run_id: str | None = None,
) -> str:
    """Atomically save a completed scan, candidates and execution telemetry.

    Does not overwrite existing scan IDs. Errors propagate so callers can show
    a warning; a failed write cannot leave a partial scan.
    """
    if not universe_name.strip():
        raise ValueError("universe_name is required")
    if not isinstance(config_snapshot, dict):
        raise TypeError("config_snapshot must be a dict")
    scan_id = scan_id or str(uuid4())
    # Serialize before opening the transaction, including nested numpy scalars.
    results = outcome.results
    discovery = outcome.discovery_result
    pre = outcome.universe_result
    excluded = pre.get("excluded", [])
    timing = {
        "scan_seconds": outcome.scan_seconds,
        "discovery_seconds": (discovery or {}).get("seconds", 0),
        "pre_screen_seconds": pre.get("seconds", 0),
        "history_cache_hits": pre.get("history_cache_hits", 0),
        "metadata_seconds": sum((r.get("timing") or {}).get("metadata_seconds", 0) for r in results),
        "metadata_cache_hits": sum(bool((r.get("timing") or {}).get("metadata_cache_hit")) for r in results),
        "history_reused": sum(bool((r.get("timing") or {}).get("history_reused")) for r in results),
        "per_symbol": {r["ticker"]: r.get("timing", {}) for r in results},
    }
    candidate_rows = []
    for r in results:
        symbol = r["ticker"]
        gate = r.get("quality_gate") or {}
        market = gate.get("market") or ("MX" if symbol.upper().endswith(".MX") else "US")
        opportunity = r.get("opportunity") or {}
        candidate_rows.append((
            scan_id, symbol, market, "MXN" if market == "MX" else "USD",
            int(bool(gate.get("passed"))),
            _finite(opportunity.get("score")), _finite(r.get("score")),
            _utc_now(), None, _finite(r.get("price")), _json(r),
        ))
    serialized_config = _json(config_snapshot)
    serialized_discovery = _json(discovery)
    serialized_pre = _json({
        "total": pre.get("total", 0),
        "passed_symbols": [row["ticker"] for row in pre.get("passed", [])],
        "seconds": pre.get("seconds", 0),
        "history_cache_hits": pre.get("history_cache_hits", 0),
    })
    serialized_excluded = _json(excluded)
    serialized_timing = _json(timing)
    discovered_count = int((discovery or {}).get("discovered", pre.get("total", 0)))
    pre_screen_count = len(pre.get("passed", []))
    quality_pass_count = sum(bool((r.get("quality_gate") or {}).get("passed")) for r in results)
    finished_dt = datetime.now(timezone.utc)
    finished = finished_dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    started = (finished_dt - timedelta(seconds=float(outcome.scan_seconds))).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")

    initialize_database(db_path)
    with database_connection(db_path) as conn:
        conn.execute(
            """INSERT INTO scan_runs
            (id,job_run_id,universe_name,started_at_utc,finished_at_utc,status,
             discovered_count,pre_screen_count,quality_pass_count,elapsed_seconds,
             config_snapshot_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (scan_id, job_run_id, universe_name, started, finished, "SUCCEEDED",
             discovered_count, pre_screen_count, quality_pass_count,
             float(outcome.scan_seconds), serialized_config),
        )
        conn.executemany(
            """INSERT INTO scan_candidates
            (scan_run_id,symbol,exchange_code,currency,quality_pass,opportunity_score,
             legacy_score,observed_at_utc,price_source,price,raw_result_json)
             VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            candidate_rows,
        )
        conn.execute(
            """INSERT INTO scan_run_telemetry
            (scan_run_id,discovery_json,pre_screen_json,timing_json,excluded_json)
            VALUES (?,?,?,?,?)""",
            (scan_id, serialized_discovery, serialized_pre, serialized_timing, serialized_excluded),
        )
    return scan_id


def get_scan(scan_id: str, *, db_path: str | Path = DEFAULT_DB_PATH) -> StoredScan | None:
    """Recover a persisted scan and all its ranked candidates."""
    initialize_database(db_path)
    with database_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM scan_runs WHERE id = ?", (scan_id,)).fetchone()
        if row is None:
            return None
        candidates = conn.execute(
            """SELECT raw_result_json FROM scan_candidates
               WHERE scan_run_id = ?
               ORDER BY quality_pass DESC, opportunity_score DESC, symbol""",
            (scan_id,),
        ).fetchall()
        telemetry = conn.execute(
            "SELECT * FROM scan_run_telemetry WHERE scan_run_id = ?", (scan_id,)
        ).fetchone()
        return StoredScan(
            id=row["id"], universe_name=row["universe_name"],
            started_at_utc=row["started_at_utc"], finished_at_utc=row["finished_at_utc"],
            status=row["status"], discovered_count=row["discovered_count"],
            pre_screen_count=row["pre_screen_count"], quality_pass_count=row["quality_pass_count"],
            elapsed_seconds=row["elapsed_seconds"],
            config_snapshot=json.loads(row["config_snapshot_json"]),
            results=[json.loads(r["raw_result_json"]) for r in candidates],
            discovery=json.loads(telemetry["discovery_json"]) if telemetry else None,
            pre_screen=json.loads(telemetry["pre_screen_json"]) if telemetry else {},
            timing=json.loads(telemetry["timing_json"]) if telemetry else {},
            excluded=json.loads(telemetry["excluded_json"]) if telemetry else [],
        )


def list_scans(*, db_path: str | Path = DEFAULT_DB_PATH, limit: int = 20) -> list[dict]:
    """Newest scan summaries for UI/history; never loads full result JSON."""
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    initialize_database(db_path)
    with database_connection(db_path) as conn:
        conn.row_factory = __import__("sqlite3").Row
        rows = conn.execute(
            """SELECT id,universe_name,finished_at_utc,status,discovered_count,
               pre_screen_count,quality_pass_count,elapsed_seconds
               FROM scan_runs ORDER BY finished_at_utc DESC, rowid DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
