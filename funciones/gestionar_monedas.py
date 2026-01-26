# funciones/gestionar_monedas.py
import streamlit as st
import pandas as pd
from .monedas import load_monedas, save_monedas


def render_gestionar_monedas():
    st.title("💱 Administrar Monedas")
    
    df = load_monedas()
    
    st.caption("Edita los valores de tipo de cambio. CLP siempre es 1 (base).")
    
    # Editor de monedas
    edited_df = st.data_editor(
        df,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        column_config={
            "Codigo": st.column_config.TextColumn("Código", disabled=True),
            "Nombre": st.column_config.TextColumn("Nombre", disabled=True),
            "ValorCLP": st.column_config.NumberColumn(
                "Valor en CLP",
                help="Cuántos pesos chilenos equivale 1 unidad de esta moneda",
                min_value=0.01,
                format="%.2f",
            ),
        },
        key="monedas_editor",
    )
    
    # Validar que CLP siempre sea 1
    clp_mask = edited_df["Codigo"].astype(str).str.upper() == "CLP"
    if clp_mask.any():
        edited_df.loc[clp_mask, "ValorCLP"] = 1.0
    
    # Botón guardar
    if st.button("💾 Guardar cambios", use_container_width=True):
        save_monedas(edited_df)
        st.success("✅ Valores de moneda actualizados.")
    
    # Info útil
    st.divider()
    st.subheader("📊 Conversiones actuales")
    
    uf_val = float(edited_df.loc[edited_df["Codigo"] == "UF", "ValorCLP"].iloc[0]) if (edited_df["Codigo"] == "UF").any() else 0
    usd_val = float(edited_df.loc[edited_df["Codigo"] == "USD", "ValorCLP"].iloc[0]) if (edited_df["Codigo"] == "USD").any() else 0
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("1 UF =", f"${uf_val:,.0f} CLP".replace(",", "."))
    with col2:
        st.metric("1 USD =", f"${usd_val:,.0f} CLP".replace(",", "."))
