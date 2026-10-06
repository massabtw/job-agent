import re
from urllib.parse import quote_plus

from playwright.sync_api import Page

from ..evaluation import skill
from ..models import Profile
from .inspector import detect_blockers
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

    links = page.locator('a[href*="/job"], a[href*="/vagas/"]').all()
    for link in links:
        if len(results) >= limit:
            break
        href = link.get_attribute("href") or ""
        external_id = None
        match = re.search(r"/(?:jobs|job|vagas)/(\d+)", href)
        if match:
            external_id = match.group(1)
        else:
            match_b64 = re.search(r"/job/([A-Za-z0-9_\-=]+)", href)
            if match_b64:
                token = match_b64.group(1)
                try:
                    import base64
                    import json
                    padded = token + "=" * (-len(token) % 4)
                    payload = json.loads(base64.urlsafe_b64decode(padded))
                    if "jobId" in payload:
                        external_id = str(payload["jobId"])
                except (ValueError, KeyError):
                    external_id = None

        if not external_id or external_id in seen_ids:
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


def search_plan(profile: Profile, queries: list[str] | None = None) -> list[tuple[str, str]]:
    """Plan local and nationwide remote searches; eligibility is still checked per job."""
    if queries is None:
        known = {skill(value) for value in profile.skills}
        queries = ["backend junior"]
        queries += [term for technology, term in (
            ("dotnet", ".net junior"), ("python", "python junior"),
            ("ia", "inteligência artificial junior"),
        ) if technology in known]
    plan = []
    for query in queries:
        if any(mode in profile.preferred_modes for mode in ("onsite", "hybrid")):
            for location in profile.preferred_locations[:1]:
                plan.append((query, "Curitiba, PR" if location == "Curitiba" else location))
        if "remote" in profile.preferred_modes:
            plan.append((f"{query} remoto", "Brasil"))
    return list(dict.fromkeys(plan))


def search_indeed(page: Page, query: str, limit: int = 10, location: str = "Brasil") -> list[dict]:
    """Search for jobs on Indeed Brasil and return candidate links."""
    encoded_query = quote_plus(query)
    search_url = f"https://br.indeed.com/jobs?q={encoded_query}&l={quote_plus(location)}"
    safe_goto(page, search_url)

    page.wait_for_timeout(2500)

    blockers = set(detect_blockers(page)) & {"CAPTCHA", "AUTH", "ANTI_BOT"}
    title = page.title().casefold()
    if blockers or any(text in title for text in ("just a moment", "access denied", "verifique")):
        raise ValueError("Busca interrompida por autenticação ou bloqueio do portal; intervenção humana necessária.")

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

