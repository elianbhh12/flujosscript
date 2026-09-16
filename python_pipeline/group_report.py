"""
Paso 4: reporte agrupado de subtipos, una fila por JSON. El nombre del
subtipo y la cantidad solo se muestran en la primera fila de cada grupo
(igual formato que generar_reporte_subtipos_agrupado.py). El orden fijo
de archivos ahora viene de referencias/pipeline_config.json en vez de
estar escrito dentro del codigo.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import common, config

logger = logging.getLogger(__name__)

_ORDER_INDEX = {name: i for i, name in enumerate(config.ORDEN_REPORTE_SUBTIPOS)}


def _order_key(file_name: str) -> Tuple[int, int, str]:
    if file_name in _ORDER_INDEX:
        return (0, _ORDER_INDEX[file_name], file_name)
    return (1, len(config.ORDEN_REPORTE_SUBTIPOS), common.normalize_text(file_name))


def _load_detalle(detalle_csv: Path) -> List[dict]:
    rows = []
    with detalle_csv.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        for row in reader:
            if (row.get("Nombre de los JSONs") or "").strip():
                rows.append(row)
    return rows


def _load_r3_info(r3_dir: Path) -> Dict[str, dict]:
    info = {}
    for json_file, data in common.load_json_files(r3_dir):
        info[json_file.name] = {
            "subtipo": common.get_tipo_documento(data),
            "proceso": common.get_proceso(data),
            "s3_path": str(data.get("s3_path") or ""),
        }
    return info


def _build_rows(r3_dir: Path, detalle_csv: Path, resultados_basenames: Optional[set]) -> Tuple[List[dict], Dict[str, dict]]:
    detalle_rows = _load_detalle(detalle_csv)
    r3_info = _load_r3_info(r3_dir)

    grupos: Dict[str, dict] = {}
    for detalle_row in detalle_rows:
        file_name = (detalle_row.get("Nombre de los JSONs") or "").strip()
        info = r3_info.get(file_name, {})

        subtipo = (detalle_row.get("Nombre del subtipo") or "").strip() or info.get("subtipo") or "REVISAR_MANUAL"
        norm = common.normalize_text(subtipo) or "revisar manual"

        grupo = grupos.setdefault(norm, {"subtipo": subtipo, "rows": []})
        grupo["rows"].append({
            "file": file_name,
            "ta_config": (detalle_row.get("Nombre TA config") or "").strip(),
            "proceso": info.get("proceso", ""),
            "s3_path": (detalle_row.get("Ruta JSON R3") or "").strip() or info.get("s3_path", ""),
            "observacion": (detalle_row.get("Observaciones") or "").strip(),
            "order_key": _order_key(file_name),
        })

    filas: List[dict] = []
    for norm, grupo in grupos.items():
        for row in grupo["rows"]:
            row = dict(row)
            row["subtipo_grupo"] = grupo["subtipo"]
            row["count_grupo"] = len(grupo["rows"])
            row["norm_grupo"] = norm
            if resultados_basenames is not None:
                row["transmisiones"] = "Si" if Path(row["file"]).stem in resultados_basenames else "No"
            filas.append(row)

    filas.sort(key=lambda r: (r["order_key"], common.normalize_text(r["file"])))
    return filas, grupos


def snapshot_rows(r3_dir: Path, detalle_csv: Path, resultados_basenames: Optional[set] = None) -> List[dict]:
    """Una fila por flujo con su estado actual (subtipo, TA, transmisiones),
    SIN el formato 'agrupado visual' (sin blanquear filas repetidas). Lo
    usa historial.py para comparar una corrida contra la anterior."""
    filas, _grupos = _build_rows(r3_dir, detalle_csv, resultados_basenames)
    return [
        {
            "file": row["file"],
            "subtipo": row["subtipo_grupo"],
            "ta_config": row["ta_config"],
            "transmisiones": row.get("transmisiones", ""),
        }
        for row in filas
    ]


def generate(
    r3_dir: Path, detalle_csv: Path, out_csv: Path,
    resultados_basenames: Optional[set] = None,
) -> Tuple[int, int, int]:
    """resultados_basenames: si se pasa (set de nombres de flujo, del
    cruce con events-manager), agrega una columna 'Transmisiones' (Si/No)
    por archivo. Si se omite, el reporte queda igual que antes."""
    filas, grupos = _build_rows(r3_dir, detalle_csv, resultados_basenames)
    incluir_transmisiones = resultados_basenames is not None

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    total_r3 = 0
    grupos_impresos = set()
    with out_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter=";", lineterminator="\n")
        header = ["Nombre de los JSONs", "Nombre TA config", "Nombre del subtipo",
                  "Cantidad de archivos con ese subtipo", "Proceso", "Ruta JSON R3", "Observaciones"]
        if incluir_transmisiones:
            header.append("Transmisiones")
        writer.writerow(header)

        for row in filas:
            mostrar = row["norm_grupo"] not in grupos_impresos
            fila = [
                row["file"], row["ta_config"],
                row["subtipo_grupo"] if mostrar else "",
                row["count_grupo"] if mostrar else "",
                row["proceso"], row["s3_path"], row["observacion"],
            ]
            if incluir_transmisiones:
                fila.append(row["transmisiones"])
            writer.writerow(fila)
            grupos_impresos.add(row["norm_grupo"])
            total_r3 += 1

        writer.writerow([])
        total_row = ["TOTAL_R3", "", "", total_r3, "", "", ""]
        if incluir_transmisiones:
            total_row.append("")
        writer.writerow(total_row)

    suma_grupos = sum(len(g["rows"]) for g in grupos.values())
    if total_r3 != suma_grupos:
        raise RuntimeError("La suma de grupos no coincide con el total de R3")

    logger.info("Reporte agrupado generado: %s (R3=%s, subtipos=%s)", out_csv, total_r3, len(grupos))
    return total_r3, suma_grupos, len(grupos)
