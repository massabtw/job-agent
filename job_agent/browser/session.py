from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SESSION_DIR = ROOT / "data" / "browser_session"

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined
});
if (!window.chrome) {
    window.chrome = {
        runtime: {}
    };
}
"""


@contextmanager
def create_browser_context(
    user_data_dir: Path | None = None,
    headless: bool = False,
) -> Generator[BrowserContext]:
    """Launch a persistent Chromium context with anti-bot evasion scripts."""
    session_dir = (user_data_dir or DEFAULT_SESSION_DIR).resolve()
    session_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(session_dir),
            headless=headless,
            viewport={"width": 1280, "height": 800},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
            ],
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        context.add_init_script(STEALTH_SCRIPT)
        try:
            yield context
        finally:
            context.close()


def safe_goto(page: Page, url: str, timeout_ms: int = 30000) -> None:
    """Navigate to a URL with standard wait and timeout."""
    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
