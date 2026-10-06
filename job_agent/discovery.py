import json
import re
import sqlite3
import time
import unicodedata
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

import httpx

from .connectors import validate_source
from .models import Job

ENDPOINT = "https://remotive.com/api/remote-jobs"


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in {"p", "li", "br", "div", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"p", "li", "div"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def extract(title: str, html: str) -> tuple[str, list[str], str, list[dict[str, str]]]:
    parser = TextParser()
    parser.feed(html)
    text = "\n".join(line.strip() for line in "".join(parser.parts).splitlines() if line.strip())
    evidence = []
    stack = []
    patterns = {
        ".NET": r"(?i)(?<!\w)\.net\b", "C#": r"(?i)\bc#",
        "SQL": r"(?i)\bsql\b", "Git": r"(?i)\bgit\b", "Azure": r"(?i)\bazure\b",
        "APIs REST": r"(?i)\brest(?:ful)?\b", "Python": r"(?i)\bpython\b",
        "IA": r"(?i)\b(?:IA|AI|intelig[eê]ncia artificial|artificial intelligence)\b",
    }
    for name, pattern in patterns.items():
        for line in [title, *text.splitlines()]:
            if re.search(pattern, line):
                stack.append(name)
                evidence.append({"field": "stack", "value": name, "excerpt": line,
                                 "classification": "mention_only_not_mandatory"})
                break
    seniority = "unknown"
    clean_title = "".join(c for c in unicodedata.normalize("NFKD", title) if not unicodedata.combining(c))
    for level, pattern in (
        ("senior", r"\b(senior|staff|lead|principal)\b"),
        ("intern", r"\b(intern|internship|estagio)\b"),
        ("trainee", r"\btrainee\b"), ("junior", r"\b(junior|jr)\b"),
        ("entry", r"\bentry[ -]level\b"),
    ):
        if re.search(pattern, clean_title, re.IGNORECASE) or re.search(pattern, title, re.IGNORECASE):
            seniority = level
            evidence.append({"field": "seniority", "value": level, "excerpt": title,
                             "classification": "title_signal"})
            break
    return text or title, stack, seniority, evidence


def fetch(cache: Path, client: httpx.Client | None = None) -> tuple[dict, bool]:
    """Persistent six-hour cooldown, including failed attempts; no immediate retries."""
    cache.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(cache, timeout=10)
    try:
        connection.execute("CREATE TABLE IF NOT EXISTS cache(id INTEGER PRIMARY KEY, attempted REAL, payload TEXT)")
        connection.commit()
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT attempted,payload FROM cache WHERE id=1").fetchone()
        now = time.time()
        if row and now - row[0] < 21600:
            connection.rollback()
            if row[1] is None:
                raise ValueError("Consulta anterior falhou ou está em andamento; aguarde o cooldown de seis horas.")
            return json.loads(row[1]), True
        connection.execute("INSERT INTO cache VALUES(1,?,NULL) ON CONFLICT(id) DO UPDATE SET attempted=?,payload=NULL", (now, now))
        connection.commit()
        owned = client is None
        client = client or httpx.Client(timeout=30, follow_redirects=False)
        try:
            response = client.get(ENDPOINT, params={"category": "software-dev"})
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
                raise TypeError("Resposta da Remotive não contém lista de vagas.")
            with connection:
                connection.execute("UPDATE cache SET payload=? WHERE id=1", (json.dumps(payload),))
            return payload, False
        finally:
            if owned:
                client.close()
    finally:
        connection.close()


def discover(payload: dict) -> tuple[list[Job], list[str]]:
    jobs = []
    errors = []
    for index, item in enumerate(payload["jobs"]):
        try:
            description, stack, seniority, evidence = extract(item["title"], item["description"])
            if not stack and not re.search(r"backend|back.end|junior|intern|trainee|entry.level", item["title"], re.IGNORECASE):
                continue
            job = Job(platform="remotive", external_id=str(item["id"]), url=item["url"],
                      company=item["company_name"], title=item["title"], seniority=seniority,
                      stack=stack, description=description, mode="remote",
                      location=item.get("candidate_required_location") or None,
                      geographic_restriction=item.get("candidate_required_location") or None,
                      published_at=item.get("publication_date"),
                      collected_at=datetime.now(UTC).isoformat(), extraction_evidence=evidence,
                      active=None, requirements_verified=False)
            validate_source(job)
            jobs.append(job)
        except (ValueError, TypeError, KeyError) as error:
            errors.append(f"Registro {index}: {error}")
    return jobs, errors