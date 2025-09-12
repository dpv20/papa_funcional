# funciones/crear_pdf.py
from __future__ import annotations

from pathlib import Path
import os
import platform
import subprocess
from datetime import datetime, date
from typing import Dict, List, Tuple

import pandas as pd
import streamlit as st

# =========================
# Utilidades base
# =========================

def _fmt_comma0(x) -> str:
    """Comma style sin decimales: 12,345"""
    try:
        return "{:,.0f}".format(float(x))
    except Exception:
        return str(x)

def _abrir_en_sistema(path: Path) -> bool:
    try:
        system = platform.system()
        if system == "Windows":
            os.startfile(str(path))  # type: ignore[attr-defined]
            return True
        elif system == "Darwin":
            subprocess.Popen(["open", str(path)])
            return True
        else:
            subprocess.Popen(["xdg-open", str(path)])
            return True
    except Exception:
        return False

def _listar_proyectos(base_dir: str = ".") -> list[str]:
    base = Path(base_dir) / "presupuestos"
    if not base.exists():
        return []
    proyectos = []
    for p in base.iterdir():
        if p.is_dir() and (p / "datos.csv").exists() and (p / "detalle.csv").exists():
            proyectos.append(p.name)
    return sorted(proyectos)

def _parse_key(code: str) -> Tuple[int, ...]:
    parts = []
    for seg in str(code).split("."):
        try:
            parts.append(int(seg))
        except Exception:
            try:
                parts.append(int(seg.lstrip("0") or "0"))
            except Exception:
                parts.append(0)
    return tuple(parts)

def _collect_parents(items: List[str]) -> List[str]:
    """Devuelve padres que tienen subcategorías: '1', '2', '2.03', '3', etc."""
    items = [str(x) for x in items if isinstance(x, str)]
    children_by_parent: Dict[str, List[str]] = {}
    for it in items:
        segs = it.split(".")
        if len(segs) >= 2:
            parent = ".".join(segs[:-1])
            children_by_parent.setdefault(parent, []).append(it)
        top = segs[0]
        if top != it and it.startswith(top + "."):
            children_by_parent.setdefault(top, []).append(it)
    parents = [p for p, childs in children_by_parent.items() if len(childs) > 0]
    return sorted(set(parents), key=_parse_key)

def _children_of_parent(items: List[str], parent: str) -> List[str]:
    pref = parent + "."
    childs = [it for it in items if it.startswith(pref) and it.count(".") == parent.count(".") + 1]
    return sorted(childs, key=_parse_key)

def _fecha_hoy_str() -> str:
    return date.today().strftime("%d/%m/%Y")

def _hora_ahora_str() -> str:
    return datetime.now().strftime("%H:%M:%S")

def pdf_output_path(proyecto: str, base_dir: str = ".") -> Path:
    return Path(base_dir) / "presupuestos" / proyecto / "presupuesto_detallado.pdf"

# =========================
# Cálculos de precios
# =========================

def _compute_precio_unitario_por_item(proyecto_dir: Path, df_maestro: pd.DataFrame) -> Dict[str, float]:
    """
    Precio Unitario por Item (hijo) = sum(cantidad * Pres) de su detalle.
    Usa detalle.csv + construction_budget_data.csv.
    """
    detalle_csv = proyecto_dir / "detalle.csv"
    if not detalle_csv.exists():
        return {}
    df_detalle = pd.read_csv(detalle_csv)
    if df_detalle.empty:
        return {}

    df_detalle["item"] = df_detalle["item"].astype(str)
    df_detalle["Codigo"] = df_detalle["Codigo"].astype(str)
    df_maestro = df_maestro.copy()
    df_maestro["Codigo"] = df_maestro["Codigo"].astype(str)

    det_full = df_detalle.merge(
        df_maestro[["Codigo", "Resumen", "Ud", "Pres"]],
        on="Codigo", how="left"
    )
    det_full["cantidad"] = pd.to_numeric(det_full["cantidad"], errors="coerce").fillna(0.0)
    det_full["Pres"] = pd.to_numeric(det_full["Pres"], errors="coerce").fillna(0.0)
    det_full["subtotal_linea"] = det_full["cantidad"] * det_full["Pres"]

    precios = det_full.groupby("item")["subtotal_linea"].sum().to_dict()
    return {str(k): float(v) for k, v in precios.items()}

def _buscar_info_101(df_datos: pd.DataFrame) -> Tuple[str, str]:
    """(Fecha, Moneda) de 1.01; si no hay, del primer 1.*; si no, primera fila."""
    df = df_datos.copy()
    df["Item"] = df["Item"].astype(str)
    cand = df[df["Item"] == "1.01"]
    if cand.empty:
        cand = df[df["Item"].str.startswith("1.")]
    if cand.empty:
        cand = df.iloc[:1]
    if cand.empty:
        return "", ""
    row = cand.iloc[0]
    return str(row.get("Fecha", "") or ""), str(row.get("moneda", "") or "")

# =========================
# Fuentes (Calibri si existe, sino Helvetica)
# =========================

def _register_fonts():
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        candidates_reg = [
            "fonts/Calibri.ttf",
            "Fonts/Calibri.ttf",
            "/usr/share/fonts/truetype/msttcorefonts/Calibri.ttf",
            "/usr/share/fonts/truetype/msttcorefonts/calibri.ttf",
            "C:/Windows/Fonts/calibri.ttf",
        ]
        candidates_bold = [
            "fonts/Calibri Bold.ttf",
            "fonts/Calibri-Bold.ttf",
            "Fonts/Calibri Bold.ttf",
            "/usr/share/fonts/truetype/msttcorefonts/Calibri-Bold.ttf",
            "C:/Windows/Fonts/calibrib.ttf",
        ]
        reg = next((p for p in candidates_reg if Path(p).exists()), None)
        bold = next((p for p in candidates_bold if Path(p).exists()), None)
        if reg and bold:
            pdfmetrics.registerFont(TTFont("Calibri", reg))
            pdfmetrics.registerFont(TTFont("Calibri-Bold", bold))
            return "Calibri", "Calibri-Bold"
    except Exception:
        pass
    return "Helvetica", "Helvetica-Bold"

# =========================
# Generación de PDF
# =========================

def generar_pdf_presupuesto(
    proyecto: str,
    base_dir: str = ".",
    maestro_csv: str = "construction_budget_data.csv",
    nombres_padres: Dict[str, str] | None = None,
    direccion: str = "",
    cliente: str = "",
    salida: str | Path | None = None
) -> Path:
    """Crea el PDF de presupuesto desglosado con formato solicitado."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer
        from reportlab.lib.units import mm
    except Exception as e:
        raise RuntimeError("Falta dependencia 'reportlab'. Agrega 'reportlab>=4' a requirements.txt") from e

    # Fuentes
    FONT_REG, FONT_BOLD = _register_fonts()
    BASE_SIZE = 11
    BOLD_SIZE = 12

    base = Path(base_dir)
    proyecto_dir = base / "presupuestos" / proyecto
    maestro_csv_path = base / maestro_csv
    datos_csv = proyecto_dir / "datos.csv"
    detalle_csv = proyecto_dir / "detalle.csv"

    if not datos_csv.exists() or not detalle_csv.exists():
        raise FileNotFoundError("No se encuentran datos.csv o detalle.csv del proyecto.")

    df_datos = pd.read_csv(datos_csv)
    df_maestro = pd.read_csv(maestro_csv_path)
    df_datos_idx = df_datos.set_index("Item")

    items = sorted(df_datos["Item"].astype(str).tolist(), key=_parse_key)
    parents = _collect_parents(items)
    nombres_padres = nombres_padres or {}
    nombres_def = {p: nombres_padres.get(p, f"Sección {p}") for p in parents}

    fecha_101, moneda_101 = _buscar_info_101(df_datos)
    fec_presup = _fecha_hoy_str()
    hora = _hora_ahora_str()

    precios_item = _compute_precio_unitario_por_item(proyecto_dir, df_maestro)

    # --- Tabla: margen izq (A), 6 columnas de datos, margen der ---
    headers_core = ["Item", "Descripción", "Ud", "Cantidad", "P. Unitario", "Total"]
    headers = [""] + headers_core + [""]  # márgenes vacíos (A y última)

    data_rows: List[List] = []
    total_presupuesto = 0.0

    for parent in parents:
        childs = _children_of_parent(items, parent)
        if not childs:
            continue

        # Datos del primer hijo (para Ud/Cantidad del bloque padre)
        ud = ""
        cant_parent = 0.0
        if childs[0] in df_datos_idx.index:
            ud = str(df_datos_idx.loc[childs[0], "cantidad tipo"])
            cant_parent = float(pd.to_numeric(df_datos_idx.loc[childs[0], "cantidad numero"], errors="coerce") or 0.0)

        total_parent = 0.0

        # Fila título del padre (esta va COMPLETA en negrita; Cantidad formateada)
        data_rows.append(["", parent, nombres_def[parent], ud, _fmt_comma0(cant_parent), "", "", ""])

        # Hijos
        for child in childs:
            if child not in df_datos_idx.index:
                continue
            row = df_datos_idx.loc[child]
            desc = str(row.get("Partida", "") or "")
            ud_child = str(row.get("cantidad tipo", "") or "")
            cant_child = float(pd.to_numeric(row.get("cantidad numero", ""), errors="coerce") or 0.0)
            punit = float(precios_item.get(str(child), 0.0))
            total_child = punit * cant_child
            total_parent += total_child

            data_rows.append([
                "",
                child,
                desc,
                ud_child,
                _fmt_comma0(cant_child),
                _fmt_comma0(punit),
                _fmt_comma0(total_child),
                "",
            ])

        # TOTAL bloque (y línea en blanco posterior)
        data_rows.append(["", "", f"TOTAL {nombres_def[parent]}", "", "", "", _fmt_comma0(total_parent), ""])
        data_rows.append(["", "", "", "", "", "", "", ""])  # línea en blanco tras el total
        total_presupuesto += total_parent

    # TOTAL PRESUPUESTO + línea en blanco final
    data_rows.append(["", "", "TOTAL PRESUPUESTO", "", "", "", _fmt_comma0(total_presupuesto), ""])
    data_rows.append(["", "", "", "", "", "", "", ""])

    # --- Documento y header por página ---
    if salida is None:
        salida = pdf_output_path(proyecto, base_dir)
    else:
        salida = Path(salida)
    salida.parent.mkdir(parents=True, exist_ok=True)

    pagesize = A4
    doc = SimpleDocTemplate(
        str(salida),
        pagesize=pagesize,
        leftMargin=12*mm, rightMargin=12*mm, topMargin=18*mm, bottomMargin=15*mm
    )

    # ColWidth: [margen izq, Item, Desc, Ud, Cant, P.Unit, Total, margen der]
    col_widths = [15*mm, 25*mm, 80*mm, 18*mm, 22*mm, 25*mm, 28*mm, 15*mm]

    # Header “manual” en cada página (con título centrado)
    def _header(canvas, doc_obj):
        canvas.saveState()
        left = doc.leftMargin
        right = doc.pagesize[0] - doc.rightMargin
        y = doc.pagesize[1] - 12*mm

        # Línea 1
        canvas.setFont(FONT_BOLD, 9)
        canvas.drawString(left, y, f"Proyecto: {proyecto}")
        canvas.drawRightString(right, y, f"Hora: {hora}")

        # Línea 2
        y -= 5*mm
        canvas.setFont(FONT_REG, 9)
        canvas.drawString(left, y, f"Dirección: {generar_pdf_presupuesto._direccion if hasattr(generar_pdf_presupuesto,'_direccion') else ''}")
        canvas.drawRightString(right, y, f"Fecha: {fecha_101}")

        # Línea 3
        y -= 5*mm
        canvas.setFont(FONT_REG, 9)
        canvas.drawString(left, y, f"Cliente: {generar_pdf_presupuesto._cliente if hasattr(generar_pdf_presupuesto,'_cliente') else ''}")
        canvas.drawRightString(right, y, f"Moneda ($): {moneda_101}")

        # Línea 4
        y -= 5*mm
        canvas.setFont(FONT_REG, 9)
        canvas.drawString(left, y, f"Fec.Presup.: {fec_presup}")
        canvas.drawRightString(right, y, f"Página Nº: {doc_obj.page}")

        # Título centrado sobre columnas Descripción + Ud
        desc_left_x = left + col_widths[0] + col_widths[1]
        desc_ud_width = col_widths[2] + col_widths[3]
        title_center_x = desc_left_x + desc_ud_width / 2.0

        y -= 2*mm
        canvas.setFont(FONT_BOLD, BOLD_SIZE)
        canvas.drawCentredString(title_center_x, y, "PRESUPUESTO DESGLOSADO")
        canvas.restoreState()

    # Guardar direccion/cliente para header
    generar_pdf_presupuesto._direccion = direccion
    generar_pdf_presupuesto._cliente = cliente

    # Espacio adicional (1–2 filas) tras las fechas/título
    spacer_altura = 10 * mm

    # ---------- Construcción de la tabla ----------
    from reportlab.platypus import Table, TableStyle, Spacer
    from reportlab.lib import colors

    # Línea en blanco ANTES del encabezado:
    blank_row = ["", "", "", "", "", "", "", ""]
    table_data = [blank_row, headers] + data_rows

    # Repetimos la fila en blanco + encabezado en cada página (2 filas)
    tbl = Table(table_data, colWidths=col_widths, repeatRows=2)

    ts = TableStyle([
        # Fuente base (cuerpo: a partir de la fila 2, cols 1..6)
        ("FONT", (1, 2), (6, -1), FONT_REG),
        ("FONTSIZE", (1, 2), (6, -1), BASE_SIZE),

        # Encabezados (fila 1, cols 1..6) -> negrita 12 + ALL BORDERS
        ("FONT", (1, 1), (6, 1), FONT_BOLD),
        ("FONTSIZE", (1, 1), (6, 1), BOLD_SIZE),
        ("ALIGN", (1, 1), (6, 1), "CENTER"),
        ("BOX", (1, 1), (6, 1), 1, colors.black),          # borde externo
        ("INNERGRID", (1, 1), (6, 1), 0.75, colors.black), # bordes internos (ALL BORDERS)

        # Grid del cuerpo (desde la 1ra fila de datos, excluye márgenes)
        ("GRID", (1, 2), (6, -1), 0.25, colors.grey),

        ("ALIGN", (3, 2), (5, -1), "CENTER"),  # Ud, Cant, P.Unit
        ("ALIGN", (6, 2), (6, -1), "RIGHT"),   # Total

        # Márgenes (col 0 y 7) invisibles
        ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
        ("TEXTCOLOR", (7, 0), (7, -1), colors.white),
    ])

    # Estilos especiales: fila padre completa en negrita; totales en negrita
    # (OJO: ahora el primer dato está en r=2 porque r=0 es blank y r=1 es header)
    for r in range(2, len(table_data)):
        item_code = table_data[r][1]
        desc_text = str(table_data[r][2] or "")
        punit = table_data[r][5]
        tot = table_data[r][6]

        # Fila padre: toda la fila en negrita (cols 1..6) -> P.Unit y Total vacíos y hay item_code
        if punit == "" and tot == "" and item_code not in (None, "", " "):
            ts.add("FONT", (1, r), (6, r), FONT_BOLD)
            ts.add("FONTSIZE", (1, r), (6, r), BOLD_SIZE)

        # Totales (TOTAL ..., TOTAL PRESUPUESTO) -> negrita 12
        if desc_text.startswith("TOTAL ") or desc_text == "TOTAL PRESUPUESTO":
            ts.add("FONT", (1, r), (6, r), FONT_BOLD)
            ts.add("FONTSIZE", (1, r), (6, r), BOLD_SIZE)

    tbl.setStyle(ts)

    story = [Spacer(0, spacer_altura), tbl]
    doc.build(story, onFirstPage=_header, onLaterPages=_header)

    return salida

def obtener_o_generar_pdf(
    proyecto: str,
    base_dir: str = ".",
    maestro_csv: str = "construction_budget_data.csv",
    nombres_padres: Dict[str, str] | None = None,
    direccion: str = "",
    cliente: str = "",
    reescribir: bool = False
) -> Path:
    out = pdf_output_path(proyecto, base_dir)
    if out.exists() and not reescribir:
        return out
    return generar_pdf_presupuesto(
        proyecto=proyecto,
        base_dir=base_dir,
        maestro_csv=maestro_csv,
        nombres_padres=nombres_padres,
        direccion=direccion,
        cliente=cliente,
        salida=out
    )

def ver_pdf(
    proyecto: str,
    base_dir: str = ".",
    maestro_csv: str = "construction_budget_data.csv",
    nombres_padres: Dict[str, str] | None = None,
    direccion: str = "",
    cliente: str = "",
    reescribir: bool = False
) -> Path:
    path = obtener_o_generar_pdf(
        proyecto=proyecto,
        base_dir=base_dir,
        maestro_csv=maestro_csv,
        nombres_padres=nombres_padres,
        direccion=direccion,
        cliente=cliente,
        reescribir=reescribir
    )
    _abrir_en_sistema(path)
    return path

# =========================
# Vista Streamlit
# =========================

def render_crear_pdf():
    st.title("🧾 Crear / Ver / Descargar PDF de Presupuesto")

    proyectos = _listar_proyectos(".")
    if not proyectos:
        st.info("No hay proyectos con `datos.csv` y `detalle.csv`.")
        return

    proyecto = st.selectbox("Proyecto", proyectos, index=0)

    colA, colB = st.columns(2)
    direccion = colA.text_input("Dirección", value="")
    cliente = colB.text_input("Cliente", value="")

    # Detectar padres y pedir nombre
    try:
        df_datos = pd.read_csv(Path("presupuestos") / proyecto / "datos.csv")
        items = sorted(df_datos["Item"].astype(str).tolist(), key=_parse_key)
        parents = _collect_parents(items)
    except Exception as e:
        parents, items = [], []
        st.error(f"No se pudieron cargar ítems: {e}")

    st.caption("Nombra las secciones (ítems padre con subcategorías):")
    nombres_padres: Dict[str, str] = {}
    for p in parents:
        nombres_padres[p] = st.text_input(f"Nombre para {p}", value=f"Sección {p}")

    ruta_pdf = pdf_output_path(proyecto)
    st.caption(f"PDF de salida: `{ruta_pdf}`")

    c1, c2, c3 = st.columns(3)

    with c1:
        if st.button("🧾 Generar PDF", use_container_width=True):
            try:
                path = obtener_o_generar_pdf(
                    proyecto=proyecto,
                    nombres_padres=nombres_padres,
                    direccion=direccion,
                    cliente=cliente,
                    reescribir=True
                )
                st.success(f"PDF generado: {path.name}")
            except Exception as e:
                st.error(f"Error al generar PDF: {e}")

    with c2:
        if st.button("👁️ Mostrar PDF", use_container_width=True):
            try:
                ver_pdf(
                    proyecto=proyecto,
                    nombres_padres=nombres_padres,
                    direccion=direccion,
                    cliente=cliente,
                    reescribir=False
                )
                st.success("Intenté abrir el PDF con la app por defecto del sistema.")
            except Exception as e:
                st.error(f"No se pudo abrir el PDF: {e}")

    with c3:
        data_pdf = None
        try:
            path_ready = obtener_o_generar_pdf(
                proyecto=proyecto,
                nombres_padres=nombres_padres,
                direccion=direccion,
                cliente=cliente,
                reescribir=False
            )
            with open(path_ready, "rb") as f:
                data_pdf = f.read()
        except Exception as e:
            st.error(f"No se pudo preparar el PDF: {e}")

        st.download_button(
            "⬇️ Descargar PDF",
            data=data_pdf if data_pdf is not None else b"",
            file_name=f"{proyecto}_presupuesto_detallado.pdf",
            mime="application/pdf",
            disabled=(data_pdf is None),
            use_container_width=True,
        )

    st.caption(f"Estado: {'✅ Existe' if ruta_pdf.exists() else '❌ No existe (se creará al generar/mostrar/descargar)'}")
