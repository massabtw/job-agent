import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .models import Job


def browser_channel(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if (parsed.scheme != "https" or parsed.username or parsed.password
            or parsed.port not in {None, 443}):
        raise ValueError("Destino precisa usar HTTPS padrão, sem credenciais.")
    for channel, domain in (("gupy", "gupy.io"), ("indeed", "indeed.com")):
        if host == domain or host.endswith("." + domain):
            return channel
    raise ValueError("Domínio de candidatura não autorizado.")


def validate_source(job: Job) -> str:
    """Canonical portal identifier; tracking parameters cannot bypass deduplication."""
    parsed = urlparse(str(job.url))
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or parsed.username or parsed.password:
        raise ValueError("Use uma URL HTTPS do anúncio, sem credenciais.")
    if job.platform == "gupy":
        if not (host == "gupy.io" or host.endswith(".gupy.io")):
            raise ValueError("URL Gupy inválida.")
        match = re.fullmatch(r"/jobs/(\d+)/?", parsed.path)
        if not match or match.group(1) != job.external_id:
            raise ValueError("ID Gupy não corresponde à URL /jobs/ID.")
    elif job.platform == "indeed":
        if not (host == "indeed.com" or host.endswith(".indeed.com")):
            raise ValueError("URL Indeed inválida; use o link canônico indeed.com.")
        ids = parse_qs(parsed.query).get("jk", [])
        if len(ids) != 1 or ids[0] != job.external_id:
            raise ValueError("ID Indeed não corresponde ao parâmetro jk.")
    else:
        if host != "remotive.com" or not parsed.path.endswith(f"-{job.external_id}"):
            raise ValueError("URL Remotive não corresponde ao ID.")
    return f"{job.platform}:{job.external_id}"


def load_jobs(path: Path) -> list[Job]:
    """Read locally supplied structured exports; no scraping or network access."""
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, list):
        raise TypeError("Arquivo de vagas deve conter uma lista JSON.")
    jobs = [Job.model_validate(item) for item in payload]
    for job in jobs:
        validate_source(job)
        validate_destination(job)
    return jobs


def submission_blocker(platform: str) -> str:
    if platform == "indeed":
        return "Indeed: envio indisponível sem integração oficialmente autorizada."
    return "Gupy: integração autorizada de envio ainda não implementada."


def validate_destination(job: Job) -> tuple[str, str]:
    channel = job.application_channel or job.platform
    url = str(job.application_url or job.url)
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or parsed.username or parsed.password:
        raise ValueError("Destino precisa usar HTTPS, sem credenciais.")
    portal = "remotive" if host == "remotive.com" else "gupy" if host == "gupy.io" or host.endswith(".gupy.io") else (
        "indeed" if host == "indeed.com" or host.endswith(".indeed.com") else "company"
    )
    if portal != channel:
        raise ValueError("Canal de candidatura não corresponde ao domínio de destino.")
    if channel != job.platform and job.application_url is None:
        raise ValueError("Canal externo exige URL explícita.")
    return channel, url


def capabilities(channel: str) -> dict[str, bool]:
    if channel not in {"gupy", "indeed", "company", "remotive"}:
        raise ValueError("Canal desconhecido.")
    return {name: False for name in (
        "can_discover", "can_read_details", "can_prepare", "can_submit",
        "can_verify_submission",
    )}