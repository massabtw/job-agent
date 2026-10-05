import re
from urllib.parse import quote_plus

from playwright.sync_api import Page

from .session import safe_goto


def search_gupy(page: Page, query: str, limit: int = 10) -> list[dict]:
    """Search for jobs on Gupy Portal and return candidate links."""
    encoded_query = quote_plus(query)
    search_url = f"https://portal.gupy.io/vagas?term={encoded_query}&jobBoardType=gupy"
    safe_goto(page, search_url)

    # Allow listings to render
    page.wait_for_timeout(2500)

    results: list[dict] = []
    seen_ids: set[str] = set()

    links = page.locator('a[href*="/jobs/"], a[href*="/vagas/"]').all()
    for link in links:
        if len(results) >= limit:
            break
        href = link.get_attribute("href") or ""
        match = re.search(r"/(?:jobs|vagas)/(\d+)", href)
        if not match:
            continue
        external_id = match.group(1)
        if external_id in seen_ids:
            continue
        seen_ids.add(external_id)

        # Normalize URL to canonical job URL format
        if href.startswith("http"):
            full_url = href
        else:
            full_url = f"https://portal.gupy.io/jobs/{external_id}"

        title = link.inner_text().splitlines()[0].strip() if link.inner_text() else f"Vaga Gupy {external_id}"
        results.append({
            "platform": "gupy",
            "external_id": external_id,
            "url": full_url,
            "title": title,
        })

    return results


def search_indeed(page: Page, query: str, limit: int = 10) -> list[dict]:
    """Search for jobs on Indeed Brasil and return candidate links."""
    encoded_query = quote_plus(query)
    search_url = f"https://br.indeed.com/jobs?q={encoded_query}&l=Brasil"
    safe_goto(page, search_url)

    page.wait_for_timeout(2500)

    results: list[dict] = []
    seen_jks: set[str] = set()

    # Find job cards with data-jk attribute or links containing jk=
    cards = page.locator("[data-jk], a[href*='jk='], .job_seen_beacon").all()
    for card in cards:
        if len(results) >= limit:
            break
        jk = card.get_attribute("data-jk")
        if not jk:
            href = card.get_attribute("href") or ""
            match = re.search(r"jk=([a-zA-Z0-9]+)", href)
            if match:
                jk = match.group(1)
        if not jk or jk in seen_jks:
            continue
        seen_jks.add(jk)

        title_elem = card.locator("h2, .jobTitle, a").first
        title = title_elem.inner_text().strip() if title_elem.count() > 0 else f"Vaga Indeed {jk}"
        canonical_url = f"https://br.indeed.com/viewjob?jk={jk}"

        results.append({
            "platform": "indeed",
            "external_id": jk,
            "url": canonical_url,
            "title": title,
        })

    return results

