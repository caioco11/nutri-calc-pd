"""
app.py — NutriCalc P&D
Aplicação principal Streamlit. Interface unificada para cálculo de tabelas
nutricionais no padrão ANVISA (RDC 429/2020).

Execução:
    streamlit run app.py
"""

import os
import sys
import streamlit as st

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


def inicializar_banco():
    """Executa setup do banco na primeira execução."""
    taco_db = os.path.join(ROOT_DIR, "taco.db")
    app_db  = os.path.join(ROOT_DIR, "nutri_calc.db")
    if not os.path.exists(taco_db) or not os.path.exists(app_db):
        with st.spinner("Inicializando banco de dados (primeira execução)..."):
            try:
                data_setup = os.path.join(ROOT_DIR, "data", "taco_setup.py")
                import importlib.util
                spec = importlib.util.spec_from_file_location("taco_setup", data_setup)
                mod  = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                mod.criar_taco_db()
                mod.criar_app_db()
                st.success("Banco de dados inicializado com sucesso.")
            except Exception as e:
                st.error(f"Erro ao inicializar banco de dados: {e}")
                st.stop()


st.set_page_config(
    page_title="NutriCalc P&D",
    page_icon="N",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from modules import style as sty
sty.inject_global_css()

inicializar_banco()

import pandas as pd

from modules import database as db
from modules import calculator as calc
from modules import parser as prs
from modules import excel_generator as xls
from modules.database import NUTRIENTES

# Migrações de banco (idempotente — seguro chamar a cada startup)
db.migrar_banco()


@st.cache_data
def _get_db_count() -> int:
    """Cached once per session — count only changes if taco_setup.py is rerun."""
    try:
        import sqlite3 as _sq
        _c = _sq.connect(os.path.join(ROOT_DIR, "taco.db"))
        n = _c.execute("SELECT COUNT(*) FROM alimentos_taco").fetchone()[0]
        _c.close()
        return n
    except Exception:
        return 0

_db_count = _get_db_count()

sty.render_page_header(_db_count)


def _init_session():
    defaults = {
        "ingredientes":          [],
        "resultado_calculo":     None,
        "receita_editando_id":   None,
        "upload_preview":        None,
        "forn_editando_id":      None,
        "forn_dados_extraidos":  {},
        "ficha_unico":           None,
        # unit selector state
        "form_unit":             "g",
        "form_modo_pct":         "A",
        "form_total_receita_g":  1000.0,
        "form_densidade_manual": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_session()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding:0.75rem 0 0.5rem">
        <div style="font-size:1.1rem;font-weight:700;letter-spacing:-0.02em">
            Nutri<span style="color:var(--accent)">Calc</span> P&amp;D
        </div>
        <div style="font-size:0.7rem;color:var(--text-muted);margin-top:3px">v2.0 · Uso Interno</div>
    </div>
    """, unsafe_allow_html=True)
    st.divider()
    st.markdown('<div class="nc-section-label">Status do Sistema</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div style="font-size:0.8rem;color:var(--text-secondary);line-height:2">
        <span style="color:#3FB950">&#9679;</span> Banco ativo: {_db_count:,} alimentos<br>
        Padrão: ANVISA RDC 429/2020<br>
        Fontes: TACO 4ª Ed. + TBCA/USDA
    </div>
    """, unsafe_allow_html=True)
    st.divider()
    st.markdown('<div class="nc-section-label">Aviso Legal</div>', unsafe_allow_html=True)
    st.markdown("""
    <div style="font-size:0.72rem;color:var(--text-muted);line-height:1.7">
        Estimativa para uso interno em P&amp;D.<br>
        Obrigatório: validação por nutricionista<br>
        habilitado (CRN) antes de uso em<br>
        rótulo comercial.
    </div>
    """, unsafe_allow_html=True)

# ── Abas principais ────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["Nova Receita", "Ingredientes de Fornecedor", "Receitas Salvas"])


# ══════════════════════════════════════════════════════════════════════════════
#  ABA 1 — NOVA RECEITA
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    col_esq, col_dir = st.columns([3, 1])

    with col_esq:
        sty.render_section_label("Dados do Produto")

    with col_dir:
        if st.session_state.receita_editando_id:
            st.info(f"Editando receita #{st.session_state.receita_editando_id}")
            if st.button("Nova Receita", use_container_width=True):
                st.session_state.ingredientes        = []
                st.session_state.resultado_calculo   = None
                st.session_state.receita_editando_id = None
                st.rerun()

    c1, c2, c3 = st.columns([3, 1.5, 1.5])
    nome_produto = c1.text_input(
        "Nome do Produto *",
        placeholder="Ex.: Bolo de Chocolate Diet",
        value=st.session_state.get("form_nome", ""),
    )
    porcao_g = c2.number_input(
        "Tamanho da Porção (g) *",
        min_value=1.0, max_value=10000.0,
        value=float(st.session_state.get("form_porcao", 30)),
        step=0.5,
    )
    num_porcoes = c3.number_input(
        "Nº de Porções por Embalagem",
        min_value=1, max_value=9999,
        value=int(st.session_state.get("form_nporcoes", 1)),
    )
    medida_caseira = st.text_input(
        "Medida Caseira (opcional)",
        placeholder="Ex.: 1 fatia, 2 colheres de sopa, 1 unidade",
        value=st.session_state.get("form_medida", ""),
    )

    with st.expander("Campos Adicionais ANVISA — Gordura Saturada, Trans, Açúcares Adicionados"):
        st.caption("Estes valores não constam na TACO e devem ser informados com base na formulação.")
        c4, c5, c6 = st.columns(3)
        gordura_saturada_total = c4.number_input(
            "Gordura Saturada Total na Receita (g)",
            min_value=0.0, max_value=10000.0,
            value=float(st.session_state.get("form_gord_sat", 0.0)), step=0.1,
            help="Soma das gorduras saturadas de todos os ingredientes",
        )
        gordura_trans_total = c5.number_input(
            "Gordura Trans Total na Receita (g)",
            min_value=0.0, max_value=10000.0,
            value=float(st.session_state.get("form_gord_trans", 0.0)), step=0.01,
        )
        acucares_adicionados_total = c6.number_input(
            "Açúcares Adicionados Total na Receita (g)",
            min_value=0.0, max_value=10000.0,
            value=float(st.session_state.get("form_acucar_ad", 0.0)), step=0.1,
            help="Quantidade de açúcar de adição (sacarose, mel, xarope, etc.)",
        )

    sty.render_divider()
    sty.render_section_label("Ingredientes")

    modo = st.radio(
        "Modo de entrada:",
        ["Manual (item a item)", "Upload de Ficha Técnica"],
        horizontal=True,
        label_visibility="collapsed",
    )

    # ── Modo A — Entrada Manual ───────────────────────────────────────────────
    if modo == "Manual (item a item)":
        st.markdown("**Adicionar Ingrediente**")
        c_busca, c_qtd, c_unit, c_btn = st.columns([4, 1.5, 1, 1])

        with c_busca:
            termo = st.text_input(
                "Buscar ingrediente",
                placeholder="Digite o nome do ingrediente...",
                key="busca_ingrediente",
                label_visibility="collapsed",
            )

        opcoes_busca = []
        mapa_busca   = {}
        if termo and len(termo.strip()) >= 2:
            candidatos = db.buscar_ingrediente(termo, limite=15)
            for c in candidatos:
                label = f"[{c['fonte']}] {c['nome']} ({c['score']}%)"
                opcoes_busca.append(label)
                mapa_busca[label] = c

        ingrediente_selecionado = None
        if opcoes_busca:
            escolha = st.selectbox(
                "Selecionar:",
                opcoes_busca,
                key="sel_ingrediente",
                label_visibility="collapsed",
            )
            ingrediente_selecionado = mapa_busca.get(escolha)
        elif termo and len(termo.strip()) >= 2:
            st.caption("Nenhum ingrediente encontrado. Verifique o nome ou cadastre em 'Ingredientes de Fornecedor'.")

        with c_unit:
            unidade = st.selectbox(
                "Unidade",
                ["g", "mL", "%"],
                key="sel_unidade",
                label_visibility="collapsed",
            )

        with c_qtd:
            qtd_manual = st.number_input(
                f"Quantidade ({unidade})",
                min_value=0.0, max_value=100000.0,
                value=100.0, step=0.0001,
                format="%.4f",
                key="qtd_manual",
                label_visibility="collapsed",
            )

        with c_btn:
            st.write("")
            adicionar_click = st.button("Adicionar", use_container_width=True, key="btn_adicionar")

        # ── Configuração de unidade selecionada ───────────────────────────────
        densidade_usada = 1.0
        total_receita_g_pct = None

        if unidade == "mL":
            nome_busca_dens = ingrediente_selecionado["nome"] if ingrediente_selecionado else (termo or "")
            densidade_auto = db.buscar_densidade(nome_busca_dens) if nome_busca_dens else None
            c_dens1, c_dens2 = st.columns([3, 1])
            with c_dens1:
                if densidade_auto:
                    st.caption(f"Densidade encontrada para '{nome_busca_dens}': **{densidade_auto} g/mL**")
                else:
                    st.caption("Densidade não encontrada na tabela — informe abaixo.")
            with c_dens2:
                densidade_manual_val = st.number_input(
                    "Densidade (g/mL)",
                    min_value=0.001, max_value=5.0,
                    value=float(densidade_auto or 1.0),
                    step=0.001, format="%.3f",
                    key="densidade_manual",
                    label_visibility="collapsed",
                )
            densidade_usada = densidade_manual_val

        elif unidade == "%":
            c_pct1, c_pct2 = st.columns([2, 2])
            with c_pct1:
                modo_pct = st.radio(
                    "Modo %:",
                    ["A — Peso total fixo", "B — Base 100g"],
                    key="radio_modo_pct",
                    horizontal=True,
                    label_visibility="collapsed",
                )
            with c_pct2:
                if "A" in modo_pct:
                    total_receita_g_pct = st.number_input(
                        "Peso total da receita (g)",
                        min_value=1.0, max_value=100000.0,
                        value=float(st.session_state.get("form_total_receita_g", 1000.0)),
                        step=1.0, format="%.1f",
                        key="total_receita_g_pct",
                        label_visibility="collapsed",
                    )
                    st.session_state["form_total_receita_g"] = total_receita_g_pct
                else:
                    st.caption("Modo B: 1% = 1g (formulação base 100g)")
                    total_receita_g_pct = None

            # Indicador de soma % em tempo real
            soma_pct = sum(
                i.get("quantidade_original", i["quantidade_gramas"])
                for i in st.session_state.ingredientes
                if i.get("unidade_original") == "%"
            )
            if soma_pct > 0 or unidade == "%":
                soma_com_atual = soma_pct + qtd_manual
                if abs(soma_com_atual - 100.0) < 0.01:
                    st.success(f"Soma percentual: {soma_com_atual:.4f}% — formulação completa (100%)")
                elif soma_com_atual > 100.0:
                    st.error(f"Soma percentual: {soma_com_atual:.4f}% — excede 100%")
                else:
                    st.warning(f"Soma percentual: {soma_com_atual:.4f}% — faltam {100 - soma_com_atual:.4f}%")

        if adicionar_click:
            if not ingrediente_selecionado:
                st.warning("Selecione um ingrediente da lista antes de adicionar.")
            elif qtd_manual <= 0:
                st.warning("Informe uma quantidade maior que zero.")
            else:
                comp = db.get_composicao_por_100g(
                    ingrediente_selecionado["fonte"],
                    ingrediente_selecionado["id"],
                )
                if comp:
                    qtd_gramas = calc.convert_to_grams(
                        qtd_manual, unidade, densidade_usada, total_receita_g_pct
                    )
                    st.session_state.ingredientes.append({
                        "nome":               ingrediente_selecionado["nome"],
                        "fonte":              ingrediente_selecionado["fonte"],
                        "fonte_id":           ingrediente_selecionado["id"],
                        "quantidade_gramas":  qtd_gramas,
                        "composicao_100g":    comp,
                        "unidade_original":   unidade,
                        "quantidade_original": qtd_manual,
                        "densidade_utilizada": densidade_usada if unidade == "mL" else 1.0,
                    })
                    st.session_state.resultado_calculo = None
                    st.rerun()
                else:
                    st.error("Não foi possível obter a composição deste ingrediente.")

    # ── Modo B — Upload de Ficha Técnica ──────────────────────────────────────
    else:
        arquivo = st.file_uploader(
            "Carregar ficha técnica",
            type=["pdf", "xlsx", "xls", "csv", "txt"],
            label_visibility="collapsed",
            key="upload_ficha",
        )

        if arquivo is not None:
            if st.button("Extrair Ingredientes", key="btn_extrair"):
                with st.spinner("Analisando arquivo..."):
                    try:
                        ext = arquivo.name.rsplit(".", 1)[-1]
                        extraidos = prs.parse_ficha_tecnica(arquivo.read(), ext)

                        item_unico = next((i for i in extraidos if "composicao_direta" in i), None)
                        if item_unico:
                            if not item_unico["nome"]:
                                item_unico["nome"] = (
                                    arquivo.name.rsplit(".", 1)[0]
                                    .replace("_", " ").replace("-", " ").title()
                                )
                            st.session_state["ficha_unico"] = item_unico
                            st.session_state.upload_preview  = None
                            n_nut = sum(
                                1 for v in item_unico["composicao_direta"].values()
                                if v is not None
                            )
                            st.success(
                                f"Ficha de ingrediente único detectada — "
                                f"{n_nut} nutrientes extraídos. Confirme abaixo."
                            )
                        else:
                            preview = []
                            for item in extraidos:
                                candidatos = db.buscar_ingrediente(item["nome"], limite=5)
                                preview.append({
                                    "nome_original":     item["nome"],
                                    "quantidade_gramas": item["quantidade_gramas"],
                                    "match_sugerido":    candidatos[0]["nome"] if candidatos else "",
                                    "match_fonte":       candidatos[0]["fonte"] if candidatos else "",
                                    "match_id":          candidatos[0]["id"] if candidatos else None,
                                    "match_score":       candidatos[0]["score"] if candidatos else 0,
                                    "_candidatos":       candidatos,
                                })
                            st.session_state.upload_preview  = preview
                            st.session_state["ficha_unico"]  = None
                            st.success(f"{len(extraidos)} ingredientes encontrados no arquivo.")
                    except ValueError as e:
                        st.error(str(e))
                    except Exception as e:
                        st.error(
                            f"Erro inesperado ao processar arquivo: {type(e).__name__}. "
                            "Tente outro arquivo ou use a entrada manual."
                        )

        # ── Ficha de ingrediente único: confirmar e cadastrar ─────────────────
        if st.session_state.get("ficha_unico"):
            fu   = st.session_state["ficha_unico"]
            comp = fu["composicao_direta"]

            sty.render_divider()
            sty.render_section_label("Ficha de Ingrediente Único Detectada")
            st.caption("Verifique e edite os valores abaixo, depois clique em Cadastrar.")

            LABELS_FU = {
                "energia_kcal":    "Energia (kcal)",
                "energia_kj":      "Energia (kJ)",
                "proteina":        "Proteínas (g)",
                "lipideos":        "Gorduras Totais (g)",
                "carboidrato":     "Carboidratos (g)",
                "fibra_alimentar": "Fibra Alimentar (g)",
                "sodio":           "Sódio (mg)",
                "umidade":         "Umidade (%)",
                "colesterol":      "Colesterol (mg)",
                "calcio":          "Cálcio (mg)",
                "ferro":           "Ferro (mg)",
                "potassio":        "Potássio (mg)",
                "vitamina_c":      "Vitamina C (mg)",
                "vitamina_d":      "Vitamina D (mcg)",
                "vitamina_e":      "Vitamina E (mg)",
                "vitamina_b12":    "Vitamina B12 (mcg)",
            }

            with st.form("form_ficha_unico"):
                fu_nome = st.text_input("Nome do ingrediente *", value=fu["nome"])
                fu_fab  = st.text_input("Fabricante (opcional)", value="")

                cols_fu = st.columns(4)
                vals_fu: dict = {}
                nutrientes_form_order = [
                    "energia_kcal", "energia_kj", "proteina",  "lipideos",
                    "carboidrato",  "fibra_alimentar", "sodio", "umidade",
                    "colesterol",   "calcio",  "ferro",         "potassio",
                    "vitamina_c",   "vitamina_d", "vitamina_e", "vitamina_b12",
                ]
                for i, nut in enumerate(nutrientes_form_order):
                    v = comp.get(nut)
                    vals_fu[nut] = cols_fu[i % 4].number_input(
                        LABELS_FU.get(nut, nut),
                        min_value=0.0,
                        value=float(v) if v is not None else 0.0,
                        step=0.01,
                        key=f"fu_{nut}",
                    )

                confirmar = st.form_submit_button(
                    "Cadastrar como Ingrediente de Fornecedor",
                    type="primary",
                    use_container_width=True,
                )

            if confirmar:
                if not fu_nome.strip():
                    st.error("Informe o nome do ingrediente.")
                else:
                    try:
                        dados_salvar = {
                            "nome_comercial": fu_nome.strip(),
                            "fabricante":     fu_fab.strip() or None,
                            **vals_fu,
                        }
                        iid = db.salvar_ingrediente_fornecedor(dados_salvar)
                        st.success(
                            f"Ingrediente '{fu_nome.strip()}' cadastrado com sucesso "
                            "a partir da ficha técnica."
                        )
                        st.session_state["ficha_unico"] = None
                        comp_100g = db.get_composicao_por_100g("FORNECEDOR", iid)
                        if comp_100g:
                            st.session_state.ingredientes.append({
                                "nome":               fu_nome.strip(),
                                "fonte":              "FORNECEDOR",
                                "fonte_id":           iid,
                                "quantidade_gramas":  100.0,
                                "composicao_100g":    comp_100g,
                                "unidade_original":   "g",
                                "quantidade_original": 100.0,
                                "densidade_utilizada": 1.0,
                            })
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar: {e}")

        # ── Preview editável (multi-ingredientes) ─────────────────────────────
        if st.session_state.upload_preview:
            st.markdown("**Revisar e confirmar ingredientes extraídos:**")
            preview = st.session_state.upload_preview

            for i, item in enumerate(preview):
                with st.container():
                    c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
                    c1.text_input(
                        "Nome original",
                        value=item["nome_original"],
                        disabled=True,
                        key=f"prev_nome_{i}",
                        label_visibility="visible",
                    )
                    c2.number_input(
                        "Qtd (g)",
                        value=float(item["quantidade_gramas"]),
                        min_value=0.0,
                        step=0.0001,
                        format="%.4f",
                        key=f"prev_qtd_{i}",
                        label_visibility="visible",
                    )
                    cands  = item["_candidatos"]
                    opcoes = [f"[{c['fonte']}] {c['nome']} ({c['score']}%)" for c in cands]
                    opcoes = ["-- Ignorar este item --"] + opcoes

                    escolha_idx = 1 if cands and cands[0]["score"] >= 80 else 0
                    escolha = c3.selectbox(
                        "Match TACO/Fornecedor",
                        opcoes,
                        index=escolha_idx,
                        key=f"prev_match_{i}",
                        label_visibility="visible",
                    )
                    preview[i]["_escolha"]     = escolha
                    preview[i]["_escolha_idx"] = opcoes.index(escolha) - 1

            if st.button("Importar Ingredientes Selecionados", key="btn_importar"):
                importados = 0
                for i, item in enumerate(preview):
                    escolha_idx = item.get("_escolha_idx", -1)
                    if escolha_idx < 0:
                        continue
                    qtd   = st.session_state.get(f"prev_qtd_{i}", item["quantidade_gramas"])
                    cands = item["_candidatos"]
                    if escolha_idx < len(cands):
                        cand = cands[escolha_idx]
                        comp = db.get_composicao_por_100g(cand["fonte"], cand["id"])
                        if comp:
                            qtd_f = float(qtd)
                            st.session_state.ingredientes.append({
                                "nome":               cand["nome"],
                                "fonte":              cand["fonte"],
                                "fonte_id":           cand["id"],
                                "quantidade_gramas":  qtd_f,
                                "composicao_100g":    comp,
                                "unidade_original":   "g",
                                "quantidade_original": qtd_f,
                                "densidade_utilizada": 1.0,
                            })
                            importados += 1

                st.session_state.upload_preview    = None
                st.session_state.resultado_calculo = None
                st.success(f"{importados} ingredientes importados.")
                st.rerun()

    # ── Tabela de ingredientes adicionados ────────────────────────────────────
    sty.render_divider()
    sty.render_section_label(f"Ingredientes da Receita ({len(st.session_state.ingredientes)})")

    if not st.session_state.ingredientes:
        st.info("Nenhum ingrediente adicionado. Use a busca acima para começar.")
    else:
        ch1, ch2, ch3, ch4, ch5 = st.columns([4, 2, 2, 2, 1])
        ch1.markdown("**Ingrediente**")
        ch2.markdown("**Fonte**")
        ch3.markdown("**Qtd. original**")
        ch4.markdown("**Qtd. (g)**")
        ch5.markdown("**Rem.**")

        for idx, ing in enumerate(st.session_state.ingredientes):
            c1, c2, c3, c4, c5 = st.columns([4, 2, 2, 2, 1])
            c1.write(ing["nome"])
            c2.markdown(sty.render_fonte_badge(ing["fonte"]), unsafe_allow_html=True)

            # Coluna 3: original quantity (display only)
            unid_orig = ing.get("unidade_original", "g") or "g"
            qtd_orig  = ing.get("quantidade_original")
            if qtd_orig is None:
                qtd_orig = ing["quantidade_gramas"]
            c3.caption(f"{calc.smart_round(qtd_orig)} {unid_orig}")

            # Coluna 4: quantity in grams (editable, 4-decimal)
            nova_qtd = c4.number_input(
                "",
                value=float(ing["quantidade_gramas"]),
                min_value=0.0,
                step=0.0001,
                format="%.4f",
                key=f"qtd_ing_{idx}",
                label_visibility="collapsed",
            )
            if nova_qtd != ing["quantidade_gramas"]:
                st.session_state.ingredientes[idx]["quantidade_gramas"] = nova_qtd
                st.session_state.resultado_calculo = None

            if c5.button("X", key=f"del_ing_{idx}", help="Remover ingrediente"):
                st.session_state.ingredientes.pop(idx)
                st.session_state.resultado_calculo = None
                st.rerun()

        peso_total = sum(i["quantidade_gramas"] for i in st.session_state.ingredientes)
        # % sum indicator (shown when any ingredient uses %)
        pct_ings = [i for i in st.session_state.ingredientes if i.get("unidade_original") == "%"]
        if pct_ings:
            soma_pct = sum(i.get("quantidade_original", 0) for i in pct_ings)
            pct_msg  = f"Soma %: {calc.smart_round(soma_pct)}% de {len(pct_ings)} ingrediente(s)"
            if abs(soma_pct - 100.0) < 0.01:
                st.success(pct_msg + " — 100% atingido")
            elif soma_pct > 100.0:
                st.error(pct_msg + f" — excede 100% em {soma_pct - 100:.4f}%")
            else:
                st.warning(pct_msg + f" — faltam {100 - soma_pct:.4f}%")

        st.caption(f"Peso total da receita: {calc.smart_round(peso_total)} g")

    # ── Botões de ação ────────────────────────────────────────────────────────
    sty.render_divider()
    col_calc, col_limpar = st.columns([3, 1])

    with col_calc:
        calcular_btn = st.button(
            "Calcular Tabela Nutricional",
            use_container_width=True,
            type="primary",
            key="btn_calcular",
        )

    with col_limpar:
        if st.button("Limpar Receita", use_container_width=True, key="btn_limpar"):
            st.session_state.ingredientes        = []
            st.session_state.resultado_calculo   = None
            st.session_state.receita_editando_id = None
            st.rerun()

    if calcular_btn:
        erros = []
        if not nome_produto.strip():
            erros.append("Informe o nome do produto.")
        if porcao_g <= 0:
            erros.append("Informe o tamanho da porção em gramas.")
        if not st.session_state.ingredientes:
            erros.append("Adicione pelo menos um ingrediente antes de calcular.")

        for msg in erros:
            st.error(msg)

        if not erros:
            with st.spinner("Calculando composição nutricional..."):
                try:
                    resultado_bruto = calc.calcular_composicao_receita(
                        st.session_state.ingredientes
                    )
                    tabela = calc.montar_tabela_rotulo(
                        nome_produto=nome_produto.strip(),
                        porcao_gramas=porcao_g,
                        peso_total=resultado_bruto["peso_total_gramas"],
                        nutrientes_totais=resultado_bruto["nutrientes"],
                        acucares_adicionados_total=acucares_adicionados_total,
                        gordura_saturada_total=gordura_saturada_total,
                        gordura_trans_total=gordura_trans_total,
                        num_porcoes=int(num_porcoes),
                        medida_caseira=medida_caseira.strip() or None,
                    )
                    detalhes_contrib = calc.calcular_contribuicoes_percentuais(
                        resultado_bruto["ingredientes_detalhes"]
                    )
                    st.session_state.resultado_calculo = {
                        "tabela":         tabela,
                        "detalhes":       detalhes_contrib,
                        "peso_total":     resultado_bruto["peso_total_gramas"],
                        "nome_produto":   nome_produto.strip(),
                        "porcao_g":       porcao_g,
                        "num_porcoes":    int(num_porcoes),
                        "medida_caseira": medida_caseira.strip() or None,
                    }
                except Exception as e:
                    st.error(f"Erro no cálculo: {str(e)}")

    # ── Resultado do Cálculo ──────────────────────────────────────────────────
    if st.session_state.resultado_calculo:
        res    = st.session_state.resultado_calculo
        tabela = res["tabela"]
        por_100 = tabela["por_100g"]
        porcao  = tabela["por_porcao"]
        vd_     = tabela["vd"]

        st.success("Cálculo realizado com sucesso.")
        sty.render_divider()
        sty.render_section_label("Informação Nutricional")
        st.caption(
            f"Porção de {tabela['info']['porcao_gramas']:.0f} g "
            f"({tabela['info']['medida_caseira']})  |  "
            f"% VD com base em uma dieta de 2.000 kcal ou 8.400 kJ."
        )

        LINHAS_ROTULO = [
            ("Valor Energético",       "energia_kcal",          "energia_kcal",          "kcal", True),
            ("",                       "energia_kj",            "energia_kj",            "kJ",   False),
            ("Carboidratos",           "carboidrato",           "carboidrato",           "g",    True),
            ("  Açúcares Totais",      "acucares_totais",       "acucares_totais",       "g",    False),
            ("  Açúcares Adicionados", "acucares_adicionados",  "acucares_adicionados",  "g",    False),
            ("Proteínas",              "proteina",              "proteina",              "g",    True),
            ("Gorduras Totais",        "lipideos",              "lipideos",              "g",    True),
            ("  Gorduras Saturadas",   "gordura_saturada",      "gordura_saturada",      "g",    False),
            ("  Gorduras Trans",       "gordura_trans",         "gordura_trans",         "g",    False),
            ("Fibra Alimentar",        "fibra_alimentar",       "fibra_alimentar",       "g",    True),
            ("Sódio",                  "sodio",                 "sodio",                 "mg",   True),
        ]

        dados_tabela = []
        for nome_nut, ch100, chpor, unidade, _ in LINHAS_ROTULO:
            v100  = por_100.get(ch100, 0) or 0
            vpor  = porcao.get(chpor, 0) or 0
            vd_val = vd_.get(chpor)

            if unidade == "kcal":
                t100 = f"{int(v100)} kcal"
                tpor = f"{int(vpor)} kcal"
            elif unidade == "kJ":
                t100 = f"{int(v100)} kJ"
                tpor = f"{int(vpor)} kJ"
            elif unidade == "mg":
                t100 = f"{int(v100)} mg"
                tpor = f"{int(vpor)} mg"
            else:
                t100 = f"{v100:.1f} g"
                tpor = f"{vpor:.1f} g"

            if ch100 == "gordura_trans":
                tpor = porcao.get("gordura_trans_rotulo", tpor)

            vd_str = f"{vd_val}%" if vd_val is not None else "**"

            dados_tabela.append({
                "Nutriente":                                       nome_nut,
                "Por 100 g":                                       t100,
                f"Por Porção ({tabela['info']['porcao_gramas']:.0f} g)": tpor,
                "%VD*":                                            vd_str,
            })

        df_rotulo = pd.DataFrame(dados_tabela)
        st.dataframe(df_rotulo, hide_index=True, use_container_width=True)

        st.caption("*%VD com base em dieta de 2.000 kcal. **Valor Diário não estabelecido.")
        sty.render_legal_notice()
        sty.render_divider()

        col_dl, col_salvar = st.columns(2)

        with col_dl:
            if "excel_bytes" not in res:
                try:
                    res["excel_bytes"] = xls.gerar_excel(
                        nome_produto=res["nome_produto"],
                        porcao_gramas=res["porcao_g"],
                        num_porcoes=res["num_porcoes"],
                        medida_caseira=res["medida_caseira"],
                        ingredientes_detalhes=res["detalhes"],
                        por_100g=tabela["por_100g"],
                        por_porcao=tabela["por_porcao"],
                        vd=vd_,
                        peso_total_gramas=res["peso_total"],
                    )
                except Exception as e:
                    st.error(f"Erro ao gerar Excel: {e}")
                    res["excel_bytes"] = None

            if res.get("excel_bytes"):
                nome_arquivo = f"NutriCalc_{res['nome_produto'].replace(' ', '_')}.xlsx"
                st.download_button(
                    label="Baixar Excel — Tabela Nutricional + P&D",
                    data=res["excel_bytes"],
                    file_name=nome_arquivo,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    type="primary",
                )

        with col_salvar:
            if st.button("Salvar Receita", use_container_width=True, key="btn_salvar"):
                try:
                    rid = db.salvar_receita(
                        nome=res["nome_produto"],
                        porcao_gramas=res["porcao_g"],
                        ingredientes=[{
                            "nome":               i["nome"],
                            "fonte":              i["fonte"],
                            "fonte_id":           i.get("fonte_id"),
                            "quantidade_gramas":  i["quantidade_gramas"],
                            "unidade_original":   i.get("unidade_original", "g"),
                            "quantidade_original": i.get("quantidade_original"),
                            "densidade_utilizada": i.get("densidade_utilizada", 1.0),
                        } for i in st.session_state.ingredientes],
                        num_porcoes=res["num_porcoes"],
                        medida_caseira=res["medida_caseira"],
                        receita_id_existente=st.session_state.receita_editando_id,
                    )
                    st.success(f"Receita salva com sucesso. (ID #{rid})")
                    st.session_state.receita_editando_id = rid
                except Exception as e:
                    st.error(f"Erro ao salvar receita: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  ABA 2 — INGREDIENTES DE FORNECEDOR
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    sty.render_section_label("Cadastro de Ingredientes Industrializados")
    st.caption("Cadastre ingredientes não encontrados na TACO: aditivos, concentrados, extratos, etc.")

    NUTRIENTES_LABELS_FORM = {
        "umidade":        "Umidade (%)",
        "energia_kcal":   "Energia (kcal)",
        "energia_kj":     "Energia (kJ)",
        "proteina":       "Proteínas (g)",
        "lipideos":       "Gorduras Totais (g)",
        "colesterol":     "Colesterol (mg)",
        "carboidrato":    "Carboidratos (g)",
        "fibra_alimentar":"Fibra Alimentar (g)",
        "cinzas":         "Cinzas (g)",
        "calcio":         "Cálcio (mg)",
        "magnesio":       "Magnésio (mg)",
        "manganes":       "Manganês (mg)",
        "fosforo":        "Fósforo (mg)",
        "ferro":          "Ferro (mg)",
        "sodio":          "Sódio (mg)",
        "potassio":       "Potássio (mg)",
        "cobre":          "Cobre (mg)",
        "zinco":          "Zinco (mg)",
        "retinol":        "Retinol (mcg)",
        "re":             "RE (mcg)",
        "rae":            "RAE (mcg)",
        "tiamina":        "Tiamina (mg)",
        "riboflavina":    "Riboflavina (mg)",
        "piridoxina":     "Piridoxina (mg)",
        "niacina":        "Niacina (mg)",
        "vitamina_c":     "Vitamina C (mg)",
        "vitamina_d":     "Vitamina D (mcg)",
        "vitamina_e":     "Vitamina E (mg)",
        "vitamina_b12":   "Vitamina B12 (mcg)",
    }

    with st.expander("Pré-preencher formulário a partir de ficha técnica do fornecedor", expanded=False):
        st.caption(
            "Carregue um PDF, Excel ou CSV com a tabela nutricional por 100 g do ingrediente. "
            "Os campos serão preenchidos automaticamente."
        )
        arq_ficha_forn = st.file_uploader(
            "Selecionar ficha técnica",
            type=["pdf", "xlsx", "xls", "csv", "txt"],
            key="upload_ficha_forn",
            label_visibility="collapsed",
        )
        col_btn_ext, col_btn_clear = st.columns([2, 1])
        with col_btn_ext:
            if arq_ficha_forn and st.button("Extrair dados nutricionais", key="btn_extrair_nutri"):
                with st.spinner("Analisando ficha técnica..."):
                    try:
                        ext_arq  = arq_ficha_forn.name.rsplit(".", 1)[-1]
                        dados_ext = prs.parse_composicao_nutricional(arq_ficha_forn.read(), ext_arq)
                        if "nome_comercial" not in dados_ext:
                            dados_ext["nome_comercial"] = (
                                arq_ficha_forn.name.rsplit(".", 1)[0]
                                .replace("_", " ").replace("-", " ").title()
                            )
                        st.session_state.forn_dados_extraidos = dados_ext
                        n = len([
                            k for k in dados_ext
                            if k != "nome_comercial" and dados_ext[k] is not None
                        ])
                        st.success(f"{n} nutrientes extraídos. Formulário pré-preenchido abaixo.")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
        with col_btn_clear:
            if st.session_state.forn_dados_extraidos:
                if st.button("Limpar extração", key="btn_clear_ext"):
                    st.session_state.forn_dados_extraidos = {}
                    st.rerun()

        if st.session_state.forn_dados_extraidos:
            campos = [
                k for k, v in st.session_state.forn_dados_extraidos.items()
                if k != "nome_comercial" and v is not None
            ]
            st.caption(f"Campos pré-preenchidos: {', '.join(campos)}")

    dados_edicao = {}
    if st.session_state.forn_editando_id:
        dados_edicao = db.get_ingrediente_fornecedor(st.session_state.forn_editando_id) or {}
        st.info(f"Editando: {dados_edicao.get('nome_comercial', '')}")

    dados_form = dados_edicao if st.session_state.forn_editando_id else st.session_state.forn_dados_extraidos

    with st.form("form_fornecedor", clear_on_submit=False):
        st.markdown("**Identificação**")
        cf1, cf2, cf3 = st.columns(3)
        f_nome_com   = cf1.text_input("Nome Comercial *",  value=dados_form.get("nome_comercial", ""))
        f_nome_gen   = cf2.text_input("Nome Genérico",     value=dados_form.get("nome_generico", ""))
        f_fabricante = cf3.text_input("Fabricante",        value=dados_form.get("fabricante", ""))
        f_obs        = st.text_area("Observações",         value=dados_form.get("observacoes", ""),
                                    height=60)

        st.markdown("**Valores Nutricionais por 100 g**")
        st.caption("Preencha com base na ficha técnica do fornecedor.")

        OBRIGATORIOS = ["energia_kcal", "energia_kj", "proteina", "lipideos",
                        "carboidrato",  "fibra_alimentar", "sodio"]

        st.markdown("*Obrigatórios ANVISA:*")
        cols_ob   = st.columns(len(OBRIGATORIOS))
        vals_forn = {}
        for i, nut in enumerate(OBRIGATORIOS):
            vals_forn[nut] = cols_ob[i].number_input(
                NUTRIENTES_LABELS_FORM.get(nut, nut),
                min_value=0.0,
                value=float(dados_form.get(nut) or 0.0),
                step=0.01,
                key=f"forn_{nut}",
            )

        with st.expander("Micronutrientes adicionais"):
            extras  = [n for n in NUTRIENTES if n not in OBRIGATORIOS]
            cols_ex = st.columns(5)
            for i, nut in enumerate(extras):
                vals_forn[nut] = cols_ex[i % 5].number_input(
                    NUTRIENTES_LABELS_FORM.get(nut, nut),
                    min_value=0.0,
                    value=float(dados_form.get(nut) or 0.0),
                    step=0.001,
                    key=f"forn_{nut}_extra",
                    format="%.4f",
                )

        label_btn = "Atualizar Ingrediente" if st.session_state.forn_editando_id else "Salvar Ingrediente"
        sub_forn  = st.form_submit_button(label_btn, use_container_width=True, type="primary")

    if sub_forn:
        if not f_nome_com.strip():
            st.error("O Nome Comercial é obrigatório.")
        else:
            try:
                dados = {
                    "nome_comercial": f_nome_com.strip(),
                    "nome_generico":  f_nome_gen.strip() or None,
                    "fabricante":     f_fabricante.strip() or None,
                    "observacoes":    f_obs.strip() or None,
                    **vals_forn,
                }
                if st.session_state.forn_editando_id:
                    db.atualizar_ingrediente_fornecedor(st.session_state.forn_editando_id, dados)
                    st.success(f"Ingrediente '{f_nome_com}' atualizado.")
                    st.session_state.forn_editando_id = None
                else:
                    db.salvar_ingrediente_fornecedor(dados)
                    st.success(f"Ingrediente '{f_nome_com}' cadastrado com sucesso.")
                st.session_state.forn_dados_extraidos = {}
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar ingrediente: {e}")

    sty.render_divider()
    sty.render_section_label("Ingredientes Cadastrados")

    try:
        forn_lista = db.listar_ingredientes_fornecedor()
        if not forn_lista:
            st.info("Nenhum ingrediente de fornecedor cadastrado ainda.")
        else:
            df_forn = pd.DataFrame(forn_lista)[[
                "id", "nome_comercial", "nome_generico", "fabricante",
                "energia_kcal", "proteina", "lipideos", "carboidrato", "sodio", "data_cadastro",
            ]].rename(columns={
                "id":             "ID",
                "nome_comercial": "Nome Comercial",
                "nome_generico":  "Nome Genérico",
                "fabricante":     "Fabricante",
                "energia_kcal":   "kcal",
                "proteina":       "Prot.(g)",
                "lipideos":       "Gord.(g)",
                "carboidrato":    "Carb.(g)",
                "sodio":          "Sódio(mg)",
                "data_cadastro":  "Cadastrado em",
            })
            st.dataframe(df_forn, hide_index=True, use_container_width=True)

            c_edit, c_del = st.columns(2)
            with c_edit:
                nomes_forn = [f["nome_comercial"] for f in forn_lista]
                mapa_forn  = {f["nome_comercial"]: f["id"] for f in forn_lista}
                sel_editar = st.selectbox(
                    "Editar ingrediente:", ["-- Selecionar --"] + nomes_forn, key="sel_forn_editar"
                )
                if sel_editar != "-- Selecionar --":
                    if st.button("Carregar para Edição", key="btn_forn_edit"):
                        st.session_state.forn_editando_id = mapa_forn[sel_editar]
                        st.rerun()

            with c_del:
                sel_deletar = st.selectbox(
                    "Excluir ingrediente:", ["-- Selecionar --"] + nomes_forn, key="sel_forn_del"
                )
                if sel_deletar != "-- Selecionar --":
                    if st.button("Excluir", key="btn_forn_del", type="secondary"):
                        db.deletar_ingrediente_fornecedor(mapa_forn[sel_deletar])
                        st.success(f"'{sel_deletar}' excluído.")
                        st.rerun()
    except Exception as e:
        st.error(f"Erro ao carregar ingredientes: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  ABA 3 — RECEITAS SALVAS
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    sty.render_section_label("Receitas Salvas")

    try:
        receitas = db.listar_receitas()
        if not receitas:
            st.info(
                "Nenhuma receita salva ainda. "
                "Calcule uma receita na aba 'Nova Receita' e clique em 'Salvar Receita'."
            )
        else:
            df_rec = pd.DataFrame(receitas)[[
                "id", "nome_produto", "porcao_gramas", "num_porcoes",
                "num_ingredientes", "data_criacao",
            ]].rename(columns={
                "id":               "ID",
                "nome_produto":     "Produto",
                "porcao_gramas":    "Porção (g)",
                "num_porcoes":      "Nº Porções",
                "num_ingredientes": "Ingredientes",
                "data_criacao":     "Criado em",
            })
            st.dataframe(df_rec, hide_index=True, use_container_width=True)

            sty.render_divider()
            nomes_rec = [f"#{r['id']} — {r['nome_produto']}" for r in receitas]
            mapa_rec  = {f"#{r['id']} — {r['nome_produto']}": r["id"] for r in receitas}
            c1, c2, c3 = st.columns(3)

            with c1:
                st.markdown("**Abrir / Reabrir Receita**")
                sel_abrir = st.selectbox("Selecionar:", ["-- Selecionar --"] + nomes_rec, key="sel_abrir")
                if sel_abrir != "-- Selecionar --":
                    if st.button("Abrir para Edição", use_container_width=True, key="btn_abrir"):
                        rid = mapa_rec[sel_abrir]
                        receita_completa = db.get_receita_completa(rid)
                        if receita_completa:
                            ings_carregados = []
                            for ing in receita_completa["ingredientes"]:
                                comp = db.get_composicao_por_100g(ing["fonte"], ing["fonte_id"])
                                if comp:
                                    ings_carregados.append({
                                        "nome":              ing["nome_ingrediente"],
                                        "fonte":             ing["fonte"],
                                        "fonte_id":          ing["fonte_id"],
                                        "quantidade_gramas": ing["quantidade_gramas"],
                                        "composicao_100g":   comp,
                                    })
                            st.session_state.ingredientes        = ings_carregados
                            st.session_state.resultado_calculo   = None
                            st.session_state.receita_editando_id = rid
                            st.session_state.form_nome           = receita_completa["nome_produto"]
                            st.session_state.form_porcao         = receita_completa["porcao_gramas"]
                            st.session_state.form_nporcoes       = receita_completa["num_porcoes"] or 1
                            st.session_state.form_medida         = receita_completa.get("medida_caseira", "")
                            st.success(
                                f"Receita '{receita_completa['nome_produto']}' carregada. "
                                "Vá para a aba 'Nova Receita'."
                            )

            with c2:
                st.markdown("**Duplicar Receita**")
                sel_dup = st.selectbox("Selecionar:", ["-- Selecionar --"] + nomes_rec, key="sel_dup")
                novo_nome_dup = st.text_input(
                    "Nome da cópia:", key="nome_dup", placeholder="Ex.: Bolo Chocolate Diet v2"
                )
                if sel_dup != "-- Selecionar --" and novo_nome_dup.strip():
                    if st.button("Duplicar", use_container_width=True, key="btn_dup"):
                        try:
                            novo_id = db.duplicar_receita(mapa_rec[sel_dup], novo_nome_dup.strip())
                            st.success(f"Receita duplicada como '{novo_nome_dup}' (ID #{novo_id}).")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao duplicar: {e}")

            with c3:
                st.markdown("**Excluir Receita**")
                sel_del = st.selectbox("Selecionar:", ["-- Selecionar --"] + nomes_rec, key="sel_del")
                if sel_del != "-- Selecionar --":
                    if st.button(
                        "Excluir Receita", use_container_width=True,
                        key="btn_del_rec", type="secondary",
                    ):
                        rid_del = mapa_rec[sel_del]
                        db.deletar_receita(rid_del)
                        st.success("Receita excluída.")
                        if st.session_state.receita_editando_id == rid_del:
                            st.session_state.receita_editando_id = None
                        st.rerun()

    except Exception as e:
        st.error(f"Erro ao carregar receitas: {e}")
