import re
import unicodedata

from .models import Evaluation, Job, Profile


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    return " ".join("".join(c for c in value if not unicodedata.combining(c)).split())


def skill(value: str) -> str:
    value = normalize(value)
    return {
        "c#": "dotnet", ".net": "dotnet", "csharp": "dotnet", "c sharp": "dotnet",
        "dotnet": "dotnet", "rest": "rest", "apis rest": "rest", "api rest": "rest",
        "sql server": "sql", "mssql": "sql",
        "inteligencia artificial": "ia", "artificial intelligence": "ia", "ai": "ia",
    }.get(value, value)


def evaluate(job: Job, profile: Profile) -> Evaluation:
    known = {skill(s) for s in profile.skills}
    stack = {skill(s) for s in job.stack}
    target_seniority = profile.facts.get("target_seniority")
    is_junior_target = target_seniority == "junior"
    junior = job.seniority in ({"junior", "entry"} if is_junior_target else {"intern", "trainee", "junior", "entry"})
    title = normalize(job.title)
    primary = bool({"dotnet", "python", "ia"} & stack & known)
    target_role = bool(re.search(r"backend|back.end|desenvolvedor|developer|\bia\b|inteligencia artificial", title))
    score = min(100, (25 if junior else 0) + (35 if primary else 0)
                + (15 if re.search(r"backend|back.end", title) else 0)
                + sum(5 for s in ("sql", "rest", "git", "azure", "arquitetura de software")
                      if s in stack & known))
    if junior and primary and target_role:
        score = max(score, 80)
    incompatible = []
    unknown = []
    description = normalize(job.description)
    if is_junior_target and re.search(
        r"(?:tipo de vaga|contratacao|regime)\s*:\s*(?:estagio|aprendiz|temporario)", description
    ):
        incompatible.append("Tipo de contratação fora do perfil CLT/PJ.")
    minimum = profile.facts.get("minimum_monthly_salary")
    if type(minimum) is int:
        # Only labelled monthly BRL amounts; never interpret yearly/hourly pay as monthly.
        for line in job.description.splitlines():
            clean = normalize(line)
            if not re.search(r"salario|remuneracao", clean) or not re.search(r"por mes|mensal", clean):
                continue
            amounts = re.findall(r"r\$\s*([0-9]+(?:\.[0-9]{3})*(?:,[0-9]{2})?)", clean)
            values = [float(value.replace(".", "").replace(",", ".")) for value in amounts]
            if values and max(values) < minimum:
                incompatible.append("Salário mensal divulgado abaixo do mínimo aceito.")
            elif values and min(values) < minimum:
                unknown.append("Faixa salarial exige confirmação do mínimo aceito.")
    if is_junior_target and (
        job.seniority in {"intern", "trainee"} or re.search(r"\b(estagio|estagiario|trainee|intern)\b", title)
    ):
        incompatible.append("Vaga de estágio/trainee fora do perfil (preferência exclusiva por júnior).")
    if job.seniority in {"mid", "senior"} or re.search(
        r"\b(senior|staff|lead|principal|pleno)\b", title
    ):
        incompatible.append("Senioridade fora do perfil.")
    if job.required_years is not None:
        if job.required_years >= 4:
            incompatible.append("Exige obrigatoriamente quatro ou mais anos.")
        elif "experience_years" not in profile.facts:
            unknown.append("Tempo de experiência não informado.")
        else:
            years = profile.facts["experience_years"]
            if type(years) is not int:
                unknown.append("experience_years precisa ser um número inteiro confirmado.")
            elif years < job.required_years:
                incompatible.append("Tempo de experiência insuficiente.")
    if job.active is False:
        incompatible.append("Vaga encerrada.")
    elif job.active is None:
        unknown.append("Disponibilidade não confirmada.")
    if job.seniority == "unknown":
        unknown.append("Senioridade não confirmada.")
    if not job.requirements_verified:
        unknown.append("Lista completa de requisitos obrigatórios não validada.")
    if job.geographic_restriction:
        unknown.append(f"Elegibilidade geográfica precisa de confirmação: {job.geographic_restriction}")
    for requirement in job.requirements:
        if requirement.operator == "skill":
            if skill(str(requirement.expected)) not in known:
                unknown.append(f"Conhecimento não confirmado: {requirement.description}")
            continue
        actual = profile.facts.get(requirement.fact)
        if actual is None:
            unknown.append(f"Informação ausente: {requirement.description}")
            continue
        if requirement.operator == "at_least":
            if type(actual) is not int or type(requirement.expected) is not int:
                unknown.append(f"Comparação numérica inválida: {requirement.description}")
                continue
            match = actual >= requirement.expected
        else:
            match = type(actual) is type(requirement.expected) and actual == requirement.expected
        if not match:
            incompatible.append(f"Requisito incompatível: {requirement.description}")
    if not job.mode or not profile.preferred_modes:
        unknown.append("Modalidade ou preferência não confirmada.")
    elif job.mode not in profile.preferred_modes:
        incompatible.append("Modalidade não aceita.")
    if job.mode != "remote":
        if not job.location or not profile.preferred_locations:
            unknown.append("Localização não confirmada.")
        elif normalize(job.location) not in {normalize(x) for x in profile.preferred_locations} and not (
            normalize(job.location) in {"curitiba - pr", "curitiba, pr", "curitiba, parana", "curitiba, parana, brasil"}
            and "curitiba" in {normalize(x) for x in profile.preferred_locations}
        ):
            incompatible.append("Localização não aceita.")
    for question in job.questions:
        if not profile.answers.get(question, "").strip():
            unknown.append(f"Pergunta sem resposta aprovada: {question}")
    if any(item.get("classification") == "unlabelled_control_needs_review"
           for item in job.extraction_evidence):
        unknown.append("Campo de formulário sem identificação: revisão humana obrigatória.")
    if not profile.history_complete:
        unknown.append("Histórico anterior de candidaturas não confirmado.")
    if not profile.identity_complete:
        unknown.append("Cadastro e currículo ainda não confirmados.")
    if incompatible or score < 80:
        return Evaluation(score=score, status="DISCARDED", reasons=incompatible + (
            ["Score abaixo de 80."] if score < 80 else []
        ))
    return Evaluation(score=score, status="NEEDS_REVIEW" if unknown else "READY", reasons=unknown)