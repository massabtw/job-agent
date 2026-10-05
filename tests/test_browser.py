import hashlib
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from job_agent.browser.filler import fill_form, upload_resume
from job_agent.browser.inspector import detect_blockers, extract_gupy_job, extract_indeed_job
from job_agent.models import Profile


@pytest.fixture
def test_profile(tmp_path):
    resume = tmp_path / "curriculo.pdf"
    resume.write_bytes(b"%PDF-1.4 Mock resume content for testing")
    sha256 = hashlib.sha256(resume.read_bytes()).hexdigest()
    return Profile(
        skills=[".NET", "C#", "SQL"],
        preferred_modes=["remote"],
        preferred_locations=["Curitiba"],
        identity={
            "full_name": "Gabriel Fiandanese",
            "email": "gabriel@example.com",
            "phone": "+5541999999999",
            "city": "Curitiba",
            "linkedin_url": "https://linkedin.com/in/gabrielfiandanese",
            "github_url": "https://github.com/gabrielfiandanese",
        },
        answers={
            "Qual sua pretensão salarial?": "A combinar",
            "Possui disponibilidade imediata?": "Sim",
        },
        resume_path=str(resume),
        resume_sha256=sha256,
        profile_confirmed=True,
    )


def test_detect_blockers_captcha():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("""
            <html>
                <body>
                    <div id="cf-turnstile"></div>
                    <iframe src="https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/b/turnstile"></iframe>
                </body>
            </html>
        """)
        blockers = detect_blockers(page)
        assert "CAPTCHA" in blockers
        browser.close()


def test_detect_blockers_login_and_salary():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("""
            <html>
                <body>
                    <form>
                        <label for="pass">Senha de acesso</label>
                        <input id="pass" type="password" />
                        <label for="sal">Informe sua pretensão salarial</label>
                        <input id="sal" type="text" />
                    </form>
                </body>
            </html>
        """)
        blockers = detect_blockers(page)
        assert "AUTH" in blockers
        assert "SALARY" in blockers
        browser.close()


def test_fill_form_success(test_profile):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("""
            <html>
                <body>
                    <form id="apply-form">
                        <label for="name">Nome completo</label>
                        <input id="name" name="fullName" type="text" />

                        <label for="email">E-mail</label>
                        <input id="email" name="email" type="email" />

                        <label for="phone">Telefone celular</label>
                        <input id="phone" name="phone" type="tel" />

                        <label for="city">Cidade</label>
                        <input id="city" name="city" type="text" />

                        <label for="linkedin">Perfil do LinkedIn</label>
                        <input id="linkedin" name="linkedin" type="url" />

                        <label for="q1">Possui disponibilidade imediata?</label>
                        <input id="q1" name="availability" type="text" />
                    </form>
                </body>
            </html>
        """)
        filled = fill_form(page, test_profile)
        assert filled["fullName"] == "Gabriel Fiandanese"
        assert filled["email"] == "gabriel@example.com"
        assert page.locator("#name").input_value() == "Gabriel Fiandanese"
        assert page.locator("#email").input_value() == "gabriel@example.com"
        assert page.locator("#phone").input_value() == "+5541999999999"
        assert page.locator("#city").input_value() == "Curitiba"
        assert page.locator("#q1").input_value() == "Sim"
        browser.close()


def test_upload_resume_integrity_check(test_profile, tmp_path):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("""
            <html>
                <body>
                    <form>
                        <label for="resume">Currículo (PDF)</label>
                        <input id="resume" type="file" />
                    </form>
                </body>
            </html>
        """)
        # Valid upload
        assert upload_resume(page, test_profile) is True

        # Tampered resume raises ValueError
        tampered = Path(test_profile.resume_path)
        tampered.write_bytes(b"Tampered content")
        with pytest.raises(ValueError, match="integridade"):
            upload_resume(page, test_profile)

        browser.close()


def test_extract_gupy_job():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("""
            <html>
                <head><title>Desenvolvedor Backend .NET - Empresa Alfa - Gupy</title></head>
                <body>
                    <h1 data-testid="job-title">Desenvolvedor Backend .NET C#</h1>
                    <span data-testid="job-company">Empresa Alfa</span>
                    <span data-testid="job-location">Curitiba - PR</span>
                    <span data-testid="job-workplace-type">Remoto</span>
                    <div data-testid="job-description">
                        <h3>Descrição</h3>
                        <p>Buscamos pessoa desenvolvedora Backend com C#, SQL, Azure e Git.</p>
                        <h3>Requisitos</h3>
                        <p>Experiência com .NET e bancos relacionais.</p>
                    </div>
                </body>
            </html>
        """)
        job = extract_gupy_job(page, "https://empresaalfa.gupy.io/jobs/987654")
        assert job.platform == "gupy"
        assert job.external_id == "987654"
        assert job.company == "Empresa Alfa"
        assert "Backend" in job.title
        assert job.mode == "remote"
        assert "C#" in job.stack
        assert "SQL" in job.stack
        browser.close()


def test_extract_indeed_job():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("""
            <html>
                <body>
                    <h1 class="jobsearch-JobInfoHeader-title">Backend Python Júnior</h1>
                    <div data-company-name="true">Tech Beta</div>
                    <div data-testid="job-location">Remoto em São Paulo, SP</div>
                    <div id="jobDescriptionText">
                        Vaga para Desenvolvedor Backend Júnior com Python, SQL e APIs REST.
                    </div>
                </body>
            </html>
        """)
        job = extract_indeed_job(page, "https://br.indeed.com/viewjob?jk=1a2b3c4d")
        assert job.platform == "indeed"
        assert job.external_id == "1a2b3c4d"
        assert job.company == "Tech Beta"
        assert job.seniority == "junior"
        assert "Python" in job.stack
        browser.close()


def test_apply_gupy_discarded(test_profile):
    from job_agent.browser.gupy import apply_gupy

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        # Mocking page goto using route
        page.route("https://empresa.gupy.io/jobs/111", lambda route: route.fulfill(
            status=200,
            content_type="text/html",
            body="""
                <html>
                    <body>
                        <h1 data-testid="job-title">Backend Java Senior</h1>
                        <span data-testid="job-company">Empresa X</span>
                        <div data-testid="job-description">Requisitos: 10 anos de Java</div>
                    </body>
                </html>
            """,
        ))
        status, job, evidence = apply_gupy(page, "https://empresa.gupy.io/jobs/111", test_profile)
        assert status == "DISCARDED"
        assert job is not None
        assert "Critérios não atendidos" in evidence
        browser.close()


def test_apply_gupy_blocked_captcha(test_profile):
    from job_agent.browser.gupy import apply_gupy

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.route("https://empresa.gupy.io/jobs/222", lambda route: route.fulfill(
            status=200,
            content_type="text/html",
            body="""
                <html>
                    <body>
                        <div id="cf-turnstile"></div>
                        <iframe src="https://challenges.cloudflare.com/cdn-cgi/challenge-platform/turnstile"></iframe>
                    </body>
                </html>
            """,
        ))
        status, _, evidence = apply_gupy(page, "https://empresa.gupy.io/jobs/222", test_profile)
        assert status == "BLOCKED_CAPTCHA"
        assert "Desafio anti-bot detectado" in evidence
        browser.close()


def test_apply_gupy_success(test_profile):
    from job_agent.browser.gupy import apply_gupy

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.route("https://empresa.gupy.io/jobs/333", lambda route: route.fulfill(
            status=200,
            content_type="text/html",
            body="""
                <html>
                    <body>
                        <h1 data-testid="job-title">Backend C# Junior</h1>
                        <span data-testid="job-company">Tech Sul</span>
                        <span data-testid="job-workplace-type">Remoto</span>
                        <div data-testid="job-description">Trabalho remoto com .NET, C# e SQL.</div>
                        <button data-testid="job-apply-button" onclick="
                            document.getElementById('form-container').style.display = 'block';
                        ">Candidatar-se</button>
                        <div id="form-container" style="display:none;">
                            <input name="fullName" id="name" />
                            <input name="email" id="email" />
                            <input name="phone" id="phone" />
                            <input type="checkbox" id="terms" />
                            <button type="submit" onclick="document.body.innerHTML='Candidatura enviada!'">Enviar candidatura</button>
                        </div>
                    </body>
                </html>
            """,
        ))
        status, job, evidence = apply_gupy(page, "https://empresa.gupy.io/jobs/333", test_profile, auto_submit=True)
        assert status == "SUBMITTED"
        assert job is not None
        assert "Candidatura submetida na Gupy" in evidence
        browser.close()

