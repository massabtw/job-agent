from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from ..connectors import browser_channel, validate_source
from ..evaluation import evaluate
from ..models import Job, Profile
from ..profile_validation import profile_blockers
from .filler import fill_form, upload_resume
from .gupy import save_diagnostic_screenshot
from .inspector import detect_blockers, extract_indeed_job, extract_questions
from .safety import form_pending, submit_confirmed, validate_page
from .session import safe_goto

ROOT = Path(__file__).resolve().parents[2]


def apply_indeed(
    page: Page,
    url: str,
    profile: Profile,
    auto_submit: bool = True,
    before_submit=None,
    review_job=None,
) -> tuple[str, Job | None, str]:
    """Execute evaluation and autonomous application on Indeed."""
    if browser_channel(url) != "indeed":
        raise ValueError("URL não pertence ao Indeed.")
    safe_goto(page, url)
    page.wait_for_timeout(2000)
    validate_page(page, "indeed")

    # 1. Pre-check for anti-bot challenges
    blockers = detect_blockers(page)
    if "CAPTCHA" in blockers:
        shot = save_diagnostic_screenshot(page, "indeed_captcha")
        return "BLOCKED_CAPTCHA", None, f"Desafio anti-bot detectado no Indeed. Screenshot: {shot}"

    # 2. Extract and evaluate job against profile
    try:
        job = extract_indeed_job(page, url)
    except (PlaywrightError, ValueError, OSError, KeyError) as exc:
        shot = save_diagnostic_screenshot(page, "indeed_extract_error")
        return "ERROR", None, f"Falha ao extrair dados da vaga Indeed: {exc}. Screenshot: {shot}"

    if review_job is not None:
        job = review_job(job)
    eval_result = evaluate(job, profile)
    validate_source(job)
    if eval_result.status != "READY":
        return eval_result.status, job, f"Critérios não atendidos: {'; '.join(eval_result.reasons)}"
    reasons = profile_blockers(profile)
    if reasons or blockers:
        return "NEEDS_REVIEW", job, "; ".join(reasons + blockers)

    # 3. Locate Indeed Apply button
    apply_btn = page.locator(
        'button#indeedApplyButton, #indeedApplyButton button, '
        'button:has-text("Candidatar-se agora"), button:has-text("Candidatura simplificada")'
    ).first

    if apply_btn.count() == 0:
        # Might be an external company link
        external_link = page.locator('a:has-text("Candidatar-se no site da empresa")').first
        if external_link.count() > 0:
            return "NEEDS_REVIEW", job, "Vaga redireciona para formulário externo da empresa."
        shot = save_diagnostic_screenshot(page, "indeed_no_apply_btn")
        return "NEEDS_REVIEW", job, f"Botão Indeed Apply não encontrado. Screenshot: {shot}"

    apply_btn.click()
    page.wait_for_timeout(2500)

    # 4. Check for modal blockers
    step_blockers = detect_blockers(page)
    if "AUTH" in step_blockers:
        shot = save_diagnostic_screenshot(page, "indeed_login_required")
        return "NEEDS_REVIEW", job, f"Exige login de conta Indeed. Screenshot: {shot}"
    if "CAPTCHA" in step_blockers:
        shot = save_diagnostic_screenshot(page, "indeed_flow_captcha")
        return "BLOCKED_CAPTCHA", job, f"Desafio antibot no modal Indeed Apply. Screenshot: {shot}"

    # 5. Advance through Indeed multi-step form wizard
    for _ in range(6):
        validate_page(page, "indeed")
        if detect_blockers(page):
            return "NEEDS_REVIEW", job, "Bloqueio ou pergunta exige intervenção humana."
        questions, question_evidence = extract_questions(page)
        job = job.model_copy(update={
            "questions": list(dict.fromkeys(job.questions + questions)),
            "extraction_evidence": job.extraction_evidence + question_evidence,
        })
        if evaluate(job, profile).status != "READY":
            return "NEEDS_REVIEW", job, "Perguntas do formulário exigem respostas aprovadas."
        fill_form(page, profile)
        try:
            upload_resume(page, profile)
        except ValueError as exc:
            return "ERROR", job, f"Erro no currículo: {exc}"
        if form_pending(page):
            return "NEEDS_REVIEW", job, "Campos ou consentimentos exigem revisão humana."

        # If submit button is reached
        submit_btn = page.locator(
            'button:has-text("Enviar candidatura"), button:has-text("Enviar sua candidatura")'
        ).first
        if submit_btn.count() > 0:
            if not auto_submit:
                return "NEEDS_REVIEW", job, "Formulário preenchido com sucesso; aguardando confirmação manual."
            if before_submit is None:
                return "NEEDS_REVIEW", job, "Envio exige reserva transacional."
            denied = before_submit(job)
            if denied:
                return denied, job, "Histórico, reserva ou limite impede nova tentativa."
            try:
                confirmation = submit_confirmed(page, submit_btn, "indeed")
                shot = save_diagnostic_screenshot(page, "indeed_submitted")
                return "SUBMITTED", job, f"Candidatura submetida no Indeed: {confirmation}. Comprovante: {shot}"
            except (PlaywrightError, OSError, TimeoutError, AssertionError, ValueError) as exc:
                shot = save_diagnostic_screenshot(page, "indeed_submit_fail")
                return "SUBMISSION_UNCERTAIN", job, f"Falha ao enviar candidatura: {exc}. Screenshot: {shot}"

        # Otherwise continue to next step
        next_btn = page.locator('button:has-text("Continuar"), button:has-text("Avançar")').first
        if next_btn.count() > 0:
            next_btn.click()
            page.wait_for_timeout(1500)
        else:
            break

    shot = save_diagnostic_screenshot(page, "indeed_pending_steps")
    return "NEEDS_REVIEW", job, f"Etapa adicional ou formulário complexo pendente. Screenshot: {shot}"
