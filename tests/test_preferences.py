import pytest

from job_agent.evaluation import evaluate
from job_agent.models import Job, Profile


def candidate():
    return Profile(skills=[".NET", "Python", "IA", "Git", "SQL", "APIs REST"],
                   facts={"target_seniority": "junior", "minimum_monthly_salary": 3500},
                   preferred_locations=["Curitiba"], preferred_modes=["remote", "onsite", "hybrid"],
                   history_complete=True, identity_complete=True)


def vacancy(**changes):
    data = {"platform": "indeed", "external_id": "123",
            "url": "https://br.indeed.com/viewjob?jk=123", "company": "Teste",
            "title": "Backend Python Junior", "seniority": "junior",
            "stack": [".NET", "Python", "Git", "SQL", "APIs REST"], "description": "Teste",
            "mode": "remote", "active": True, "requirements_verified": True}
    return Job(**{**data, **changes})


def test_python_and_ai_are_not_discarded_for_missing_dotnet():
    for title, stack in [("Backend Python Junior", ["Python"]),
                         ("Desenvolvedor IA Junior", ["IA"])]:
        assert evaluate(vacancy(title=title, stack=stack), candidate()).status == "READY"


def test_salary_preference_is_enforced():
    job = vacancy(description="Salário: R$ 2.800 por mês. Contratação CLT.")
    assert evaluate(job, candidate()).status == "DISCARDED"


@pytest.mark.parametrize("location", ["São José dos Pinhais, PR", "Colombo", "Pinhais"])
def test_metro_area_is_not_curitiba(location):
    assert evaluate(vacancy(mode="onsite", location=location), candidate()).status == "DISCARDED"


def test_remote_any_city_and_undisclosed_salary_allowed():
    assert evaluate(vacancy(location="São Paulo"), candidate()).status == "READY"


def test_internship_in_description_excluded():
    assert evaluate(vacancy(description="Tipo de vaga: Estágio."), candidate()).status == "DISCARDED"


def test_curitiba_state_suffix_allowed():
    assert evaluate(vacancy(mode="hybrid", location="Curitiba - PR"), candidate()).status == "READY"


def test_search_plan_uses_local_and_remote_searches():
    from job_agent.browser import search

    assert hasattr(search, "search_plan")
    plan = search.search_plan(candidate())
    assert ("python junior", "Curitiba, PR") in plan
    assert ("python junior remoto", "Brasil") in plan
    assert ("inteligência artificial junior remoto", "Brasil") in plan


@pytest.mark.parametrize("text, expected", [
    ("Salário: R$ 3.500 por mês", "READY"),
    ("Salário: R$ 2.800 a R$ 4.000 por mês", "NEEDS_REVIEW"),
    ("Salário: R$ 30.000 por ano", "READY"),
    ("Salário: R$ 30 por hora", "READY"),
])
def test_salary_units_and_ranges(text, expected):
    assert evaluate(vacancy(description=text), candidate()).status == expected


def test_autopilot_reports_blocked_search_as_failure(tmp_path, monkeypatch, capsys):
    from contextlib import contextmanager

    import job_agent.__main__ as cli

    profile_path = tmp_path / "profile.json"
    profile_path.write_text(candidate().model_dump_json(), encoding="utf-8")
    calls = []

    @contextmanager
    def context(**kwargs):
        class Context:
            def new_page(self):
                return None
        yield Context()

    def blocked(*args, **kwargs):
        calls.append(kwargs)
        raise ValueError("Bloqueio do portal; intervenção humana necessária.")

    monkeypatch.setattr(cli, "create_browser_context", context)
    monkeypatch.setattr(cli, "search_indeed", blocked)
    monkeypatch.setattr("sys.argv", ["job_agent", "--db", str(tmp_path / "db.sqlite3"),
                                   "autopilot", "--profile", str(profile_path), "--no-submit",
                                   "--output", str(tmp_path / "report.json")])
    assert cli.main() == 1
    assert len(calls) == 1