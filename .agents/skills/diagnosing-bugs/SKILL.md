---
name: diagnosing-bugs
description: Use quando houver um bug ou comportamento inesperado. Primeiro reproduz o problema de forma determinística, investiga a causa raiz antes de alterar código, valida hipóteses com evidências e adiciona teste de regressão.
---

# Diagnosing Bugs

Use esta skill sempre que se deparar com erros, falhas de testes, exceções em runtime ou comportamento inconsistente.

## Quando Usar
- Relato de bug por parte do usuário.
- Falha inesperada durante a execução de testes ou tarefas.
- Problemas intermitentes ou regressões de comportamento.

## Regras Fundamentais
1. **Não altere código às cegas**: É estritamente proibido "chutar" correções sem entender a causa raiz.
2. **Reprodução Primeiro**: Crie um feedback loop confiável (um teste mínimo ou script de reprodução).
3. **Hipótese Baseada em Evidências**: Formule uma explicação causal clara e confirme-a com dados/logs antes de codificar a correção.
4. **Teste de Regressão Obrigatório**: O teste de reprodução deve passar a fazer parte permanente da suíte de testes.

## Processo de Investigação
1. **Construir Loop de Feedback (Reproduzir)**:
   - Crie um teste automatizado ou comando isolado que falhe deterministicamente exibindo o sintoma exato.
2. **Isolar e Investigar**:
   - Trace o fluxo de dados, inspecione chamadas de funções, variáveis e estado interno.
   - Redija logs ou tracebacks protegendo dados sensíveis/credenciais.
3. **Formular Hipótese**:
   - Defina: *"O bug acontece porque [causa específica] quando [condição específica]"*.
   - Colete evidências que confirmem ou refutem a hipótese.
4. **Corrigir na Raiz**:
   - Aplique a menor alteração que elimine a causa raiz sem mascarar o sintoma.
5. **Verificar & Prevenir Regressão**:
   - Execute o teste de reprodução e garanta que ele passa (Verde).
   - Execute toda a suíte de testes para garantir que nada foi quebrado.
