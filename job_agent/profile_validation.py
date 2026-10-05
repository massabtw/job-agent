import hashlib
import re
from pathlib import Path

from .models import Profile


def profile_blockers(profile: Profile) -> list[str]:
    """Check local completeness, not the truth of declarations or resume contents."""
    reasons = []
    if not profile.profile_confirmed:
        reasons.append("Perfil factual ainda não confirmado pelo usuário.")
    for field in ("full_name", "email", "phone", "country", "city"):
        if not profile.identity.get(field, "").strip():
            reasons.append(f"Identidade incompleta: {field}.")
    email = profile.identity.get("email", "")
    if email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        reasons.append("Formato de email inválido.")
    if not profile.resume_path or not profile.resume_sha256:
        reasons.append("Currículo e versão SHA-256 não cadastrados.")
    else:
        path = Path(profile.resume_path)
        if not path.is_absolute():
            reasons.append("Caminho do currículo deve ser absoluto.")
        else:
            try:
                content = path.read_bytes()
                if not content or hashlib.sha256(content).hexdigest() != profile.resume_sha256:
                    reasons.append("Currículo vazio ou alterado desde a confirmação.")
            except OSError:
                reasons.append("Currículo não acessível.")
    return reasons