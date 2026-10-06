import pytest
from playwright.sync_api import sync_playwright

from job_agent.browser.filler import fill_form
from job_agent.browser.inspector import extract_questions
from job_agent.browser.safety import form_pending
from job_agent.models import Profile


def test_application_waits_for_delayed_controls(page):
    from job_agent.browser.indeed import wait_for_application_controls

    page.set_content('<main>Carregando</main>')
    page.evaluate("setTimeout(() => document.body.innerHTML = '<input aria-label=Nome>', 150)")
    assert wait_for_application_controls(page, timeout_ms=2000) is True


def test_application_loading_timeout_is_not_ready(page):
    from job_agent.browser.indeed import wait_for_application_controls

    page.set_content('<input hidden><button>Definições de cookies</button>')
    assert wait_for_application_controls(page, timeout_ms=200) is False


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


def test_company_question_never_uses_candidate_name(page):
    page.set_content('<form><label for="company">Qual o nome da sua última empresa?</label>'
                     '<input id="company" name="fullName"></form>')
    profile = Profile(skills=[], identity={"full_name": "Candidato"},
                      answers={"Qual o nome da sua última empresa?": "Empresa correta"})
    fill_form(page, profile)
    assert page.locator("#company").input_value() == "Empresa correta"
    profile.answers.clear()
    page.locator("#company").fill("")
    fill_form(page, profile)
    assert page.locator("#company").input_value() == ""


def test_invisible_recaptcha_anchor_is_not_an_interactive_challenge(page):
    from job_agent.browser.inspector import detect_blockers

    page.set_content('<iframe src="https://www.recaptcha.net/recaptcha/enterprise/anchor?size=invisible"></iframe>')
    assert "CAPTCHA" not in detect_blockers(page)
    page.set_content('<iframe src="https://www.recaptcha.net/recaptcha/enterprise/anchor?size=invisible"></iframe>'
                     '<iframe src="https://www.recaptcha.net/recaptcha/enterprise/bframe"></iframe>')
    assert "CAPTCHA" in detect_blockers(page)


def test_indeed_separate_contact_names(page):
    page.set_content('''<form><label for="first">Nome *</label>
        <input id="first" name="names-first-name"><label for="last">Sobrenome *</label>
        <input id="last" name="names-last-name"><input id="phone" aria-label="Digite o número de telefone"></form>''')
    profile = Profile(skills=[], identity={"full_name": "Gabriel Almeida Massa",
                                          "phone": "41999999999"})
    fill_form(page, profile)
    assert page.locator("#first").input_value() == "Gabriel"
    assert page.locator("#last").input_value() == "Almeida Massa"
    assert page.locator("#phone").input_value() == "41999999999"


def test_smartapply_questions_outside_form_are_not_missed(page):
    page.route('https://smartapply.indeed.com/questions', lambda route: route.fulfill(
        body='<label for="cpf">Informe seu CPF *</label><input id="cpf" required>'
             '<label for="pay">Qual foi sua última remuneração?</label><textarea id="pay"></textarea>',
        content_type='text/html; charset=utf-8'))
    page.goto('https://smartapply.indeed.com/questions')
    questions, _ = extract_questions(page)
    assert questions == ["Informe seu CPF *", "Qual foi sua última remuneração?"]


def test_aria_and_implicit_labels_share_mapping(page):
    page.set_content('<form><label>Disponibilidade?<textarea id="a"></textarea></label>'
                     '<input id="b" aria-label="Pretensão salarial?"></form>')
    profile = Profile(skills=[], answers={"Disponibilidade?": "Imediata",
                                         "Pretensão salarial?": "5000"})
    fill_form(page, profile)
    assert page.locator("#a").input_value() == "Imediata"
    assert page.locator("#b").input_value() == "5000"


def test_select_radio_and_exact_checkbox_approval(page):
    page.set_content('''<form>
        <label for="shift">Turno?</label><select id="shift" required>
        <option value="">Escolha</option><option value="am">Manhã</option></select>
        <fieldset><legend>Aceita viajar?</legend>
        <label><input type="radio" name="travel" value="yes" required>Sim</label>
        <label><input type="radio" name="travel" value="no" required>Não</label></fieldset>
        <label><input id="terms" type="checkbox" required>Li e aceito estes termos</label>
        </form>''')
    questions, _ = extract_questions(page)
    assert "Aceita viajar?" in questions
    assert "Sim" not in questions
    profile = Profile(skills=[], answers={"Turno?": "Manhã", "Aceita viajar?": "Sim",
                                         "Li e aceito estes termos": "Sim"})
    fill_form(page, profile)
    assert page.locator("#shift").input_value() == "am"
    assert page.locator('[value="yes"]').is_checked()
    assert page.locator("#terms").is_checked()
    assert form_pending(page) is False


def test_unapproved_checkbox_is_not_checked(page):
    page.set_content('<form><label><input type="checkbox" required>Receber publicidade</label></form>')
    fill_form(page, Profile(skills=[]))
    assert page.locator("input").is_checked() is False
    assert form_pending(page) is True


def test_gupy_rejected_before_any_browser_action(tmp_path):
    from job_agent.__main__ import guarded_apply
    from job_agent.storage import Store

    store = Store(tmp_path / "db.sqlite3")
    try:
        with pytest.raises(ValueError, match="Indeed"):
            guarded_apply(None, "https://x.gupy.io/jobs/123", Profile(skills=[]), store, "batch")
    finally:
        store.close()


def test_salary_with_approved_answer_is_not_a_blocker(page):
    from job_agent.browser.indeed import application_blockers

    page.set_content('<form><label for="salary">Qual sua pretensão salarial?</label>'
                     '<input id="salary"></form>')
    profile = Profile(skills=[], answers={"Qual sua pretensão salarial?": "5000"})
    assert "SALARY" not in application_blockers(page, profile)
    profile.answers.clear()
    assert "SALARY" in application_blockers(page, profile)


def test_queue_continues_after_one_error(tmp_path, monkeypatch, capsys):
    import json
    from contextlib import contextmanager

    import job_agent.__main__ as cli
    from job_agent.models import Job
    from job_agent.storage import Store

    db = tmp_path / "db.sqlite3"
    store = Store(db)
    for number in [1, 2]:
        job = Job(platform="indeed", external_id=str(number),
                  url=f"https://br.indeed.com/viewjob?jk={number}", company="Teste",
                  title="Backend", seniority="junior", stack=[], description="Fixture")
        key = store.register(job)
        store.enqueue(key, "indeed", str(job.url))
    store.connection.execute("UPDATE queue SET state='READY'")
    store.connection.commit()
    store.close()
    path = tmp_path / "profile.json"
    path.write_text(Profile(skills=[]).model_dump_json(), encoding="utf-8")
    calls = []

    @contextmanager
    def context(**kwargs):
        class Context:
            def new_page(self):
                return None
        yield Context()

    def apply(page, url, *args, **kwargs):
        calls.append(url)
        if url.endswith("=1"):
            raise ValueError("Falha local antes da reserva")
        return "NEEDS_REVIEW", None, "Pergunta pendente"

    monkeypatch.setattr(cli, "create_browser_context", context)
    monkeypatch.setattr(cli, "guarded_apply", apply)
    monkeypatch.setattr("sys.argv", ["job_agent", "--db", str(db), "process-queue",
                                     "--profile", str(path)])
    assert cli.main() == 1
    assert len(calls) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["results"][0]["status"] == "ERROR"