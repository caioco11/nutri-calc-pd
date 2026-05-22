"""
database.py — Operações com SQLite para o NutriCalc P&D
Toda interação com taco.db e nutri_calc.db passa por aqui.
"""

import sqlite3
import os
import unicodedata
from datetime import datetime
from rapidfuzz import fuzz, process


def _normalizar(texto: str) -> str:
    """Remove acentos para comparação fuzzy agnóstica a acentuação."""
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii").lower()


# ─── DDL da tabela de densidades ──────────────────────────────────────────────
_SQL_DENSIDADES = """
CREATE TABLE IF NOT EXISTS densidades_ingredientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome_ingrediente TEXT NOT NULL UNIQUE,
    densidade_g_ml REAL NOT NULL,
    fonte TEXT DEFAULT 'manual',
    data_cadastro TEXT DEFAULT (datetime('now','localtime'))
);
"""

_DENSIDADES_INICIAIS = [
    ("Leite integral UHT",  1.030, "tabela"),
    ("Leite desnatado",     1.035, "tabela"),
    ("Creme de leite 35%",  1.012, "tabela"),
    ("Iogurte integral",    1.050, "tabela"),
    ("Soro whey",           1.025, "tabela"),
    ("Leite condensado",    1.300, "tabela"),
    ("Óleo de soja",        0.915, "tabela"),
    ("Óleo de palma",       0.910, "tabela"),
    ("Azeite",              0.911, "tabela"),
    ("Óleo de girassol",    0.920, "tabela"),
    ("Água",                1.000, "tabela"),
    ("Suco de laranja",     1.045, "tabela"),
    ("Vinagre",             1.006, "tabela"),
    ("Mel",                 1.420, "tabela"),
    ("Glicerina",           1.261, "tabela"),
    ("Álcool etílico",      0.789, "tabela"),
    ("Xarope de glicose",   1.380, "tabela"),
    ("Extrato de malte",    1.200, "tabela"),
]

# ─── Caminhos ──────────────────────────────────────────────────────────────────
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TACO_DB  = os.path.join(ROOT_DIR, "taco.db")
APP_DB   = os.path.join(ROOT_DIR, "nutri_calc.db")

# ─── Nutrientes (mesma lista do taco_setup.py) ─────────────────────────────────
NUTRIENTES = [
    "umidade", "energia_kcal", "energia_kj", "proteina", "lipideos",
    "colesterol", "carboidrato", "fibra_alimentar", "cinzas",
    "calcio", "magnesio", "manganes", "fosforo", "ferro", "sodio",
    "potassio", "cobre", "zinco", "retinol", "re", "rae",
    "tiamina", "riboflavina", "piridoxina", "niacina",
    "vitamina_c", "vitamina_d", "vitamina_e", "vitamina_b12",
]

NUTRIENTES_EXIBICAO = {
    "energia_kcal":    "Valor Energético (kcal)",
    "energia_kj":      "Valor Energético (kJ)",
    "carboidrato":     "Carboidratos",
    "proteina":        "Proteínas",
    "lipideos":        "Gorduras Totais",
    "fibra_alimentar": "Fibra Alimentar",
    "sodio":           "Sódio",
    "colesterol":      "Colesterol",
    "calcio":          "Cálcio",
    "ferro":           "Ferro",
    "vitamina_c":      "Vitamina C",
}


def _conn_taco() -> sqlite3.Connection:
    if not os.path.exists(TACO_DB):
        raise FileNotFoundError(
            f"Banco TACO não encontrado em '{TACO_DB}'. "
            "Execute 'python data/taco_setup.py' primeiro."
        )
    conn = sqlite3.connect(TACO_DB)
    conn.row_factory = sqlite3.Row
    return conn


def _conn_app() -> sqlite3.Connection:
    if not os.path.exists(APP_DB):
        raise FileNotFoundError(
            f"Banco da aplicação não encontrado em '{APP_DB}'. "
            "Execute 'python data/taco_setup.py' primeiro."
        )
    conn = sqlite3.connect(APP_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def banco_inicializado() -> bool:
    """Verifica se os dois bancos existem e estão populados."""
    return os.path.exists(TACO_DB) and os.path.exists(APP_DB)


def migrar_banco():
    """
    Aplica migrações incrementais ao banco da aplicação.
    Seguro para chamar múltiplas vezes — todas as operações são idempotentes.
    """
    if not os.path.exists(APP_DB):
        return
    conn = sqlite3.connect(APP_DB)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Adicionar novas colunas a receita_ingredientes (SQLite não tem IF NOT EXISTS para colunas)
    for col, typ, defval in [
        ("unidade_original",    "TEXT", "'g'"),
        ("quantidade_original", "REAL", "NULL"),
        ("densidade_utilizada", "REAL", "1.0"),
    ]:
        try:
            conn.execute(
                f"ALTER TABLE receita_ingredientes ADD COLUMN {col} {typ} DEFAULT {defval}"
            )
        except Exception:
            pass  # coluna já existe

    # Criar tabela de densidades se ainda não existir
    conn.executescript(_SQL_DENSIDADES)

    # Popular densidades iniciais apenas se a tabela estiver vazia
    count = conn.execute("SELECT COUNT(*) FROM densidades_ingredientes").fetchone()[0]
    if count == 0:
        conn.executemany(
            "INSERT OR IGNORE INTO densidades_ingredientes (nome_ingrediente, densidade_g_ml, fonte) VALUES (?,?,?)",
            _DENSIDADES_INICIAIS,
        )

    conn.commit()
    conn.close()


# ─── Busca de Ingredientes ─────────────────────────────────────────────────────

def buscar_ingrediente(termo: str, limite: int = 10) -> list[dict]:
    """
    Fuzzy matching contra TACO + fornecedores cadastrados.
    Retorna lista de candidatos com: id, nome, fonte, score, categoria.
    Threshold: 60 (aceita matches razoáveis para autocomplete).
    """
    if not termo or len(termo.strip()) < 2:
        return []

    candidatos = []

    # Buscar na TACO
    try:
        conn = _conn_taco()
        rows = conn.execute("SELECT id, nome_alimento, categoria FROM alimentos_taco").fetchall()
        nomes_taco = [(r["id"], r["nome_alimento"], r["categoria"]) for r in rows]
        conn.close()

        termo_norm = _normalizar(termo)
        for id_, nome, cat in nomes_taco:
            nome_norm = _normalizar(nome)
            s_tsr = fuzz.token_set_ratio(termo_norm, nome_norm)
            # partial_ratio só ajuda quando o nome é pelo menos tão longo quanto o termo
            s_par = fuzz.partial_ratio(termo_norm, nome_norm) if len(nome_norm) >= len(termo_norm) else 0
            score = max(s_tsr, s_par)
            if score >= 60:
                candidatos.append({
                    "id": id_,
                    "nome": nome,
                    "fonte": "TACO",
                    "categoria": cat or "",
                    "score": score,
                })
    except Exception:
        pass

    # Buscar em fornecedores
    try:
        conn = _conn_app()
        rows = conn.execute(
            "SELECT id, nome_comercial, nome_generico, fabricante FROM ingredientes_fornecedor"
        ).fetchall()
        conn.close()

        for r in rows:
            nome_busca = r["nome_comercial"]
            nome_norm = _normalizar(nome_busca)
            t_norm = _normalizar(termo)
            s_tsr = fuzz.token_set_ratio(t_norm, nome_norm)
            s_par = fuzz.partial_ratio(t_norm, nome_norm) if len(nome_norm) >= len(t_norm) else 0
            score = max(s_tsr, s_par)
            if score >= 60:
                candidatos.append({
                    "id": r["id"],
                    "nome": r["nome_comercial"],
                    "fonte": "FORNECEDOR",
                    "categoria": f"Fornecedor: {r['fabricante'] or 'N/A'}",
                    "score": score,
                })
    except Exception:
        pass

    # Ordenar por score e retornar top N
    candidatos.sort(key=lambda x: x["score"], reverse=True)
    return candidatos[:limite]


def get_nomes_ingredientes() -> list[str]:
    """Retorna lista de nomes de todos os ingredientes para autocomplete."""
    nomes = []
    try:
        conn = _conn_taco()
        rows = conn.execute("SELECT nome_alimento FROM alimentos_taco ORDER BY nome_alimento").fetchall()
        nomes += [r["nome_alimento"] for r in rows]
        conn.close()
    except Exception:
        pass
    try:
        conn = _conn_app()
        rows = conn.execute("SELECT nome_comercial FROM ingredientes_fornecedor ORDER BY nome_comercial").fetchall()
        nomes += [f"[Fornecedor] {r['nome_comercial']}" for r in rows]
        conn.close()
    except Exception:
        pass
    return sorted(nomes)


# ─── Composição Nutricional ────────────────────────────────────────────────────

def get_composicao_por_100g(fonte: str, id_: int) -> dict | None:
    """
    Retorna dict com todos os nutrientes por 100g do ingrediente.
    fonte: 'TACO' ou 'FORNECEDOR'
    """
    cols = ", ".join(NUTRIENTES)

    if fonte == "TACO":
        try:
            conn = _conn_taco()
            row = conn.execute(
                f"SELECT nome_alimento, {cols} FROM alimentos_taco WHERE id = ?", (id_,)
            ).fetchone()
            conn.close()
            if row:
                return {"nome": row["nome_alimento"], **{n: row[n] for n in NUTRIENTES}}
        except Exception:
            return None

    elif fonte == "FORNECEDOR":
        try:
            conn = _conn_app()
            row = conn.execute(
                f"SELECT nome_comercial, {cols} FROM ingredientes_fornecedor WHERE id = ?", (id_,)
            ).fetchone()
            conn.close()
            if row:
                return {"nome": row["nome_comercial"], **{n: row[n] for n in NUTRIENTES}}
        except Exception:
            return None

    return None


def get_composicao_por_nome(nome: str) -> dict | None:
    """Busca composição pelo nome exato (TACO primeiro, depois fornecedor)."""
    try:
        conn = _conn_taco()
        cols = ", ".join(NUTRIENTES)
        row = conn.execute(
            f"SELECT id, nome_alimento, {cols} FROM alimentos_taco WHERE nome_alimento = ?", (nome,)
        ).fetchone()
        conn.close()
        if row:
            return {"id": row["id"], "fonte": "TACO", "nome": row["nome_alimento"],
                    **{n: row[n] for n in NUTRIENTES}}
    except Exception:
        pass

    try:
        conn = _conn_app()
        cols = ", ".join(NUTRIENTES)
        row = conn.execute(
            f"SELECT id, nome_comercial, {cols} FROM ingredientes_fornecedor WHERE nome_comercial = ?", (nome,)
        ).fetchone()
        conn.close()
        if row:
            return {"id": row["id"], "fonte": "FORNECEDOR", "nome": row["nome_comercial"],
                    **{n: row[n] for n in NUTRIENTES}}
    except Exception:
        pass

    return None


# ─── Receitas ─────────────────────────────────────────────────────────────────

def salvar_receita(
    nome: str,
    porcao_gramas: float,
    ingredientes: list[dict],
    num_porcoes: int | None = None,
    medida_caseira: str | None = None,
    observacoes: str | None = None,
    receita_id_existente: int | None = None,
) -> int:
    """
    Persiste ou atualiza receita e seus ingredientes.
    ingredientes: [{"nome": str, "fonte": str, "fonte_id": int, "quantidade_gramas": float}, ...]
    Retorna: id da receita salva.
    """
    conn = _conn_app()
    try:
        if receita_id_existente:
            conn.execute(
                """UPDATE receitas SET nome_produto=?, porcao_gramas=?, num_porcoes=?,
                   medida_caseira=?, observacoes=?, data_atualizacao=?
                   WHERE id=?""",
                (nome, porcao_gramas, num_porcoes, medida_caseira, observacoes,
                 datetime.now().isoformat(), receita_id_existente)
            )
            conn.execute("DELETE FROM receita_ingredientes WHERE receita_id=?", (receita_id_existente,))
            rid = receita_id_existente
        else:
            cur = conn.execute(
                "INSERT INTO receitas (nome_produto, porcao_gramas, num_porcoes, medida_caseira, observacoes) VALUES (?,?,?,?,?)",
                (nome, porcao_gramas, num_porcoes, medida_caseira, observacoes)
            )
            rid = cur.lastrowid

        for i, ing in enumerate(ingredientes):
            conn.execute(
                """INSERT INTO receita_ingredientes
                   (receita_id, nome_ingrediente, fonte, fonte_id, quantidade_gramas,
                    eh_subrecita, subrecita_id, ordem,
                    unidade_original, quantidade_original, densidade_utilizada)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (rid, ing["nome"], ing["fonte"], ing.get("fonte_id"),
                 ing["quantidade_gramas"], ing.get("eh_subrecita", 0),
                 ing.get("subrecita_id"), i,
                 ing.get("unidade_original", "g"),
                 ing.get("quantidade_original"),
                 ing.get("densidade_utilizada", 1.0))
            )

        conn.commit()
        return rid
    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"Erro ao salvar receita: {e}")
    finally:
        conn.close()


def listar_receitas() -> list[dict]:
    """Lista todas as receitas salvas (resumo)."""
    conn = _conn_app()
    rows = conn.execute(
        """SELECT r.id, r.nome_produto, r.porcao_gramas, r.num_porcoes,
                  r.data_criacao, r.data_atualizacao,
                  COUNT(ri.id) as num_ingredientes
           FROM receitas r
           LEFT JOIN receita_ingredientes ri ON ri.receita_id = r.id
           GROUP BY r.id
           ORDER BY r.data_criacao DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_receita_completa(receita_id: int) -> dict | None:
    """Retorna receita com todos os ingredientes."""
    conn = _conn_app()
    r = conn.execute("SELECT * FROM receitas WHERE id=?", (receita_id,)).fetchone()
    if not r:
        conn.close()
        return None

    ings = conn.execute(
        "SELECT * FROM receita_ingredientes WHERE receita_id=? ORDER BY ordem",
        (receita_id,)
    ).fetchall()
    conn.close()

    return {**dict(r), "ingredientes": [dict(i) for i in ings]}


def deletar_receita(receita_id: int):
    """Remove receita e seus ingredientes (CASCADE)."""
    conn = _conn_app()
    conn.execute("DELETE FROM receitas WHERE id=?", (receita_id,))
    conn.commit()
    conn.close()


def duplicar_receita(receita_id: int, novo_nome: str) -> int:
    """Cria cópia da receita com novo nome."""
    receita = get_receita_completa(receita_id)
    if not receita:
        raise ValueError("Receita não encontrada.")
    return salvar_receita(
        nome=novo_nome,
        porcao_gramas=receita["porcao_gramas"],
        ingredientes=receita["ingredientes"],
        num_porcoes=receita["num_porcoes"],
        medida_caseira=receita.get("medida_caseira"),
        observacoes=receita.get("observacoes"),
    )


# ─── Ingredientes de Fornecedor ───────────────────────────────────────────────

def salvar_ingrediente_fornecedor(dados: dict) -> int:
    """Cadastra novo ingrediente industrializado."""
    conn = _conn_app()
    cols = ["nome_comercial", "nome_generico", "fabricante", "observacoes"] + NUTRIENTES
    vals = [dados.get(c) for c in cols]
    placeholders = ", ".join(["?" for _ in cols])
    col_str = ", ".join(cols)
    cur = conn.execute(
        f"INSERT INTO ingredientes_fornecedor ({col_str}) VALUES ({placeholders})", vals
    )
    conn.commit()
    conn.close()
    return cur.lastrowid


def atualizar_ingrediente_fornecedor(id_: int, dados: dict):
    """Atualiza ingrediente de fornecedor existente."""
    conn = _conn_app()
    cols = ["nome_comercial", "nome_generico", "fabricante", "observacoes"] + NUTRIENTES
    sets = ", ".join([f"{c}=?" for c in cols])
    vals = [dados.get(c) for c in cols] + [id_]
    conn.execute(f"UPDATE ingredientes_fornecedor SET {sets} WHERE id=?", vals)
    conn.commit()
    conn.close()


def listar_ingredientes_fornecedor() -> list[dict]:
    """Lista todos os ingredientes de fornecedores cadastrados."""
    conn = _conn_app()
    rows = conn.execute(
        "SELECT * FROM ingredientes_fornecedor ORDER BY nome_comercial"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def deletar_ingrediente_fornecedor(id_: int):
    """Remove ingrediente de fornecedor."""
    conn = _conn_app()
    conn.execute("DELETE FROM ingredientes_fornecedor WHERE id=?", (id_,))
    conn.commit()
    conn.close()


def get_ingrediente_fornecedor(id_: int) -> dict | None:
    """Retorna ingrediente de fornecedor por ID."""
    conn = _conn_app()
    row = conn.execute(
        "SELECT * FROM ingredientes_fornecedor WHERE id=?", (id_,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ─── Densidades ────────────────────────────────────────────────────────────────

def buscar_densidade(nome: str) -> float | None:
    """
    Busca densidade (g/mL) para um ingrediente por fuzzy matching.
    Retorna o valor encontrado se score >= 70, senão None.
    """
    if not nome or not os.path.exists(APP_DB):
        return None
    try:
        conn = sqlite3.connect(APP_DB)
        rows = conn.execute(
            "SELECT nome_ingrediente, densidade_g_ml FROM densidades_ingredientes"
        ).fetchall()
        conn.close()
        if not rows:
            return None
        nome_norm = _normalizar(nome)
        melhor_score = 0
        melhor_dens  = None
        for nome_ing, dens in rows:
            score = fuzz.token_set_ratio(nome_norm, _normalizar(nome_ing))
            if score > melhor_score:
                melhor_score = score
                melhor_dens  = dens
        return melhor_dens if melhor_score >= 70 else None
    except Exception:
        return None


def salvar_densidade(nome: str, densidade: float, fonte: str = "manual"):
    """Insere ou atualiza a densidade de um ingrediente na tabela."""
    conn = _conn_app()
    conn.execute(
        """INSERT INTO densidades_ingredientes (nome_ingrediente, densidade_g_ml, fonte)
           VALUES (?,?,?)
           ON CONFLICT(nome_ingrediente) DO UPDATE SET densidade_g_ml=excluded.densidade_g_ml,
                                                       fonte=excluded.fonte""",
        (nome, densidade, fonte),
    )
    conn.commit()
    conn.close()
