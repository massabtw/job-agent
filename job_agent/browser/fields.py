from playwright.sync_api import Locator

from ..evaluation import normalize

IDENTITY_LABELS = {
    "nome": "full_name", "nome completo": "full_name", "fullname": "full_name",
    "full name": "full_name", "name": "full_name", "email": "email", "e mail": "email",
    "telefone": "phone", "telefone celular": "phone", "celular": "phone", "phone": "phone",
    "cidade": "city", "city": "city", "pais": "country", "country": "country",
    "linkedin": "linkedin_url", "perfil do linkedin": "linkedin_url",
    "github": "github_url", "perfil do github": "github_url",
    "sobrenome": "last_name", "last name": "last_name", "first name": "first_name",
    "digite o numero de telefone": "phone", "numero de telefone": "phone",
}


def identity_field(text: str) -> str | None:
    return IDENTITY_LABELS.get(normalize(text.replace("-", " ").replace("_", " ")).rstrip(" *:"))


def control_label(control: Locator, group: bool = True) -> str:
    label = control.evaluate(r"""(element, group) => {
        const text = node => {
            const clone = node.cloneNode(true);
            clone.querySelectorAll('input,textarea,select,button,script,style')
                .forEach(child => child.remove());
            return clone.textContent.trim();
        };
        if (group && element.type === 'radio') {
            const legend = element.closest('fieldset')?.querySelector('legend');
            if (legend) return text(legend);
        }
        const refs = (element.getAttribute('aria-labelledby') || '').split(/\s+/)
            .filter(Boolean).map(id => document.getElementById(id)).filter(Boolean);
        if (refs.length) return refs.map(text).join(' ');
        const aria = element.getAttribute('aria-label');
        if (aria) return aria.trim();
        return Array.from(element.labels || []).map(text).join(' ');
    }""", group)
    return " ".join(label.split())