---
name: grill-with-docs
description: Use quando os requisitos estiverem vagos, incompletos ou ambíguos. Conduz uma entrevista estruturada para esclarecer objetivo, regras, exceções e comportamento esperado, registrando termos e decisões antes de qualquer código ser alterado.
---

# Grill With Docs

Use esta skill antes de iniciar qualquer desenvolvimento quando uma tarefa, funcionalidade ou requisito não estiver perfeitamente claro, completo e delimitado.

## Quando Usar
- Requisitos vagos, abertos ou incompletos.
- Ambiguidade sobre casos de erro, fluxos alternativos ou casos de borda.
- Decisões de design, dados ou arquitetura que ainda não foram tomadas.
- Tarefas onde os limites de escopo não estão nítidos.

## Regras Fundamentais
1. **Não implemente antes dos requisitos estarem claros**: Nunca escreva código com base em suposições ou "vibe coding".
2. **Entrevista Estruturada**: Questione ativamente o usuário sobre:
   - **Objetivo**: Qual o problema real que estamos resolvendo?
   - **Regras de Negócio**: Quais invariantes e comportamentos devem ser garantidos?
   - **Exceções & Edge Cases**: O que acontece quando algo falha ou inputs anômalos ocorrem?
   - **Limites de Escopo**: O que explicitamente **NÃO** faz parte desta entrega?
3. **Documente os Termos e Decisões**:
   - Registre um glossário de termos no contexto do projeto (`CONTEXT.md` ou docs).
   - Documente Architectural Decision Records (ADRs) para decisões técnicas e trade-offs importantes.

## Processo Passo a Passo
1. **Analisar o Pedido**: Identifique lacunas, pressupostos ocultos e ambiguidades.
2. **Fazer Perguntas Direcionadas**: Formule perguntas claras e concisas (preferencialmente de múltipla escolha ou com opções pré-analisadas).
3. **Consolidar Respostas**: Registre os termos definidos e decisões tomadas no contexto do repositório.
4. **Alinhamento Final**: Confirme o entendimento com o usuário antes de passar para a fase de especificação (`to-spec`).

