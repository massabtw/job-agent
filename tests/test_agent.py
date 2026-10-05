import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from job_agent.connectors import load_jobs, validate_source
from job_agent.evaluation import evaluate
from job_agent.models import Job, Profile, Requirement
from job_agent.runner import run
from job_agent.storage import Store


@pytest.fixture
def profile():
    return Profile(
        skills=[".NET", "SQL", "APIs REST", "Git", "Azure"],
        preferred_modes=["remote"], history_complete=True, identity_complete=True,
    )


@pytest.fixture
def job():
    return Job(
        platform="gupy", external_id="123", url="https://company.gupy.io/jobs/123",
        company="Fictícia", title="Backend C# Junior", seniority="junior",
        stack=["C#", "SQL", "APIs REST", "Git", "Azure"], mode="remote",
        description="Exemplo local.", active=True, requirements_verified=True,
    )


@pytest.fixture
def store(tmp_path):
    instance = Store(tmp_path / "history.sqlite3")
    yield instance
    instance.close()


def test_ready_and_score(job, profile):
    result = evaluate(job, profile)
    assert result.status == "READY"
    assert result.score == 95
    assert not result.reasons


@pytest.mark.parametrize("change", [
    {"seniority": "senior"}, {"title": "Backend .NET Lead"},
    {"required_years": 4}, {"active": False}, {"stack": ["Java"]},
])
def test_discard(job, profile, change):
    assert evaluate(job.model_copy(update=change), profile).status == "DISCARDED"


@pytest.mark.parametrize("change", [
    {"seniority": "intern"}, {"seniority": "trainee"},
    {"title": "Estágio Backend C#"}, {"title": "Trainee em Desenvolvimento"},
])
def test_target_seniority_junior_excludes_intern_and_trainee(job, profile, change):
    profile.facts["target_seniority"] = "junior"
    result = evaluate(job.model_copy(update=change), profile)
    assert result.status == "DISCARDED"
    assert any("fora do perfil" in r for r in result.reasons)



@pytest.mark.parametrize("change", [
    {"active": None}, {"requirements_verified": False}, {"mode": None},
    {"questions": ["Pretensão salarial?"]}, {"required_years": 1},
])
def test_unknown_blocks(job, profile, change):
    assert evaluate(job.model_copy(update=change), profile).status == "NEEDS_REVIEW"


def test_unknown_requirement_and_explicit_incompatibility(job, profile):
    job.requirements = [Requirement(fact="enrolled", expected=True, description="Matriculado")]
    assert evaluate(job, profile).status == "NEEDS_REVIEW"
    profile.facts["enrolled"] = False
    assert evaluate(job, profile).status == "DISCARDED"
    profile.facts["enrolled"] = True
    assert evaluate(job, profile).status == "READY"


def test_no_invented_answers(job, profile):
    job.questions = ["Conclusão do curso?"]
    profile.answers["Conclusão do curso?"] = " "
    assert evaluate(job, profile).status == "NEEDS_REVIEW"
    profile.answers["Conclusão do curso?"] = "Resposta aprovada para teste"
    assert evaluate(job, profile).status == "READY"


def test_numeric_requirement(job, profile):
    job.requirements = [Requirement(
        fact="semester", expected=4, operator="at_least", description="Quarto semestre",
    )]
    profile.facts["semester"] = "4"
    assert evaluate(job, profile).status == "NEEDS_REVIEW"
    profile.facts["semester"] = 3
    assert evaluate(job, profile).status == "DISCARDED"
    profile.facts["semester"] = 4
    assert evaluate(job, profile).status == "READY"


def test_identity_and_history_required(job, profile):
    profile.history_complete = False
    profile.identity_complete = False
    assert evaluate(job, profile).status == "NEEDS_REVIEW"


def test_unknown_skill_not_assumed(job, profile):
    job.requirements = [Requirement(
        fact="docker", expected="Docker", operator="skill", description="Docker",
    )]
    assert evaluate(job, profile).status == "NEEDS_REVIEW"


@pytest.mark.parametrize("url", [
    "https://gupy.io.evil.test/jobs/123", "http://company.gupy.io/jobs/123",
    "https://company.gupy.io/jobs/456", "https://user:pass@company.gupy.io/jobs/123",
])
def test_invalid_portal(job, url):
    invalid = Job.model_validate({**job.model_dump(), "url": url})
    with pytest.raises(ValueError):
        validate_source(invalid)


def test_indeed_import(job, tmp_path):
    job.platform = "indeed"
    payload = job.model_dump(mode="json")
    payload["url"] = "https://br.indeed.com/viewjob?jk=123"
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps([payload]), encoding="utf-8")
    assert validate_source(load_jobs(path)[0]) == "indeed:123"


def test_duplicate_in_batch(job, profile, store):
    report = run([job, job], profile, store)
    assert report["found"] == 1
    assert report["duplicates"] == 1
    assert report["submitted"] == 0


def test_history_prevents_reapplication(job, profile, store):
    key = store.register(job)
    store.record_external(key, "SUBMITTED", "Confirmação externa fictícia para teste")
    assert run([job], profile, store)["items"][0]["status"] == "DUPLICATE"


def test_uncertain_not_retried(job, profile, store):
    key = store.register(job)
    store.record_external(key, "SUBMISSION_UNCERTAIN", "Sem confirmação, teste")
    item = run([job], profile, store)["items"][0]
    assert item["status"] == "NEEDS_REVIEW"
    assert "não repetir" in item["reasons"][0]


def test_cross_platform_requisition_dedup(job, profile, store):
    job.requisition_id = "REQUISITION-1"
    other = Job.model_validate({
        **job.model_dump(), "platform": "indeed", "url": "https://indeed.com/viewjob?jk=123",
    })
    assert run([job, other], profile, store)["duplicates"] == 1


def test_limit_and_blocked_submission(job, profile, store):
    jobs = [Job.model_validate({
        **job.model_dump(), "external_id": str(i), "url": f"https://x.gupy.io/jobs/{i}",
    }) for i in range(1, 8)]
    report = run(jobs, profile, store)
    assert report["needs_review"] == 5
    assert report["items"][-1]["status"] == "LIMIT_REACHED"
    assert report["submitted"] == 0
    assert store.connection.execute("SELECT COUNT(*) FROM applications").fetchone()[0] == 0
    with pytest.raises(ValueError):
        run(jobs, profile, store, 6)


def test_evidence_required(job, store):
    key = store.register(job)
    with pytest.raises(ValueError):
        store.record_external(key, "SUBMITTED", " ")


def test_no_string_boolean_coercion():
    with pytest.raises(ValidationError):
        Profile(skills=[], history_complete="false")


def test_cli_end_to_end(tmp_path):
    root = Path(__file__).resolve().parents[1]
    report = tmp_path / "report.json"
    process = subprocess.run([
        sys.executable, "-X", "utf8", "-m", "job_agent", "--db", str(tmp_path / "db.sqlite3"), "run",
        "--profile", str(root / "profile.json"), "--jobs", str(root / "examples" / "jobs.json"),
        "--report", str(report),
    ], cwd=root, capture_output=True, text=True, encoding="utf-8", check=False)
    assert process.returncode == 0, process.stderr
    result = json.loads(report.read_text(encoding="utf-8"))
    assert (result["found"], result["discarded"], result["needs_review"]) == (2, 1, 1)
    assert result["submitted"] == 0