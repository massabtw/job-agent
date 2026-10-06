import hashlib
from pathlib import Path

from playwright.sync_api import Locator, Page

from ..models import Profile


def _match_identity_value(label_or_name: str, identity: dict[str, str]) -> str | None:
    text = label_or_name.lower().replace("-", " ").replace("_", " ")

    if any(k in text for k in ("nome completo", "fullname", "full name", "nome")):
        return identity.get("full_name")
    if any(k in text for k in ("e mail", "email", "e-mail")):
        return identity.get("email")
    if any(k in text for k in ("telefone", "celular", "phone", "whatsapp")):
        return identity.get("phone")
    if any(k in text for k in ("cidade", "city", "municipio", "município")):
        return identity.get("city")
    if "linkedin" in text:
        return identity.get("linkedin_url")
    if "github" in text:
        return identity.get("github_url")

    return None


def _find_answer(question_text: str, answers: dict[str, str]) -> str | None:
    q_norm = question_text.strip().lower()
    for key, val in answers.items():
        if q_norm and key.strip().lower() == q_norm:
            return val
    return None


def fill_form(page: Page, profile: Profile) -> dict[str, str]:
    """Fill candidate identity and mapped answers into form inputs."""
    filled: dict[str, str] = {}
    inputs = page.locator("input:not([type='hidden']):not([type='submit']):not([type='file']), textarea").all()

    for inp in inputs:
        if (not inp.is_visible() or not inp.is_enabled()
                or inp.get_attribute("type") in {"checkbox", "radio", "password", "button", "reset"}):
            continue
        inp_id = inp.get_attribute("id") or ""
        inp_name = inp.get_attribute("name") or ""
        placeholder = inp.get_attribute("placeholder") or ""

        # Find associated label text if present
        label_text = ""
        if inp_id:
            label_loc = page.locator(f"label[for='{inp_id}']")
            if label_loc.count() > 0:
                label_text = label_loc.first.inner_text().strip()

        combined_desc = f"{label_text} {inp_name} {inp_id} {placeholder}".strip()

        value_to_fill = _match_identity_value(combined_desc, profile.identity)
        if not value_to_fill and label_text:
            value_to_fill = _find_answer(label_text, profile.answers)

        if value_to_fill:
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

