from pathlib import Path
import streamlit as st
import pandas as pd
from datetime import datetime

CATALOGO_PATH = Path("construction_budget_data.csv")
PRESUP_ROOT = Path("presupuestos")

def presup_folder(nombre: str) -> Path:
    return PRESUP_ROOT / nombre

def list_presupuestos():
    PRESUP_ROOT.mkdir(exist_ok=True)
    return sorted([p.name for p in PRESUP_ROOT.iterdir() if p.is_dir()])

def empty_datos_df():
    return pd.DataFrame(columns=["Item", "Partida", "Fecha", "cantidad tipo", "cantidad numero", "moneda"])

def empty_detalle_df():
    return pd.DataFrame(columns=["item", "Codigo", "cantidad"])

def load_presupuesto(nombre: str):
    base = presup_folder(nombre)
    datos_p = base / "datos.csv"
    det_p = base / "detalle.csv"
    if not base.exists():
        return empty_datos_df(), empty_detalle_df()
    datos_df = pd.read_csv(datos_p) if datos_p.exists() else empty_datos_df()
    detalle_df = pd.read_csv(det_p) if det_p.exists() else empty_detalle_df()

    if "Fecha" in datos_df.columns:
        datos_df["Fecha"] = datos_df["Fecha"].astype(str)
    for c in ["cantidad numero", "moneda"]:
        if c in datos_df.columns:
            datos_df[c] = pd.to_numeric(datos_df[c], errors="coerce")
    if "cantidad" in detalle_df.columns:
        detalle_df["cantidad"] = pd.to_numeric(detalle_df["cantidad"], errors="coerce")
    return datos_df, detalle_df

def save_presupuesto(nombre: str, datos_df: pd.DataFrame, detalle_df: pd.DataFrame):
    base = presup_folder(nombre)
    base.mkdir(parents=True, exist_ok=True)
    datos_tmp = base / "datos.tmp.csv"
    detalle_tmp = base / "detalle.tmp.csv"
    datos_df.to_csv(datos_tmp, index=False)
    detalle_df.to_csv(detalle_tmp, index=False)
    datos_tmp.replace(base / "datos.csv")
    detalle_tmp.replace(base / "detalle.csv")

@st.cache_data
def load_catalogo():
    df = pd.read_csv(CATALOGO_PATH)
    # Eliminar columnas de índice exportadas (e.g., "Unnamed: 0")
    df = df.loc[:, ~df.columns.astype(str).str.match(r'^Unnamed(:?\s*\d*)?$')]
    # Asegurar columnas mínimas
    for c in ["Codigo","Resumen","Ud","Pres","Fecha","Categoria","Subcategoria"]:
        if c not in df.columns:
            df[c] = ""
    # Normalizar tipos básicos
    df["Codigo"] = df["Codigo"].astype(str)
    df["Resumen"] = df["Resumen"].astype(str)
    df["Ud"] = df["Ud"].astype(str)
    df["Categoria"] = df["Categoria"].astype(str)
    df["Subcategoria"] = df["Subcategoria"].astype(str)
    return df

def clp(x):
    try:
        return "$" + f"{int(round(float(x))):,}".replace(",", ".")
    except Exception:
        return x

def today_str():
    return datetime.now().strftime("%d/%m/%Y")


def catalog_selector_with_qty(df_catalogo: pd.DataFrame, state_key_prefix: str, qty_key: str):
    """
    Catálogo con columna 'cantidad' (stepper) y búsqueda por código independiente.
    Muestra columnas: Codigo, Categoria, Subcategoria, Resumen, Ud, Precio, Fecha, cantidad.
    """
    st.subheader("📦 Catálogo")

    # --- Filtros por categoría / subcategoría / nombre (Resumen) ---
    cats = sorted(df_catalogo["Categoria"].dropna().unique().tolist())
    selected_cat = st.selectbox("Categoría", options=cats, key=f"{state_key_prefix}_cat")
    filt = df_catalogo[df_catalogo["Categoria"] == selected_cat].copy()

    subcats = sorted(filt["Subcategoria"].dropna().unique().tolist())
    selected_subcat = st.selectbox("Subcategoría", options=subcats, key=f"{state_key_prefix}_subcat")
    filt = filt[filt["Subcategoria"] == selected_subcat].copy()

    search_options = filt["Resumen"].tolist()
    search_query = st.selectbox(
        "🔍 Buscar por nombre:",
        options=[""] + sorted(set(search_options)),
        index=0,
        key=f"{state_key_prefix}_search"
    )
    if search_query:
        q = search_query.lower()
        filt = filt[filt["Resumen"].str.lower().str.contains(q)].copy()

    # --- Búsqueda por CÓDIGO (ignora filtros anteriores) ---
    code_query = st.text_input(
        "🔢 Buscar por código (ignora filtros)",
        key=f"{state_key_prefix}_code_search",
        placeholder="Ej: MAA00575 o parte del código como MA o ma y clickea enter"
    )
    if code_query and code_query.strip():
        cq = code_query.strip().lower()
        filt = df_catalogo[df_catalogo["Codigo"].astype(str).str.lower().str.contains(cq)].copy()

    # --- Estado global de cantidades {Codigo: cantidad} ---
    if qty_key not in st.session_state:
        st.session_state[qty_key] = {}
    qty_map = st.session_state[qty_key]

    # --- Construir vista sin índice y sin columna de insertar filas ---
    view = filt[["Codigo", "Categoria", "Subcategoria", "Resumen", "Ud", "Pres", "Fecha"]].copy()
    view["Codigo"] = view["Codigo"].astype(str)
    view["Precio"] = view["Pres"].apply(clp)

    # Orden final (Categoria/Subcategoria después de Codigo y antes de Resumen)
    view = view[["Codigo", "Categoria", "Subcategoria", "Resumen", "Ud", "Precio", "Fecha"]]

    # Prellenar cantidad (0 por defecto) desde el mapa global
    view["cantidad"] = view["Codigo"].map(lambda c: qty_map.get(c, 0.0))

    edited = st.data_editor(
        view,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",  # evita columna para insertar filas
        column_config={
            "Codigo": st.column_config.TextColumn("Codigo", disabled=True),
            "Categoria": st.column_config.TextColumn("Categoria", disabled=True),
            "Subcategoria": st.column_config.TextColumn("Subcategoria", disabled=True),
            "Resumen": st.column_config.TextColumn("Resumen", disabled=True),
            "Ud": st.column_config.TextColumn("Ud", disabled=True),
            "Precio": st.column_config.TextColumn("Precio", disabled=True),
            "Fecha": st.column_config.TextColumn("Fecha", disabled=True),
            "cantidad": st.column_config.NumberColumn("cantidad", step=1.0, min_value=0.0),
        },
        key=f"{state_key_prefix}_editor",
    )

    current_codes = set(edited["Codigo"].astype(str))
    return edited, current_codes, qty_key
