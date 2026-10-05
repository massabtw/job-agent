---
name: to-spec
description: Use depois que os requisitos estiverem definidos para transformar as decisões em uma especificação formal, objetiva e executável, cobrindo comportamento esperado, regras, casos de borda e limites de escopo.
---

# To-Spec

Use esta skill para transformar decisões alinhadas em uma especificação inequívoca que serve de contrato para a implementação.

## Quando Usar
- Imediatamente após a definição de requisitos (ex.: após uma sessão de `grill-with-docs` ou briefing detalhado).
- Antes de iniciar a implementação de tarefas complexas ou não triviais.
- Para congelar o escopo e permitir que qualquer sessão de desenvolvimento execute a tarefa sem ambiguidades.

## Regras Fundamentais
1. **Especificação Objetiva**: Não faça brainstorming aqui. As decisões já foram tomadas; agora organize-as formalmente.
2. **Clareza de Limites**: O documento deve declarar de forma explícita o que está **DENTRO** e o que está **FORA** do escopo.
3. **Critérios Verificáveis**: Cada requisito deve ser passível de validação por teste automatizado ou critério de aceitação observável.

## Estrutura da Especificação
Toda spec deve conter:
- **Resumo & Contexto**: Problema a ser resolvido e objetivo direto.
- **Comportamento Esperado**: Fluxo principal, fluxos secundários e saídas esperadas.
- **Regras & Invariantes**: Regras de validação, limites de taxa, estruturas de dados e contratos de API.
- **Casos Importantes & Edge Cases**: Cenários de exceção, dados nulos, timeouts, concorrência.
- **Limites de Escopo**: O que não será implementado nesta etapa.
- **Critérios de Aceitação**: Checklist de verificação final.

## Armazenamento
- Salve a especificação em um local versionável do repositório (ex.: `specs/<nome-da-feature>.md` ou em issue trackers / documentação acordada).

