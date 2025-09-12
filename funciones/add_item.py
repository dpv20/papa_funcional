# funciones/add_item.py
import streamlit as st
import pandas as pd
import re
from pathlib import Path
from datetime import date

DATA_PATH = Path("construction_budget_data.csv")
CATEGORIES_PATH = Path("categorias.csv")

@st.cache_data
def load_data():
    if DATA_PATH.exists():
        return pd.read_csv(DATA_PATH)
    cols = ["Codigo", "Resumen", "Categoria", "Subcategoria", "Ud", "Pres", "Fecha"]
    return pd.DataFrame(columns=cols)

def save_data(df: pd.DataFrame):
    tmp = DATA_PATH.with_suffix(".tmp.csv")
    df.to_csv(tmp, index=False)
    tmp.replace(DATA_PATH)

def load_categories():
    if CATEGORIES_PATH.exists():
        return pd.read_csv(CATEGORIES_PATH)
    return pd.DataFrame(columns=["Categoria", "Subcategoria", "Prefijo", "MaxNumero", "Count", "NextCodigo"])

def save_categories(df):
    df.to_csv(CATEGORIES_PATH, index=False)

# Formato CLP solo visual
def clp(x):
    try:
        return "$" + f"{int(round(float(x))):,}".replace(",", ".")
    except Exception:
        return x

def _digits_len_from_next(next_code: str, fallback_width: int = 4) -> int:
    """Largo de dígitos según NextCodigo (ej: MAA06108 -> 5)."""
    if isinstance(next_code, str):
        m = re.search(r"(\d+)$", next_code.strip())
        if m:
            return len(m.group(1))
    return fallback_width

def render_add_item():
    st.title("➕ Agregar ítem")

    df_items = load_data()
    df_cat = load_categories()

    if df_cat.empty:
        st.error("⚠️ No existen categorías. Primero agrega una en '🗂️ Agregar Categoría'.")
        return

    # ---------- Selección de clasificación (fuera del form para actualizar al instante) ----------
    st.subheader("Clasificación")

    categorias = sorted(df_cat["Categoria"].astype(str).unique())
    sub_map = {
        cat: sorted(df_cat[df_cat["Categoria"].astype(str) == cat]["Subcategoria"].astype(str).unique())
        for cat in categorias
    }

    # Estado inicial
    if "cat_sel" not in st.session_state:
        st.session_state["cat_sel"] = "—"
    if "sub_sel" not in st.session_state:
        st.session_state["sub_sel"] = "—"

    def _reset_sub():
        st.session_state["sub_sel"] = "—"

    colc1, colc2 = st.columns(2)
    with colc1:
        st.selectbox(
            "Categoría*",
            options=["—"] + categorias,
            key="cat_sel",
            index=(["—"] + categorias).index(st.session_state["cat_sel"]) if st.session_state["cat_sel"] in (["—"] + categorias) else 0,
            on_change=_reset_sub
        )

    with colc2:
        if st.session_state["cat_sel"] != "—":
            sub_opts = sub_map.get(st.session_state["cat_sel"], [])
            st.selectbox(
                "Subcategoría*",
                options=["—"] + sub_opts,
                key="sub_sel",
                index=(["—"] + sub_opts).index(st.session_state["sub_sel"]) if st.session_state["sub_sel"] in (["—"] + sub_opts) else 0
            )
        else:
            # Sin categoría seleccionada aún: no permitimos elegir subcategoría
            st.selectbox("Subcategoría*", options=["—"], key="sub_sel", index=0, disabled=True)

    # Vista previa del próximo código (si ya hay cat/sub elegidas válidas)
    preview_code = ""
    if st.session_state["cat_sel"] != "—" and st.session_state["sub_sel"] != "—":
        row = df_cat[
            (df_cat["Categoria"].astype(str) == st.session_state["cat_sel"]) &
            (df_cat["Subcategoria"].astype(str) == st.session_state["sub_sel"])
        ]
        if not row.empty:
            prefijo = str(row["Prefijo"].iloc[0]).strip()
            max_num = int(row["MaxNumero"].iloc[0]) if pd.notna(row["MaxNumero"].iloc[0]) else 0
            width = _digits_len_from_next(str(row["NextCodigo"].iloc[0]) if "NextCodigo" in row.columns else "", max(4, len(str(max_num))))
            next_num = max_num + 1
            preview_code = f"{prefijo}{str(next_num).zfill(width)}"
            st.caption(f"**Siguiente código sugerido:** {preview_code}")

    # ---------- Formulario de datos del ítem ----------
    with st.form("add_item_form", clear_on_submit=False):
        st.subheader("Datos del ítem")

        c1, c2 = st.columns(2)
        with c1:
            resumen = st.text_input("Resumen*", placeholder="Descripción breve").strip()

        with c2:
            # Unidad sugerida desde ítems existentes
            opts_ud = sorted({str(v).strip() for v in df_items["Ud"].dropna()}) if not df_items.empty else []
            ud_choice = st.selectbox("Unidad (Ud)*", options=["—"] + opts_ud, index=0)

            pres = st.number_input("Precio (Pres)*", min_value=0, step=1, value=0, format="%d")
            fecha = st.date_input("Fecha", value=date.today())

        submitted = st.form_submit_button("Guardar ítem")

    if submitted:
        errores = []
        if st.session_state["cat_sel"] == "—":
            errores.append("La **Categoría** es obligatoria.")
        if st.session_state["sub_sel"] == "—":
            errores.append("La **Subcategoría** es obligatoria.")
        if not resumen:
            errores.append("El **Resumen** es obligatorio.")
        if ud_choice == "—":
            errores.append("La **Unidad (Ud)** es obligatoria.")

        if errores:
            for e in errores:
                st.error(e)
            return

        # Buscar la combinación en categorias.csv
        row = df_cat[
            (df_cat["Categoria"].astype(str) == st.session_state["cat_sel"]) &
            (df_cat["Subcategoria"].astype(str) == st.session_state["sub_sel"])
        ]
        if row.empty:
            st.error("⚠️ Esa combinación Categoría/Subcategoría no existe en categorias.csv.")
            return

        prefijo = str(row["Prefijo"].iloc[0]).strip()
        max_num = int(row["MaxNumero"].iloc[0]) if pd.notna(row["MaxNumero"].iloc[0]) else 0
        width = _digits_len_from_next(str(row["NextCodigo"].iloc[0]) if "NextCodigo" in row.columns else "", max(4, len(str(max_num))))
        next_num = max_num + 1
        codigo = f"{prefijo}{str(next_num).zfill(width)}"

        # Guardar fecha como DD/MM/YYYY
        fecha_str = fecha.strftime("%d/%m/%Y")

        # Crear y guardar el ítem
        nuevo = {
            "Codigo": codigo,
            "Resumen": resumen,
            "Categoria": st.session_state["cat_sel"],
            "Subcategoria": st.session_state["sub_sel"],
            "Ud": ud_choice,
            "Pres": float(pres),
            "Fecha": fecha_str,
        }

        df_items = pd.concat([df_items, pd.DataFrame([nuevo])], ignore_index=True)
        save_data(df_items)

        # Actualizar categorias.csv
        next_next = next_num + 1
        next_codigo = f"{prefijo}{str(next_next).zfill(width)}"
        df_cat.loc[
            (df_cat["Categoria"].astype(str) == st.session_state["cat_sel"]) &
            (df_cat["Subcategoria"].astype(str) == st.session_state["sub_sel"]),
            ["MaxNumero", "Count", "NextCodigo"]
        ] = [
            next_num,
            int(row["Count"].iloc[0]) + 1 if pd.notna(row["Count"].iloc[0]) else 1,
            next_codigo
        ]
        save_categories(df_cat)

        st.success(
            f"✅ Ítem agregado con Código **{codigo}** "
            f"({resumen} · {ud_choice} · {clp(pres)} · {fecha_str})"
        )
        # Limpiar la caché de items para que otras vistas recarguen
        load_data.clear()
