"""SQLite repository. One connection, guarded by a lock; WAL so readers never block the writer.

All JSON blobs are stored as compact UTF-8 text and decoded on read. Schema migrations are
applied on open (``PRAGMA user_version``).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class StoreError(RuntimeError):
    pass


@dataclass(frozen=True)
class EventRow:
    id: int
    run_id: str
    type: str
    data: dict[str, Any]
    created_at: str


_RUN_JSON_COLUMNS = (
    "stages",
    "plan",
    "ai_plan",
    "ai_report",
    "ai_alternatives",
    "verdict",
    "failure",
    "source_pins",
    "tool_versions",
    "extra",
)
_RUN_COLUMNS = (
    "run_id",
    "mode",
    "status",
    "configuration_id",
    "configuration_version",
    "change_id",
    "plan_id",
    "parent_run_id",
    "evidence_run_id",
    "runner_family",
    "created_at",
    "started_at",
    "finished_at",
    *_RUN_JSON_COLUMNS,
)

_MIGRATIONS: tuple[str, ...] = (
    # v1
    """
    CREATE TABLE runs (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL UNIQUE,
        mode TEXT NOT NULL,
        status TEXT NOT NULL,
        configuration_id TEXT NOT NULL,
        configuration_version TEXT NOT NULL,
        change_id TEXT NOT NULL,
        plan_id TEXT NOT NULL,
        parent_run_id TEXT,
        evidence_run_id TEXT,
        runner_family TEXT,
        created_at TEXT NOT NULL,
        started_at TEXT,
        finished_at TEXT,
        stages TEXT NOT NULL DEFAULT '[]',
        plan TEXT NOT NULL DEFAULT '[]',
        ai_plan TEXT,
        ai_report TEXT,
        ai_alternatives TEXT,
        verdict TEXT,
        failure TEXT,
        source_pins TEXT NOT NULL DEFAULT '{}',
        tool_versions TEXT NOT NULL DEFAULT '{}',
        extra TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX runs_status ON runs(status);
    CREATE INDEX runs_parent ON runs(parent_run_id);

    CREATE TABLE events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        type TEXT NOT NULL,
        data TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE INDEX events_run ON events(run_id, id);

    CREATE TABLE observations (
        run_id TEXT NOT NULL,
        observation_id TEXT NOT NULL,
        test_id TEXT NOT NULL,
        source_run_id TEXT NOT NULL,
        data TEXT NOT NULL,
        PRIMARY KEY (run_id, observation_id)
    );

    CREATE TABLE artifacts (
        run_id TEXT NOT NULL,
        artifact_id TEXT NOT NULL,
        owner_run_id TEXT NOT NULL,
        name TEXT NOT NULL,
        rel_path TEXT NOT NULL,
        kind TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        size_bytes INTEGER NOT NULL,
        test_id TEXT,
        ord INTEGER NOT NULL,
        data TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY (run_id, artifact_id)
    );

    CREATE TABLE test_results (
        run_id TEXT NOT NULL,
        template_id TEXT NOT NULL,
        test_id TEXT NOT NULL,
        ord INTEGER NOT NULL,
        data TEXT NOT NULL,
        PRIMARY KEY (run_id, template_id)
    );

    CREATE TABLE results (
        run_id TEXT PRIMARY KEY,
        assessment TEXT NOT NULL,
        result TEXT NOT NULL,
        gap_plan TEXT,
        dossier_md TEXT,
        evidence TEXT NOT NULL DEFAULT '[]',
        manifest_sha256 TEXT NOT NULL,
        canonical_hash TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE ai_traces (
        trace_id TEXT PRIMARY KEY,
        run_id TEXT,
        module TEXT NOT NULL,
        status TEXT NOT NULL,
        started_at TEXT NOT NULL,
        latency_ms INTEGER,
        prompt_tokens INTEGER,
        completion_tokens INTEGER,
        data TEXT NOT NULL
    );
    CREATE INDEX ai_traces_run ON ai_traces(run_id);

    CREATE TABLE idempotency_keys (
        key TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        request_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
)


def _dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, default=str)


def _loads(value: str | None) -> Any:
    return None if value is None else json.loads(value)


class Store:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            self.path, check_same_thread=False, isolation_level=None, timeout=30
        )
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._migrate()

    # ------------------------------------------------------------------ plumbing

    def _migrate(self) -> None:
        version = int(self._conn.execute("PRAGMA user_version").fetchone()[0])
        for index, script in enumerate(_MIGRATIONS[version:], start=version + 1):
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                for statement in filter(None, (s.strip() for s in script.split(";"))):
                    self._conn.execute(statement)
                self._conn.execute(f"PRAGMA user_version = {index}")
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    @property
    def schema_version(self) -> int:
        with self._lock:
            return int(self._conn.execute("PRAGMA user_version").fetchone()[0])

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            self._conn.execute("COMMIT")

    def _query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, tuple(params)).fetchall()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------ runs

    @staticmethod
    def _encode_run(fields: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in fields.items():
            if key not in _RUN_COLUMNS:
                raise StoreError(f"unknown run column {key}")
            out[key] = _dumps(value) if key in _RUN_JSON_COLUMNS and value is not None else value
        return out

    @staticmethod
    def _decode_run(row: sqlite3.Row) -> dict[str, Any]:
        data = {key: row[key] for key in _RUN_COLUMNS}
        for key in _RUN_JSON_COLUMNS:
            data[key] = _loads(data[key])
        data["seq"] = row["seq"]
        return data

    def insert_run(self, run: dict[str, Any], *, conn: sqlite3.Connection | None = None) -> None:
        encoded = self._encode_run(run)
        cols = ", ".join(encoded)
        marks = ", ".join("?" for _ in encoded)
        with self._lock:
            (conn or self._conn).execute(
                f"INSERT INTO runs ({cols}) VALUES ({marks})", tuple(encoded.values())
            )

    def update_run(self, run_id: str, **fields: Any) -> None:
        if not fields:
            return
        encoded = self._encode_run(fields)
        assignments = ", ".join(f"{k} = ?" for k in encoded)
        with self._lock:
            cur = self._conn.execute(
                f"UPDATE runs SET {assignments} WHERE run_id = ?", (*encoded.values(), run_id)
            )
            if cur.rowcount != 1:
                raise StoreError(f"unknown run {run_id}")

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        rows = self._query("SELECT * FROM runs WHERE run_id = ?", (run_id,))
        return self._decode_run(rows[0]) if rows else None

    def list_runs(self, *, limit: int = 50, statuses: Iterable[str] | None = None) -> list[dict]:
        if statuses is not None:
            wanted = list(statuses)
            marks = ", ".join("?" for _ in wanted) or "''"
            rows = self._query(
                f"SELECT * FROM runs WHERE status IN ({marks}) ORDER BY seq ASC", wanted
            )
        else:
            rows = self._query("SELECT * FROM runs ORDER BY seq DESC LIMIT ?", (int(limit),))
        return [self._decode_run(r) for r in rows]

    def list_child_runs(self, parent_run_id: str) -> list[dict[str, Any]]:
        rows = self._query(
            "SELECT * FROM runs WHERE parent_run_id = ? ORDER BY seq ASC", (parent_run_id,)
        )
        return [self._decode_run(r) for r in rows]

    # ------------------------------------------------------------------ idempotency

    def get_idempotency(self, key: str) -> tuple[str, str] | None:
        rows = self._query(
            "SELECT run_id, request_hash FROM idempotency_keys WHERE key = ?", (key,)
        )
        return (rows[0]["run_id"], rows[0]["request_hash"]) if rows else None

    def insert_run_with_key(
        self, run: dict[str, Any], *, key: str | None, request_hash: str, created_at: str
    ) -> tuple[str, bool]:
        """Insert ``run`` unless ``key`` already maps to a run. Returns (run_id, created)."""
        with self.transaction() as conn:
            if key is not None:
                row = conn.execute(
                    "SELECT run_id, request_hash FROM idempotency_keys WHERE key = ?", (key,)
                ).fetchone()
                if row is not None:
                    if row["request_hash"] != request_hash:
                        raise StoreError("idempotency key reused with a different request")
                    return str(row["run_id"]), False
            self.insert_run(run, conn=conn)
            if key is not None:
                conn.execute(
                    "INSERT INTO idempotency_keys (key, run_id, request_hash, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (key, run["run_id"], request_hash, created_at),
                )
        return str(run["run_id"]), True

    # ------------------------------------------------------------------ events

    def append_event(
        self,
        run_id: str,
        type_: str,
        data: dict[str, Any],
        *,
        created_at: str,
        on_commit: Callable[[EventRow], None] | None = None,
    ) -> EventRow:
        """Persist one event; ``on_commit`` runs under the store lock (ids publish in order)."""
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO events (run_id, type, data, created_at) VALUES (?, ?, ?, ?)",
                (run_id, type_, _dumps(data), created_at),
            )
            row = EventRow(int(cur.lastrowid or 0), run_id, type_, data, created_at)
            if on_commit is not None:
                on_commit(row)
            return row

    def list_events(self, run_id: str, *, after: int = 0, limit: int = 1000) -> list[EventRow]:
        rows = self._query(
            "SELECT * FROM events WHERE run_id = ? AND id > ? ORDER BY id ASC LIMIT ?",
            (run_id, int(after), int(limit)),
        )
        return [
            EventRow(r["id"], r["run_id"], r["type"], json.loads(r["data"]), r["created_at"])
            for r in rows
        ]

    # ------------------------------------------------------------------ evidence

    def add_observation(
        self, run_id: str, observation: dict[str, Any], *, source_run_id: str
    ) -> None:
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO observations"
                    " (run_id, observation_id, test_id, source_run_id, data)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (
                        run_id,
                        observation["observation_id"],
                        observation["test_id"],
                        source_run_id,
                        _dumps(observation),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise StoreError(f"duplicate observation {observation['observation_id']}") from exc

    def list_observations(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._query(
            "SELECT data FROM observations WHERE run_id = ? ORDER BY rowid ASC", (run_id,)
        )
        return [json.loads(r["data"]) for r in rows]

    def add_artifact(self, run_id: str, artifact: dict[str, Any]) -> None:
        with self._lock:
            ord_ = self._conn.execute(
                "SELECT COUNT(*) FROM artifacts WHERE run_id = ?", (run_id,)
            ).fetchone()[0]
            try:
                self._conn.execute(
                    "INSERT INTO artifacts (run_id, artifact_id, owner_run_id, name, rel_path,"
                    " kind,"
                    " sha256, size_bytes, test_id, ord, data)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        artifact["artifact_id"],
                        artifact.get("owner_run_id") or run_id,
                        artifact["name"],
                        artifact["rel_path"],
                        artifact["kind"],
                        artifact["sha256"],
                        int(artifact["size_bytes"]),
                        artifact.get("test_id"),
                        int(ord_),
                        _dumps(artifact.get("event") or {}),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise StoreError(f"duplicate artifact {artifact['artifact_id']}") from exc

    @staticmethod
    def _decode_artifact(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["event"] = json.loads(data.pop("data") or "{}")
        return data

    def list_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._query("SELECT * FROM artifacts WHERE run_id = ? ORDER BY ord ASC", (run_id,))
        return [self._decode_artifact(r) for r in rows]

    def get_artifact(self, run_id: str, artifact_id: str) -> dict[str, Any] | None:
        rows = self._query(
            "SELECT * FROM artifacts WHERE run_id = ? AND artifact_id = ?", (run_id, artifact_id)
        )
        return self._decode_artifact(rows[0]) if rows else None

    def add_test_result(self, run_id: str, result: dict[str, Any]) -> None:
        with self._lock:
            ord_ = self._conn.execute(
                "SELECT COUNT(*) FROM test_results WHERE run_id = ?", (run_id,)
            ).fetchone()[0]
            try:
                self._conn.execute(
                    "INSERT INTO test_results (run_id, template_id, test_id, ord, data)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (run_id, result["template_id"], result["test_id"], int(ord_), _dumps(result)),
                )
            except sqlite3.IntegrityError as exc:
                raise StoreError(f"duplicate test result {result['template_id']}") from exc

    def list_test_results(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._query(
            "SELECT data FROM test_results WHERE run_id = ? ORDER BY ord ASC", (run_id,)
        )
        return [json.loads(r["data"]) for r in rows]

    # ------------------------------------------------------------------ results

    def save_result(
        self,
        run_id: str,
        *,
        assessment: dict[str, Any],
        result: dict[str, Any],
        gap_plan: Any,
        dossier_md: str | None,
        evidence: list[dict[str, Any]],
        manifest_sha256: str,
        canonical_hash: str | None,
        created_at: str,
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO results (run_id, assessment, result, gap_plan, dossier_md, evidence,"
                " manifest_sha256, canonical_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    _dumps(assessment),
                    _dumps(result),
                    _dumps(gap_plan),
                    dossier_md,
                    _dumps(evidence),
                    manifest_sha256,
                    canonical_hash,
                    created_at,
                ),
            )

    def get_result(self, run_id: str) -> dict[str, Any] | None:
        rows = self._query("SELECT * FROM results WHERE run_id = ?", (run_id,))
        if not rows:
            return None
        r = rows[0]
        return {
            "run_id": r["run_id"],
            "assessment": json.loads(r["assessment"]),
            "result": json.loads(r["result"]),
            "gap_plan": _loads(r["gap_plan"]),
            "dossier_markdown": r["dossier_md"],
            "evidence": json.loads(r["evidence"]),
            "manifest_sha256": r["manifest_sha256"],
            "canonical_hash": r["canonical_hash"],
            "created_at": r["created_at"],
        }

    # ------------------------------------------------------------------ AI traces

    def add_ai_trace(self, trace: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO ai_traces (trace_id, run_id, module, status, started_at,"
                " latency_ms, prompt_tokens, completion_tokens, data)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    trace["trace_id"],
                    trace.get("run_id"),
                    trace["module"],
                    trace["status"],
                    trace["started_at"],
                    trace.get("latency_ms"),
                    trace.get("prompt_tokens"),
                    trace.get("completion_tokens"),
                    _dumps(trace),
                ),
            )

    def list_ai_traces(self, run_id: str | None = None, *, limit: int = 500) -> list[dict]:
        if run_id is None:
            rows = self._query(
                "SELECT data FROM ai_traces ORDER BY started_at DESC LIMIT ?", (int(limit),)
            )
        else:
            rows = self._query(
                "SELECT data FROM ai_traces WHERE run_id = ? ORDER BY started_at ASC, rowid ASC",
                (run_id,),
            )
        return [json.loads(r["data"]) for r in rows]

    def ai_trace_rows(self) -> list[dict[str, Any]]:
        rows = self._query(
            "SELECT module, status, latency_ms, prompt_tokens, completion_tokens FROM ai_traces"
        )
        return [dict(r) for r in rows]
