import re
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Page

from ..discovery import extract
from ..evaluation import normalize
from ..models import Job


def extract_experience(description: str) -> tuple[float | None, list[dict[str, str]]]:
    """Recognize only narrow explicit minima; ambiguous/optional statements stay unknown."""
    number = r"([0-9]+(?:[.,][0-9]+)?)"
    patterns = [
        rf"\bexperiencia minima (?:de )?{number} anos?\b",
        rf"\bobrigatorio:\s*{number} anos? de experiencia\b",
        rf"\bminimum {number} years? of experience\b",
        rf"\bat least {number} years? of experience required\b",
    ]
    optional_section = False
    evidence = []
    values = set()
    for line in description.splitlines():
        clean = normalize(line).strip()
        if clean.rstrip(":") in {"diferenciais", "desejavel", "nice to have", "preferred qualifications"}:
            optional_section = True
            continue
        if clean.rstrip(":") in {"requisitos", "requisitos obrigatorios", "requirements", "required qualifications"}:
            optional_section = False
            continue
        if optional_section or re.search(
            r"\b(nao|not|desejavel|diferencial|preferencial|preferred|optional|opcional|"
            r"nice to have|ou|or)\b", clean
        ):
            continue
        # Do not turn the upper bound of a range, or a suffix of a number, into a minimum.
        if re.search(r"\d\s*(?:a|to|[-–])\s*\d", clean):
            continue
        for pattern in patterns:
            match = re.search(pattern, clean)
            if match:
                value = float(match.group(1).replace(",", "."))
                values.add(value)
                evidence.append({"field": "required_years", "value": str(value),
                                 "excerpt": line.strip(), "classification": "explicit_minimum"})
                break
    if len(values) != 1:
        return None, [{**item, "classification": "conflicting_minima_needs_review"}
                      for item in evidence]
    return values.pop(), evidence


def closed_notice(page: Page) -> tuple[bool | None, list[dict[str, str]]]:
    """A visible exact notice is a closure signal, not proof that other jobs are active."""
    notices = {"vaga encerrada", "esta vaga nao esta mais disponivel", "this job has expired"}
    for locator in page.locator('[role="alert"], h1, h2, h3').all():
        if not locator.is_visible():
            continue
        text = locator.inner_text().strip()
        if normalize(text).rstrip(".!") in notices:
            return False, [{"field": "active", "value": "false", "excerpt": text,
                            "classification": "visible_closed_notice"}]
    return None, []


def extract_questions(page: Page) -> tuple[list[str], list[dict[str, str]]]:
    """Inspect labelled controls inside forms without reading candidate answers."""
    identity_labels = {
        "nome", "nome completo", "full name", "email", "e-mail", "e mail",
        "telefone", "celular", "phone", "cidade", "city", "pais", "country",
        "linkedin", "perfil do linkedin", "github", "perfil do github",
    }
    questions = []
    evidence = []
    controls = page.locator("form input, form textarea, form select").all()
    for control in controls:
        if not control.is_visible() or not control.is_enabled():
            continue
        if control.get_attribute("type") in {
            "hidden", "submit", "button", "reset", "password", "file", "search",
        }:
            continue
        label = control.evaluate(r"""element => {
            const text = node => {
                const clone = node.cloneNode(true);
                clone.querySelectorAll('input, textarea, select, button, script, style')
                     .forEach(child => child.remove());
                return clone.textContent.trim();
            };
            const refs = (element.getAttribute('aria-labelledby') || '').split(/\s+/)
                .filter(Boolean).map(id => document.getElementById(id)).filter(Boolean);
            if (refs.length) return refs.map(text).join(' ');
            const aria = element.getAttribute('aria-label');
            if (aria) return aria.trim();
            return Array.from(element.labels || []).map(text).join(' ');
        }""")
        label = " ".join(label.split())
        if not label:
            evidence.append({"field": "questions", "value": "unknown", "excerpt": "",
                             "classification": "unlabelled_control_needs_review"})
            continue
        if normalize(label).rstrip(" *:") in identity_labels or label in questions:
            continue
        questions.append(label)
        evidence.append({"field": "questions", "value": label, "excerpt": label,
                         "classification": "visible_form_question"})
    return questions, evidence


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
    external_id = None
    match = re.search(r"/(?:jobs|job|vagas)/(\d+)", parsed.path)
    if match:
        external_id = match.group(1)
    else:
        match_b64 = re.search(r"/job/([A-Za-z0-9_\-=]+)", parsed.path)
        if match_b64:
            token = match_b64.group(1)
            try:
                import base64
                import json
                padded = token + "=" * (-len(token) % 4)
                data = json.loads(base64.urlsafe_b64decode(padded))
                if "jobId" in data:
                    external_id = str(data["jobId"])
            except (ValueError, KeyError):
                external_id = None

    if not external_id:
        raise ValueError(f"Não foi possível extrair o ID da vaga da URL Gupy: {url}")

    canonical_url = f"https://{parsed.hostname}/jobs/{external_id}"


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
    required_years, experience_evidence = extract_experience(description)
    active, availability_evidence = closed_notice(page)
    questions, question_evidence = extract_questions(page)
    evidence.extend(experience_evidence + availability_evidence + question_evidence)

    return Job(
        platform="gupy",
        external_id=external_id,
        url=canonical_url,  # type: ignore[arg-type]
        company=company,
        title=title,
        seniority=seniority,
        stack=stack,
        location=location,
        mode=mode,
        description=description,
        requirements_verified=False,
        required_years=required_years,
        active=active,
        questions=questions,
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
    required_years, experience_evidence = extract_experience(description)
    active, availability_evidence = closed_notice(page)
    questions, question_evidence = extract_questions(page)
    evidence.extend(experience_evidence + availability_evidence + question_evidence)

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
        requirements_verified=False,
        required_years=required_years,
        active=active,
        questions=questions,
        extraction_evidence=evidence,
    )

