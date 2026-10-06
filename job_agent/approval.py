import hashlib
import json
from datetime import UTC, datetime

from .connectors import validate_destination, validate_source
from .evaluation import evaluate, normalize
from .models import Job, Profile
from .profile_validation import profile_blockers


def profile_digest(profile: Profile) -> str:
    payload = json.dumps(profile.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def reviewed_job(store, fresh: Job, profile: Profile) -> Job:
    key = validate_source(fresh)
    approval = store.connection.execute("SELECT * FROM approvals WHERE key=?", (key,)).fetchone()
    if not approval:
        return fresh
    age = (datetime.now(UTC) - datetime.fromisoformat(approval["created_at"])).total_seconds()
    if age < 0 or age > 86400 or approval["profile_hash"] != profile_digest(profile):
        return fresh
    approved = Job.model_validate_json(approval["payload"])
    for field in ("title", "company", "description", "location", "mode", "required_years"):
        old, new = getattr(approved, field), getattr(fresh, field)
        if isinstance(old, str) and isinstance(new, str):
            old, new = normalize(old), normalize(new)
        if old != new:
            return fresh
    if fresh.active is False:
        return fresh
    # Only reviewed facts are reused; current questions and warnings remain authoritative.
    return approved.model_copy(update={
        "questions": list(dict.fromkeys(approved.questions + fresh.questions)),
        "extraction_evidence": approved.extraction_evidence + fresh.extraction_evidence,
    })


def approve_jobs(store, jobs: list[Job], profile: Profile, evidence: str):
    if not evidence.strip() or not jobs:
        raise ValueError("Vagas revisadas e evidência não vazia são obrigatórias.")
    blockers = profile_blockers(profile)
    if blockers:
        raise ValueError("; ".join(blockers))
    destinations = []
    for job in jobs:
        validate_source(job)
        channel, destination = validate_destination(job)
        if channel not in {"gupy", "indeed"} or destination != str(job.url):
            raise ValueError("Aprovação suporta somente destino original Gupy/Indeed.")
        result = evaluate(job, profile)
        if result.status != "READY":
            raise ValueError("Vaga não está pronta: " + "; ".join(result.reasons))
        destinations.append((channel, destination))
    keys = []
    for job, (channel, destination) in zip(jobs, destinations, strict=True):
        key = store.register(job)
        store.enqueue(key, channel, destination)
        store.connection.execute("BEGIN IMMEDIATE")
        try:
            if store.application_status(key):
                raise ValueError("Candidatura anterior ou reserva impede aprovação.")
            row = store.connection.execute("SELECT * FROM queue WHERE key=?", (key,)).fetchone()
            if row["destination"] != destination or row["channel"] != channel:
                raise ValueError("Destino da fila não corresponde à aprovação.")
            store.connection.execute(
                "INSERT INTO approvals VALUES(?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET "
                "payload=excluded.payload,profile_hash=excluded.profile_hash,"
                "evidence=excluded.evidence,created_at=excluded.created_at",
                (key, job.model_dump_json(), profile_digest(profile), evidence.strip(),
                 datetime.now(UTC).isoformat()),
            )
            store.connection.execute(
                "UPDATE queue SET state='READY',evidence=? WHERE key=?", (evidence.strip(), key)
            )
            store.connection.commit()
        except Exception:
            store.connection.rollback()
            raise
        keys.append(key)
    return keys