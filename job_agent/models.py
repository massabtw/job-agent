from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Profile(StrictModel):
    skills: list[str]
    facts: dict[str, str | bool | int] = Field(default_factory=dict)
    answers: dict[str, str] = Field(default_factory=dict)
    preferred_locations: list[str] = Field(default_factory=list)
    preferred_modes: list[str] = Field(default_factory=list)
    history_complete: bool = False
    identity_complete: bool = False
    identity: dict[str, str] = Field(default_factory=dict)
    resume_path: str | None = None
    resume_sha256: str | None = None
    profile_confirmed: bool = False


class Requirement(StrictModel):
    fact: str
    expected: str | bool | int
    operator: Literal["equals", "at_least", "skill"] = "equals"
    description: str


class Job(StrictModel):
    platform: Literal["gupy", "indeed", "remotive"]
    external_id: str = Field(min_length=1)
    url: HttpUrl
    company: str = Field(min_length=1)
    title: str = Field(min_length=1)
    seniority: Literal["intern", "trainee", "junior", "entry", "mid", "senior", "unknown"]
    stack: list[str]
    location: str | None = None
    mode: Literal["remote", "hybrid", "onsite"] | None = None
    description: str = Field(min_length=1)
    required_years: float | None = Field(default=None, ge=0)
    requirements: list[Requirement] = Field(default_factory=list)
    requirements_verified: bool = False
    questions: list[str] = Field(default_factory=list)
    active: bool | None = None
    published_at: str | None = None
    requisition_id: str | None = None
    application_channel: Literal["gupy", "indeed", "company", "remotive"] | None = None
    application_url: HttpUrl | None = None
    collected_at: str | None = None
    extraction_evidence: list[dict[str, str]] = Field(default_factory=list)
    geographic_restriction: str | None = None


class Evaluation(StrictModel):
    score: int = Field(ge=0, le=100)
    status: Literal["DISCARDED", "NEEDS_REVIEW", "READY"]
    reasons: list[str]