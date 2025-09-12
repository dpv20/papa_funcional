# funciones/modify_item.py
import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime, date

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

@st.cache_data
def load_categories():
    if CATEGORIES_PATH.exists():
        return pd.read_csv(CATEGORIES_PATH)
    return pd.DataFrame(columns=["Categoria", "Subcategoria", "Prefijo", "MaxNumero", "Count", "NextCodigo"])

# Formateador visual CLP
def clp(x):
    try:
        return "$" + f"{int(round(float(x))):,}".replace(",", ".")
    except Exception:
        return x

def _parse_ddmmyyyy(fecha_str: str) -> date:
    """Intenta parsear DD/MM/YYYY; si falla, intenta otros formatos; si vuelve a fallar → hoy."""
    if not isinstance(fecha_str, str):
        return date.today()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):  # soporta ambos
        try:
            return datetime.strptime(fecha_str.strip(), fmt).date()
        except Exception:
            pass
    return date.today()

def _detalle_item(df, codigo_sel):
    row = df[df["Codigo"].astype(str) == str(codigo_sel)].iloc[0]
    st.markdown(f"**Código:** {row['Codigo']}")
    st.markdown(f"**Resumen:** {row['Resumen']}")
    st.markdown(f"**Categoría/Subcategoría:** {row['Categoria']} / {row.get('Subcategoria','')}")
    st.markdown(f"**Ud:** {row['Ud']}  |  **Precio:** {clp(row['Pres'])}")
    st.markdown(f"**Fecha:** {row['Fecha']}")

def render_modify_item():
    st.title("✏️ Modificar / Eliminar ítem")

    df = load_data()
    if df.empty:
        st.info("No hay datos aún. Agrega ítems en la sección **Agregar ítem**.")
        return

    df_cat = load_categories()
    if df_cat.empty:
        st.warning("No se encontraron categorías en **categorias.csv**. La selección puede ser limitada.")
        categorias = sorted(df["Categoria"].dropna().astype(str).unique().tolist())
        sub_map = {
            c: sorted(df[df["Categoria"].astype(str) == c]["Subcategoria"].dropna().astype(str).unique().tolist())
            for c in categorias
        }
    else:
        categorias = sorted(df_cat["Categoria"].dropna().astype(str).unique().tolist())
        sub_map = {
            c: sorted(df_cat[df_cat["Categoria"].astype(str) == c]["Subcategoria"].dropna().astype(str).unique().tolist())
            for c in categorias
        }

    # ---------- Selección guiada: Categoría → Subcategoría → Ítem ----------
    st.subheader("Selecciona el ítem a editar")

    colf1, colf2 = st.columns(2)
    with colf1:
        cat = st.selectbox("Categoría", options=["—"] + categorias, index=0)
    with colf2:
        if cat != "—":
            sub_opts = sub_map.get(cat, [])
            sub = st.selectbox("Subcategoría", options=["—"] + sub_opts, index=0)
        else:
            sub = st.selectbox("Subcategoría", options=["—"], index=0, disabled=True)

    # Filtrar ítems según selección
    filt = df.copy()
    if cat != "—":
        filt = filt[filt["Categoria"].astype(str) == cat]
    if sub != "—":
        filt = filt[filt["Subcategoria"].astype(str) == sub]

    if filt.empty:
        st.warning("No hay ítems para la combinación seleccionada.")
        return

    # Seleccionar ítem por Código (no escribirlo)
    codigo_sel = st.selectbox(
        "Ítem",
        options=sorted(filt["Codigo"].astype(str).tolist()),
        format_func=lambda x: f"{x} — {filt.loc[filt['Codigo'].astype(str)==x, 'Resumen'].iloc[0]}"
    )

    # Detalle actual
    with st.expander("Detalle actual", expanded=False):
        _detalle_item(df, codigo_sel)

    # ---- Edición (sin cambiar Código / Categoría / Subcategoría) ----
    st.write("### Editar valores")
    row = df[df["Codigo"].astype(str) == str(codigo_sel)].iloc[0]

    # Valores actuales
    cur_resumen = str(row["Resumen"]) if pd.notna(row["Resumen"]) else ""
    cur_ud = str(row["Ud"]) if pd.notna(row["Ud"]) else ""
    cur_pres = float(row["Pres"]) if pd.notna(row["Pres"]) else 0.0
    cur_fecha = _parse_ddmmyyyy(str(row["Fecha"]))  # convierte a date para el date_input

    # Sugerencias de Unidad
    opts_ud = sorted({str(v).strip() for v in df["Ud"].dropna().astype(str) if str(v).strip() != ""})

    with st.form("edit_item_form"):
        c1, c2 = st.columns(2)
        with c1:
            st.text_input("Código", value=str(row["Codigo"]), disabled=True)
            st.text_input("Categoría", value=str(row["Categoria"]), disabled=True)
            st.text_input("Subcategoría", value=str(row.get("Subcategoria", "")), disabled=True)
            nuevo_resumen = st.text_input("Resumen*", value=cur_resumen).strip()
        with c2:
            nueva_ud = st.selectbox("Unidad (Ud)*", options=["—"] + opts_ud, index=(["—"] + opts_ud).index(cur_ud) if cur_ud in (["—"] + opts_ud) else 0)
            # Precio entero como en "Agregar ítem"
            nuevo_pres = st.number_input("Precio (Pres)*", min_value=0, step=1, value=int(round(cur_pres)), format="%d")
            nueva_fecha = st.date_input("Fecha", value=cur_fecha)

        colb1, colb2, colb3 = st.columns([1,1,2])
        guardar = colb1.form_submit_button("💾 Guardar cambios")
        eliminar = colb2.form_submit_button("🗑️ Eliminar ítem")

    # ---- Acciones
    if guardar:
        errores = []
        if not nuevo_resumen:
            errores.append("El **Resumen** es obligatorio.")
        if nueva_ud == "—":
            errores.append("La **Unidad (Ud)** es obligatoria.")

        if errores:
            for e in errores:
                st.error(e)
        else:
            idx = df.index[df["Codigo"].astype(str) == str(codigo_sel)][0]
            # No cambiamos Código/Categoría/Subcategoría
            df.loc[idx, "Resumen"] = nuevo_resumen
            df.loc[idx, "Ud"] = nueva_ud
            df.loc[idx, "Pres"] = float(nuevo_pres)
            # Fecha en DD/MM/YYYY
            df.loc[idx, "Fecha"] = nueva_fecha.strftime("%d/%m/%Y")

            save_data(df)
            st.success(f"Ítem **{codigo_sel}** actualizado.")
            load_data.clear()

    if eliminar:
        confirm = st.checkbox("Confirmo que deseo eliminar este ítem de forma permanente.")
        if confirm:
            df = df[df["Codigo"].astype(str) != str(codigo_sel)].copy()
            save_data(df)
            st.success(f"Ítem **{codigo_sel}** eliminado.")
            load_data.clear()
        else:
            st.warning("Debes confirmar la eliminación marcando la casilla.")
