import re

from playwright.sync_api import Page, expect

from ..connectors import browser_channel


def validate_page(page: Page, channel: str) -> None:
    if browser_channel(page.url) != channel:
        raise ValueError("Fluxo redirecionou para canal não autorizado.")


def form_pending(page: Page) -> bool:
    """Never infer consent or answers for required fields."""
    return bool(page.locator(
        'input:visible:invalid, textarea:visible:invalid, select:visible:invalid, '
        'input[type="checkbox"]:visible:not(:checked)'
    ).count())


def submit_confirmed(page: Page, button, channel: str) -> str:
    """Require an explicit visible confirmation after the final click."""
    pattern = re.compile(
        r"^(?:Candidatura enviada!?|Candidatura enviada com sucesso!?|"
        r"Sua candidatura foi enviada!?|Application submitted!?)$", re.IGNORECASE
    )
    confirmation = page.get_by_text(pattern).first
    if confirmation.count() and confirmation.is_visible():
        raise ValueError("Confirmação já existia antes da tentativa.")
    validate_page(page, channel)
    button.click(timeout=5000)
    expect(confirmation).to_be_visible(timeout=5000)
    validate_page(page, channel)
    return confirmation.inner_text().strip()