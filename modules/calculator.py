"""
calculator.py — Motor de Cálculo Nutricional
Implementa toda a lógica de cálculo conforme RDC 429/2020 (ANVISA).
"""

from __future__ import annotations
from typing import Any

# ─── Valores Diários de Referência (RDC 429/2020 — Adultos) ───────────────────
VALORES_DIARIOS = {
    "energia_kcal":         2000.0,
    "energia_kj":           8400.0,
    "carboidrato":           300.0,
    "acucares_adicionados":   50.0,
    "proteina":               75.0,
    "lipideos":               65.0,
    "gordura_saturada":       22.0,
    "fibra_alimentar":        25.0,
    "sodio":                2300.0,
}

# Nutrientes que não têm %VD estabelecido
SEM_VD = {"acucares_totais", "gordura_trans", "colesterol"}

# ─── Limites "Não contém" (RDC 429/2020) ──────────────────────────────────────
LIMITES_NAO_CONTEM = {
    "gordura_trans":  0.1,   # g/porção
    "sodio":          1.0,   # mg/porção
    "energia_kcal":   4.0,   # kcal/porção
    "energia_kj":    17.0,   # kJ/porção
}


def _safe_float(valor: Any, default: float = 0.0) -> float:
    """Converte valor para float, retornando default se None/inválido."""
    if valor is None:
        return default
    try:
        return float(valor)
    except (ValueError, TypeError):
        return default


def smart_round(valor, contexto: str = "display"):
    """
    contexto='display': retorna string formatada sem zeros desnecessários (até 4 decimais)
    contexto='calc': retorna float arredondado a 4 casas decimais
    """
    v = round(_safe_float(valor), 4)
    if contexto == "calc":
        return v
    if v == int(v):
        return str(int(v))
    return f"{v:.4f}".rstrip("0").rstrip(".")


def convert_to_grams(valor: float, unidade: str, densidade: float = 1.0,
                     total_receita_g: float | None = None) -> float:
    """
    Converte quantidade para gramas.

    unidade: 'g' | 'mL' | '%'
    densidade: g/mL — usado quando unidade='mL'
    total_receita_g: peso total da receita (Modo A para %)
                     None → Modo B: 1% = 1g (base 100g)
    """
    valor = _safe_float(valor)
    if unidade == "g":
        return valor
    if unidade == "mL":
        return round(valor * _safe_float(densidade, 1.0), 4)
    if unidade == "%":
        if total_receita_g is not None and _safe_float(total_receita_g) > 0:
            return round((valor / 100.0) * _safe_float(total_receita_g), 4)
        return valor  # Modo B: 1% = 1g
    return valor


def calcular_composicao_receita(
    ingredientes: list[dict],
    receita_id: int | None = None,
    validar_taco: bool = True,
) -> dict:
    """
    Calcula composição TOTAL somando contribuições de cada ingrediente.

    Args:
        ingredientes: lista de dicts com:
            - composicao_100g: dict com todos os nutrientes
            - quantidade_gramas: float
            - nome: str
            - fonte: str
        receita_id: id da receita para registro de auditoria (opcional)
        validar_taco: se True, executa validação TACO×TBCA em ingredientes TACO

    Returns:
        dict com:
            - nutrientes: {nutriente: valor_total_g_receita}
            - peso_total_gramas: float
            - ingredientes_detalhes: lista com contribuição individual + metadados de fonte
            - alertas_validacao: lista de alertas para exibição na UI
    """
    from modules.database import NUTRIENTES

    # Importação lazy para evitar dependência circular
    _validator = None
    if validar_taco:
        try:
            from modules import validator as _validator
        except ImportError:
            _validator = None

    totais = {n: 0.0 for n in NUTRIENTES}
    peso_total = 0.0
    detalhes = []
    alertas  = []

    for ing in ingredientes:
        comp_original = ing.get("composicao_100g", {})
        qtd   = _safe_float(ing.get("quantidade_gramas", 0))
        nome  = ing.get("nome", "?")
        fonte = ing.get("fonte", "?")

        # ── Validação TACO×TBCA ───────────────────────────────────────────────
        metadados_validacao = {
            "triangulacao_aplicada": False,
            "nivel_confianca":       "—",
            "match_tbca":            "",
            "score_match":           0.0,
            "nutrientes_corrigidos": [],
            "fonte_primaria":        fonte,
        }

        comp = comp_original  # default: usar TACO sem modificação

        if _validator and fonte == "TACO" and comp_original:
            try:
                inconsistencias = _validator.detectar_inconsistencias(nome, comp_original)
                if inconsistencias["inconsistente"]:
                    resultado_tri = _validator.triangular_com_tbca(
                        nome, comp_original, inconsistencias
                    )
                    comp = resultado_tri["dados_finais"]

                    metadados_validacao.update({
                        "triangulacao_aplicada": resultado_tri["triangulacao_aplicada"],
                        "nivel_confianca":       resultado_tri["nivel_confianca"],
                        "match_tbca":            resultado_tri["match_tbca"],
                        "score_match":           resultado_tri["score_match"],
                        "nutrientes_corrigidos": resultado_tri["nutrientes_corrigidos"],
                        "divergencias":          resultado_tri["divergencias"],
                        "fonte_primaria":        "TACO+TBCA" if resultado_tri["triangulacao_aplicada"] else "TACO",
                        "motivo_inconsistencia": inconsistencias["motivo"],
                    })

                    if resultado_tri["triangulacao_aplicada"]:
                        alertas.append({
                            "ingrediente":   nome,
                            "motivo":        inconsistencias["motivo"],
                            "match_tbca":    resultado_tri["match_tbca"],
                            "score_match":   resultado_tri["score_match"],
                            "corrigidos":    resultado_tri["nutrientes_corrigidos"],
                            "nivel":         resultado_tri["nivel_confianca"],
                            "divergencias":  resultado_tri["divergencias"],
                        })

                        if receita_id is not None:
                            _validator.registrar_auditoria(
                                receita_id, nome, resultado_tri
                            )
            except Exception as e:
                print(f"[calculator] Validação falhou para '{nome}': {e}")

        # ── Cálculo da contribuição ───────────────────────────────────────────
        fator  = qtd / 100.0
        contrib = {}
        for nutriente in NUTRIENTES:
            val          = _safe_float(comp.get(nutriente, 0))
            contribuicao = val * fator
            contrib[nutriente] = contribuicao
            totais[nutriente] += contribuicao

        peso_total += qtd
        detalhes.append({
            "nome":                  nome,
            "fonte":                 fonte,
            "quantidade_gramas":     qtd,
            "composicao_100g":       comp,
            "contribuicao":          contrib,
            # campos extras de unidade original (passados pelo app.py)
            "unidade_original":      ing.get("unidade_original", "g"),
            "quantidade_original":   ing.get("quantidade_original"),
            "densidade_utilizada":   ing.get("densidade_utilizada", 1.0),
            # metadados de rastreabilidade de fonte
            "validacao":             metadados_validacao,
        })

    return {
        "nutrientes":            totais,
        "peso_total_gramas":     peso_total,
        "ingredientes_detalhes": detalhes,
        "alertas_validacao":     alertas,
    }


def calcular_por_100g_produto(composicao_total: dict, peso_total_gramas: float) -> dict:
    """
    Normaliza composição total para base de 100g do produto final.
    """
    if peso_total_gramas <= 0:
        return {n: 0.0 for n in composicao_total}

    fator = 100.0 / peso_total_gramas
    return {n: v * fator for n, v in composicao_total.items()}


def calcular_por_porcao(composicao_total: dict, peso_total_gramas: float, porcao_gramas: float) -> dict:
    """
    Calcula valores para a porção informada.
    """
    if peso_total_gramas <= 0 or porcao_gramas <= 0:
        return {n: 0.0 for n in composicao_total}

    fator = porcao_gramas / peso_total_gramas
    return {n: v * fator for n, v in composicao_total.items()}


def calcular_vd(por_porcao: dict, acucares_adicionados_porcao: float = 0.0,
                gordura_saturada_porcao: float = 0.0, gordura_trans_porcao: float = 0.0) -> dict:
    """
    Calcula %VD para cada nutriente obrigatório conforme RDC 429/2020.
    """
    vd = {}

    mapeamento = {
        "energia_kcal":   ("energia_kcal",  VALORES_DIARIOS["energia_kcal"]),
        "carboidrato":    ("carboidrato",    VALORES_DIARIOS["carboidrato"]),
        "proteina":       ("proteina",       VALORES_DIARIOS["proteina"]),
        "lipideos":       ("lipideos",       VALORES_DIARIOS["lipideos"]),
        "fibra_alimentar":("fibra_alimentar",VALORES_DIARIOS["fibra_alimentar"]),
        "sodio":          ("sodio",          VALORES_DIARIOS["sodio"]),
    }

    for key, (nutriente, vd_ref) in mapeamento.items():
        val = _safe_float(por_porcao.get(nutriente, 0))
        vd[key] = round((val / vd_ref) * 100) if vd_ref > 0 else 0

    # Gordura saturada e açúcares adicionados (informados separadamente)
    vd["gordura_saturada"] = round((gordura_saturada_porcao / VALORES_DIARIOS["gordura_saturada"]) * 100)
    vd["acucares_adicionados"] = round((acucares_adicionados_porcao / VALORES_DIARIOS["acucares_adicionados"]) * 100)

    # Gorduras trans e açúcares totais: não têm %VD
    vd["gordura_trans"] = None
    vd["acucares_totais"] = None

    return vd


def aplicar_arredondamentos(valores: dict, porcao_gramas: float) -> dict:
    """
    Aplica regras de arredondamento da RDC 429/2020.

    Regras:
    - Energia kcal/kJ: inteiro
    - Carboidratos, proteínas, gorduras, fibra: 1 decimal
    - Sódio: inteiro (mg)
    - Gorduras trans: "0 g" se < 0,1g/porção
    - Sódio: "0 mg" se < 1mg/porção
    """
    r = dict(valores)

    # Energia
    r["energia_kcal"] = round(_safe_float(r.get("energia_kcal", 0)))
    r["energia_kj"]   = round(_safe_float(r.get("energia_kj",   0)))

    # Macros: 1 decimal
    for n in ["carboidrato", "proteina", "lipideos", "fibra_alimentar",
              "gordura_saturada", "gordura_trans", "acucares_totais", "acucares_adicionados"]:
        if n in r:
            val = _safe_float(r.get(n, 0))
            r[n] = round(val, 1)

    # Sódio: inteiro (mg)
    r["sodio"] = round(_safe_float(r.get("sodio", 0)))

    # Colesterol: inteiro (mg) — se presente
    if "colesterol" in r:
        r["colesterol"] = round(_safe_float(r.get("colesterol", 0)))

    # Regra "Não contém gorduras trans"
    if _safe_float(r.get("gordura_trans", 0)) < 0.1:
        r["gordura_trans_rotulo"] = "0 g**"
        r["gordura_trans"] = 0.0
    else:
        r["gordura_trans_rotulo"] = f'{r["gordura_trans"]:.1f} g'

    # Regra "Não contém" para sódio
    if _safe_float(r.get("sodio", 0)) < 1:
        r["sodio"] = 0

    return r


def montar_tabela_rotulo(
    nome_produto:    str,
    porcao_gramas:   float,
    peso_total:      float,
    nutrientes_totais: dict,
    acucares_adicionados_total: float = 0.0,
    gordura_saturada_total: float = 0.0,
    gordura_trans_total: float = 0.0,
    num_porcoes: int | None = None,
    medida_caseira: str | None = None,
) -> dict:
    """
    Função principal: monta a tabela completa para o rótulo ANVISA.

    Returns:
        dict com:
            - por_100g: dict (valores arredondados)
            - por_porcao: dict (valores arredondados)
            - vd: dict (%VD por nutriente)
            - info: dict (metadados para o rótulo)
    """
    # Calcular por 100g
    por_100g_raw  = calcular_por_100g_produto(nutrientes_totais, peso_total)
    por_porcao_raw = calcular_por_porcao(nutrientes_totais, peso_total, porcao_gramas)

    # Calcular gordura saturada e trans a partir do lipídios (estimativa)
    # Nota: TACO não diferencia gordura saturada — usuário deve informar ou estimar
    gord_sat_porcao   = gordura_saturada_total * (porcao_gramas / peso_total) if peso_total > 0 else 0
    gord_trans_porcao = gordura_trans_total    * (porcao_gramas / peso_total) if peso_total > 0 else 0
    acucar_ad_porcao  = acucares_adicionados_total * (porcao_gramas / peso_total) if peso_total > 0 else 0

    # Adicionar campos extras ao por_porcao_raw
    por_porcao_raw["gordura_saturada"]    = gord_sat_porcao
    por_porcao_raw["gordura_trans"]       = gord_trans_porcao
    por_porcao_raw["acucares_adicionados"] = acucar_ad_porcao
    por_porcao_raw["acucares_totais"]     = por_porcao_raw.get("carboidrato", 0) * 0.4  # estimativa

    por_100g_raw["gordura_saturada"]    = gordura_saturada_total * 100 / peso_total if peso_total > 0 else 0
    por_100g_raw["gordura_trans"]       = gordura_trans_total    * 100 / peso_total if peso_total > 0 else 0
    por_100g_raw["acucares_adicionados"] = acucares_adicionados_total * 100 / peso_total if peso_total > 0 else 0
    por_100g_raw["acucares_totais"]     = por_100g_raw.get("carboidrato", 0) * 0.4

    # Arredondar
    por_100g   = aplicar_arredondamentos(por_100g_raw,   100)
    por_porcao = aplicar_arredondamentos(por_porcao_raw, porcao_gramas)

    # Calcular %VD
    vd = calcular_vd(
        por_porcao,
        acucares_adicionados_porcao=acucar_ad_porcao,
        gordura_saturada_porcao=gord_sat_porcao,
        gordura_trans_porcao=gord_trans_porcao,
    )

    return {
        "por_100g":   por_100g,
        "por_porcao": por_porcao,
        "vd":         vd,
        "info": {
            "nome_produto":   nome_produto,
            "porcao_gramas":  porcao_gramas,
            "peso_total":     peso_total,
            "num_porcoes":    num_porcoes,
            "medida_caseira": medida_caseira or f"{porcao_gramas:.0f} g",
        },
    }


def calcular_contribuicoes_percentuais(detalhes: list[dict]) -> list[dict]:
    """
    Calcula % de contribuição de cada ingrediente no total de cada nutriente.
    """
    from modules.database import NUTRIENTES

    # Calcular totais por nutriente
    totais_nut = {n: 0.0 for n in NUTRIENTES}
    for ing in detalhes:
        for n in NUTRIENTES:
            totais_nut[n] += _safe_float(ing["contribuicao"].get(n, 0))

    # Calcular percentuais
    resultado = []
    for ing in detalhes:
        contrib_perc = {}
        for n in NUTRIENTES:
            total = totais_nut[n]
            val   = _safe_float(ing["contribuicao"].get(n, 0))
            contrib_perc[n] = round((val / total) * 100, 1) if total > 0 else 0.0

        resultado.append({
            **ing,
            "contribuicao_percentual": contrib_perc,
        })

    return resultado


# ─── LIMITAÇÕES CONHECIDAS ─────────────────────────────────────────────────────
# 1. Gordura saturada e trans não são diferenciadas na TACO — devem ser informadas
#    manualmente pelo usuário ou calculadas por formulação específica.
# 2. Açúcares adicionados ≠ açúcares totais — a TACO não diferencia; usuário deve
#    informar separadamente a quantidade de açúcar adicionado na formulação.
# 3. Açúcares totais são estimados como 40% dos carboidratos — isso é uma estimativa
#    grosseira; o valor real depende da composição específica dos ingredientes.
# 4. Perdas nutricionais por processamento térmico (cozimento, pasteurização, etc.)
#    NÃO são calculadas — a TACO fornece valores de alimentos crus ou em estado padrão.
# 5. Medida caseira deve ser informada manualmente — não é calculada automaticamente.
# 6. Variações sazonais e de origem dos ingredientes não são contempladas pela TACO.
# 7. OBRIGATÓRIO: validação por nutricionista habilitado (CRN) antes de uso em
#    rótulo comercial para venda. Este sistema é uma ferramenta de P&D, não substitui
#    análise laboratorial nem laudo técnico obrigatório pela legislação.
