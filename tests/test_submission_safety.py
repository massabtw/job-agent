import hashlib
from contextlib import contextmanager

import pytest
from playwright.sync_api import sync_playwright

from job_agent.browser.filler import _find_answer, upload_resume
from job_agent.browser.gupy import apply_gupy
from job_agent.browser.inspector import extract_gupy_job
from job_agent.models import Profile


@pytest.fixture
def profile(tmp_path):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"Local resume fixture")
    return Profile(
        skills=[".NET", "SQL", "APIs REST", "Git", "Azure"],
        preferred_modes=["remote"], history_complete=True, identity_complete=True,
        profile_confirmed=True,
        identity={"full_name": "Teste", "email": "test@example.com", "phone": "123",
                  "country": "Brasil", "city": "Curitiba"},
        resume_path=str(resume), resume_sha256=hashlib.sha256(resume.read_bytes()).hexdigest(),
    )


@pytest.fixture
def page():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            yield browser.new_page()
        finally:
            browser.close()


HTML = """
<h1 data-testid="job-title">Backend .NET Junior</h1>
<span data-testid="job-company">Teste</span>
<span data-testid="job-workplace-type">Remoto</span>
<div data-testid="job-description">.NET SQL REST Git Azure remoto</div>
<button data-testid="job-apply-button">Candidatar-se</button>
<label for="newsletter">Receber publicidade</label><input type="checkbox" id="newsletter">
<button onclick="window.clicked=true">Enviar candidatura</button>
"""
URL = "https://teste.gupy.io/jobs/123"


def test_extraction_does_not_claim_verified_requirements(page):
    page.set_content(HTML)
    assert extract_gupy_job(page, URL).requirements_verified is False


def test_review_stops_before_apply(page, profile, monkeypatch):
    import job_agent.browser.gupy as connector

    page.route(URL, lambda route: route.fulfill(body=HTML))
    page.set_content(HTML)
    job = extract_gupy_job(page, URL).model_copy(update={"requirements_verified": False})
    monkeypatch.setattr(connector, "extract_gupy_job", lambda *args: job)
    monkeypatch.setattr(connector, "fill_form", lambda *args: None)
    status, _, _ = apply_gupy(page, URL, profile)
    assert status == "NEEDS_REVIEW"
    assert page.evaluate("window.clicked === true") is False


def test_upload_requires_hash(page, profile):
    page.set_content('<input type="file">')
    profile.resume_sha256 = None
    with pytest.raises(ValueError):
        upload_resume(page, profile)


def test_answers_require_exact_question():
    assert _find_answer("", {"Você aceita viajar?": "Sim"}) is None
    assert _find_answer("Você aceita viajar todos os dias?", {"Você aceita viajar": "Sim"}) is None


def test_invalid_domain_rejected_before_navigation(profile):
    class NoNavigation:
        def goto(self, *args, **kwargs):
            pytest.fail("Não deve navegar para domínio inválido")

    with pytest.raises(ValueError):
        apply_gupy(NoNavigation(), "https://gupy.io.evil.test/jobs/123", profile)


def test_queue_review_is_not_processed(tmp_path, monkeypatch, profile, capsys):
    import job_agent.__main__ as cli
    from job_agent.models import Job
    from job_agent.storage import Store

    path = tmp_path / "db.sqlite3"
    store = Store(path)
    job = Job(platform="gupy", external_id="123", url=URL, company="Teste", title="Backend",
              seniority="junior", stack=[], description="Teste")
    key = store.register(job)
    store.enqueue(key, "gupy", URL)
    store.close()
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(profile.model_dump_json(), encoding="utf-8")

    @contextmanager
    def context(**kwargs):
        class Context:
            def new_page(self):
                return object()
        yield Context()

    monkeypatch.setattr(cli, "create_browser_context", context)
    monkeypatch.setattr(cli, "apply_gupy", lambda *a, **k: pytest.fail("Fila não aprovada"))
    monkeypatch.setattr("sys.argv", ["job_agent", "--db", str(path), "process-queue",
                                     "--profile", str(profile_path)])
    assert cli.main() == 0


def test_cli_reserves_and_persists_uncertain(tmp_path, monkeypatch, profile, capsys):
    import job_agent.__main__ as cli
    from job_agent.models import Job
    from job_agent.storage import Store

    path = tmp_path / "db.sqlite3"
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(profile.model_dump_json(), encoding="utf-8")
    job = Job(platform="gupy", external_id="123", url=URL, company="Teste",
              title="Backend .NET Junior", seniority="junior",
              stack=profile.skills, description="Teste", mode="remote",
              active=True, requirements_verified=True)

    @contextmanager
    def context(**kwargs):
        class Context:
            def new_page(self):
                return object()
        yield Context()

    def apply(*args, **kwargs):
        assert "before_submit" in kwargs
        assert kwargs["before_submit"](job) is None
        return "SUBMISSION_UNCERTAIN", job, "Sem confirmação local"

    monkeypatch.setattr(cli, "create_browser_context", context)
    monkeypatch.setattr(cli, "apply_gupy", apply)
    monkeypatch.setattr("sys.argv", ["job_agent", "--db", str(path), "auto-apply",
                                     "--url", URL, "--profile", str(profile_path)])
    assert cli.main() == 1
    store = Store(path)
    try:
        assert store.application_status("gupy:123") == "SUBMISSION_UNCERTAIN"
        assert store.queue_items()[0]["state"] == "SUBMISSION_UNCERTAIN"
    finally:
        store.close()


def test_click_without_confirmation_is_not_success(page, monkeypatch):
    from job_agent.browser.safety import submit_confirmed

    page.route(URL, lambda route: route.fulfill(body='<button>Enviar candidatura</button>'))
    page.goto(URL)
    with pytest.raises(AssertionError):
        submit_confirmed(page, page.get_by_role("button"), "gupy")


def test_existing_confirmation_cannot_be_reused(page):
    from job_agent.browser.safety import submit_confirmed

    page.route(URL, lambda route: route.fulfill(
        body='<p>Candidatura enviada!</p><button>Enviar candidatura</button>'
    ))
    page.goto(URL)
    with pytest.raises(ValueError, match="já existia"):
        submit_confirmed(page, page.get_by_role("button"), "gupy")


def test_guarded_apply_prevents_repetition_and_counts_uncertain(tmp_path, monkeypatch, profile):
    import job_agent.__main__ as cli
    from job_agent.models import Job
    from job_agent.storage import Store

    store = Store(tmp_path / "db.sqlite3")
    store.create_batch("one", 1)
    calls = []

    def apply(page, url, profile, before_submit, **kwargs):
        job = Job(platform="gupy", external_id=url.rsplit("/", 1)[1], url=url,
                  company="Teste", title="Backend .NET Junior", seniority="junior",
                  stack=profile.skills, description="Fixture", mode="remote", active=True,
                  requirements_verified=True)
        denied = before_submit(job)
        if denied:
            return denied, job, "Bloqueado"
        calls.append(url)
        return "SUBMISSION_UNCERTAIN", job, "Timeout local"

    monkeypatch.setattr(cli, "apply_gupy", apply)
    try:
        assert cli.guarded_apply(None, URL, profile, store, "one")[0] == "SUBMISSION_UNCERTAIN"
        assert cli.guarded_apply(None, URL, profile, store, "one")[0] == "NEEDS_REVIEW"
        assert cli.guarded_apply(None, URL + "4", profile, store, "one")[0] == "LIMIT_REACHED"
        assert calls == [URL]
    finally:
        store.close()


def test_ready_queue_returns_to_review_when_validation_fails(tmp_path, monkeypatch, profile):
    import job_agent.__main__ as cli
    from job_agent.models import Job
    from job_agent.storage import Store

    store = Store(tmp_path / "db.sqlite3")
    job = Job(platform="gupy", external_id="123", url=URL, company="Teste", title="Backend",
              seniority="junior", stack=[], description="Fixture")
    key = store.register(job)
    store.enqueue(key, "gupy", URL)
    store.connection.execute("UPDATE queue SET state='READY' WHERE key=?", (key,))
    store.connection.commit()
    store.create_batch("batch", 1)
    monkeypatch.setattr(cli, "apply_gupy", lambda *a, **kw: (
        "NEEDS_REVIEW", job, "Requisitos não confirmados"
    ))
    try:
        cli.guarded_apply(None, URL, profile, store, "batch", expected_key=key)
        assert store.queue_items()[0]["state"] == "NEEDS_REVIEW"
        assert store.queue_items()[0]["evidence"] == "Requisitos não confirmados"
    finally:
        store.close()