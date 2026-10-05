import hashlib
from concurrent.futures import ThreadPoolExecutor

import pytest

from job_agent.connectors import validate_destination
from job_agent.models import Job, Profile
from job_agent.profile_validation import profile_blockers
from job_agent.storage import Store


def seed(store, number):
    job = Job(platform="gupy", external_id=str(number),
              url=f"https://x.gupy.io/jobs/{number}", company="Teste", title="Backend",
              seniority="junior", stack=[], description="Teste local")
    key = store.register(job)
    store.enqueue(key, "gupy", str(job.url))
    # Test-only promotion: production has no authorized connector yet.
    with store.connection:
        store.connection.execute("UPDATE queue SET state='READY' WHERE key=?", (key,))
    return key


def test_concurrent_reservation_and_limit(tmp_path):
    path = tmp_path / "db.sqlite3"
    setup = Store(path)
    try:
        keys = [seed(setup, i) for i in range(7)]
        setup.create_batch("batch", 5)
    finally:
        setup.close()

    def worker(key):
        store = Store(path)
        try:
            return store.reserve(key, "batch")
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=4) as pool:
        tokens = list(pool.map(worker, keys + keys))
    assert sum(token is not None for token in tokens) == 5


def test_uncertain_retains_slot_and_reconciles(tmp_path):
    store = Store(tmp_path / "db.sqlite3")
    try:
        key = seed(store, 1)
        second = seed(store, 2)
        store.create_batch("one", 1)
        token = store.reserve(key, "one")
        with pytest.raises(ValueError):
            store.transition(key, "wrong", "SUBMITTING")
        store.transition(key, token, "SUBMITTING")
        with pytest.raises(ValueError):
            store.transition(key, token, "SUBMITTED")
        store.transition(key, token, "SUBMISSION_UNCERTAIN", "Timeout fictício")
        assert store.reserve(second, "one") is None
        assert store.application_status(key) == "SUBMISSION_UNCERTAIN"
        store.transition(key, token, "SUBMITTED", "Confirmação fictícia")
        assert store.application_status(key) == "SUBMITTED"
    finally:
        store.close()


def test_profile_content_hash(tmp_path):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"Local test fixture, not a real resume")
    profile = Profile(skills=[], profile_confirmed=True,
                      identity={"full_name": "Teste", "email": "test@example.com",
                                "phone": "123", "country": "Teste", "city": "Teste"},
                      resume_path=str(resume),
                      resume_sha256=hashlib.sha256(resume.read_bytes()).hexdigest())
    assert not profile_blockers(profile)
    resume.write_bytes(b"Changed")
    assert profile_blockers(profile)
    resume.unlink()
    assert profile_blockers(profile)


def test_source_and_destination_separate():
    job = Job(platform="indeed", external_id="abc",
              url="https://indeed.com/viewjob?jk=abc", company="Teste", title="Backend",
              seniority="junior", stack=[], description="Teste",
              application_channel="company", application_url="https://example.com/careers")
    assert validate_destination(job) == ("company", "https://example.com/careers")
    job.application_url = job.url
    with pytest.raises(ValueError):
        validate_destination(job)