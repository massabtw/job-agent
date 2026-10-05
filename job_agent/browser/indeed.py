from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from ..evaluation import evaluate
from ..models import Job, Profile
from .filler import fill_form, upload_resume
from .gupy import save_diagnostic_screenshot
from .inspector import detect_blockers, extract_indeed_job
from .session import safe_goto

ROOT = Path(__file__).resolve().parents[2]


def apply_indeed(
    page: Page,
    url: str,
    profile: Profile,
    auto_submit: bool = True,
) -> tuple[str, Job | None, str]:
    """Execute evaluation and autonomous application on Indeed."""
    safe_goto(page, url)
    page.wait_for_timeout(2000)

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

    eval_result = evaluate(job, profile)
    if eval_result.status == "DISCARDED":
        return "DISCARDED", job, f"Critérios não atendidos: {'; '.join(eval_result.reasons)}"

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
        fill_form(page, profile)
        try:
            upload_resume(page, profile)
        except ValueError as exc:
            return "ERROR", job, f"Erro no currículo: {exc}"

        # If submit button is reached
        submit_btn = page.locator(
            'button:has-text("Enviar candidatura"), button:has-text("Enviar sua candidatura")'
        ).first
        if submit_btn.count() > 0:
            if not auto_submit:
                return "NEEDS_REVIEW", job, "Formulário preenchido com sucesso; aguardando confirmação manual."
            try:
                submit_btn.click(timeout=5000)
                page.wait_for_timeout(3000)
                shot = save_diagnostic_screenshot(page, "indeed_submitted")
                return "SUBMITTED", job, f"Candidatura submetida no Indeed. Comprovante: {shot}"
            except (PlaywrightError, OSError, TimeoutError) as exc:
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
