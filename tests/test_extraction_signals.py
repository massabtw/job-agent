import html

import pytest
from playwright.sync_api import sync_playwright

from job_agent.browser.inspector import extract_gupy_job, extract_indeed_job
from job_agent.evaluation import evaluate
from job_agent.models import Profile


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(headless=True)
        yield instance
        instance.close()


@pytest.fixture
def page(browser):
    instance = browser.new_page()
    yield instance
    instance.close()


def job_from(page, platform, description, notice=""):
    selector = 'data-testid="job-description"' if platform == "gupy" else 'id="jobDescriptionText"'
    page.set_content(f'<h1>Backend .NET Junior</h1><div {selector}>'
                     f'{description}</div>{notice}')
    if platform == "gupy":
        return extract_gupy_job(page, "https://x.gupy.io/jobs/123")
    return extract_indeed_job(page, "https://br.indeed.com/viewjob?jk=abc")


@pytest.mark.parametrize("platform", ["gupy", "indeed"])
@pytest.mark.parametrize("text,years", [
    ("Experiência mínima de 4 anos com .NET.", 4),
    ("Obrigatório: 2 anos de experiência com SQL.", 2),
    ("Minimum 3 years of experience with Python.", 3),
    ("At least 2.5 years of experience required.", 2.5),
])
def test_explicit_experience_with_evidence(page, platform, text, years):
    job = job_from(page, platform, html.escape(text))
    assert job.required_years == years
    assert job.requirements_verified is False
    evidence = [item for item in job.extraction_evidence if item["field"] == "required_years"]
    assert evidence[0]["excerpt"] == text


@pytest.mark.parametrize("text", [
    "Desejável: experiência mínima de 4 anos.",
    "Não é obrigatório ter 4 anos de experiência.",
    "Minimum 3 years of experience preferred, not required.",
    "Experiência mínima de 2 a 4 anos.",
    "Experiência mínima de 2 anos ou formação equivalente.",
    "Nossa empresa tem 20 anos de experiência.",
    "Experiência mínima de 4 anos não é necessária.",
])
def test_ambiguous_or_optional_experience_stays_unknown(page, text):
    assert job_from(page, "gupy", html.escape(text)).required_years is None


@pytest.mark.parametrize("platform", ["gupy", "indeed"])
@pytest.mark.parametrize("notice", ["Vaga encerrada", "Esta vaga não está mais disponível",
                                    "This job has expired"])
def test_visible_closed_notice(page, platform, notice):
    job = job_from(page, platform, "Trabalho remoto .NET SQL REST Git Azure",
                   f'<div role="alert">{notice}</div>')
    assert job.active is False
    assert any(item["field"] == "active" and item["excerpt"] == notice
               for item in job.extraction_evidence)
    result = evaluate(job, Profile(skills=[".NET", "SQL", "APIs REST", "Git", "Azure"]))
    assert "Vaga encerrada." in result.reasons


@pytest.mark.parametrize("notice", [
    '<div style="display:none">Vaga encerrada</div>',
    '<p>Você será avisado quando esta vaga não está mais disponível.</p>',
    '<button>Candidatar-se</button>',
])
def test_no_unproven_availability(page, notice):
    assert job_from(page, "gupy", "Trabalho remoto", notice).active is None


def test_optional_section_is_not_mandatory(page):
    job = job_from(page, "gupy", '<h3>Diferenciais</h3><p>Experiência mínima de 4 anos.</p>')
    assert job.required_years is None


@pytest.mark.parametrize("text", [
    "Experiência mínima de 4 anos seria um diferencial.",
    "Experiência mínima de 4 anos é opcional.",
    "Minimum 4 years of experience is a nice to have.",
])
def test_optional_wording_not_extracted(text):
    from job_agent.browser.inspector import extract_experience

    assert extract_experience(text)[0] is None


def test_conflicting_minima_require_review():
    from job_agent.browser.inspector import extract_experience

    years, evidence = extract_experience(
        "Experiência mínima de 2 anos.\nExperiência mínima de 4 anos."
    )
    assert years is None
    assert len(evidence) == 2
    assert all(item["classification"] == "conflicting_minima_needs_review" for item in evidence)


@pytest.mark.parametrize("platform", ["gupy", "indeed"])
def test_visible_form_questions_with_evidence(page, platform):
    form = '''<form>
        <label for="salary">Qual sua pretensão salarial?</label><input id="salary">
        <label>Possui disponibilidade para viajar?<textarea></textarea></label>
        <select aria-label="Turno preferido"><option>Manhã</option></select>
        <label for="name">Nome completo</label><input id="name">
        <label for="hidden">Pergunta oculta?</label><input id="hidden" hidden>
        <label for="disabled">Pergunta desabilitada?</label><input id="disabled" disabled>
        <input type="search" aria-label="Pesquisar vagas">
    </form>'''
    job = job_from(page, platform, "Trabalho remoto .NET SQL REST Git Azure", form)
    assert job.questions == ["Qual sua pretensão salarial?",
                             "Possui disponibilidade para viajar?", "Turno preferido"]
    evidence = [item for item in job.extraction_evidence if item["field"] == "questions"]
    assert [item["excerpt"] for item in evidence] == job.questions
    reviewed = job.model_copy(update={"active": True, "requirements_verified": True})
    profile = Profile(skills=[".NET", "SQL", "APIs REST", "Git", "Azure"],
                      preferred_modes=["remote"], history_complete=True, identity_complete=True)
    assert evaluate(reviewed, profile).status == "NEEDS_REVIEW"
    profile.answers = dict.fromkeys(job.questions, "Resposta aprovada localmente")
    assert evaluate(reviewed, profile).status == "READY"


def test_questions_deduplicated_without_reading_answers(page):
    form = '''<form>
        <label for="a">Disponibilidade?</label><input id="a" value="Segredo do candidato">
        <input aria-label="Disponibilidade?">
        <span id="q">Motivação profissional</span><textarea aria-labelledby="q"></textarea>
    </form>
    <label for="filter">Filtro de vagas?</label><input id="filter">'''
    job = job_from(page, "gupy", "Remoto", form)
    assert job.questions == ["Disponibilidade?", "Motivação profissional"]
    assert "Segredo do candidato" not in str(job.extraction_evidence)


def test_unlabelled_field_records_review_evidence(page):
    job = job_from(page, "gupy", "Remoto", '<form><textarea required></textarea></form>')
    assert job.questions == []
    assert any(item["classification"] == "unlabelled_control_needs_review"
               for item in job.extraction_evidence)


def test_unlabelled_control_blocks_even_reviewed_job(page):
    job = job_from(page, "gupy", "Trabalho remoto .NET SQL REST Git Azure",
                   '<form><textarea required></textarea></form>')
    job = job.model_copy(update={"active": True, "requirements_verified": True})
    profile = Profile(skills=[".NET", "SQL", "APIs REST", "Git", "Azure"],
                      preferred_modes=["remote"], history_complete=True, identity_complete=True)
    result = evaluate(job, profile)
    assert result.status == "NEEDS_REVIEW"
    assert "Campo de formulário sem identificação: revisão humana obrigatória." in result.reasons