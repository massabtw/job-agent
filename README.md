# Job Agent — ambiente Python

Agente de busca, triagem e candidatura com foco no **Indeed**.
O fluxo ativo de navegador (login, busca, inspeção, aprovação e envio) é exclusivo
do Indeed. A importação e os registros antigos de outras fontes permanecem por
compatibilidade, mas não autorizam envio nesses portais. A descoberta Remotive
continua separada, como fonte auxiliar de triagem.
Os comandos de triagem não acessam contas nem enviam candidaturas. Há também
comandos experimentais de navegador com sessão persistente; não utilizam IA.
O envio é bloqueado enquanto disponibilidade e requisitos não forem comprovados.
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

Os testes usam páginas locais, rotas simuladas e bancos temporários, sem enviar
candidaturas reais ou acessar contas nas plataformas.
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
O comando discover não coleta Indeed. A busca no Indeed é experimental
e separada, pelo comando search (Indeed é o padrão).
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
& '.\.venv\Scripts\python.exe' -X utf8 -m job_agent record-history --key 'indeed:ID_REAL' --status SUBMITTED --evidence 'Comprovante real do portal'
```

Esse comando não envia nem verifica o comprovante; registra a declaração do usuário.
SUBMISSION_UNCERTAIN bloqueia novas tentativas. O comando reconcile permite confirmar
manualmente o envio mediante evidência, sem liberar nova tentativa.
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
A fila persiste oportunidades encaminhadas em NEEDS_REVIEW. O comando approve aceita
vagas revisadas com evidência e autorização explícita, vinculadas ao perfil por 24 horas.
A guarda de envio só promove e reserva quando avaliação e perfil completos passam
nas validações; uma nota em review não equivale a essa aprovação.
O armazenamento suporta READY → RESERVED → SUBMITTING → SUBMITTED, com estado
SUBMISSION_UNCERTAIN e reconciliação para SUBMITTED mediante evidência.
BEGIN IMMEDIATE protege reservas concorrentes; cada lote permite no máximo cinco
reservas e envios incertos continuam ocupando a posição. Reservas interrompidas
não são liberadas automaticamente, evitando repetição após falhas.
Essa infraestrutura sozinha não envia pela rede nem torna a aplicação autônoma.

Validar fontes e integrações autorizadas para busca e envio, extração com evidências
e eventual IA. Informações desconhecidas resultam em NEEDS_REVIEW.
Aplicar score mínimo 80, deduplicação e limite de cinco envios por execução.
Só registrar SUBMITTED após confirmação verificável.
Os comandos de navegador usam reserva transacional antes do clique final. Ainda
falta uma integração autorizada validada nos portais. A reconciliação manual está
disponível pela CLI, sem verificar o portal automaticamente.
CAPTCHA, MFA e testes avaliativos interrompem a candidatura para intervenção humana.
Não salvar senhas em código nem versionar currículos, sessões ou dados pessoais.

## Navegador experimental e limites de segurança

Comandos disponíveis: login, search, inspect, auto-apply, process-queue e autopilot.
Use `python -m job_agent <comando> --help` para os argumentos.

- search busca links; inspect extrai dados sem preencher formulários.
- auto-apply e autopilot aceitam --no-submit, mas continuam dependendo de perfil
  completo e avaliação READY para sequer preencher o formulário.
- A extração atual mantém requirements_verified=false e active desconhecido,
  exceto quando encontra aviso explícito visível de encerramento (active=false).
  Portanto vagas extraídas dos portais ficam descartadas ou em NEEDS_REVIEW até
  revisão factual e autorização explícita pelo comando approve.
- process-queue considera somente READY e revalida antes do envio. Pendências
  retornam a NEEDS_REVIEW com evidência; não altere o banco para contornar validações.
- URLs do fluxo ativo precisam ser HTTPS do Indeed, sem credenciais e porta alternativa.
  Redirecionamentos são conferidos antes de preencher e enviar dados.
- Respostas exigem correspondência exata da pergunta, sem inferir dados pessoais
  a partir de palavras soltas. Labels explícitos, implícitos e ARIA compartilham
  a mesma identificação na inspeção e no preenchimento.
- Selects usam o texto exato de uma única opção habilitada; rádios usam a pergunta
  do grupo (legend) e o texto exato da opção. Consentimentos só são marcados com
  resposta explícita (Sim/Yes/Aceito/I agree) para aquele texto no perfil.
  Controles não resolvidos interrompem o fluxo; não são escolhidos por aproximação.
- Perguntas salariais podem prosseguir com resposta aprovada e campos identificados.
- process-queue continua após falha individual e retorna código 1 se houver erro
  ou envio incerto. Reservas existentes continuam bloqueando novas tentativas.
- Upload exige caminho absoluto e SHA-256; não basta identity_complete=true.
- Antes do clique final, histórico e reserva transacional bloqueiam repetições.
  Cada lote permite 1 a 5 tentativas; envio incerto também ocupa a posição.
- SUBMITTED exige mensagem explícita visível de confirmação após o clique.
  Clique sem confirmação reconhecida vira SUBMISSION_UNCERTAIN, sem repetição automática.
  Os textos de confirmação suportados são limitados e precisam de validação por portal.
- Os testes de sucesso usam vagas revisadas simuladas. Eles não comprovam
  compatibilidade com os formulários reais, autorização de uso nem entrega real.

## Revisão de pendências e reconciliação manual

Os comandos abaixo usam apenas o banco local; não abrem navegador nem enviam dados.
Execute no diretório C:\Users\m84832\Desktop\job-agent:

```powershell
& 'C:\Users\m84832\Desktop\job-agent\.venv\Scripts\python.exe' -m job_agent review
& 'C:\Users\m84832\Desktop\job-agent\.venv\Scripts\python.exe' -m job_agent review --key 'indeed:123'
& 'C:\Users\m84832\Desktop\job-agent\.venv\Scripts\python.exe' -m job_agent review --key 'indeed:123' --note 'Requisitos ainda precisam de conferência'
```

Use a chave real listada pelo comando, não necessariamente indeed:123. review lista
pendências da fila, reservas/interrupções e histórico externo incerto. Com --key,
exibe os dados armazenados da vaga, fila, histórico e notas cronológicas.
Esses dados são snapshots locais, não comprovação atualizada do anúncio.
Notas ficam registradas sem substituir notas anteriores e **não aprovam** a vaga,
não mudam requisitos, não promovem a READY e não removem bloqueios.

Somente depois de conferir manualmente uma confirmação real no portal:

```powershell
& 'C:\Users\m84832\Desktop\job-agent\.venv\Scripts\python.exe' -m job_agent reconcile --key 'indeed:123' --evidence 'Confirmação real conferida no portal; referência do comprovante'
```

reconcile aceita somente envio explicitamente SUBMISSION_UNCERTAIN, na fila ou no
histórico externo. Registra a declaração do usuário; **não valida o comprovante**.
Atualiza histórico e fila existente para SUBMITTED em uma transação, preservando
lote/reserva e auditando o estado/evidência anterior. Não envia outra candidatura
nem libera posições do lote. Estados RESERVED/SUBMITTING ou já confirmados são
rejeitados; não há opção de reset/reenvio. Sem comprovação, mantenha o envio incerto.

Os comandos retornam JSON e código 0 em sucesso, 1 para erros de negócio e 2 para
argumentos inválidos. A tabela reviews é criada automaticamente sem apagar dados
existentes. Não inclua senhas ou tokens em notas/evidências: o texto é armazenado
localmente e aparece na saída de review.

## Extração conservadora de experiência e encerramento

inspect e os conectores de navegador extraem alguns mínimos explícitos de experiência,
como "Experiência mínima de 4 anos", "Obrigatório: 2 anos de experiência",
"Minimum 3 years of experience" e "At least 2.5 years of experience required".
O trecho original fica em extraction_evidence com classificação explicit_minimum.
Diferenciais, opcionais, negações, alternativas e faixas não são promovidos a
exigência; mínimos conflitantes permanecem desconhecidos com evidências de revisão.
Seções textuais reconhecidas como Diferenciais/Desejável também são ignoradas.

Avisos exatos e visíveis em alertas ou títulos ("Vaga encerrada", "Esta vaga não está
mais disponível", "This job has expired") geram active=false com o trecho de prova.
Avisos ocultos e frases semelhantes não confirmam encerramento. Ausência desses
avisos ou presença de botão de candidatura **não comprovam** que a vaga está ativa.

As regras são limitadas, não interpretam toda linguagem natural nem comprovam a
lista completa de obrigatórios: requirements_verified continua false. Textos não
reconhecidos exigem conferência humana. Esta melhoria não libera envio automático
nem altera retroativamente anúncios já persistidos no banco.

## Perguntas visíveis do formulário

A inspeção Indeed registra em questions os textos associados a campos visíveis
e habilitados dentro de elementos form. São reconhecidos labels explícitos/implícitos,
aria-label e referências aria-labelledby. Cada pergunta inclui evidência textual
visible_form_question, sem ler valores ou respostas já preenchidos.
Perguntas com texto idêntico são deduplicadas. Labels básicos de cadastro, campos de
busca, senha, arquivo, botões e campos ocultos/desabilitados não viram perguntas.

Perguntas sem resposta aprovada correspondente no perfil mantêm NEEDS_REVIEW.
Campos sem label reconhecido geram unlabelled_control_needs_review e bloqueiam
READY, mesmo que os demais requisitos tenham sido revisados.
Nenhuma resposta é inventada. A inspeção apenas identifica campos; o preenchimento
usa respostas aprovadas, incluindo selects, rádios e consentimentos específicos.

Isso é uma inspeção parcial da página atual: não avança etapas, não abre modais,
não percorre iframes e não comprova que todas as perguntas foram encontradas.
Controles fora de form e componentes personalizados precisam de revisão humana.
requirements_verified continua false na extração; esta melhoria não autoriza envio.

## Fluxo de envio automático após aprovação

O fluxo agora permite executar o envio de vagas explicitamente aprovadas, usando
os conectores experimentais de navegador. Não é seleção/envio totalmente autônomo:
o usuário precisa conferir os dados e autorizar a candidatura antes.
Os testes locais exercitam os conectores completos; não comprovam compatibilidade
com os portais reais nem autorização de uso. Confira as condições do portal e use
somente sua própria conta. CAPTCHA, MFA, testes e consentimentos não aprovados param o fluxo.

No diretório C:\Users\m84832\Desktop\job-agent, exporte uma vaga:

```powershell
& 'C:\Users\m84832\Desktop\job-agent\.venv\Scripts\python.exe' -m job_agent inspect --url 'https://br.indeed.com/viewjob?jk=123' --output 'C:\Users\m84832\Desktop\job-agent\data\reviewed-jobs.json'
```

Substitua a URL pela vaga real. O arquivo exportado é uma lista de objetos Job.
Confira o anúncio e complete os dados do objeto: requisitos obrigatórios em
requirements, senioridade, modalidade, localidade, experiência mínima, perguntas
e restrições geográficas. Preserve título, empresa, descrição, URL e dados extraídos
que precisam coincidir com a próxima inspeção. Somente após comprovar a disponibilidade
use active=true; somente após revisar a lista completa use requirements_verified=true.
Não basta trocar esses dois flags: requisitos ausentes produzem aprovação incorreta.
Informação desconhecida deve continuar pendente. A declaração é do usuário; o comando
não verifica a veracidade da revisão. A triagem precisa retornar READY (score >=80),
o perfil precisa estar completo, com histórico e currículo/hash confirmados.

Depois da revisão factual, autorize o envio:

```powershell
& 'C:\Users\m84832\Desktop\job-agent\.venv\Scripts\python.exe' -m job_agent approve --jobs 'C:\Users\m84832\Desktop\job-agent\data\reviewed-jobs.json' --evidence 'Referência da revisão e comprovação no portal' --authorize-submit
& 'C:\Users\m84832\Desktop\job-agent\.venv\Scripts\python.exe' -m job_agent queue
```

approve não envia. Persiste a aprovação e coloca as vagas válidas em READY. A validade
é de 24 horas e o hash vincula a aprovação ao perfil inteiro, incluindo respostas
e currículo configurado. Alterar o perfil exige nova aprovação. O processamento é
por vaga: se ocorrer falha em um item, itens anteriores podem já estar aprovados;
confira queue antes de repetir. Históricos e reservas existentes não são liberados.

Para testar o preenchimento sem clicar no envio final:

```powershell
& 'C:\Users\m84832\Desktop\job-agent\.venv\Scripts\python.exe' -m job_agent auto-apply --url 'https://br.indeed.com/viewjob?jk=123' --no-submit
```

O modo --no-submit não envia a candidatura, mas preenche dados e pode carregar currículo
na plataforma; não é uma simulação offline. Esse resultado retorna a fila para revisão,
exigindo nova aprovação para process-queue. Para envio real, após autorizar conscientemente:

```powershell
& 'C:\Users\m84832\Desktop\job-agent\.venv\Scripts\python.exe' -m job_agent process-queue --limit 1
```

Esse último comando **pode enviar candidaturas reais**. Reutiliza sessão autenticada
do comando login. A implementação atual suporta até seis etapas Indeed, sem cobrir
todas as variações/modais/iframes do portal. A Gupy não faz parte do fluxo ativo;
registros e código legado são mantidos apenas para compatibilidade.
A descrição, título, empresa, modalidade, localidade e experiência mínima atuais
precisam coincidir com a aprovação. Mudança, encerramento, aprovação expirada ou perfil
alterado impedem reutilizar a revisão. Perguntas que aparecem após abrir o formulário
são reavaliadas antes do preenchimento e também precisam de respostas aprovadas.
Somente confirmação explícita após o clique resulta em SUBMITTED; ausência de
confirmação vira SUBMISSION_UNCERTAIN. O histórico/reserva impede repetição.
Use review para pendências e reconcile apenas após comprovar um envio incerto.

### Preferências e busca autônoma

O perfil local está configurado para júnior/entrada, sem estágio/trainee, CLT/PJ,
presencial/híbrido somente em Curitiba (não inclui região metropolitana) e remoto
de qualquer cidade, sujeito às restrições geográficas da vaga. Python e IA também
pontuam como tecnologias principais, sem exigir .NET. Conhecimento declarado não
é convertido em anos de experiência.

O mínimo configurado é R$ 3.500 mensais. A triagem reconhece valores em reais
explicitamente identificados como salário/remuneração mensal na descrição: máximo
abaixo do mínimo descarta; faixa que atravessa o mínimo exige revisão. Não converte
valores anuais/horários e não garante detectar salário em componentes separados
da descrição. Salário não divulgado permanece elegível; ausência não comprova o valor.
Respostas salariais só são usadas nas perguntas exatas cadastradas no perfil.

Sem `--queries`, autopilot planeja buscas de backend, .NET, Python e IA conforme
o perfil, combinando Curitiba com buscas nacionais acrescidas de "remoto".
Não é necessário fornecer links. As vagas encontradas continuam sujeitas à
triagem factual e aprovação; esta atualização não elimina pendências de requisitos.

```powershell
& 'C:\Users\m84832\Desktop\job-agent\.venv\Scripts\python.exe' -m job_agent autopilot --no-submit --limit 3 --max-applies 1
```

CAPTCHA/autenticação interrompem as buscas sem tentar contornar o bloqueio.
O relatório registra os termos/localidades planejados e os erros; autopilot retorna
código de saída 1 em erro ou envio incerto. Login/desafios precisam de intervenção
no navegador, nunca de senha compartilhada com o agente.