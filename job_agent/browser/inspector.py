import re
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Page

from ..discovery import extract
from ..models import Job


def detect_blockers(page: Page) -> list[str]:
    """Detect anti-bot challenges, authentication walls, and blocking questions."""
    blockers: list[str] = []

    # 1. CAPTCHA & Cloudflare checks
    captcha_selectors = [
        'iframe[src*="recaptcha"]',
        'iframe[src*="turnstile"]',
        'iframe[src*="hcaptcha"]',
        "div#cf-turnstile",
        "div.cf-turnstile",
        "#challenge-running",
        "#cf-challenge-body",
    ]
    for sel in captcha_selectors:
        if page.locator(sel).count() > 0:
            blockers.append("CAPTCHA")
            break

    if "CAPTCHA" not in blockers:
        content = page.content().lower()
        if (
            "verifique que você é humano" in content
            or "challenges.cloudflare.com" in content
            or "just a moment..." in content
        ):
            blockers.append("CAPTCHA")

    # 2. Authentication walls (Password / Login)
    if page.locator('input[type="password"]').count() > 0:
        blockers.append("AUTH")
    else:
        current_url = page.url.lower()
        if any(auth_part in current_url for auth_part in ("/login", "/signin", "/auth/")):
            blockers.append("AUTH")

    # 3. Salary expectation prompts
    salary_patterns = [
        "pretensao salarial",
        "pretensão salarial",
        "salario pretendido",
        "salário pretendido",
        "remuneracao pretendida",
        "remuneração pretendida",
        "salary expectation",
    ]
    labels_text = " ".join(page.locator("label, placeholder").all_inner_texts()).lower()
    if any(pat in labels_text for pat in salary_patterns):
        blockers.append("SALARY")

    # 4. Assessment or behavioral tests
    assessment_patterns = [
        "teste de perfil",
        "teste comportamental",
        "teste de raciocínio",
        "questionário avaliativo",
        "assessment test",
    ]
    page_text = page.inner_text("body").lower() if page.locator("body").count() > 0 else ""
    if any(pat in page_text for pat in assessment_patterns):
        blockers.append("ASSESSMENT")

    return list(dict.fromkeys(blockers))


def extract_gupy_job(page: Page, url: str) -> Job:
    """Extract structured Job object from a Gupy job posting page."""
    parsed = urlparse(url)
    match = re.search(r"/jobs/(\d+)", parsed.path)
    if not match:
        raise ValueError(f"Não foi possível extrair o ID da vaga da URL Gupy: {url}")
    external_id = match.group(1)

    title_locator = page.locator('h1[data-testid="job-title"], h1').first
    title = title_locator.inner_text().strip() if title_locator.count() > 0 else "Vaga Gupy"

    company_locator = page.locator('[data-testid="job-company"]').first
    if company_locator.count() > 0:
        company = company_locator.inner_text().strip()
    else:
        # Fallback to subdomain or title
        host_parts = (parsed.hostname or "").split(".")
        company = host_parts[0].capitalize() if host_parts else "Empresa"

    desc_locator = page.locator('[data-testid="job-description"]').first
    description = desc_locator.inner_text().strip() if desc_locator.count() > 0 else page.inner_text("body").strip()

    # Determine mode
    mode_text = (
        page.locator('[data-testid="job-workplace-type"]').first.inner_text().lower()
        if page.locator('[data-testid="job-workplace-type"]').count() > 0
        else ""
    )
    if not mode_text:
        mode_text = f"{title} {description}".lower()

    if "remoto" in mode_text:
        mode = "remote"
    elif "híbrido" in mode_text or "hibrido" in mode_text:
        mode = "hybrid"
    elif "presencial" in mode_text:
        mode = "onsite"
    else:
        mode = None

    location_locator = page.locator('[data-testid="job-location"]').first
    location = location_locator.inner_text().strip() if location_locator.count() > 0 else None

    # Use existing discovery extractor to determine stack, seniority and evidence
    _, stack, seniority, evidence = extract(title, description)

    return Job(
        platform="gupy",
        external_id=external_id,
        url=url,  # type: ignore[arg-type]
        company=company,
        title=title,
        seniority=seniority,
        stack=stack,
        location=location,
        mode=mode,
        description=description,
        requirements_verified=True,
        extraction_evidence=evidence,
    )


def extract_indeed_job(page: Page, url: str) -> Job:
    """Extract structured Job object from an Indeed job posting page."""
    parsed = urlparse(url)
    ids = parse_qs(parsed.query).get("jk", [])
    if not ids:
        # Check path if formatted as /viewjob/ID
        match = re.search(r"/(?:viewjob|rc/clk)\?.*jk=([a-zA-Z0-9]+)", url)
        external_id = match.group(1) if match else "unknown"
    else:
        external_id = ids[0]

    title_locator = page.locator("h1.jobsearch-JobInfoHeader-title, h1").first
    title = title_locator.inner_text().strip() if title_locator.count() > 0 else "Vaga Indeed"

    company_locator = page.locator('[data-company-name="true"], .jobsearch-InlineCompanyRating-companyHeader').first
    company = company_locator.inner_text().strip() if company_locator.count() > 0 else "Empresa Indeed"

    desc_locator = page.locator("#jobDescriptionText").first
    description = desc_locator.inner_text().strip() if desc_locator.count() > 0 else page.inner_text("body").strip()

    loc_locator = page.locator('[data-testid="job-location"], .jobsearch-JobInfoHeader-subtitle div').first
    location = loc_locator.inner_text().strip() if loc_locator.count() > 0 else None

    desc_lower = f"{title} {description}".lower()
    if "remoto" in desc_lower or "remote" in desc_lower:
        mode = "remote"
    elif "híbrido" in desc_lower or "hybrid" in desc_lower:
        mode = "hybrid"
    else:
        mode = "onsite" if location else None

    _, stack, seniority, evidence = extract(title, description)

    return Job(
        platform="indeed",
        external_id=external_id,
        url=url,  # type: ignore[arg-type]
        company=company,
        title=title,
        seniority=seniority,
        stack=stack,
        location=location,
        mode=mode,
        description=description,
        requirements_verified=True,
        extraction_evidence=evidence,
    )

