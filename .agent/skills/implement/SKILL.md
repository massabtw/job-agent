---
name: implement
description: Use para executar uma task já definida ou baseada em uma spec. Lê o contexto e a spec antes de alterar código, faz a menor mudança necessária e valida o resultado com build e testes apropriados.
---

# Implement

Use esta skill para traduzir uma task ou especificação em código funcional de forma disciplinada e minimalista.

## Quando Usar
- Tarefa ou especificação já definida e aprovada.
- Requisitos claros e sem pendências conceituais.
- Implementação de novas funcionalidades ou alterações estruturais planejadas.

## Regras Fundamentais
1. **Leitura Prévia Obrigatória**: Leia a spec, os arquivos afetados e o contexto relevante **antes** de alterar qualquer linha de código.
2. **Mudança Cirúrgica / Mínima**:
   - Faça apenas a menor alteração estritamente necessária para cumprir a task.
   - Não adicione refatorações não solicitadas, código "para o futuro" ou complexidade prematura.
3. **Respeito aos Padrões do Projeto**:
   - Siga as convenções de código, tipagem, formatação e estrutura do repositório.
4. **Validação Obrigatória**:
   - Execute linters, checagens de tipos e a suíte de testes relevante antes de considerar o código pronto.
5. **Integração com Outras Skills**:
   - Use `tdd` para desenvolver comportamento verificável.
   - Finalize sempre com `code-review` antes de entregar a tarefa.

## Processo Passo a Passo
1. **Revisar a Spec**: Certifique-se de que todos os critérios de aceitação foram compreendidos.
2. **Mapear Mudanças**: Identifique os pontos de costura (*seams*) no código onde as alterações serão feitas.
3. **Implementar**: Escreva as alterações mínimas necessárias (preferencialmente guiado por testes).
4. **Validar**: Execute os testes e verifique linters/build.
5. **Revisão**: Acione a skill `code-review` para avaliar o diff.

