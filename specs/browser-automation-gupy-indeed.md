# Especificação Técnica: Conectores de Navegador para Gupy e Indeed (Busca & Automação)

**Status**: Especificação Aprovada  
**Skill**: `to-spec`  
**Data**: 2026-10-05  

---

## 1. Resumo & Objetivo

Construir os conectores de automação de navegador (baseados em Playwright) para as plataformas **Gupy** (`*.gupy.io`) e **Indeed** (`*.indeed.com`), permitindo ao `job-agent`:
1. **Buscar vagas ativas**: Consultar os portais de busca da Gupy e Indeed a partir de palavras-chave do perfil (ex.: "backend", "c#", ".net", "python") e extrair anúncios para a triagem.
2. **Inspeção estruturada**: Navegar até o anúncio da vaga e extrair todos os dados estruturados (descrição, requisitos, modalidade, localidade e perguntas do formulário).
3. **Triagem de compatibilidade**: Avaliar a vaga contra o `profile.json` utilizando o motor determinístico `job_agent.evaluation` (score mínimo 80).
4. **Execução Autônoma com Evasão Stealth & Sessão Persistente**:
   - Reutilizar sessão autenticada persistente (`user_data_dir`) e flags de evasão stealth para mitigar CAPTCHAs repetidos e bloqueios Cloudflare.
   - Preencher dados cadastrais e currículo a partir do perfil validado.
   - Efetuar a submissão de forma automatizada quando todos os dados estiverem completos.
5. **Tratamento Gracioso de Bloqueios Irrecuperáveis**: Caso surja um CAPTCHA irrecuperável ou pergunta não mapeada, registrar evidência diagnóstica (screenshot e log), marcar `BLOCKED_CAPTCHA` ou `NEEDS_REVIEW` no SQLite e prosseguir de forma resiliente para as próximas vagas da fila sem travar a execução.

---

## 2. Invariantes, Segurança e Evasão

1. **Sessão Persistente (`user_data_dir`)**:
   - Manter dados de perfil de navegador e cookies em `data/browser_session` (ignorado no `.gitignore`).
   - O usuário faz login nas plataformas uma vez pelo navegador persistente ou importa cookies; as sessões subsequentes reutilizam a autenticação, minimizando desafios Cloudflare Turnstile, reCAPTCHA e telas de login por SMS/MFA.
2. **Playwright Stealth & Evasão**:
   - Mascarar `navigator.webdriver`, habilitar plugins e manter User-Agent realista.
   - Argumentos do Chromium: `--disable-blink-features=AutomationControlled`, `--start-maximized`.
3. **Resiliência e Continuidade sem Travamentos**:
   - Se um antibot/CAPTCHA bloquear a página e não houver como resolver sem intervenção, o agente salva screenshot em `data/screenshots/`, registra a ocorrência no histórico com `SUBMISSION_UNCERTAIN` / `BLOCKED_CAPTCHA` e passa para a próxima vaga da fila.
4. **Uso Exclusivo de Dados Aprovados**:
   - O preenchimento automático limita-se a campos mapeados de `profile.identity` (Nome, E-mail, Telefone, Cidade, URLs do GitHub e LinkedIn) e `profile.answers`.
   - O upload do currículo valida previamente o SHA-256 contra `profile.resume_sha256`.
5. **Fila e Histórico Transacional**:
   - Transições no SQLite: `READY` → `RESERVED` → `SUBMITTING` → `SUBMITTED` (ou `SUBMISSION_UNCERTAIN` / `BLOCKED_CAPTCHA`).
   - Limite configurável por lote (default: 5 candidaturas por execução).

---

## 3. Arquitetura dos Módulos

```text
job_agent/
└── browser/
    ├── __init__.py
    ├── session.py        # Gerenciador de contexto Playwright (sessão persistente + evasão stealth)
    ├── search.py         # Busca de anúncios ativos no Gupy e Indeed por palavras-chave
    ├── inspector.py      # Extração de detalhes da vaga e detecção de bloqueios/formulários
    ├── filler.py         # Preenchimento determinístico de campos e upload de currículo
    ├── gupy.py           # Fluxo completo Gupy: busca, leitura, preenchimento e submissão
    └── indeed.py         # Fluxo completo Indeed: busca, leitura, preenchimento e submissão
```

### 3.1. `session.py` (Gerenciador de Sessão & Stealth)
- Inicializa Chromium com `launch_persistent_context` apontando para `data/browser_session`.
- Injeta scripts de evasão (remoção de `navigator.webdriver`, spoof de `window.chrome`).
- Suporta modos: `headless=False` (padrão para estabilidade antibot) e `headless=True`.

### 3.2. `search.py` (Busca Ativa de Vagas)
- **Gupy**: Consulta o portal de busca Gupy (`portal.gupy.io/vagas`) e coleta links `/jobs/:id`.
- **Indeed**: Consulta a busca Indeed (`br.indeed.com/jobs`) e coleta links canônicos `viewjob?jk=:id`.
- Converte os links para instâncias `Job` e adiciona ao banco de dados e fila.

### 3.3. `inspector.py` (Inspeção & Detecção de Bloqueios)
- Extrai título, empresa, localização, modalidade, requisitos e texto da vaga.
- Converte em objeto `Job` estruturado para o motor `job_agent.evaluation`.
- Detecta bloqueios antibot (`iframe[src*="recaptcha"]`, `iframe[src*="turnstile"]`, Cloudflare challenge).

### 3.4. `filler.py` (Preenchimento Automatizado)
- Preenche inputs cadastrais com base em seletores flexíveis (labels, placeholders, names):
  - Nome completo, e-mail, telefone, localidade, links do LinkedIn/GitHub.
  - Upload do arquivo de currículo em `profile.resume_path` garantindo hash SHA-256 íntegro.
  - Responde perguntas mapeadas diretamente em `profile.answers`.

### 3.5. `gupy.py` e `indeed.py` (Conectores Especializados)
- **Gupy**: Navega pelas etapas do fluxo de candidatura da Gupy (`/apply`), preenche termos LGPD, etapas de dados e executa o clique de confirmação.
- **Indeed**: Opera sobre fluxos "Candidatura Simplificada" (*Indeed Apply*), avançando pelas etapas do modal e submetendo a aplicação.

---

## 4. Comandos de Linha de Comando (CLI)

1. **Buscar vagas ativas nos portais**:
   ```powershell
   & '.\.venv\Scripts\python.exe' -X utf8 -m job_agent search --platform gupy --query "backend .NET"
   & '.\.venv\Scripts\python.exe' -X utf8 -m job_agent search --platform indeed --query "desenvolvedor python"
   ```

2. **Inspecionar Vaga Individual**:
   ```powershell
   & '.\.venv\Scripts\python.exe' -X utf8 -m job_agent inspect --url "https://empresa.gupy.io/jobs/123456"
   ```

3. **Candidatura Automatizada**:
   ```powershell
   & '.\.venv\Scripts\python.exe' -X utf8 -m job_agent auto-apply --url "https://empresa.gupy.io/jobs/123456"
   # ou processar fila em lote:
   & '.\.venv\Scripts\python.exe' -X utf8 -m job_agent process-queue --limit 5
   ```

---

## 5. Limites de Escopo (O que NÃO está incluso nesta fase)

- **InfoJobs**: Planejado para a próxima iteração logo após a consolidação de Gupy e Indeed.
- **Resolução de testes técnicos complexos/provas**: Etapas que exigem testes de lógica/habilidade de terceiros serão marcadas como `NEEDS_REVIEW` ou puladas com log explicativo.
- **Armazenamento de senhas em texto puro**: A autenticação nas plataformas ocorre via perfil de sessão persistente do navegador, nunca salvando credenciais no código.

---

## 6. Critérios de Aceitação e Testes

- [ ] Suporte a `launch_persistent_context` com injeção de evasão de automação.
- [ ] Testes unitários para extração e mapeamento de campos com páginas HTML de exemplo (fixtures locais).
- [ ] Verificação de integridade de currículo (SHA-256) antes do upload.
- [ ] Tratamento determinístico de bloqueios: salvar screenshot e marcar `BLOCKED_CAPTCHA` sem crashar a execução.
- [ ] `pytest -q` e `ruff check .` passando com 100% de sucesso.
