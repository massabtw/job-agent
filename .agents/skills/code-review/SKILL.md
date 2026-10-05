---
name: code-review
description: Use após a implementação. Revisa todo o diff em dois eixos (aderência à spec e qualidade técnica), identificando bugs, regressões, complexidade, segurança e testes ausentes, corrigindo problemas encontrados.
---

# Code Review

Use esta skill imediatamente após concluir uma implementação ou correção, antes de submeter ou considerar o trabalho finalizado.

## Quando Usar
- Ao término de uma rodada de desenvolvimento (`implement` ou resolução de bugs).
- Antes de commitar ou abrir um pull request.
- Como barreira de qualidade contra código inflado, vazamento de escopo ou bugs sutis.

## Processo de Revisão
1. **Inspecione o Diff Completo**:
   - Analise `git diff` e `git status` para garantir que todas as modificações sejam intencionais e necessárias.
2. **Avaliação em Dois Eixos**:
   - **Eixo 1: Aderência à Especificação / Task**:
     - O código cumpre todos os requisitos definidos?
     - Há código extra, escopo vazado ou recursos não solicitados?
     - Os critérios de aceitação foram comprovadamente atendidos?
   - **Eixo 2: Qualidade Técnica & Segurança**:
     - **Bugs & Regressões**: Há risco de quebra em funcionalidades existentes?
     - **Complexidade**: O código é simples, legível e direto? Há abstrações desnecessárias?
     - **Tratamento de Erros**: Erros e exceções são tratados de forma explícita e elegante?
     - **Segurança**: Há vazamento de credenciais, injeção de comandos, problemas de concorrência ou dados sensíveis expostos?
     - **Cobertura de Testes**: Todos os novos caminhos e exceções possuem testes correspondentes?
3. **Ação Corretiva Imediata**:
   - Corrija problemas relevantes encontrados **antes** de considerar a task concluída.
   - Execute a suíte de testes novamente após as correções.
