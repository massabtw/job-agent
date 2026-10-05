import importlib
import sqlite3
from contextlib import closing

import pytest
from playwright.sync_api import sync_playwright


@pytest.mark.parametrize("module", ["httpx", "pydantic", "dotenv", "playwright"])
def test_dependencies_import(module):
    assert importlib.import_module(module) is not None


def test_sqlite_available():
    with closing(sqlite3.connect(":memory:")) as connection:
        assert connection.execute("SELECT 1").fetchone() == (1,)


def test_chromium_local_form():
    """Validate browser interaction without accounts, network, or real applications."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(
                '<label for="name">Nome</label><input id="name">'
                '<button onclick="document.getElementById(\'result\').textContent = '
                'document.getElementById(\'name\').value">Simular</button>'
                '<output id="result"></output>'
            )
            page.get_by_label("Nome").fill("Teste local")
            page.get_by_role("button", name="Simular").click()
            assert page.locator("#result").inner_text() == "Teste local"
        finally:
            browser.close()