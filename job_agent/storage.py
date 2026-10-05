import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .connectors import validate_source
from .evaluation import normalize
from .models import Job


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                key TEXT PRIMARY KEY, fingerprint TEXT UNIQUE NOT NULL,
                payload TEXT NOT NULL, discovered_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS applications (
                key TEXT PRIMARY KEY REFERENCES jobs(key),
                status TEXT NOT NULL CHECK(status IN ('SUBMITTED','SUBMISSION_UNCERTAIN')),
                evidence TEXT NOT NULL, recorded_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, report TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS batches (
                id TEXT PRIMARY KEY, max_attempts INTEGER NOT NULL CHECK(max_attempts BETWEEN 1 AND 5)
            );
            CREATE TABLE IF NOT EXISTS queue (
                key TEXT PRIMARY KEY REFERENCES jobs(key), channel TEXT NOT NULL,
                destination TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN
                ('NEEDS_REVIEW','READY','RESERVED','SUBMITTING','SUBMITTED','SUBMISSION_UNCERTAIN')),
                batch_id TEXT REFERENCES batches(id), token TEXT, evidence TEXT NOT NULL DEFAULT ''
            );
        """)

    def close(self):
        self.connection.close()

    def register(self, job: Job) -> str:
        key = validate_source(job)
        identity = (f"{normalize(job.company)}:{job.requisition_id}"
                    if job.requisition_id else key)
        fingerprint = hashlib.sha256(identity.encode()).hexdigest()
        with self.connection:
            row = self.connection.execute(
                "SELECT key FROM jobs WHERE key = ? OR fingerprint = ?", (key, fingerprint)
            ).fetchone()
            if row:
                return row["key"]
            self.connection.execute(
                "INSERT INTO jobs VALUES (?, ?, ?, ?)",
                (key, fingerprint, job.model_dump_json(), datetime.now(UTC).isoformat()),
            )
        return key

    def application_status(self, key: str) -> str | None:
        row = self.connection.execute(
            "SELECT status FROM applications WHERE key = ?", (key,)
        ).fetchone()
        if row:
            return row["status"]
        queued = self.connection.execute("SELECT state FROM queue WHERE key=?", (key,)).fetchone()
        if queued and queued["state"] in {
            "RESERVED", "SUBMITTING", "SUBMITTED", "SUBMISSION_UNCERTAIN"
        }:
            return "SUBMITTED" if queued["state"] == "SUBMITTED" else "SUBMISSION_UNCERTAIN"
        return None

    def record_external(self, key: str, status: str, evidence: str):
        if status not in {"SUBMITTED", "SUBMISSION_UNCERTAIN"} or not evidence.strip():
            raise ValueError("Status válido e evidência são obrigatórios.")
        if not self.connection.execute("SELECT 1 FROM jobs WHERE key=?", (key,)).fetchone():
            raise ValueError("Importe a vaga antes de registrar o histórico.")
        with self.connection:
            self.connection.execute(
                "INSERT INTO applications VALUES (?, ?, ?, ?)",
                (key, status, evidence, datetime.now(UTC).isoformat()),
            )

    def save_report(self, report: dict):
        with self.connection:
            self.connection.execute(
                "INSERT INTO runs(created_at, report) VALUES (?, ?)",
                (datetime.now(UTC).isoformat(), json.dumps(report, ensure_ascii=False)),
            )

    def enqueue(self, key: str, channel: str, destination: str):
        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO queue(key, channel, destination, state) VALUES(?,?,?,?)",
                (key, channel, destination, "NEEDS_REVIEW"),
            )

    def queue_items(self) -> list[dict]:
        return [dict(row) for row in self.connection.execute(
            "SELECT key, channel, destination, state, batch_id, evidence FROM queue ORDER BY key"
        )]

    def create_batch(self, batch_id: str, limit: int = 5):
        if not batch_id.strip() or not 1 <= limit <= 5:
            raise ValueError("Lote não vazio e limite entre 1 e 5 são obrigatórios.")
        with self.connection:
            self.connection.execute("INSERT INTO batches VALUES(?,?)", (batch_id, limit))

    def reserve(self, key: str, batch_id: str) -> str | None:
        """Atomically reserve a READY row. No production path currently promotes to READY."""
        from uuid import uuid4

        self.connection.execute("BEGIN IMMEDIATE")
        try:
            batch = self.connection.execute(
                "SELECT max_attempts FROM batches WHERE id=?", (batch_id,)
            ).fetchone()
            if not batch:
                raise ValueError("Lote desconhecido.")
            count = self.connection.execute(
                "SELECT COUNT(*) FROM queue WHERE batch_id=?", (batch_id,)
            ).fetchone()[0]
            prior = self.connection.execute(
                "SELECT 1 FROM applications WHERE key=?", (key,)
            ).fetchone()
            if count >= batch["max_attempts"] or prior:
                self.connection.rollback()
                return None
            token = str(uuid4())
            updated = self.connection.execute(
                "UPDATE queue SET state='RESERVED', batch_id=?, token=? WHERE key=? AND state='READY'",
                (batch_id, token, key),
            ).rowcount
            self.connection.commit()
            return token if updated else None
        except Exception:
            self.connection.rollback()
            raise

    def transition(self, key: str, token: str, state: str, evidence: str = ""):
        allowed = {
            "SUBMITTING": {"RESERVED"},
            "SUBMITTED": {"SUBMITTING", "SUBMISSION_UNCERTAIN"},
            "SUBMISSION_UNCERTAIN": {"RESERVED", "SUBMITTING"},
        }
        if state not in allowed or (state != "SUBMITTING" and not evidence.strip()):
            raise ValueError("Transição inválida ou evidência ausente.")
        with self.connection:
            row = self.connection.execute(
                "SELECT state, token FROM queue WHERE key=?", (key,)
            ).fetchone()
            if not row or row["token"] != token or row["state"] not in allowed[state]:
                raise ValueError("Reserva não pertence ao worker ou estado incompatível.")
            self.connection.execute(
                "UPDATE queue SET state=?, evidence=? WHERE key=?", (state, evidence, key)
            )