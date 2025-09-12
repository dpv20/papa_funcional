# funciones/modificar_presupuesto.py
import streamlit as st
import pandas as pd
import shutil
import re  # <-- NUEVO: para normalizar códigos de ítem

from .presupuesto_utils import (
    list_presupuestos, load_presupuesto, save_presupuesto,
    load_catalogo, empty_datos_df, empty_detalle_df,
    catalog_selector_with_qty, today_str, clp, presup_folder
)

# ----------------- Helpers de ordenamiento (NUEVO) -----------------
def _norm_item_code(code: str, width: int = 6) -> str:
    """
    Normaliza un código tipo '02.01.10' a un string comparable numéricamente por segmentos:
    '02.01.10' -> '000002.000001.000010'
    Si no hay dígitos, retorna el código tal cual.
    """
    if code is None:
        return ""
    s = str(code)
    # Extrae todos los grupos de dígitos en orden:
    parts = re.findall(r"\d+", s)
    if not parts:
        return s
    return ".".join(p.zfill(width) for p in parts)

def _sort_datos_by_item(datos_df: pd.DataFrame) -> pd.DataFrame:
    """Ordena datos.csv por Item jerárquicamente."""
    if datos_df is None or datos_df.empty or "Item" not in datos_df.columns:
        return datos_df
    df = datos_df.copy()
    df["__sort"] = df["Item"].astype(str).map(_norm_item_code)
    df = df.sort_values(["__sort"], kind="mergesort").drop(columns="__sort").reset_index(drop=True)
    return df

def _sort_detalle_by_item(detalle_df: pd.DataFrame) -> pd.DataFrame:
    """Ordena detalle.csv por item (jerárquico) y luego por Codigo."""
    if detalle_df is None or detalle_df.empty or "item" not in detalle_df.columns:
        return detalle_df
    df = detalle_df.copy()
    df["__sort"] = df["item"].astype(str).map(_norm_item_code)
    # Conserva el orden estable y luego por Codigo
    df = df.sort_values(["__sort", "Codigo"], kind="mergesort").drop(columns="__sort").reset_index(drop=True)
    return df

def _sort_both_by_item(datos_df: pd.DataFrame, detalle_df: pd.DataFrame):
    """Devuelve (datos_sorted, detalle_sorted) con orden jerárquico por ítem."""
    return _sort_datos_by_item(datos_df), _sort_detalle_by_item(detalle_df)

# ----------------- Helpers existentes -----------------
def _upsert_item(datos_df: pd.DataFrame, item_code: str, partida: str, fecha: str,
                 cant_tipo: str, cant_num: float, moneda: float) -> pd.DataFrame:
    """Inserta o actualiza una fila en datos.csv para Item=item_code."""
    datos = datos_df.copy()
    mask = (datos["Item"].astype(str) == str(item_code))
    row = {
        "Item": str(item_code).strip(),
        "Partida": partida.strip(),
        "Fecha": str(fecha).strip(),
        "cantidad tipo": cant_tipo,
        "cantidad numero": float(cant_num),
        "moneda": float(moneda),
    }
    if mask.any():
        idx = datos.index[mask][0]
        for k, v in row.items():
            datos.at[idx, k] = v
    else:
        datos = pd.concat([datos, pd.DataFrame([row])], ignore_index=True)
    return datos

def _build_preview(catalogo: pd.DataFrame, qty_map: dict) -> pd.DataFrame:
    """Construye preview del detalle con columnas pedidas desde qty_map (solo >0)."""
    if not qty_map:
        return pd.DataFrame(columns=["Codigo","Resumen","Ud","Precio","Fecha","cantidad"])
    positive_codes = [c for c, q in qty_map.items() if q and float(q) > 0]
    if not positive_codes:
        return pd.DataFrame(columns=["Codigo","Resumen","Ud","Precio","Fecha","cantidad"])

    base = catalogo.loc[catalogo["Codigo"].astype(str).isin(positive_codes),
                        ["Codigo","Resumen","Ud","Pres","Fecha"]].copy()
    base["Codigo"] = base["Codigo"].astype(str)
    base["Precio"] = base["Pres"].apply(clp)
    base["cantidad"] = base["Codigo"].map(lambda c: float(qty_map.get(c, 0)))
    base = base[["Codigo","Resumen","Ud","Precio","Fecha","cantidad"]].sort_values("Codigo").reset_index(drop=True)
    return base

def _migrate_prefix_keys(old_prefix: str, new_prefix: str):
    """
    Migra claves de sesión que comienzan con old_prefix -> new_prefix.
    Úsalo SOLO para claves lógicas (NO widgets). Evita *_editor.
    """
    to_move = []
    for k in list(st.session_state.keys()):
        if isinstance(k, str) and k.startswith(old_prefix):
            if k.endswith("_editor") or "_editor" in k:
                continue
            to_move.append(k)
    for k in to_move:
        new_k = k.replace(old_prefix, new_prefix, 1)
        st.session_state[new_k] = st.session_state[k]
        del st.session_state[k]

def _clear_widget_keys(prefix: str):
    """Elimina claves de widgets que tengan este prefijo (p.ej., 'mod_<item>')."""
    to_del = []
    for k in list(st.session_state.keys()):
        if isinstance(k, str) and k.startswith(prefix) and ("_editor" in k or k.endswith("_editor")):
            to_del.append(k)
    for k in to_del:
        del st.session_state[k]

def _delete_prefix_keys(prefix: str):
    """Elimina cualquier clave de sesión (lógica o widget) que empiece con prefix."""
    to_del = [k for k in list(st.session_state.keys()) if isinstance(k, str) and k.startswith(prefix)]
    for k in to_del:
        del st.session_state[k]

def _keys_for_item(state_prefix: str, item_code: str):
    base = f"{state_prefix}__{item_code}"
    return {
        "qty": f"{base}__qty_map",          # {Codigo: cantidad} del ítem activo (lógico)
        "preview": f"{base}__preview",      # DF preview del ítem (lógico)
        "ui_prefix": f"mod_{item_code}",    # prefijo UI para editor de catálogo (widgets) -> NO migrar
    }

def _rename_item_and_consolidate(datos_df: pd.DataFrame, detalle_df: pd.DataFrame,
                                 old_item: str, new_item: str,
                                 partida: str, fecha_str: str,
                                 cant_tipo: str, cant_num: float, moneda: float):
    """
    Renombra old_item -> new_item en datos.csv y detalle.csv.
    - Upsertea la fila del nuevo ítem en datos.csv con los valores indicados.
    - Elimina la fila del old_item si queda duplicada.
    - En detalle.csv cambia 'item' y consolida por ['item','Codigo'] sumando 'cantidad'.
    - Devuelve ambos dataframes YA ORDENADOS por ítem.
    """
    # 1) datos.csv
    datos_updated = _upsert_item(datos_df, new_item, partida, fecha_str, cant_tipo, cant_num, moneda)
    if new_item != old_item:
        datos_updated = datos_updated[datos_updated["Item"].astype(str) != old_item]

    # 2) detalle.csv
    det_updated = detalle_df.copy()
    if new_item != old_item and not det_updated.empty:
        det_updated.loc[det_updated["item"].astype(str) == old_item, "item"] = new_item
        det_updated["cantidad"] = pd.to_numeric(det_updated["cantidad"], errors="coerce").fillna(0)
        det_updated = (det_updated
            .groupby(["item","Codigo"], as_index=False)["cantidad"]
            .sum()
            .reset_index(drop=True))

    # 3) ORDENAMIENTO (NUEVO)
    datos_sorted, det_sorted = _sort_both_by_item(datos_updated, det_updated)
    return datos_sorted, det_sorted

def _delete_item(datos_df: pd.DataFrame, detalle_df: pd.DataFrame, item_code: str):
    """Elimina por completo un ítem de datos.csv y detalle.csv. Devuelve ambos ya ordenados."""
    datos_updated = datos_df[datos_df["Item"].astype(str) != str(item_code)].copy()
    detalle_updated = detalle_df[detalle_df["item"].astype(str) != str(item_code)].copy()
    # Consolidación defensiva
    if not detalle_updated.empty:
        detalle_updated["cantidad"] = pd.to_numeric(detalle_updated["cantidad"], errors="coerce").fillna(0)
        detalle_updated = (detalle_updated
            .groupby(["item","Codigo"], as_index=False)["cantidad"].sum()
            .reset_index(drop=True))
    # ORDENAMIENTO (NUEVO)
    datos_sorted, det_sorted = _sort_both_by_item(datos_updated, detalle_updated)
    return datos_sorted, det_sorted

def _delete_project_folder(project_name: str):
    """Borra la carpeta completa del proyecto 'presupuestos/<project_name>'."""
    base = presup_folder(project_name)
    if base.exists():
        shutil.rmtree(base)

def _delete_all_state_for_project(state_prefix: str):
    """Limpia cualquier clave de sesión relacionada a un proyecto."""
    to_del = [k for k in list(st.session_state.keys()) if isinstance(k, str) and k.startswith(state_prefix)]
    for k in to_del:
        del st.session_state[k]

# ----------------- Vista principal -----------------
def render_modificar_presupuesto():
    st.title("✏️ Modificar Presupuesto")

    # 1) Elegir presupuesto
    PROJ_KEY = "mod_project_sel"
    PROJ_PENDING = "mod_project_sel_pending"
    existentes = list_presupuestos()
    if PROJ_PENDING in st.session_state:
        st.session_state[PROJ_KEY] = st.session_state[PROJ_PENDING]
        del st.session_state[PROJ_PENDING]
    nombre_sel = st.selectbox("Seleccionar presupuesto", options=[""] + existentes, key=PROJ_KEY)
    if not nombre_sel:
        st.info("Elige un presupuesto.")
        return

    datos_df, detalle_df = load_presupuesto(nombre_sel)
    catalogo = load_catalogo()
    uds_unique = [""] + sorted(catalogo["Ud"].dropna().unique().tolist())

    # Estado por presupuesto
    state_prefix = f"mod_{nombre_sel}"
    MODE_KEY = f"{state_prefix}_mode"      # 'existente' | 'nuevo_global'

    # --- Si NO hay ítems: mostrar opción de ELIMINAR PROYECTO ---
    items_now = datos_df["Item"].astype(str).tolist() if not datos_df.empty else []
    if not items_now:
        st.warning("No hay ítems en datos.csv. Cambia a **'Crear ítem nuevo'** o elimina el proyecto.")
        PROJ_DEL_FLAG = f"{state_prefix}_show_project_delete_dialog"
        if st.button("🗑️ Eliminar proyecto (carpeta)"):
            st.session_state[PROJ_DEL_FLAG] = True

        def _confirm_delete_project(project_name: str, state_prefix: str):
            # Borra carpeta y estado; recarga con selección limpia
            try:
                _delete_project_folder(project_name)
                _delete_all_state_for_project(state_prefix)
                st.success(f"Proyecto **{project_name}** eliminado.")
                st.session_state[PROJ_PENDING] = ""  # limpia selección
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo eliminar el proyecto: {e}")

        # Modal si disponible; inline si no
        if st.session_state.get(PROJ_DEL_FLAG, False):
            if hasattr(st, "dialog"):
                @st.dialog("Confirmar eliminación de proyecto")
                def _delete_project_dialog():
                    st.warning(f"¿Seguro que quieres eliminar el proyecto **{nombre_sel}**? Se borrará la carpeta completa.")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("❌ Cancelar"):
                            st.session_state[PROJ_DEL_FLAG] = False
                            st.rerun()
                    with c2:
                        if st.button("🗑️ Confirmar eliminación"):
                            _confirm_delete_project(nombre_sel, state_prefix)
                _delete_project_dialog()
            else:
                st.warning(f"¿Seguro que quieres eliminar el proyecto **{nombre_sel}**? Se borrará la carpeta completa.")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("❌ Cancelar"):
                        st.session_state[PROJ_DEL_FLAG] = False
                        st.rerun()
                with c2:
                    if st.button("🗑️ Confirmar eliminación"):
                        _confirm_delete_project(nombre_sel, state_prefix)
        # No seguimos con el flujo de ítems si no hay.
        return

    # --- Con ítems: flujo normal ---
    st.subheader("Ítem a trabajar")
    mode = st.radio("Modo", ["Usar ítem existente", "Crear ítem nuevo"], horizontal=True, key=MODE_KEY)

    # ---------- MODO: Ítem existente (editable + rename + eliminar) ----------
    if mode == "Usar ítem existente":
        ITEM_KEY = f"{state_prefix}_item_sel"
        PENDING_KEY = f"{state_prefix}_item_sel_pending"
        DEL_FLAG = f"{state_prefix}_show_delete_dialog"
        DEL_TARGET = f"{state_prefix}_delete_target"

        # Si hay una selección pendiente, aplicarla ANTES de crear el widget
        if PENDING_KEY in st.session_state:
            st.session_state[ITEM_KEY] = st.session_state[PENDING_KEY]
            del st.session_state[PENDING_KEY]

        items = datos_df["Item"].astype(str).tolist() if not datos_df.empty else []
        if not items:
            st.warning("No hay ítems en datos.csv. Cambia a 'Crear ítem nuevo'.")
            return

        # Selector del ítem existente
        item_sel = st.selectbox("Ítem existente", options=items, key=ITEM_KEY)

        # Botón eliminar + diálogo de confirmación
        col_del1, col_del2 = st.columns([1,3])
        with col_del1:
            if st.button("🗑️ Eliminar ítem"):
                st.session_state[DEL_TARGET] = item_sel
                st.session_state[DEL_FLAG] = True

        # Confirmación eliminar ÍTEM
        def _confirm_delete_item(nombre_presupuesto, state_prefix, datos_df, detalle_df, item_to_delete, ITEM_KEY, PENDING_KEY):
            if not item_to_delete:
                st.session_state[DEL_FLAG] = False
                st.session_state.pop(DEL_TARGET, None)
                st.rerun()

            # Borrar del CSV (devuelve ORDENADOS)
            datos_updated, detalle_updated = _delete_item(datos_df, detalle_df, item_to_delete)
            save_presupuesto(nombre_presupuesto, datos_updated, detalle_updated)

            # Actualizar dataframes en memoria
            datos_df[:] = datos_updated
            detalle_df[:] = detalle_updated

            # Limpiar estados de sesión del ítem borrado (lógicos y widgets)
            keys = _keys_for_item(state_prefix, item_to_delete)
            _delete_prefix_keys(keys["qty"])
            _delete_prefix_keys(keys["preview"])
            _clear_widget_keys(keys["ui_prefix"])

            # Elegir siguiente ítem (si queda alguno), o activar flujo de eliminación de proyecto
            remaining = datos_updated["Item"].astype(str).tolist() if not datos_updated.empty else []
            st.session_state[DEL_FLAG] = False
            st.session_state.pop(DEL_TARGET, None)
            if remaining:
                st.session_state[PENDING_KEY] = remaining[0]
                st.success(f"Ítem **{item_to_delete}** eliminado.")
            else:
                st.success(f"Ítem **{item_to_delete}** eliminado. No quedan ítems en el proyecto.")
            st.rerun()

        # Modal pop-out si está disponible
        if st.session_state.get(DEL_FLAG, False):
            if hasattr(st, "dialog"):
                @st.dialog("Confirmar eliminación de ítem")
                def _delete_dialog():
                    st.warning(f"¿Seguro que quieres eliminar **{st.session_state.get(DEL_TARGET,'')}**? Esta acción no se puede deshacer.")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("❌ Cancelar"):
                            st.session_state[DEL_FLAG] = False
                            st.session_state.pop(DEL_TARGET, None)
                            st.rerun()
                    with c2:
                        if st.button("🗑️ Confirmar eliminación"):
                            _confirm_delete_item(nombre_sel, state_prefix, datos_df, detalle_df, st.session_state.get(DEL_TARGET, ""), ITEM_KEY, PENDING_KEY)
                _delete_dialog()
            else:
                st.warning(f"¿Seguro que quieres eliminar **{st.session_state.get(DEL_TARGET,'')}**? Esta acción no se puede deshacer.")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("❌ Cancelar"):
                        st.session_state[DEL_FLAG] = False
                        st.session_state.pop(DEL_TARGET, None)
                        st.rerun()
                with c2:
                    if st.button("🗑️ Confirmar eliminación"):
                        _confirm_delete_item(nombre_sel, state_prefix, datos_df, detalle_df, st.session_state.get(DEL_TARGET, ""), ITEM_KEY, PENDING_KEY)

        # --- Editor del ítem (editable + rename) ---
        row = datos_df[datos_df["Item"].astype(str) == item_sel].iloc[0]
        st.caption("Edita campos del ítem seleccionado. Si cambias el código, se renombrará también en detalle.csv.")
        c0, c1 = st.columns([1,3])
        with c0:
            new_item_code = st.text_input("Código de Ítem", value=str(row.get("Item","")).strip(), key=f"{state_prefix}_new_code")
        with c1:
            partida = st.text_input("Partida (descripción)", value=str(row.get("Partida","")))
        c2, c3 = st.columns([1,1])
        with c2:
            fecha_str = st.text_input("Fecha (DD/MM/YYYY)", value=str(row.get("Fecha","")) or today_str())
        with c3:
            current_tipo = str(row.get("cantidad tipo",""))
            tipo_index = uds_unique.index(current_tipo) if current_tipo in uds_unique else 0
            cant_tipo = st.selectbox("Cantidad tipo (unidad)", options=uds_unique, index=tipo_index)

        c4, c5 = st.columns([1,1])
        with c4:
            cant_num = st.number_input("Cantidad número", min_value=0.0, value=float(row.get("cantidad numero", 0) or 0), step=1.0)
        with c5:
            moneda = st.number_input("Moneda", min_value=0.0, value=float(row.get("moneda", 1) or 1), step=1.0)

        # Guardar cambios del ÍTEM (datos.csv) + rename (detalle.csv) + consolidación
        if st.button("💠 Guardar cambios del ítem"):
            if not new_item_code.strip():
                st.error("El código del Ítem no puede estar vacío.")
            else:
                old_item = str(item_sel).strip()
                new_item = str(new_item_code).strip()

                datos_df_updated, detalle_updated = _rename_item_and_consolidate(
                    datos_df=datos_df,
                    detalle_df=detalle_df,
                    old_item=old_item,
                    new_item=new_item,
                    partida=partida,
                    fecha_str=fecha_str,
                    cant_tipo=cant_tipo,
                    cant_num=cant_num,
                    moneda=moneda
                )

                # (Ya vienen ordenados)
                save_presupuesto(nombre_sel, datos_df_updated, detalle_updated)
                datos_df[:] = datos_df_updated
                detalle_df[:] = detalle_updated

                if new_item != old_item:
                    # Migrar SOLO claves lógicas (qty/preview). NO migrar claves de widgets.
                    old_keys = _keys_for_item(state_prefix, old_item)
                    new_keys = _keys_for_item(state_prefix, new_item)
                    _migrate_prefix_keys(old_keys["qty"], new_keys["qty"])
                    _migrate_prefix_keys(old_keys["preview"], new_keys["preview"])
                    _clear_widget_keys(old_keys["ui_prefix"])  # limpia widgets del viejo
                    # Forzar que el selectbox muestre el nuevo ítem en el siguiente rerun
                    st.session_state[PENDING_KEY] = new_item
                    st.success(f"Ítem **{new_item}** guardado y renombrado (detalle.csv actualizado).")
                    st.rerun()
                else:
                    st.success(f"Ítem **{new_item}** guardado en datos.csv.")

        # ---- Trabajar el DETALLE del ítem (cantidades) ----
        active_item = st.session_state.get(ITEM_KEY, item_sel)
        keys = _keys_for_item(state_prefix, active_item)
        qty_key = keys["qty"]
        preview_key = keys["preview"]
        ui_prefix = keys["ui_prefix"]

        # Inicializar qty_map desde detalle.csv (solo 1 vez por ítem)
        if qty_key not in st.session_state:
            qty_map = {}
            if not detalle_df.empty:
                sub = detalle_df[detalle_df["item"].astype(str) == active_item]
                for _, r in sub.iterrows():
                    qty_map[str(r["Codigo"])] = float(r.get("cantidad", 0) or 0)
            st.session_state[qty_key] = qty_map

        if preview_key not in st.session_state:
            st.session_state[preview_key] = _build_preview(catalogo, st.session_state[qty_key])

        st.divider()
        st.subheader(f"Catálogo para el ítem: {active_item}")
        edited, current_codes, _ = catalog_selector_with_qty(
            catalogo, state_key_prefix=ui_prefix, qty_key=qty_key
        )

        if st.button("✅ Aplicar selección"):
            qty_map = st.session_state[qty_key]
            temp = edited[["Codigo","cantidad"]].copy()
            temp["Codigo"] = temp["Codigo"].astype(str)
            temp["cantidad"] = pd.to_numeric(temp["cantidad"], errors="coerce").fillna(0)
            for _, r in temp.iterrows():
                qty_map[r["Codigo"]] = float(r["cantidad"])
            st.session_state[qty_key] = qty_map
            st.session_state[preview_key] = _build_preview(catalogo, qty_map)
            st.success("Selección aplicada (acumulada para el ítem activo).")

        st.markdown("### Detalle actual (vista previa)")
        preview_full = st.session_state.get(preview_key, pd.DataFrame(columns=["Codigo","Resumen","Ud","Precio","Fecha","cantidad"]))
        if preview_full is not None and not preview_full.empty:
            edited_preview = st.data_editor(
                preview_full,
                use_container_width=True, hide_index=True, num_rows="dynamic",
                column_config={
                    "Codigo": st.column_config.TextColumn("Codigo", disabled=True),
                    "Resumen": st.column_config.TextColumn("Resumen", disabled=True),
                    "Ud": st.column_config.TextColumn("Ud", disabled=True),
                    "Precio": st.column_config.TextColumn("Precio", disabled=True),
                    "Fecha": st.column_config.TextColumn("Fecha", disabled=True),
                    "cantidad": st.column_config.NumberColumn("cantidad", step=1.0, min_value=0.0),
                },
                key=f"{ui_prefix}_preview_editor",
            )
            # Sync cantidades preview -> qty_map
            qty_map = st.session_state[qty_key]
            sync_temp = edited_preview[["Codigo","cantidad"]].copy()
            sync_temp["Codigo"] = sync_temp["Codigo"].astype(str)
            sync_temp["cantidad"] = pd.to_numeric(sync_temp["cantidad"], errors="coerce").fillna(0)
            for _, r in sync_temp.iterrows():
                qty_map[r["Codigo"]] = float(r["cantidad"])
            st.session_state[qty_key] = qty_map
            st.session_state[preview_key] = edited_preview

            # Guardar cambios del DETALLE (debajo de la vista previa)
            if st.button("💾 Guardar cambios"):
                positive = [(c, q) for c, q in qty_map.items() if q and float(q) > 0]
                if positive:
                    new_det = pd.DataFrame(positive, columns=["Codigo","cantidad"])
                    new_det["item"] = active_item
                    new_det = new_det[["item","Codigo","cantidad"]]
                else:
                    new_det = empty_detalle_df()

                others = detalle_df[detalle_df["item"].astype(str) != active_item].copy() if not detalle_df.empty else empty_detalle_df()
                detalle_updated = pd.concat([others, new_det], ignore_index=True)
                if not detalle_updated.empty:
                    detalle_updated["cantidad"] = pd.to_numeric(detalle_updated["cantidad"], errors="coerce").fillna(0)
                    detalle_updated = (detalle_updated
                        .groupby(["item","Codigo"], as_index=False)["cantidad"].sum()
                        .reset_index(drop=True))
                    # ORDENAMIENTO (NUEVO) solo detalle; datos_df no cambia acá
                    detalle_updated = _sort_detalle_by_item(detalle_updated)

                save_presupuesto(nombre_sel, datos_df, detalle_updated)
                detalle_df[:] = detalle_updated
                st.success(f"Cambios guardados en **{nombre_sel}** para el ítem **{active_item}**.")
        else:
            st.caption("Ajusta cantidades (> 0) y presiona **✅ Aplicar selección** para verlas aquí.")

    # ---------- MODO: Crear ítem nuevo (con catálogo y guardado completo) ----------
    else:
        st.caption("Define el nuevo ítem y arma su detalle acá mismo (sin cambiar de modo).")

        c1, c2 = st.columns([1,1])
        with c1:
            item_new = st.text_input("Item (ej. 02.01 o 03.02.01.03)", key=f"{state_prefix}_new_item_code")
        with c2:
            fecha_new = st.text_input("Fecha (DD/MM/YYYY)", value=today_str(), key=f"{state_prefix}_new_fecha")
        partida_new = st.text_input("Partida (descripción)", key=f"{state_prefix}_new_partida")

        c4, c5, c6 = st.columns([1,1,1])
        uds_unique = [""] + sorted(catalogo["Ud"].dropna().unique().tolist())
        with c4:
            cant_tipo_new = st.selectbox("Cantidad tipo (unidad)", options=uds_unique, index=0, key=f"{state_prefix}_new_tipo")
        with c5:
            cant_num_new = st.number_input("Cantidad número", min_value=0.0, value=1.0, step=1.0, key=f"{state_prefix}_new_num")
        with c6:
            moneda_new = st.number_input("Moneda", min_value=0.0, value=1.0, step=1.0, key=f"{state_prefix}_new_moneda")

        if not item_new.strip():
            st.info("Ingresa el código del ítem nuevo para habilitar el catálogo y el detalle.")
            return

        # Claves por ÍTEM NUEVO (estado lógico separado por código)
        new_keys = _keys_for_item(state_prefix, f"new__{item_new.strip()}")
        new_qty_key = new_keys["qty"]
        new_preview_key = new_keys["preview"]
        new_ui_prefix = f"mod_new_{item_new.strip()}"

        # Inicializar qty_map (vacío)
        if new_qty_key not in st.session_state:
            st.session_state[new_qty_key] = {}

        if new_preview_key not in st.session_state:
            st.session_state[new_preview_key] = _build_preview(catalogo, st.session_state[new_qty_key])

        st.divider()
        st.subheader(f"Catálogo para el ítem nuevo: {item_new.strip()}")
        edited, current_codes, _ = catalog_selector_with_qty(
            catalogo, state_key_prefix=new_ui_prefix, qty_key=new_qty_key
        )

        if st.button("✅ Aplicar selección", key=f"{new_ui_prefix}_apply"):
            qty_map = st.session_state[new_qty_key]
            temp = edited[["Codigo","cantidad"]].copy()
            temp["Codigo"] = temp["Codigo"].astype(str)
            temp["cantidad"] = pd.to_numeric(temp["cantidad"], errors="coerce").fillna(0)
            for _, r in temp.iterrows():
                qty_map[r["Codigo"]] = float(r["cantidad"])
            st.session_state[new_qty_key] = qty_map
            st.session_state[new_preview_key] = _build_preview(catalogo, qty_map)
            st.success("Selección aplicada (acumulada para el ítem nuevo).")

        st.markdown("### Detalle actual (vista previa)")
        preview_full_new = st.session_state.get(new_preview_key, pd.DataFrame(columns=["Codigo","Resumen","Ud","Precio","Fecha","cantidad"]))
        if preview_full_new is not None and not preview_full_new.empty:
            edited_preview_new = st.data_editor(
                preview_full_new,
                use_container_width=True, hide_index=True, num_rows="dynamic",
                column_config={
                    "Codigo": st.column_config.TextColumn("Codigo", disabled=True),
                    "Resumen": st.column_config.TextColumn("Resumen", disabled=True),
                    "Ud": st.column_config.TextColumn("Ud", disabled=True),
                    "Precio": st.column_config.TextColumn("Precio", disabled=True),
                    "Fecha": st.column_config.TextColumn("Fecha", disabled=True),
                    "cantidad": st.column_config.NumberColumn("cantidad", step=1.0, min_value=0.0),
                },
                key=f"{new_ui_prefix}_preview_editor",
            )
            # Sync cantidades preview -> qty_map
            qty_map = st.session_state[new_qty_key]
            sync_temp = edited_preview_new[["Codigo","cantidad"]].copy()
            sync_temp["Codigo"] = sync_temp["Codigo"].astype(str)
            sync_temp["cantidad"] = pd.to_numeric(sync_temp["cantidad"], errors="coerce").fillna(0)
            for _, r in sync_temp.iterrows():
                qty_map[r["Codigo"]] = float(r["cantidad"])
            st.session_state[new_qty_key] = qty_map
            st.session_state[new_preview_key] = edited_preview_new

            # Guardar cambios COMPLETOS (datos + detalle) para el ítem nuevo
            if st.button("💾 Guardar cambios", key=f"{new_ui_prefix}_save"):
                if not item_new.strip():
                    st.error("Debes indicar el código del Item.")
                    return

                # 1) Upsert en datos.csv del ítem nuevo
                datos_df_updated = _upsert_item(
                    datos_df, item_new.strip(), partida_new, fecha_new, cant_tipo_new, cant_num_new, moneda_new
                )

                # 2) Detalle nuevo para este ítem (solo >0)
                positive = [(c, q) for c, q in st.session_state[new_qty_key].items() if q and float(q) > 0]
                if positive:
                    new_det = pd.DataFrame(positive, columns=["Codigo","cantidad"])
                    new_det["item"] = item_new.strip()
                    new_det = new_det[["item","Codigo","cantidad"]]
                else:
                    new_det = empty_detalle_df()

                # 3) Reemplaza (si ya existía) el detalle de ese ítem y conserva los demás
                others = detalle_df[detalle_df["item"].astype(str) != item_new.strip()].copy() if not detalle_df.empty else empty_detalle_df()
                detalle_updated = pd.concat([others, new_det], ignore_index=True)
                if not detalle_updated.empty:
                    detalle_updated["cantidad"] = pd.to_numeric(detalle_updated["cantidad"], errors="coerce").fillna(0)
                    detalle_updated = (detalle_updated
                        .groupby(["item","Codigo"], as_index=False)["cantidad"].sum()
                        .reset_index(drop=True))

                # 4) ORDENAMIENTO (NUEVO) en ambos antes de guardar
                datos_df_sorted, detalle_sorted = _sort_both_by_item(datos_df_updated, detalle_updated)

                save_presupuesto(nombre_sel, datos_df_sorted, detalle_sorted)
                datos_df[:] = datos_df_sorted
                detalle_df[:] = detalle_sorted
                st.success(f"Ítem **{item_new.strip()}** creado/actualizado con su detalle en **{nombre_sel}**.")
        else:
            st.caption("Ajusta cantidades (> 0) y presiona **✅ Aplicar selección** para verlas aquí.")
