import contextlib
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from ..connectors import browser_channel, validate_source
from ..evaluation import evaluate
from ..models import Job, Profile
from ..profile_validation import profile_blockers
from .filler import fill_form, upload_resume
from .inspector import detect_blockers, extract_gupy_job, extract_questions
from .safety import form_pending, submit_confirmed, validate_page
from .session import safe_goto

ROOT = Path(__file__).resolve().parents[2]
SCREENSHOTS_DIR = ROOT / "data" / "screenshots"


def save_diagnostic_screenshot(page: Page, prefix: str) -> str:
    """Capture page state on blockers or errors for human audit."""
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    path = SCREENSHOTS_DIR / f"{prefix}_{stamp}.png"
    with contextlib.suppress(PlaywrightError, OSError):
        page.screenshot(path=str(path), full_page=True)
    return str(path)


def apply_gupy(
    page: Page,
    url: str,
    profile: Profile,
    auto_submit: bool = True,
    before_submit=None,
    review_job=None,
) -> tuple[str, Job | None, str]:
    """Execute evaluation and autonomous application on Gupy."""
    if browser_channel(url) != "gupy":
        raise ValueError("URL não pertence à Gupy.")
    safe_goto(page, url)
    page.wait_for_timeout(2000)
    validate_page(page, "gupy")

    # 1. Pre-check for anti-bot challenges
    blockers = detect_blockers(page)
    if "CAPTCHA" in blockers:
        shot = save_diagnostic_screenshot(page, "gupy_captcha")
        return "BLOCKED_CAPTCHA", None, f"Desafio anti-bot detectado. Screenshot: {shot}"

    # 2. Extract and evaluate job against profile
    try:
        job = extract_gupy_job(page, url)
    except (PlaywrightError, ValueError, OSError, KeyError) as exc:
        shot = save_diagnostic_screenshot(page, "gupy_extract_error")
        return "ERROR", None, f"Falha ao extrair dados da vaga: {exc}. Screenshot: {shot}"

    if review_job is not None:
        job = review_job(job)
    eval_result = evaluate(job, profile)
    validate_source(job)
    if eval_result.status != "READY":
        return eval_result.status, job, f"Critérios não atendidos: {'; '.join(eval_result.reasons)}"
    reasons = profile_blockers(profile)
    if reasons or blockers:
        return "NEEDS_REVIEW", job, "; ".join(reasons + blockers)

    # 3. Locate and click apply button
    apply_btn = page.locator(
        'button:has-text("Candidatar-se"), a:has-text("Candidatar-se"), '
        'button[data-testid="job-apply-button"], a[data-testid="job-apply-button"]'
    ).first
    if apply_btn.count() == 0:
        # Check if already on application page
        if "/apply" not in page.url:
            shot = save_diagnostic_screenshot(page, "gupy_no_apply_btn")
            return "NEEDS_REVIEW", job, f"Botão de candidatura não encontrado. Screenshot: {shot}"
    else:
        apply_btn.click()
        page.wait_for_timeout(2000)
    validate_page(page, "gupy")

    # 4. Check for blockers inside application flow (Auth/Login or Captcha)
    step_blockers = detect_blockers(page)
    if "AUTH" in step_blockers:
        shot = save_diagnostic_screenshot(page, "gupy_login_required")
        return "NEEDS_REVIEW", job, f"Exige login de conta Gupy. Screenshot: {shot}"
    if "CAPTCHA" in step_blockers:
        shot = save_diagnostic_screenshot(page, "gupy_flow_captcha")
        return "BLOCKED_CAPTCHA", job, f"Desafio antibot na tela de formulário. Screenshot: {shot}"
    if step_blockers:
        return "NEEDS_REVIEW", job, "; ".join(step_blockers)

    # 5. Fill application inputs and upload resume
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

    # Consent is never inferred, even for apparently mandatory terms.
    if form_pending(page):
        return "NEEDS_REVIEW", job, "Campos ou consentimentos exigem revisão humana."

    if not auto_submit:
        return "NEEDS_REVIEW", job, "Formulário preenchido com sucesso; aguardando confirmação manual."

    # 7. Autonomous submission click
    submit_btn = page.locator(
        'button:has-text("Enviar candidatura")'
    ).first

    if submit_btn.count() > 0:
        if before_submit is None:
            return "NEEDS_REVIEW", job, "Envio exige reserva transacional."
        denied = before_submit(job)
        if denied:
            return denied, job, "Histórico, reserva ou limite impede nova tentativa."
        try:
            confirmation = submit_confirmed(page, submit_btn, "gupy")
            shot = save_diagnostic_screenshot(page, "gupy_submitted")
            return "SUBMITTED", job, f"Candidatura submetida na Gupy: {confirmation}. Comprovante: {shot}"
        except (PlaywrightError, OSError, TimeoutError, AssertionError, ValueError) as exc:
            shot = save_diagnostic_screenshot(page, "gupy_submit_fail")
            return "SUBMISSION_UNCERTAIN", job, f"Falha ao clicar no envio final: {exc}. Screenshot: {shot}"

    shot = save_diagnostic_screenshot(page, "gupy_pending_step")
    return "NEEDS_REVIEW", job, f"Etapa adicional requer atenção. Screenshot: {shot}"
