import json

import pytest

from job_agent.__main__ import main
from job_agent.models import Job
from job_agent.storage import Store


@pytest.fixture
def store(tmp_path):
    instance = Store(tmp_path / "db.sqlite3")
    job = Job(platform="gupy", external_id="123", url="https://x.gupy.io/jobs/123",
              company="Teste", title="Backend", seniority="junior", stack=[],
              description="Fixture local")
    instance.register(job)
    instance.enqueue("gupy:123", "gupy", str(job.url))
    yield instance
    instance.close()


def cli(store, monkeypatch, *args):
    path = store.connection.execute("PRAGMA database_list").fetchone()[2]
    monkeypatch.setattr("sys.argv", ["job_agent", "--db", path, *args])
    try:
        return main()
    except SystemExit as error:
        return error.code


def test_review_lists_pending_and_detail(store, monkeypatch, capsys):
    assert cli(store, monkeypatch, "review") == 0
    listing = json.loads(capsys.readouterr().out)
    assert listing[0]["key"] == "gupy:123"
    assert listing[0]["state"] == "NEEDS_REVIEW"
    assert cli(store, monkeypatch, "review", "--key", "gupy:123") == 0
    detail = json.loads(capsys.readouterr().out)
    assert detail["job"]["company"] == "Teste"
    assert detail["reviews"] == []
    assert "token" not in detail["queue"]


def test_review_note_is_audited_without_approval(store, monkeypatch, capsys):
    assert cli(store, monkeypatch, "review", "--key", "gupy:123",
               "--note", "Requisitos ainda pendentes") == 0
    first = json.loads(capsys.readouterr().out)
    assert first["queue"]["state"] == "NEEDS_REVIEW"
    assert first["reviews"][0]["evidence"] == "Requisitos ainda pendentes"
    assert cli(store, monkeypatch, "review", "--key", "gupy:123", "--note", "Nova nota") == 0
    second = json.loads(capsys.readouterr().out)
    assert len(second["reviews"]) == 2
    assert second["reviews"][0] == first["reviews"][0]


def uncertain(store):
    store.connection.execute("UPDATE queue SET state='READY' WHERE key='gupy:123'")
    store.connection.commit()
    store.create_batch("batch", 1)
    token = store.reserve("gupy:123", "batch")
    store.transition("gupy:123", token, "SUBMITTING")
    store.transition("gupy:123", token, "SUBMISSION_UNCERTAIN", "Timeout original")
    return token


def test_reconcile_confirms_and_keeps_reservation(store, monkeypatch, capsys):
    token = uncertain(store)
    assert cli(store, monkeypatch, "reconcile", "--key", "gupy:123",
               "--evidence", "Confirmação verificada manualmente no portal") == 0
    detail = json.loads(capsys.readouterr().out)
    assert detail["application"]["status"] == "SUBMITTED"
    assert detail["queue"]["state"] == "SUBMITTED"
    previous = json.loads(detail["reviews"][0]["previous_evidence"])
    assert previous["queue"]["evidence"] == "Timeout original"
    row = store.connection.execute("SELECT token,batch_id FROM queue").fetchone()
    assert tuple(row) == (token, "batch")
    store.create_batch("new", 1)
    assert store.reserve("gupy:123", "new") is None
    assert cli(store, monkeypatch, "reconcile", "--key", "gupy:123",
               "--evidence", "Outra confirmação") == 1


def test_reconcile_external_uncertainty(store, monkeypatch, capsys):
    store.record_external("gupy:123", "SUBMISSION_UNCERTAIN", "Declaração original")
    assert cli(store, monkeypatch, "reconcile", "--key", "gupy:123",
               "--evidence", "Comprovante externo") == 0
    result = json.loads(capsys.readouterr().out)
    assert result["application"]["status"] == "SUBMITTED"
    assert result["queue"]["state"] == "SUBMITTED"


@pytest.mark.parametrize("args", [
    ("review", "--note", "Sem chave"),
    ("review", "--key", "gupy:123", "--note", " "),
    ("review", "--key", "gupy:999"),
    ("reconcile", "--key", "gupy:123", "--evidence", " "),
    ("reconcile", "--key", "gupy:123", "--evidence", "Sem tentativa incerta"),
])
def test_invalid_requests_do_not_change_state(store, monkeypatch, args):
    assert cli(store, monkeypatch, *args) in {1, 2}
    assert store.queue_items()[0]["state"] == "NEEDS_REVIEW"
    assert store.application_status("gupy:123") is None
    assert store.connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 0


@pytest.mark.parametrize("state", ["RESERVED", "SUBMITTING"])
def test_cannot_reconcile_active_worker(store, monkeypatch, state):
    store.connection.execute("UPDATE queue SET state=? WHERE key='gupy:123'", (state,))
    store.connection.commit()
    assert cli(store, monkeypatch, "reconcile", "--key", "gupy:123",
               "--evidence", "Sem estado incerto explícito") == 1
    assert store.queue_items()[0]["state"] == state


def test_reconcile_rolls_back_audit_on_write_failure(store):
    uncertain(store)
    store.connection.executescript("""
        CREATE TRIGGER simulate_failure BEFORE INSERT ON applications
        BEGIN SELECT RAISE(ABORT, 'simulated failure'); END;
    """)
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        store.reconcile("gupy:123", "Comprovante local")
    assert store.queue_items()[0]["state"] == "SUBMISSION_UNCERTAIN"
    assert store.connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 0


def test_concurrent_reconciliation_records_only_one_confirmation(store):
    from concurrent.futures import ThreadPoolExecutor

    uncertain(store)
    path = store.connection.execute("PRAGMA database_list").fetchone()[2]

    def worker(number):
        from pathlib import Path

        other = Store(Path(path))
        try:
            other.reconcile("gupy:123", f"Comprovante {number}")
            return True
        except ValueError:
            return False
        finally:
            other.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(worker, [1, 2])) == 1
    assert store.application_status("gupy:123") == "SUBMITTED"
    assert len(store.review_detail("gupy:123")["reviews"]) == 1