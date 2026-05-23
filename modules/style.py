"""
style.py — Design system for NutriCalc P&D
Dark-mode SaaS aesthetic with CSS custom properties and reusable components.
"""
import streamlit as st

_TOKENS = """
:root {
    --bg-primary:     #0D1117;
    --bg-surface:     #161B22;
    --bg-card:        #1C2128;
    --bg-input:       #21262D;
    --border:         #30363D;
    --border-focus:   #2D7DD2;
    --text-primary:   #E6EDF3;
    --text-secondary: #8B949E;
    --text-muted:     #656D76;
    --accent:         #2D7DD2;
    --accent-hover:   #3A8DE0;
    --accent-dim:     #1A3A5C;
    --success:        #238636;
    --success-bg:     #0F2A0F;
    --warning:        #9E6A03;
    --warning-bg:     #2A1E00;
    --error:          #DA3633;
    --error-bg:       #2A0E0E;
    --taco-color:     #2D7DD2;
    --forn-color:     #2EA043;
    --radius-sm:      4px;
    --radius-md:      8px;
    --radius-lg:      12px;
    --shadow-card:    0 1px 3px rgba(0,0,0,0.4), 0 4px 12px rgba(0,0,0,0.2);
}
"""

_GLOBAL_CSS = """
/* ── Base ─────────────────────────────────────────────────────────────────── */
.stApp {
    background-color: var(--bg-primary) !important;
}
.main .block-container {
    padding: 1.5rem 2rem 3rem !important;
    max-width: 1280px;
}
/* Aplica fonte apenas em elementos de texto — spans deliberadamente excluídos
   para não sobrescrever ícones Material Icons do Streamlit (sidebar toggle,
   expander arrows) que usam font-family: 'Material Symbols Rounded'. */
html, body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif !important;
}
p, label, div[class*="stMarkdown"], div[class*="stText"],
div[data-testid="stMarkdownContainer"],
div[data-testid="stText"] {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif !important;
}
h1, h2, h3, h4, h5, h6 {
    color: var(--text-primary) !important;
    font-weight: 600 !important;
    letter-spacing: -0.02em;
}

/* ── Sidebar ──────────────────────────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background-color: var(--bg-surface) !important;
    border-right: 1px solid var(--border) !important;
}
section[data-testid="stSidebar"] * {
    color: var(--text-primary) !important;
}

/* ── Tabs ─────────────────────────────────────────────────────────────────── */
div[data-testid="stTabs"] [data-baseweb="tab-list"] {
    background-color: var(--bg-surface) !important;
}
div[data-testid="stTabs"] [data-baseweb="tab"] {
    background-color: transparent !important;
    color: var(--text-secondary) !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    transition: color 0.15s ease !important;
}
div[data-testid="stTabs"] [aria-selected="true"] {
    color: var(--text-primary) !important;
}
div[data-testid="stTabs"] [data-baseweb="tab-highlight"] {
    background-color: var(--accent) !important;
}
div[data-testid="stTabs"] [data-baseweb="tab-border"] {
    background-color: var(--border) !important;
}

/* ── Inputs ───────────────────────────────────────────────────────────────── */
div[data-baseweb="input"] input,
div[data-baseweb="textarea"] textarea {
    background-color: var(--bg-input) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
    color: var(--text-primary) !important;
    font-size: 0.875rem !important;
}

/* ── Buttons ──────────────────────────────────────────────────────────────── */
.stButton > button {
    background-color: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    color: var(--text-primary) !important;
    border-radius: var(--radius-sm) !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    transition: border-color 0.15s ease, color 0.15s ease !important;
    white-space: nowrap !important;
    min-width: fit-content !important;
}
.stButton > button:hover {
    border-color: var(--accent) !important;
    color: var(--accent) !important;
}
.stButton > button[kind="primary"],
.stButton > button[data-testid*="primary"] {
    background-color: var(--accent) !important;
    border-color: var(--accent) !important;
    color: #ffffff !important;
    font-weight: 600 !important;
}
.stButton > button[kind="primary"]:hover {
    background-color: var(--accent-hover) !important;
    border-color: var(--accent-hover) !important;
    color: #ffffff !important;
}

/* ── Download button ──────────────────────────────────────────────────────── */
.stDownloadButton > button {
    background-color: var(--accent) !important;
    border-color: var(--accent) !important;
    color: #ffffff !important;
    font-weight: 600 !important;
}

/* ── Dataframe ────────────────────────────────────────────────────────────── */
.stDataFrame {
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-md) !important;
}

/* ── Expander ─────────────────────────────────────────────────────────────── */
details[data-testid="stExpander"] {
    background-color: var(--bg-surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-md) !important;
}
details[data-testid="stExpander"] summary {
    color: var(--text-secondary) !important;
    font-size: 0.875rem !important;
}

/* ── Divider ──────────────────────────────────────────────────────────────── */
hr {
    border-color: var(--border) !important;
    margin: 1.25rem 0 !important;
}

/* ── Caption ──────────────────────────────────────────────────────────────── */
small, .stCaption, [data-testid="stCaptionContainer"] * {
    color: var(--text-secondary) !important;
    font-size: 0.8rem !important;
}

/* ── File uploader ────────────────────────────────────────────────────────── */
section[data-testid="stFileUploadDropzone"] {
    background-color: var(--bg-surface) !important;
    border: 2px dashed var(--border) !important;
    border-radius: var(--radius-md) !important;
}

/* ── Select / Dropdown ────────────────────────────────────────────────────── */
div[data-baseweb="select"] > div {
    background-color: var(--bg-input) !important;
    border-color: var(--border) !important;
}

/* ── Alert boxes ──────────────────────────────────────────────────────────── */
div[data-testid="stAlert"] {
    border-radius: var(--radius-md) !important;
}

/* ── Info box override ────────────────────────────────────────────────────── */
.stInfo {
    background-color: var(--accent-dim) !important;
    border: 1px solid var(--border-focus) !important;
    border-radius: var(--radius-md) !important;
}

/* ── NutriCalc components ─────────────────────────────────────────────────── */
.nc-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;
    padding: 1.125rem 1.5rem;
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    margin-bottom: 1.5rem;
}
.nc-logo-mark {
    font-size: 1.375rem;
    font-weight: 700;
    letter-spacing: -0.03em;
    color: var(--text-primary);
    line-height: 1;
}
.nc-logo-mark span {
    color: var(--accent);
}
.nc-tagline {
    font-size: 0.72rem;
    color: var(--text-muted);
    margin-top: 4px;
    letter-spacing: 0.01em;
}
.nc-header-badges {
    display: flex;
    gap: 6px;
    align-items: center;
    flex-wrap: wrap;
}
.nc-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 9px;
    border-radius: 20px;
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    white-space: nowrap;
}
.nc-badge-taco {
    background: var(--accent-dim);
    color: var(--accent);
    border: 1px solid var(--accent);
}
.nc-badge-forn {
    background: #0D2818;
    color: var(--forn-color);
    border: 1px solid var(--forn-color);
}
.nc-badge-live {
    background: var(--success-bg);
    color: #3FB950;
    border: 1px solid #238636;
}
.nc-badge-neutral {
    background: var(--bg-card);
    color: var(--text-secondary);
    border: 1px solid var(--border);
}
.nc-section-label {
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 0.5rem;
    margin-top: 0.25rem;
}
.nc-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 1rem 1.25rem;
    margin-bottom: 0.75rem;
}
.nc-card-accent {
    border-left: 3px solid var(--accent);
}
.nc-alert-legal {
    background: var(--warning-bg);
    border: 1px solid rgba(158,106,3,0.5);
    border-left: 3px solid #9E6A03;
    border-radius: var(--radius-md);
    padding: 0.65rem 1rem;
    color: #E3B341;
    font-size: 0.8rem;
    line-height: 1.6;
    margin-top: 0.75rem;
}
"""


def inject_global_css():
    """Injects the NutriCalc design system into the Streamlit page."""
    st.markdown(f"<style>{_TOKENS}{_GLOBAL_CSS}</style>", unsafe_allow_html=True)


def render_page_header(db_count: int = 0):
    """Renders the top application header with logo and system status badges."""
    count_badge = (
        f'<span class="nc-badge nc-badge-neutral">{db_count:,} alimentos</span>'
        if db_count else ""
    )
    st.markdown(f"""
    <div class="nc-header">
        <div>
            <div class="nc-logo-mark">Nutri<span>Calc</span> P&amp;D</div>
            <div class="nc-tagline">
                Tabelas Nutricionais &middot; Padrão ANVISA RDC 429/2020 &middot; Uso Interno P&amp;D
            </div>
        </div>
        <div class="nc-header-badges">
            <span class="nc-badge nc-badge-live">&#9679;&nbsp;Sistema Ativo</span>
            <span class="nc-badge nc-badge-taco">TACO 4ª Ed.</span>
            {count_badge}
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_section_label(text: str):
    """Renders a small-caps section label above a content block."""
    st.markdown(f'<div class="nc-section-label">{text}</div>', unsafe_allow_html=True)


def render_card(content_html: str, accent: bool = False):
    """Wraps HTML content in a styled dark card."""
    cls = "nc-card nc-card-accent" if accent else "nc-card"
    st.markdown(f'<div class="{cls}">{content_html}</div>', unsafe_allow_html=True)


def render_divider():
    """Renders a styled horizontal rule."""
    st.markdown('<hr>', unsafe_allow_html=True)


def render_legal_notice():
    """Renders the ANVISA legal disclaimer card."""
    st.markdown("""
    <div class="nc-alert-legal">
        <strong>Aviso Legal:</strong> Este cálculo é uma estimativa para uso interno em P&amp;D.
        <strong>Obrigatório:</strong> validação por nutricionista habilitado (CRN) antes do uso
        em rótulo comercial para venda. Valores podem diferir de análise laboratorial.
    </div>
    """, unsafe_allow_html=True)


def render_fonte_badge(fonte: str) -> str:
    """Returns an inline HTML badge string for TACO or FORNECEDOR source."""
    if fonte == "TACO":
        return '<span class="nc-badge nc-badge-taco">TACO</span>'
    return '<span class="nc-badge nc-badge-forn">Fornecedor</span>'
