# Diretrizes do Projeto & Skills do Agente (Matt Pocock Workflow)

Este projeto adota um fluxo de engenharia disciplinado baseado nas skills de agente de Matt Pocock. O objetivo é priorizar alinhamento, clareza e testes sobre alterações precipitadas de código.

---

## Regras Gerais

1. **Uso Seletivo**: Não use todas as skills automaticamente. Use somente as que fizerem sentido para a tarefa atual.
2. **Composição**: As skills são modulares e podem ser combinadas quando apropriado.
3. **Disciplina antes do Código**: Sempre prefira um fluxo estruturado e disciplinado a simplesmente começar a alterar código às cegas.

---

## Catálogo de Skills

| Skill | Quando Usar | Ação Principal |
| :--- | :--- | :--- |
| **`grill-with-docs`** | Requisitos vagos, incompletos ou ambíguos | Entrevistar, esclarecer regras/exceções/limites e documentar decisões/termos. Não codificar antes do alinhamento. |
| **`to-spec`** | Requisitos já definidos | Transformar decisões em especificação formal com comportamento esperado, regras, edge cases e limites de escopo. |
| **`implement`** | Executar uma task ou spec já definida | Ler a spec e o contexto antes de codificar, fazer a menor mudança necessária e validar com testes/build. |
| **`tdd`** | Comportamento validável por testes | Ciclo Red → Green → Refactor: demonstrar a falha primeiro, implementar o mínimo para passar, e refatorar com testes verdes. |
| **`code-review`** | Após a implementação | Revisar todo o diff verificando aderência à spec, bugs, regressões, complexidade, segurança e testes ausentes. Corrigir antes de concluir. |
| **`diagnosing-bugs`** | Bug ou comportamento inesperado | Reproduzir deterministicamente primeiro, investigar causa raiz antes de mexer no código, validar hipótese com evidências e adicionar teste de regressão. |
| **`research`** | Falta de conhecimento técnico ou contexto externo | Pesquisar documentação oficial, APIs e limitações, registrando conclusões antes de implementar. |
| **`retro`** | Após várias execuções ou problemas recorrentes | Analisar o que funcionou e o que falhou, identificar gargalos e propor melhorias concretas e reutilizáveis. |

---

## Fluxos de Trabalho Típicos

### 1. Fluxo de Novas Funcionalidades / Mudanças Estruturais
```text
grill-with-docs ──▶ to-spec ──▶ implement (com tdd) ──▶ code-review
```
- Se os requisitos estiverem claros de antemão, pule `grill-with-docs` e comece direto em `to-spec` ou `implement`.
- Se faltar conhecimento sobre uma API de terceiros, execute `research` antes do alinhamento.

### 2. Fluxo de Correção de Bugs
```text
diagnosing-bugs ──▶ tdd (teste de regressão) ──▶ implement (correção mínima) ──▶ code-review
```

### 3. Melhoria Contínua
- Execute `retro` periodicamente ou quando houver atritos frequentes para atualizar estas regras e os scripts do projeto.

---

## Localização das Definições das Skills
As instruções detalhadas de cada skill encontram-se em:
- `.agent/skills/grill-with-docs/SKILL.md`
- `.agent/skills/to-spec/SKILL.md`
- `.agent/skills/implement/SKILL.md`
- `.agent/skills/tdd/SKILL.md`
- `.agent/skills/code-review/SKILL.md`
- `.agent/skills/diagnosing-bugs/SKILL.md`
- `.agent/skills/research/SKILL.md`
- `.agent/skills/retro/SKILL.md`

