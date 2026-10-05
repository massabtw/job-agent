# Job Agent — ambiente Python

Primeira versão executável de triagem factual e histórico de candidaturas.
Busca anúncios reais na API pública da Remotive e importa anúncios estruturados
Gupy/Indeed. Avalia por regras e gera relatório.
Não acessa contas, não utiliza IA e não envia candidaturas.
Nenhuma conta ou credencial é necessária para os testes locais.

## Ambiente

- Python 3.14, ambiente isolado em `.venv`.
- Playwright e Chromium para interação com navegador.
- HTTPX, Pydantic e python-dotenv para a implementação futura.
- SQLite disponível na biblioteca padrão.
- Pytest e Ruff para testes e verificação do código.

## Instalar novamente (PowerShell)

```powershell
Set-Location 'C:\Users\m84832\Desktop\job-agent'
python -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -r requirements-dev.txt
& '.\.venv\Scripts\python.exe' -m playwright install chromium
```

## Validar

```powershell
Set-Location 'C:\Users\m84832\Desktop\job-agent'
& '.\.venv\Scripts\python.exe' -m pip check
& '.\.venv\Scripts\python.exe' -m pytest -q
& '.\.venv\Scripts\python.exe' -m ruff check .
```

Os testes usam somente um formulário em memória, sem acessar plataformas.
Não é necessário ativar o ambiente nem alterar a política de execução do Windows.

## Executar

### Buscar vagas reais

```powershell
Set-Location 'C:\Users\m84832\Desktop\job-agent'
& '.\.venv\Scripts\python.exe' -X utf8 -m job_agent discover
```

O agente consulta a Remotive, seleciona anúncios por menções às tecnologias do perfil
ou títulos iniciais/backend e executa a triagem. Isso não garante que a stack principal
seja compatível: menções genéricas podem gerar candidatos que serão descartados.
Preserva a atribuição Remotive e o link original de cada anúncio.

Arquivos gerados em C:\Users\m84832\Desktop\job-agent\data:
- discovered.json: anúncios selecionados e evidências extraídas.
- discovery-report.json: resultados e motivos por vaga.
- remotive-cache.sqlite3: resposta original e horário da tentativa.

A fonte informa atraso de 24 horas e recomenda no máximo quatro consultas por dia.
Documentação oficial: https://github.com/remotive-com/remote-jobs-api
O agente mantém intervalo mínimo de seis horas entre tentativas, inclusive falhas.
Dentro desse intervalo reutiliza a resposta; se a tentativa anterior falhou, informa
o bloqueio em vez de repetir. Não apague o cache para contornar esse intervalo.
Timeout de rede de 30 segundos; não segue redirecionamentos automaticamente.

received é o total retornado pela API; selected é o total escolhido pelo filtro local.
discarded refere-se à triagem dos selecionados, não aos registros não selecionados.
Nenhuma vaga é declarada nova só por ter sido coletada agora.
collected_at representa o horário da normalização local, inclusive a partir do cache;
from_cache indica reutilização, e published_at preserva a data fornecida pela fonte.

A extração registra tecnologias mencionadas e sinais de senioridade com trechos.
Não promove diferenciais a requisitos, não extrai uma lista completa de obrigatórios
e não comprova elegibilidade. requirements_verified continua false e active desconhecido.
Restrições geográficas são preservadas; remoto não significa elegibilidade mundial.
Gupy/Indeed continuam apenas como importação local, sem coleta direta desses portais.
discover executa uma busca por comando: ainda não há agendamento online automático.

### Executar exemplo local

```powershell
Set-Location 'C:\Users\m84832\Desktop\job-agent'
& '.\.venv\Scripts\python.exe' -X utf8 -m job_agent run --jobs '.\examples\jobs.json'
```

O exemplo é inteiramente fictício: duas vagas, uma descartada, uma para revisão,
zero envios. Relatório: data/report.json. Histórico: data/history.sqlite3.
Todos os resultados de execução ficam no SQLite; o relatório em arquivo é o último lote.

## Perfil e requisitos

Edite profile.json somente com fatos confirmados. skills contém conhecimentos;
facts contém informações tipadas (por exemplo enrolled booleano, semester e
experience_years inteiros); answers mapeia pergunta exata para resposta aprovada.
preferred_modes aceita remote, hybrid e onsite; preferred_locations contém
localizações aceitas para presencial/híbrido, conforme aparecem no anúncio.
history_complete só deve ser true após importar/conferir candidaturas anteriores.
identity_complete só deve ser true após confirmar cadastro e currículo.
Esses indicadores são declarações do usuário, não verificações automáticas.

O perfil inicial não presume formação, experiência, disponibilidade nem localização.
Conhecimento ausente é desconhecido. Dados locais não são criptografados.

Use examples/jobs.json como referência do formato de importação. URL e ID precisam
corresponder. Anúncios devem ter todos os requisitos estruturados e conferidos:
requirements_verified só pode ser true após essa conferência. active precisa refletir
uma verificação real, que pode ficar desatualizada. A descoberta extrai apenas sinais
limitados do texto livre, não os requisitos obrigatórios completos.
operator=skill verifica expected nos conhecimentos; equals compara tipo e valor;
at_least compara inteiros. Campos adicionais são rejeitados.

Score: senioridade inicial 25, .NET/C# 35, backend no título 15 e até 25 para SQL,
REST, Git, Azure e arquitetura. Score mínimo 80; regras obrigatórias prevalecem.
Todo resultado READY vira NEEDS_REVIEW porque não há integração autorizada de envio.
O limite atual é de até cinco oportunidades elegíveis para encaminhamento por execução.

## Observar arquivos locais

```powershell
Set-Location 'C:\Users\m84832\Desktop\job-agent'
& '.\.venv\Scripts\python.exe' -X utf8 -m job_agent watch --interval 60
```

Coloque listas JSON em data/inbox. Arquivos novos/alterados são processados.
Ctrl+C encerra. Isso não monitora portais nem instala serviço no Windows.
Reiniciar reavalia arquivos, mas não repete candidaturas registradas.
Não execute várias instâncias com o mesmo arquivo de relatório.

## Histórico anterior

Importe a vaga antes e registre uma confirmação real usando sua chave plataforma:ID:

```powershell
Set-Location 'C:\Users\m84832\Desktop\job-agent'
& '.\.venv\Scripts\python.exe' -X utf8 -m job_agent record-history --key 'gupy:ID_REAL' --status SUBMITTED --evidence 'Comprovante real do portal'
```

Esse comando não envia nem verifica o comprovante; registra a declaração do usuário.
SUBMISSION_UNCERTAIN bloqueia novas tentativas até reconciliação, ainda não implementada.
Registros existentes não são sobrescritos. A deduplicação usa plataforma/ID ou
requisition_id comprovadamente compartilhado entre plataformas. Sem esse identificador,
vagas repetidas em portais diferentes precisam de revisão humana.

requirements-lock.txt registra todas as versões instaladas para reprodução.
Para testes rigorosos use pytest -q -W error.

## Próxima fase

### Evolução: perfil, destino e fila transacional

O anúncio aceita application_channel (gupy, indeed, company, remotive) e application_url.
A origem continua em platform/url; o destino é validado independentemente.
Domínio de portal não pode ser rotulado como company para evitar bloqueios.
As capacidades do canal de candidatura continuam desabilitadas. A coleta da Remotive
é separada dessas capacidades; não autoriza preparação ou envio de formulários.

O perfil aceita identity (full_name, email, phone, country, city), resume_path absoluto,
resume_sha256 e profile_confirmed. O hash valida que o arquivo local não mudou;
não verifica veracidade nem conteúdo do currículo. identity_complete é mantido
por compatibilidade na triagem, mas não substitui as novas verificações.

```powershell
Set-Location 'C:\Users\m84832\Desktop\job-agent'
& '.\.venv\Scripts\python.exe' -X utf8 -m job_agent check-profile
& '.\.venv\Scripts\python.exe' -X utf8 -m job_agent queue
```

check-profile retorna código 1 quando faltam dados, sem exibir dados pessoais.
A fila persiste oportunidades encaminhadas em NEEDS_REVIEW. Não há comando de
produção para promover a READY enquanto não existe integração autorizada.
O armazenamento suporta READY → RESERVED → SUBMITTING → SUBMITTED, com estado
SUBMISSION_UNCERTAIN e reconciliação para SUBMITTED mediante evidência.
BEGIN IMMEDIATE protege reservas concorrentes; cada lote permite no máximo cinco
reservas e envios incertos continuam ocupando a posição. Reservas interrompidas
não são liberadas automaticamente, evitando repetição após falhas.
Essa infraestrutura não envia pela rede nem torna a aplicação totalmente autônoma.

Validar fontes e integrações autorizadas para busca e envio, extração com evidências
e eventual IA. Informações desconhecidas resultam em NEEDS_REVIEW.
Aplicar score mínimo 80, deduplicação e limite de cinco envios por execução.
Só registrar SUBMITTED após confirmação verificável.
Antes de habilitar envio, implementar reserva transacional e reconciliação.
CAPTCHA, MFA e testes avaliativos interrompem a candidatura para intervenção humana.
Não salvar senhas em código nem versionar currículos, sessões ou dados pessoais.