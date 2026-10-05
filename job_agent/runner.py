from datetime import UTC, datetime

from .connectors import capabilities, submission_blocker, validate_destination
from .evaluation import evaluate
from .models import Job, Profile
from .profile_validation import profile_blockers
from .storage import Store


def run(jobs: list[Job], profile: Profile, store: Store, limit: int = 5) -> dict:
    if not 1 <= limit <= 5:
        raise ValueError("Limite deve estar entre 1 e 5.")
    items = []
    seen = set()
    eligible = 0
    for job in jobs:
        channel, destination = validate_destination(job)
        key = store.register(job)
        result = evaluate(job, profile)
        status = result.status
        reasons = list(result.reasons)
        existing = store.application_status(key)
        if key in seen or existing:
            status = "DUPLICATE" if existing != "SUBMISSION_UNCERTAIN" else "NEEDS_REVIEW"
            reasons = ["Já processada neste lote ou candidatura anterior registrada."
                       if status == "DUPLICATE" else "Envio anterior incerto: reconciliar, não repetir."]
        elif status == "READY":
            if eligible >= limit:
                status = "LIMIT_REACHED"
                reasons = ["Limite de oportunidades elegíveis desta execução atingido."]
            else:
                eligible += 1
                status = "NEEDS_REVIEW"
                reasons = profile_blockers(profile) + [
                    submission_blocker(channel) if channel != "company" else
                    "Site da empresa: integração autorizada ainda não implementada."
                ]
                store.enqueue(key, channel, destination)
        seen.add(key)
        items.append({
            "key": key, "company": job.company, "title": job.title,
            "url": str(job.url), "score": result.score, "status": status,
            "reasons": reasons, "platform": job.platform,
            "seniority": job.seniority, "stack": job.stack,
            "requirements": [r.model_dump() for r in job.requirements],
            "location": job.location, "mode": job.mode, "published_at": job.published_at,
            "application_channel": channel, "application_url": destination,
            "capabilities": capabilities(channel),
            "source": "Remotive" if job.platform == "remotive" else job.platform,
            "collected_at": job.collected_at,
            "extraction_evidence": job.extraction_evidence,
            "geographic_restriction": job.geographic_restriction,
        })
    report = {
        "created_at": datetime.now(UTC).isoformat(), "mode": "screening_only",
        "found": len(seen), "input_records": len(jobs),
        "discarded": sum(x["status"] == "DISCARDED" for x in items),
        "needs_review": sum(x["status"] == "NEEDS_REVIEW" for x in items),
        "duplicates": sum(x["status"] == "DUPLICATE" for x in items),
        "submitted": 0, "items": items,
    }
    store.save_report(report)
    return report