import hashlib
import json
from contextlib import contextmanager

import pytest
from playwright.sync_api import sync_playwright

import job_agent.__main__ as cli
from job_agent.browser.inspector import extract_gupy_job, extract_indeed_job
from job_agent.models import Profile
from job_agent.storage import Store


@pytest.mark.parametrize("platform", ["gupy", "indeed"])
@pytest.mark.parametrize("change", ["none", "description", "profile", "closed", "question", "expired"])
def test_approve_then_real_connector_submission(tmp_path, monkeypatch, capsys, platform, change):
    url = ("https://x.gupy.io/jobs/123" if platform == "gupy"
           else "https://br.indeed.com/viewjob?jk=123")
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"Local resume fixture")
    profile = Profile(
        skills=[".NET", "SQL", "APIs REST", "Git", "Azure"], preferred_modes=["remote"],
        history_complete=True, identity_complete=True, profile_confirmed=True,
        identity={"full_name": "Teste", "email": "test@example.com", "phone": "123",
                  "country": "Brasil", "city": "Curitiba"},
        resume_path=str(resume), resume_sha256=hashlib.sha256(resume.read_bytes()).hexdigest(),
    )
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(profile.model_dump_json(), encoding="utf-8")
    db = tmp_path / "db.sqlite3"
    desc_attr = ('data-testid="job-description"' if platform == "gupy"
                 else 'id="jobDescriptionText"')
    button_attr = ('data-testid="job-apply-button"' if platform == "gupy"
                   else 'id="indeedApplyButton"')
    html = f'''<h1>Backend .NET Junior</h1>
        <div {desc_attr}>Trabalho remoto .NET SQL REST Git Azure</div>
        <button {button_attr} onclick="document.getElementById('form').hidden=false">
        Candidatar-se</button><form id="form" hidden onsubmit="return false">
        <label for="name">Nome completo</label><input id="name" required>
        <input type="file" required>
        <button type="button" onclick="window.sent=(window.sent||0)+1;
            document.body.innerHTML='<p>Candidatura enviada!</p>'">Enviar candidatura</button></form>'''
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(html)
            extract = extract_gupy_job if platform == "gupy" else extract_indeed_job
            reviewed = extract(page, url).model_copy(update={"active": True,
                                                             "requirements_verified": True})
            jobs_path = tmp_path / "reviewed.json"
            jobs_path.write_text(json.dumps([reviewed.model_dump(mode="json")]), encoding="utf-8")
            monkeypatch.setattr("sys.argv", ["job_agent", "--db", str(db), "approve",
                "--jobs", str(jobs_path), "--profile", str(profile_path),
                "--evidence", "Requisitos e disponibilidade conferidos na fixture",
                "--authorize-submit"])
            try:
                code = cli.main()
            except SystemExit as error:
                code = error.code
            assert code == 0
            capsys.readouterr()
            if change == "expired":
                store = Store(db)
                with store.connection:
                    store.connection.execute(
                        "UPDATE approvals SET created_at='2000-01-01T00:00:00+00:00'"
                    )
                store.close()
            if change == "description":
                html = html.replace("Trabalho remoto", "Novo requisito Docker. Trabalho remoto")
            elif change == "closed":
                html += '<div role="alert">Vaga encerrada</div>'
            elif change == "profile":
                profile.identity["phone"] = "456"
                profile_path.write_text(profile.model_dump_json(), encoding="utf-8")
            elif change == "question":
                html = html.replace('<input type="file" required>',
                    '<input type="file" required><label for="question">Aceita viajar?</label>'
                    '<input id="question">')
            page.route(url, lambda route: route.fulfill(body=html))

            @contextmanager
            def context(**kwargs):
                class Context:
                    def new_page(self):
                        return page
                yield Context()

            monkeypatch.setattr(cli, "create_browser_context", context)
            monkeypatch.setattr("job_agent.browser.gupy.SCREENSHOTS_DIR", tmp_path / "screens")
            monkeypatch.setattr("sys.argv", ["job_agent", "--db", str(db), "process-queue",
                                             "--profile", str(profile_path)])
            assert cli.main() == 0
            report = json.loads(capsys.readouterr().out)
            store = Store(db)
            try:
                if change == "none":
                    assert report["results"][0]["status"] == "SUBMITTED"
                    assert store.application_status(f"{platform}:123") == "SUBMITTED"
                    assert store.queue_items()[0]["state"] == "SUBMITTED"
                    monkeypatch.setattr("sys.argv", ["job_agent", "--db", str(db),
                        "auto-apply", "--url", url, "--profile", str(profile_path)])
                    assert cli.main() == 0
                    assert "não repetir" in capsys.readouterr().out
                else:
                    assert report["results"][0]["status"] != "SUBMITTED"
                    assert store.application_status(f"{platform}:123") is None
                    assert page.evaluate("window.sent || 0") == 0
            finally:
                store.close()
        finally:
            browser.close()