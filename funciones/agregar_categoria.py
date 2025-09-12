# funciones/agregar_categoria.py
import streamlit as st
import pandas as pd
from pathlib import Path

CATEGORIES_PATH = Path("categorias.csv")

TYPE_OPTIONS = [
    "MATERIALES",
    "EQUIPOS, MAQUINARIAS, HERRAMIENTAS",
    "MANO DE OBRA",
    "SUBCONTRATOS",
    "OTROS",
    "SUB-ANALISIS",
]

COLS_ORDER = [
    "Prefijo",
    "Categoria",
    "Subcategoria",
    "MaxNumero",
    "Count",
    "NextCodigo",
    "Tipo",
]


def _ensure_tipo_column(df: pd.DataFrame) -> pd.DataFrame:
    """Garantiza que exista 'Tipo' y que sus valores sean válidos."""
    if "Tipo" not in df.columns:
        df["Tipo"] = "MATERIALES"
    df["Tipo"] = df["Tipo"].fillna("MATERIALES").astype(str).str.strip()
    df.loc[~df["Tipo"].isin(TYPE_OPTIONS), "Tipo"] = "MATERIALES"
    return df


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Asegura columnas mínimas y su orden al persistir."""
    for c in COLS_ORDER:
        if c not in df.columns:
            df[c] = None
    return df[COLS_ORDER]


def load_categories() -> pd.DataFrame:
    if CATEGORIES_PATH.exists():
        df = pd.read_csv(CATEGORIES_PATH)
    else:
        df = pd.DataFrame(columns=COLS_ORDER)
    return _ensure_tipo_column(df)


def save_categories(df: pd.DataFrame) -> None:
    df = _normalize_columns(df)
    df.to_csv(CATEGORIES_PATH, index=False)


def render_add_category():
    st.title("🗂️ Agregar Categoría / Subcategoría")

    df = load_categories()

    # --- Formulario: Nuevo registro ---
    st.subheader("Nueva Categoría/Subcategoría")
    with st.form("add_category_form", clear_on_submit=False):
        col1, col2, col3, col4 = st.columns([2, 2, 1, 2])

        with col1:
            categoria = st.text_input(
                "Categoría*",
                placeholder="Ej: Hormigones y morteros",
                key="categoria_input",
            ).strip()
        with col2:
            subcategoria = st.text_input(
                "Subcategoría*",
                placeholder="Ej: Hormigones",
                key="subcategoria_input",
            ).strip()
        with col3:
            prefijo = st.text_input(
                "Prefijo*",
                placeholder="Ej: MAA",
                key="prefijo_input",
            ).strip().upper()
        with col4:
            tipo_sel = st.selectbox(
                "Tipo*",
                TYPE_OPTIONS,
                index=0,
                key="new_tipo_select",
                help="Selecciona el tipo del nuevo registro.",
            )

        submitted = st.form_submit_button("Guardar", use_container_width=True)
        if submitted:
            if not categoria or not subcategoria or not prefijo or not tipo_sel:
                st.error("Todos los campos son obligatorios.")
            else:
                duplicado = (
                    not df.empty
                    and not df[
                        (df["Categoria"].astype(str).str.strip() == categoria)
                        & (df["Subcategoria"].astype(str).str.strip() == subcategoria)
                    ].empty
                )
                if duplicado:
                    st.error("Esta combinación Categoría/Subcategoría ya existe.")
                else:
                    numero_inicial = 1
                    ancho = 4
                    next_code = f"{prefijo}{str(numero_inicial).zfill(ancho)}"
                    nuevo = {
                        "Categoria": categoria,
                        "Subcategoria": subcategoria,
                        "Prefijo": prefijo,
                        "MaxNumero": numero_inicial - 1,
                        "Count": 0,
                        "NextCodigo": next_code,
                        "Tipo": tipo_sel,
                    }
                    df = pd.concat([df, pd.DataFrame([nuevo])], ignore_index=True)
                    save_categories(df)
                    st.success(
                        f"✅ Agregado: {prefijo} → {categoria} / {subcategoria} (Tipo: {tipo_sel})"
                    )

    # --- Editor: modificar Tipo de existentes ---
    st.subheader("Editar Tipo de Categorías/Subcategorías Existentes")

    if df.empty:
        st.info("Aún no hay categorías registradas.")
        return

    edit_df = (
        df[COLS_ORDER]
        .sort_values(["Prefijo", "Categoria", "Subcategoria"], na_position="last")
        .reset_index(drop=True)
    )

    edited_df = st.data_editor(
        edit_df,
        use_container_width=True,
        num_rows="fixed",
        key="editor_tipos",
        column_config={
            "Tipo": st.column_config.SelectboxColumn(
                "Tipo",
                options=TYPE_OPTIONS,
                help="Selecciona el tipo para cada categoría/subcategoría.",
                required=True,
            ),
            "Prefijo": st.column_config.TextColumn("Prefijo", help="Solo lectura"),
            "Categoria": st.column_config.TextColumn("Categoria"),
            "Subcategoria": st.column_config.TextColumn("Subcategoria"),
            "MaxNumero": st.column_config.NumberColumn("MaxNumero"),
            "Count": st.column_config.NumberColumn("Count"),
            "NextCodigo": st.column_config.TextColumn("NextCodigo"),
        },
        disabled=["Prefijo", "MaxNumero", "Count", "NextCodigo"],
    )

    if st.button("💾 Guardar cambios de Tipo", key="btn_guardar_tipos", use_container_width=True):
        edited_df["Tipo"] = edited_df["Tipo"].astype(str).str.strip()
        edited_df = _ensure_tipo_column(edited_df)
        save_categories(edited_df)
        st.success("Cambios guardados correctamente.")
