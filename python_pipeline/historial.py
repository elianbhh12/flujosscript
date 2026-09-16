"""
Historial del inventario: compara cada corrida contra el ultimo estado
guardado, para saber que flujos son nuevos, cuales desaparecieron, y
cuales cambiaron (de subtipo, de configuracion TA, o de transmisiones).

Se guarda por ambiente (qa/pdn/dev no se mezclan):
  historial/<ambiente>/estado_actual.json  -> snapshot mas reciente conocido
  historial/<ambiente>/eventos.csv         -> log append-only de cada cambio

No requiere que el usuario haga nada: se actualiza solo cada vez que
corre el pipeline completo.
"""
from __future__ import annotations

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from . import config

logger = logging.getLogger(__name__)

HISTORIAL_DIR = config.BASE_DIR / "historial"
_CAMPOS_COMPARADOS = ("subtipo", "ta_config", "transmisiones")


def _estado_file(environment: str) -> Path:
    return HISTORIAL_DIR / environment / "estado_actual.json"


def _eventos_file(environment: str) -> Path:
    return HISTORIAL_DIR / environment / "eventos.csv"


def _load_estado(environment: str) -> Dict[str, dict]:
    path = _estado_file(environment)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("No se pudo leer el historial previo (%s); se trata como si no hubiera historial.", exc)
        return {}


def _save_estado(environment: str, estado: Dict[str, dict]) -> None:
    path = _estado_file(environment)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_eventos(environment: str, eventos: List[dict]) -> None:
    if not eventos:
        return
    path = _eventos_file(environment)
    path.parent.mkdir(parents=True, exist_ok=True)
    escribir_encabezado = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter=";", lineterminator="\n")
        if escribir_encabezado:
            writer.writerow(["Fecha", "Flujo", "Tipo de cambio", "Detalle"])
        for ev in eventos:
            writer.writerow([ev["fecha"], ev["flujo"], ev["tipo"], ev["detalle"]])


def actualizar(environment: str, filas_actuales: List[dict], fecha: str = None) -> dict:
    """filas_actuales: lista de dicts con 'file', 'subtipo', 'ta_config',
    'transmisiones' (ver group_report.snapshot_rows). Devuelve un resumen
    {nuevos, eliminados, cambios} (listas de nombres) y deja el historial
    actualizado en disco (estado_actual.json + eventos.csv)."""
    fecha = fecha or datetime.now().strftime(config.DATE_FORMAT)

    estado_anterior = _load_estado(environment)
    estado_nuevo: Dict[str, dict] = {}
    eventos: List[dict] = []
    nuevos: List[str] = []
    cambios: List[str] = []

    for fila in filas_actuales:
        nombre = fila["file"]
        snapshot = {campo: fila.get(campo, "") for campo in _CAMPOS_COMPARADOS}
        previo = estado_anterior.get(nombre)

        snapshot["primera_vez"] = previo.get("primera_vez", fecha) if previo else fecha
        snapshot["ultima_vez"] = fecha
        estado_nuevo[nombre] = snapshot

        if previo is None:
            nuevos.append(nombre)
            eventos.append({
                "fecha": fecha, "flujo": nombre, "tipo": "NUEVO",
                "detalle": f"subtipo={snapshot['subtipo']}",
            })
        else:
            diffs = [
                f"{campo}: '{previo.get(campo, '')}' -> '{snapshot[campo]}'"
                for campo in _CAMPOS_COMPARADOS
                if previo.get(campo, "") != snapshot[campo]
            ]
            if diffs:
                cambios.append(nombre)
                eventos.append({"fecha": fecha, "flujo": nombre, "tipo": "CAMBIO", "detalle": "; ".join(diffs)})

    eliminados = [nombre for nombre in estado_anterior if nombre not in estado_nuevo]
    for nombre in eliminados:
        eventos.append({
            "fecha": fecha, "flujo": nombre, "tipo": "ELIMINADO",
            "detalle": "ya no aparece en la descarga mas reciente",
        })

    _save_estado(environment, estado_nuevo)
    _append_eventos(environment, eventos)

    resumen = {"nuevos": nuevos, "eliminados": eliminados, "cambios": cambios}
    logger.info(
        "Historial actualizado (%s): %s nuevos, %s eliminados, %s con cambios.",
        environment, len(nuevos), len(eliminados), len(cambios),
    )
    return resumen
