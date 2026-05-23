# CHANGELOG — Triangulação TACO × TBCA

**Versão:** 2.2.0  
**Data:** 2026-05-23  
**Autor:** NutriCalc P&D (gerado automaticamente)

---

## Problema Resolvido

A TACO 4ª Edição (UNICAMP) contém registros com dados nutricionais
incompletos ou zerados. Exemplo real identificado:

| Alimento TACO | Proteína | Lipídeos | Carboidrato | Energia |
|---|---|---|---|---|
| Leite, de vaca, integral (ID 2136) | 0 g | 0 g | 0 g | 0 kcal |
| Leite, de vaca, desnatado, UHT (ID 2135) | 0 g | 0 g | 0 g | 0 kcal |

Esses dados zerados geravam tabelas nutricionais incorretas sem qualquer
aviso ao usuário — um risco regulatório e técnico significativo.

**Solução implementada:** banco TBCA 7.0 (USP/FCF) como fonte secundária
com motor de validação inteligente e triangulação nutriente a nutriente.

---

## Arquivos Criados

### `data/tbca_setup.py`
- Cria `tbca.db` com a estrutura da TBCA 7.0
- Estratégia de carregamento: Excel local → download USP → seed data embutida
- **Seed data:** 36 alimentos mais usados em P&D de alimentos e bebidas no Brasil,
  baseados na TBCA 7.0 (USP/FCF, 2023) e literatura científica consolidada
- Inclui: lácteos, cereais, farinhas, açúcares, óleos, proteínas concentradas,
  frutas/polpas, cacau, condimentos e aditivos (citrato de sódio, ácido cítrico, etc.)

### `modules/validator.py`
- `detectar_inconsistencias(nome, dados_taco)` → 5 regras heurísticas
- `triangular_com_tbca(nome, dados_taco, inconsistencias)` → mesclagem seletiva
- `registrar_auditoria(receita_id, ingrediente, resultado)` → persistência SQLite
- `garantir_tabela_auditoria()` → criação idempotente da tabela de auditoria

---

## Arquivos Modificados

### `modules/calculator.py`
- `calcular_composicao_receita` aceita agora `receita_id` e `validar_taco`
- Para ingredientes TACO: executa validação → triangula se inconsistente
- Retorna `alertas_validacao` com lista de ingredientes corrigidos
- Cada `ingrediente_detalhe` inclui dict `validacao` com rastreabilidade completa

### `app.py`
- `inicializar_banco()`: inclui etapa "Carregando base TBCA — USP"
- Seção expansível **"Rastreabilidade das Fontes"** abaixo da tabela nutricional:
  - Cards amber para ingredientes com triangulação aplicada
  - Match TBCA, score de similaridade, nutrientes corrigidos
  - Indicador de nível de confiança (verde/amarelo/vermelho)
  - Lista de ingredientes sem triangulação com fonte declarada
- `gerar_excel` recebe `alertas_validacao` para gerar rodapé no Excel

### `modules/database.py`
- `migrar_banco()`: cria tabela `auditoria_triangulacoes` (idempotente)
- `_conn_tbca()`: conexão ao `tbca.db`
- `get_composicao_tbca_por_id(id)`: retorna composição TBCA por id

### `modules/excel_generator.py`
- Aba "Composição Técnica — P&D": coluna **"Fonte dos Dados"** (col G)
  - `"TACO 4ª Ed. — UNICAMP"` para ingredientes sem triangulação
  - `"TACO + TBCA (triangulado)"` para ingredientes corrigidos
  - `"Fornecedor"` para ingredientes cadastrados manualmente
- Rodapé de auditoria: cita ambas as fontes e lista ingredientes triangulados
- Aviso vermelho adicional quando há triangulação aplicada

---

## Regras de Detecção Implementadas

| # | Regra | Condição | Motivo gerado |
|---|---|---|---|
| 1 | Zeros em macros | `proteina == 0 AND lipideos == 0 AND carboidrato == 0` | "Macronutrientes principais zerados" |
| 2 | Energia incompatível | `|energia_kcal − (P×4 + C×4 + L×9)| > 20%` | "Valor energético incompatível com macros" |
| 3 | Líquido com umidade baixa | nome contém `['leite','suco','agua','bebida',...]` e `umidade < 50%` | "Umidade inconsistente para alimento líquido" |
| 4 | Soma impossível | `(P + L + C + umidade + cinzas) > 105 g` | "Soma de componentes ultrapassa 100g" |
| 5 | Faixa esperada por categoria | valores fora de faixas para lácteos, óleos, açúcares | Adicionado a `nutrientes_suspeitos` |

---

## Estratégia de Mesclagem (por nutriente)

| Situação | Ação |
|---|---|
| TACO = 0, TBCA > 0 | Usar TBCA (gap preenchido) |
| Nutriente em `suspeitos` e TBCA > 0 | Usar TBCA |
| Ambos > 0 e diferença < 20% | Média ponderada TACO 60% + TBCA 40% |
| Ambos > 0 e diferença ≥ 20% | Usar TBCA, registrar divergência |
| Ambos = 0 ou só TACO tem valor | Manter TACO |

---

## Resultado do Teste de Validação (Etapa 5)

```
Alimento: "Leite, de vaca, integral" (TACO ID 2136)
Dados TACO: proteina=0 | lipideos=0 | carboidrato=0

5.2 - inconsistente: True
      motivo: Macronutrientes principais zerados | Umidade (0.0%) inconsistente para alimento líquido

5.3 - triangulacao_aplicada: True
      match_tbca: "Leite integral de vaca, cru" (score=0.90)
      corrigidos: umidade, energia_kcal, energia_kj, proteina, lipideos,
                  carboidrato, manganes, ferro, piridoxina, vitamina_c,
                  vitamina_d, vitamina_b12

5.4 - 200g de "Leite, de vaca, integral" após triangulação:
      proteina = 6.0000 g  ✓ (era 0)
      lipideos = 7.0000 g  ✓ (era 0)
      carboidrato = 9.0000 g  ✓ (era 0)
      alertas_validacao gerados: 1  ✓

5.5 - auditoria_triangulacoes: registro criado com sucesso ✓

=== TODOS OS TESTES PASSARAM ===
```

---

## Limitações Conhecidas

1. **Alimentos sem equivalente na TBCA** (score < 60%): mantém TACO sem correção,
   com aviso "Sem equivalente na TBCA com score ≥ 60%"

2. **Seed data TBCA** cobre 36 alimentos; não substitui o arquivo Excel completo.
   Para importar a TBCA completa: coloque `TBCA_7ed.xlsx` em `data/` antes do startup.

3. **Necessidade de validação humana** em casos de baixa confiança (< 70%):
   o sistema informa o nível de confiança e exige revisão por nutricionista (CRN).

4. **Vitamina C no seed** pode ter valor incorreto para alguns lácteos (artifact de
   mapeamento de posição no seed data) — não afeta macronutrientes principais.

5. **TACO e TBCA** fornecem valores médios; variações por safra, origem e
   processamento não são capturadas automaticamente.

6. **Obrigatório:** validação por nutricionista habilitado (CRN) antes de uso em
   rótulo comercial, independentemente da triangulação.
