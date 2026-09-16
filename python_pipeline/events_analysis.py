"""
Identifica, para cada flujo de la tabla events-manager (UDZ), si tiene
solo 'crudos' o tambien 'resultados' (transmisiones).

Un flujo se identifica por la parte del s3_path que queda igual entre
crudos/ y resultados/, por ejemplo:
  crudos:      s3://.../crudos/ns_apoyo_corporativo/MI_FLUJO
  resultados:  s3://.../resultados/ns_apoyo_corporativo/MI_FLUJO
  -> mismo flujo: 'ns_apoyo_corporativo/MI_FLUJO'

Crudos siempre deberia existir; un flujo con SOLO resultados (sin crudos)
es una anomalia que vale la pena revisar.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Dict

from . import common

logger = logging.getLogger(__name__)

HEADER = ["Flujo", "Tiene Crudos", "Tiene Transmisiones", "Observacion", "Archivo Crudos", "Archivo Transmisiones"]


def analyze(events_dir: Path) -> list[dict]:
    flows: Dict[str, dict] = {}

    for json_file, data in common.load_json_files(events_dir):
        s3_path = str(data.get("s3_path") or "")
        tipo = common.classify_udz_tipo(s3_path)
        if not tipo:
            continue

        key = common.udz_flow_key(s3_path, tipo)
        flow = flows.setdefault(key, {
            "flujo": key,
            "tiene_crudos": False,
            "tiene_transmisiones": False,
            "archivo_crudos": "",
            "archivo_transmisiones": "",
        })

        if tipo == "crudos":
            flow["tiene_crudos"] = True
            flow["archivo_crudos"] = json_file.name
        else:
            flow["tiene_transmisiones"] = True
            flow["archivo_transmisiones"] = json_file.name

    for flow in flows.values():
        if flow["tiene_crudos"] and flow["tiene_transmisiones"]:
            flow["observacion"] = "Crudos + Transmisiones"
        elif flow["tiene_crudos"]:
            flow["observacion"] = "Solo Crudos"
        else:
            flow["observacion"] = "ALERTA: solo Transmisiones (falta crudos)"

    return sorted(flows.values(), key=lambda f: f["flujo"])


def resultados_basenames(events_dir: Path) -> set:
    """Nombres (ultimo segmento del flujo, igual al nombre de archivo R3
    sin '.json') que SI tienen transmisiones (resultados). Para cruzar
    contra el reporte agrupado de R3 con una sola columna Si/No, sin
    necesitar el detalle completo de cada flujo UDZ."""
    if not events_dir.is_dir():
        logger.warning("No existe el directorio de events-manager (%s); Transmisiones quedara vacio.", events_dir)
        return set()

    names = set()
    for flow in analyze(events_dir):
        if flow["tiene_transmisiones"]:
            names.add(flow["flujo"].rsplit("/", 1)[-1])
    return names


def generate(events_dir: Path, out_csv: Path) -> dict:
    if not events_dir.is_dir():
        raise FileNotFoundError(f"No existe el directorio de events-manager: {events_dir}")

    flows = analyze(events_dir)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter=";", lineterminator="\n")
        writer.writerow(HEADER)
        for flow in flows:
            writer.writerow([
                flow["flujo"],
                "Si" if flow["tiene_crudos"] else "No",
                "Si" if flow["tiene_transmisiones"] else "No",
                flow["observacion"],
                flow["archivo_crudos"],
                flow["archivo_transmisiones"],
            ])

    solo_crudos = sum(1 for f in flows if f["observacion"] == "Solo Crudos")
    ambos = sum(1 for f in flows if f["observacion"] == "Crudos + Transmisiones")
    alertas = sum(1 for f in flows if f["observacion"].startswith("ALERTA"))

    summary = {
        "total_flujos": len(flows),
        "solo_crudos": solo_crudos,
        "crudos_y_transmisiones": ambos,
        "alertas_sin_crudos": alertas,
        "out_csv": out_csv,
        "flows": flows,
    }
    logger.info(
        "Identificacion UDZ finalizada: %s flujos (%s solo crudos, %s con transmisiones, %s alertas)",
        summary["total_flujos"], solo_crudos, ambos, alertas,
    )
    return summary
