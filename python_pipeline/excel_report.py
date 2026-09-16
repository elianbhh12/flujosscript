"""
Genera un unico .xlsx a partir de los reportes de una corrida, para
entregar al usuario final algo mas presentable que varios CSV sueltos
separados por ';' (que ademas se prestan a confusion segun la
configuracion regional de Excel).

Hojas generadas (en este orden, la mas importante primero):
  - Resumen: metadatos de la corrida (ambiente, fecha, tablas, totales).
  - Reporte Agrupado: la hoja principal, salida del paso 4, con los
    subtipos agrupados visualmente (celdas combinadas), colores para
    Transmisiones y alertas resaltadas en Observaciones.
  - Historial (vs corrida anterior): que flujos son nuevos, cuales
    desaparecieron y cuales cambiaron desde la ultima vez que corrio el
    pipeline (solo aparece si hubo algun cambio).
  - Comparacion - Clasificados / Revisar: salida del paso 2.
  - Subtipos Repetidos: salida del paso 3, ya estructurada.
  - Nuevos vs Baseline: salida del paso 5 (si corrio).
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_HEADER_FILL = "FDDA24"       # amarillo (ACCENT)
_HEADER_FONT_COLOR = "000000"  # negro (INK)
_BAND_FILL = "FAFAF9"          # gris muy sutil, banda alterna
_OK_FILL = "E2EFDA"           # verde claro (Transmisiones: Si)
_ALERT_FILL = "FCE4E4"        # rojo claro (alertas)
_ALERT_FONT_COLOR = "9C0006"  # rojo oscuro
_TOTAL_FILL = "D9D9D9"        # gris, fila de totales
_MAX_COL_WIDTH = 60
_BORDER_COLOR = "9C9A98"      # gris oscuro, bordes finos


def _get_openpyxl():
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter
    except ImportError as exc:
        raise RuntimeError(
            "Falta openpyxl. Instala dependencias con: pip install -r requirements.txt"
        ) from exc
    return Workbook, Alignment, Border, Font, PatternFill, Side, get_column_letter


def _thin_border():
    _, _, Border, _, _, Side, _ = _get_openpyxl()
    side = Side(style="thin", color=_BORDER_COLOR)
    return Border(left=side, right=side, top=side, bottom=side)


def _autofit_columns(ws, n_cols: int, n_rows: int) -> None:
    _, _, _, _, _, _, get_column_letter = _get_openpyxl()
    for col in range(1, n_cols + 1):
        max_len = 0
        for row in range(1, n_rows + 1):
            value = ws.cell(row=row, column=col).value
            if value is not None:
                max_len = max(max_len, len(str(value)))
        ws.column_dimensions[get_column_letter(col)].width = min(max(max_len + 2, 10), _MAX_COL_WIDTH)


def _style_header(ws, n_cols: int) -> None:
    _, Alignment, _, Font, PatternFill, _, get_column_letter = _get_openpyxl()
    header_font = Font(bold=True, color=_HEADER_FONT_COLOR)
    header_fill = PatternFill(start_color=_HEADER_FILL, end_color=_HEADER_FILL, fill_type="solid")
    for col in range(1, n_cols + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center")
    ws.freeze_panes = "A2"


def _style_sheet(ws, n_cols: int, n_rows: int) -> None:
    """Estilo generico para hojas simples: encabezado, bordes, banda
    alterna fila-si/fila-no, filtro y autofit."""
    _, _, _, _, PatternFill, _, get_column_letter = _get_openpyxl()
    _style_header(ws, n_cols)

    border = _thin_border()
    band_fill = PatternFill(start_color=_BAND_FILL, end_color=_BAND_FILL, fill_type="solid")
    for row in range(1, n_rows + 1):
        for col in range(1, n_cols + 1):
            cell = ws.cell(row=row, column=col)
            cell.border = border
            if row > 1 and row % 2 == 0:
                cell.fill = band_fill

    if n_rows > 0:
        ws.auto_filter.ref = f"A1:{get_column_letter(n_cols)}{n_rows}"
    _autofit_columns(ws, n_cols, n_rows)


def _write_rows_sheet(wb, title: str, header: list[str], rows: list[list]) -> None:
    ws = wb.create_sheet(title=title[:31])  # Excel limita el nombre de hoja a 31 caracteres
    ws.append(header)
    for row in rows:
        ws.append(row)
    _style_sheet(ws, len(header), len(rows) + 1)
    return ws


def _write_csv_sheet(wb, title: str, csv_path: Path, delimiter: str = ";") -> None:
    if not csv_path.exists():
        return
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh, delimiter=delimiter))
    if not rows:
        return
    header, body = rows[0], rows[1:]
    _write_rows_sheet(wb, title, header, body)


def _repeated_to_rows(repeated: list[dict]) -> list[list]:
    rows = []
    for group in repeated:
        first = True
        for archivo_info in group["archivos"]:
            rows.append([
                group["subtipo"] if first else "",
                len(group["archivos"]) if first else "",
                archivo_info["archivo"],
                archivo_info["proceso"],
            ])
            first = False
    return rows


def _write_grouped_report_sheet(wb, csv_path: Path):
    """Hoja principal: reporte agrupado por subtipo. A diferencia de las
    demas, aqui SI vale la pena invertir en presentacion porque es la que
    usa el usuario final para revisar todo de un vistazo:
      - El subtipo y la cantidad quedan en una sola celda combinada por
        grupo (en vez de una celda vacia por cada fila repetida).
      - Bandas de color alternas por grupo, para separar visualmente
        donde empieza y termina cada subtipo.
      - Transmisiones en verde cuando es 'Si'.
      - Observaciones con alertas ('ALERTA', 'Validar Manualmente') en
        rojo y negrita.
      - La fila TOTAL_R3 queda resaltada al final.
    """
    if not csv_path.exists():
        return None

    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        raw_rows = list(csv.reader(fh, delimiter=";"))
    if not raw_rows:
        return None

    header = raw_rows[0]
    body = [r for r in raw_rows[1:] if r and r[0] != "TOTAL_R3"]
    total_row = next((r for r in raw_rows[1:] if r and r[0] == "TOTAL_R3"), None)

    idx_subtipo = header.index("Nombre del subtipo")
    idx_cantidad = header.index("Cantidad de archivos con ese subtipo")
    idx_observ = header.index("Observaciones") if "Observaciones" in header else None
    idx_transm = header.index("Transmisiones") if "Transmisiones" in header else None

    Workbook, Alignment, Border, Font, PatternFill, Side, get_column_letter = _get_openpyxl()
    ws = wb.create_sheet(title="Reporte Agrupado")
    ws.append(header)
    n_cols = len(header)

    band_fill = PatternFill(start_color=_BAND_FILL, end_color=_BAND_FILL, fill_type="solid")
    ok_fill = PatternFill(start_color=_OK_FILL, end_color=_OK_FILL, fill_type="solid")
    alert_fill = PatternFill(start_color=_ALERT_FILL, end_color=_ALERT_FILL, fill_type="solid")
    alert_font = Font(color=_ALERT_FONT_COLOR, bold=True)
    border = _thin_border()
    center = Alignment(horizontal="center", vertical="center")

    row_idx = 2
    band_on = False
    i = 0
    while i < len(body):
        cantidad_str = (body[i][idx_cantidad] or "").strip()
        span = int(cantidad_str) if cantidad_str.isdigit() else 1

        for offset in range(span):
            data_row = body[i + offset] if i + offset < len(body) else [""] * n_cols
            for col in range(n_cols):
                value = data_row[col] if col < len(data_row) else ""
                cell = ws.cell(row=row_idx + offset, column=col + 1, value=value)
                cell.border = border
                if band_on:
                    cell.fill = band_fill

            if idx_transm is not None:
                transm_cell = ws.cell(row=row_idx + offset, column=idx_transm + 1)
                transm_cell.alignment = center
                if str(transm_cell.value).strip().lower() == "si":
                    transm_cell.fill = ok_fill

            if idx_observ is not None:
                obs_cell = ws.cell(row=row_idx + offset, column=idx_observ + 1)
                obs_text = str(obs_cell.value or "")
                if "ALERTA" in obs_text.upper():
                    obs_cell.fill = alert_fill
                    obs_cell.font = alert_font

        if span > 1:
            ws.merge_cells(start_row=row_idx, start_column=idx_subtipo + 1, end_row=row_idx + span - 1, end_column=idx_subtipo + 1)
            ws.merge_cells(start_row=row_idx, start_column=idx_cantidad + 1, end_row=row_idx + span - 1, end_column=idx_cantidad + 1)
            ws.cell(row=row_idx, column=idx_subtipo + 1).alignment = Alignment(vertical="center", wrap_text=True)
            ws.cell(row=row_idx, column=idx_cantidad + 1).alignment = center
        else:
            ws.cell(row=row_idx, column=idx_cantidad + 1).alignment = center

        row_idx += span
        band_on = not band_on
        i += span

    if total_row:
        total_fill = PatternFill(start_color=_TOTAL_FILL, end_color=_TOTAL_FILL, fill_type="solid")
        for col in range(n_cols):
            value = total_row[col] if col < len(total_row) else ""
            cell = ws.cell(row=row_idx, column=col + 1, value=value)
            cell.font = Font(bold=True)
            cell.fill = total_fill
            cell.border = border

    _style_header(ws, n_cols)
    ws.auto_filter.ref = f"A1:{get_column_letter(n_cols)}{row_idx - 1}"
    _autofit_columns(ws, n_cols, row_idx)
    return ws


def _historial_to_rows(historial_resumen: dict) -> list[list]:
    rows = []
    for flujo in historial_resumen.get("nuevos", []):
        rows.append(["NUEVO", flujo])
    for flujo in historial_resumen.get("cambios", []):
        rows.append(["CAMBIO", flujo])
    for flujo in historial_resumen.get("eliminados", []):
        rows.append(["ELIMINADO", flujo])
    return rows


def build_workbook(
    out_path: Path,
    *,
    resumen: dict,
    classified_file: Optional[Path] = None,
    unclassified_file: Optional[Path] = None,
    repeated: Optional[list[dict]] = None,
    group_csv: Optional[Path] = None,
    nuevos_csv: Optional[Path] = None,
    historial_resumen: Optional[dict] = None,
) -> Path:
    Workbook, *_rest = _get_openpyxl()
    wb = Workbook()
    wb.remove(wb.active)

    resumen_rows = [[str(k), "" if v is None else str(v)] for k, v in resumen.items()]
    _write_rows_sheet(wb, "Resumen", ["Campo", "Valor"], resumen_rows)

    if group_csv:
        _write_grouped_report_sheet(wb, group_csv)
    if historial_resumen and any(historial_resumen.values()):
        _write_rows_sheet(wb, "Historial (vs corrida anterior)", ["Tipo de cambio", "Flujo"], _historial_to_rows(historial_resumen))
    if classified_file:
        _write_csv_sheet(wb, "Comparacion - Clasificados", classified_file)
    if unclassified_file:
        _write_csv_sheet(wb, "Comparacion - Revisar", unclassified_file)
    if repeated:
        _write_rows_sheet(
            wb, "Subtipos Repetidos",
            ["Subtipo", "Cantidad de archivos", "Archivo", "Proceso"],
            _repeated_to_rows(repeated),
        )
    if nuevos_csv and nuevos_csv.exists():
        _write_csv_sheet(wb, "Nuevos vs Baseline", nuevos_csv)

    wb.active = 0  # abrir siempre en Resumen
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    logger.info("Excel generado: %s", out_path)
    return out_path
