import hashlib
from pathlib import Path

from playwright.sync_api import Locator, Page

from ..models import Profile
from .fields import control_label, identity_field


def _match_identity_value(label_or_name: str, identity: dict[str, str]) -> str | None:
    field = identity_field(label_or_name)
    if field in {"first_name", "last_name"}:
        parts = identity.get("full_name", "").strip().split(maxsplit=1)
        return identity.get(field) or (parts[0 if field == "first_name" else 1]
                                       if len(parts) == 2 else None)
    return identity.get(field) if field else None


def _find_answer(question_text: str, answers: dict[str, str]) -> str | None:
    q_norm = question_text.strip().lower()
    for key, val in answers.items():
        if q_norm and key.strip().lower() == q_norm:
            return val
    return None


def fill_form(page: Page, profile: Profile) -> dict[str, str]:
    """Fill candidate identity and mapped answers into form inputs."""
    filled: dict[str, str] = {}
    inputs = page.locator("input, textarea, select").all()

    for inp in inputs:
        if (not inp.is_visible() or not inp.is_enabled()
                or inp.get_attribute("type") in {"hidden", "file", "submit", "search", "password", "button", "reset"}):
            continue
        inp_id = inp.get_attribute("id") or ""
        inp_name = inp.get_attribute("name") or ""
        placeholder = inp.get_attribute("placeholder") or ""

        label_text = control_label(inp)
        value_to_fill = _find_answer(label_text, profile.answers)
        if value_to_fill is None:
            # A labelled question must never fall back to a misleading name/id attribute.
            candidates = [label_text] if label_text else [inp_name, inp_id, placeholder]
            value_to_fill = next((value for text in candidates
                                  if (value := _match_identity_value(text, profile.identity))), None)
            if inp_name == "names-first-name" and identity_field(label_text) == "full_name":
                value_to_fill = _match_identity_value("first name", profile.identity)

        if value_to_fill:
            kind = inp.get_attribute("type")
            if kind == "checkbox":
                if value_to_fill.strip().casefold() not in {"sim", "yes", "aceito", "i agree"}:
                    continue
                inp.check()
            elif kind == "radio":
                if control_label(inp, group=False).casefold() != value_to_fill.strip().casefold():
                    continue
                inp.check()
            elif inp.evaluate("element => element.tagName") == "SELECT":
                options = inp.locator("option").all()
                matches = [option for option in options
                           if option.inner_text().strip().casefold() == value_to_fill.strip().casefold()
                           and option.is_enabled()]
                if len(matches) != 1:
                    continue
                inp.select_option(value=matches[0].get_attribute("value") or matches[0].inner_text())
            else:
                inp.fill(value_to_fill)
            key = inp_name or inp_id or label_text or "field"
            filled[key] = value_to_fill

    return filled


def upload_resume(page: Page, profile: Profile) -> bool:
    """Verify resume SHA-256 integrity and upload file to file inputs."""
    file_inputs: list[Locator] = page.locator('input[type="file"]').all()
    if not file_inputs:
        return False

    if not profile.resume_path:
        raise ValueError("Caminho do currículo não configurado no perfil.")

    resume_file = Path(profile.resume_path)
    if not resume_file.exists():
        raise ValueError(f"Arquivo de currículo não encontrado: {resume_file}")

    content = resume_file.read_bytes()
    computed_hash = hashlib.sha256(content).hexdigest()

    if not resume_file.is_absolute() or not profile.resume_sha256:
        raise ValueError("Currículo exige caminho absoluto e SHA-256 confirmado.")
    if computed_hash.lower() != profile.resume_sha256.lower():
        raise ValueError(
            "Falha na validação de integridade: o hash SHA-256 do currículo "
            "não corresponde ao registrado no perfil."
        )

    for file_input in file_inputs:
        file_input.set_input_files(str(resume_file.resolve()))

    return True

