---
name: tdd
description: Use quando houver comportamento que possa ser validado por testes. Trabalha estritamente no ciclo Red -> Green -> Refactor, demonstrando primeiro a falha, implementando o mínimo para passar, e refatorando com testes verdes.
---

# Test-Driven Development (TDD)

Use esta skill para desenvolver lógica de negócio, novas funcionalidades ou correções de forma confiável e verificável através do ciclo clássico de TDD.

## Quando Usar
- Desenvolvimento de qualquer comportamento passível de teste unitário ou de integração.
- Fatiamento vertical de tarefas complexas em comportamentos incrementais.
- Criação de novas funções, classes, validações ou fluxos de dados.

## Ciclo Red → Green → Refactor

### 1. Red (Vermelho)
- Escreva um teste automatizado que expresse o comportamento faltante ou quebrado.
- Execute o teste e confirme que ele **falha**.
- **Atenção**: O teste deve falhar pelo motivo correto (asserção esperada), e não por erros de digitação, sintaxe ou import inválido.

### 2. Green (Verde)
- Implemente apenas o código estritamente necessário para fazer o teste passar.
- Não tente construir a solução definitiva ou genérica nesta etapa; foque em tornar o teste verde da maneira mais simples e direta.
- Execute os testes e comprove o status de aprovação.

### 3. Refactor (Refatorar)
- Apenas após o teste estar validado e verde, melhore o design do código.
- Elimine duplicações, ajuste nomes de variáveis/funções, simplifique estruturas.
- Mantenha a suíte de testes rodando para garantir que nenhuma regressão foi introduzida.

## Regras Fundamentais
- Nunca escreva código de produção sem um teste que falhou primeiro.
- Avance um comportamento por vez (pequenos passos e fatias verticais).
- Não refatore na fase Vermelha; refatore apenas na fase Verde.

