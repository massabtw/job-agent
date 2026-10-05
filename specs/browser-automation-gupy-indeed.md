# Especificação Técnica: Conectores de Navegador para Gupy e Indeed

**Status**: Proposta para Implementação  
**Skill**: `to-spec`  
**Data**: 2026-10-05  

---

## 1. Resumo & Objetivo

Construir os conectores de automação de navegador (baseados em Playwright) para as plataformas **Gupy** (`*.gupy.io`) e **Indeed** (`*.indeed.com`), permitindo ao `job-agent`:
1. Navegar até o anúncio da vaga e extrair todos os dados estruturados (descrição, requisitos, modalidade, localidade e perguntas do formulário).
2. Avaliar a compatibilidade contra o [`profile.json`](file:///c:/Users/m84832/Desktop/job-agent/profile.json) utilizando as regras de `job_agent.evaluation`.
3. Detectar bloqueios que exigem intervenção humana obrigatória (*Human-in-the-Loop*).
4. Realizar o preenchimento seguro de dados cadastrais e anexo de currículo.
5. Exigir confirmação humana antes de qualquer submissão real, registrando comprovante no histórico SQLite.

---

## 2. Invariantes e Regras de Segurança

1. **Envio Não-Autônomo sem Confirmação**: O robô **nunca** deve clicar no botão final de submissão sem validação explícita do usuário no terminal ou no navegador.
2. **Pausa para Intervenção Humana (*Human-in-the-Loop*)**: O fluxo deve pausar imediatamente e solicitar a ação do usuário sempre que detectar:
   - Desafios antibot (Cloudflare, reCAPTCHA, hCaptcha);
   - Solicitação de login, senha ou autenticação de dois fatores (MFA/2FA);
   - Perguntas de pretensão salarial;
   - Perguntas adicionais sem resposta cadastrada em `profile.answers`;
   - Testes avaliativos, questionários técnicos ou testes de perfil comportamental.
3. **Uso Exclusivo de Dados Aprovados**: O preenchimento automático limita-se a campos mapeados de `profile.identity` (Nome, E-mail, Telefone com +55 e DDD 41, Cidade, URLs do GitHub e LinkedIn) e o arquivo de currículo cujo SHA-256 corresponda a `profile.resume_sha256`.
4. **Fila e Histórico Transacional**:
   - Cada tentativa deve registrar transição no banco SQLite: `READY` → `RESERVED` → `SUBMITTING` → `SUBMITTED`.
   - Se ocorrer timeout ou falha de rede antes da tela de sucesso, o status deve ser registrado como `SUBMISSION_UNCERTAIN` com evidência textual do erro, bloqueando novas tentativas até conferência.
   - Limite rígido de no máximo 5 candidaturas por lote.

---

## 3. Arquitetura dos Módulos

```text
job_agent/
└── browser/
    ├── __init__.py
    ├── session.py        # Inicialização e contexto seguro do Playwright (headless/headed)
    ├── inspector.py      # Extração de detalhes da vaga e detecção de bloqueios
    ├── filler.py         # Preenchimento de campos padrão e upload de currículo
    ├── gupy.py           # Conector específico para formulários e fluxos da Gupy
    └── indeed.py         # Conector específico para fluxos Indeed Apply
```

### 3.1. `session.py` (Gerenciador de Sessão Playwright)
- Função para criar instâncias de `BrowserContext` isoladas.
- Suporte a alternância entre `headless=True` (para inspeção e extração rápida) e `headless=False` (quando houver necessidade de intervenção humana ou confirmação).
- Configuração de timeouts previsíveis (ex.: 15 segundos para localização de seletores).

### 3.2. `inspector.py` (Inspeção & Detecção de Bloqueios)
- **Extração da Vaga**:
  - Título, nome da empresa, requisitos, modalidade, localidade e texto completo.
  - Converte as informações extraídas para o modelo `Job` existente.
- **Classificação de Bloqueios**:
  - `Blocker.CAPTCHA`: Detecção de `iframe[src*="recaptcha"]`, `iframe[src*="turnstile"]`, `iframe[src*="hcaptcha"]` ou elementos de desafio.
  - `Blocker.AUTH`: Redirecionamento para tela de login ou pedido de código/SMS.
  - `Blocker.SALARY`: Campo de texto contendo termos como *"pretensão salarial"*, *"remuneração pretendida"*, *"salary"*.
  - `Blocker.ASSESSMENT`: Detecção de etapas com testes de lógica ou fit cultural.
  - `Blocker.UNKNOWN_QUESTION`: Campos de perguntas de formulário não catalogadas.

### 3.3. `filler.py` (Preenchedor de Formulário)
- Mapeamento determinístico de formulário baseado em rótulos (`label` acessível, `name`, `placeholder`):
  - Nome completo → `profile.identity["full_name"]`
  - E-mail → `profile.identity["email"]`
  - Telefone → `profile.identity["phone"]`
  - Cidade / Estado → `profile.identity["city"]`, `profile.identity["state"]`
  - Links profissionais → `profile.identity["linkedin_url"]`, `profile.identity["github_url"]`
  - Upload de Currículo → `input[type="file"]` recebe o arquivo em `profile.resume_path`.
- Validação pós-preenchimento: verifica que o valor preenchido reflete o dado do perfil antes de prosseguir.

### 3.4. `gupy.py` (Conector Gupy)
- Suporta URLs no formato `https://*.gupy.io/jobs/:id` e páginas de aplicação `/apply`.
- Lê a descrição estruturada, requisitos obrigatórios vs. desejáveis e termos de consentimento LGPD.
- Navega pelas etapas do fluxo de candidatura da Gupy.

### 3.5. `indeed.py` (Conector Indeed)
- Suporta URLs no formato `https://*.indeed.com/viewjob?jk=:id`.
- Suporta candidaturas com selo "Candidatura Simplificada" (*Indeed Apply*).
- Identifica quando a vaga redireciona para site externo de empresa (canal `company`), marcando o destino adequado.

---

## 4. Novos Comandos de Linha de Comando (CLI)

1. **Inspecionar Vaga sem Preencher**:
   ```powershell
   & '.\.venv\Scripts\python.exe' -X utf8 -m job_agent inspect --url "https://empresa.gupy.io/jobs/123456"
   ```
   - Abre a vaga em modo rápido, extrai dados, avalia compatibilidade com o perfil e lista o score, motivos e eventuais bloqueios encontrados.

2. **Candidatura Assistida (*Interactive Apply*)**:
   ```powershell
   & '.\.venv\Scripts\python.exe' -X utf8 -m job_agent apply --url "https://empresa.gupy.io/jobs/123456"
   ```
   - Executa a inspeção e triagem.
   - Se `DISCARDED`: exibe os motivos e encerra com código 0.
   - Se `NEEDS_REVIEW` por bloqueio: abre a janela para intervenção humana e aguarda o usuário concluir a etapa bloqueante.
   - Se os dados estiverem completos: preenche os campos cadastrais e anexa o currículo.
   - Solicita confirmação no terminal: `"Deseja confirmar o envio desta candidatura? (s/n)"`.
   - Se aprovado: conclui o envio, extrai evidência textual/recibo da tela e salva em `history.sqlite3` com status `SUBMITTED`.

---

## 5. Limites de Escopo (O que NÃO está incluso nesta fase)

- **Envio 100% autônomo sem supervisão**: Não será suportado; toda candidatura exige presença do usuário para auditoria ou confirmação.
- **Quebra automática de CAPTCHA**: Não será implementada; desafios antibot sempre requerem resolução manual do usuário.
- **Armazenamento de senhas**: Não haverá login automático por senha no código.
- **Portais fora de Gupy e Indeed**: Plataformas como Catho, Vagas.com ou formulários proprietários complexos permanecem fora do escopo imediato.

---

## 6. Critérios de Aceitação e Testes

- [ ] Teste unitário e de integração com página HTML mockada reproduzindo formulários Gupy e Indeed sem acesso à rede.
- [ ] Validador de bloqueios disparando corretamente para campos de pretensão salarial e perguntas desconhecidas.
- [ ] Upload de arquivo mockado validando a conferência do hash SHA-256 antes da anexação.
- [ ] Gravação determinística de estados no SQLite (`RESERVED` → `SUBMITTING` → `SUBMITTED` ou `SUBMISSION_UNCERTAIN`).
- [ ] `pytest -q` e `ruff check .` passando com 100% de sucesso.

