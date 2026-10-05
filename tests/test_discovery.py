import httpx
import pytest

from job_agent.connectors import validate_destination
from job_agent.discovery import discover, extract, fetch


def payload():
    return {"jobs": [{"id": 123, "url": "https://remotive.com/remote-jobs/software-dev/backend-123",
                      "title": "Junior Backend .NET", "company_name": "Local test",
                      "description": "<p>SQL required.</p><p>Azure is a nice to have.</p>",
                      "candidate_required_location": "USA"}]}


def test_extraction_not_requirement():
    text, stack, seniority, evidence = extract("Junior Backend C#", "<p>Azure optional</p><script>SQL</script>")
    assert "SQL" not in text
    assert stack == ["C#", "Azure"]
    assert seniority == "junior"
    assert evidence[1]["classification"] == "mention_only_not_mandatory"


def test_discovery_conservative():
    jobs, errors = discover(payload())
    assert not errors
    assert jobs[0].active is None
    assert not jobs[0].requirements_verified
    assert jobs[0].geographic_restriction == "USA"
    assert validate_destination(jobs[0])[0] == "remotive"


def test_cache_no_repeat(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=payload())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert fetch(tmp_path / "cache.db", client)[1] is False
        assert fetch(tmp_path / "cache.db", client)[1] is True
    assert len(calls) == 1


def test_failed_attempt_cooldown(tmp_path):
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503))) as client:
        with pytest.raises(httpx.HTTPStatusError):
            fetch(tmp_path / "cache.db", client)
        with pytest.raises(ValueError, match="cooldown"):
            fetch(tmp_path / "cache.db", client)


def test_invalid_record_does_not_stop_batch():
    data = payload()
    data["jobs"].append({"title": "Incomplete"})
    jobs, errors = discover(data)
    assert len(jobs) == len(errors) == 1


def test_invalid_api_response_cooldown(tmp_path):
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[]))) as client:
        with pytest.raises(TypeError, match="lista de vagas"):
            fetch(tmp_path / "cache.db", client)
        with pytest.raises(ValueError, match="cooldown"):
            fetch(tmp_path / "cache.db", client)


def test_title_seniority_takes_precedence():
    _, _, seniority, _ = extract("Senior Backend .NET", "We mentor junior developers.")
    assert seniority == "senior"