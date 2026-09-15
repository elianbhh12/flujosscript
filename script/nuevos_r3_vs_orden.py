#!/usr/bin/env python3
"""
Compara los JSON de una carpeta R3 descargada contra Orden_RE_Base.txt
(el archivo que define el orden vigente de subtipos) y genera un CSV de
los nuevos, con las mismas columnas que
"reporte_documentos_encontrados_aid(Subtipos de flujos R3).csv", listo
para copiar y pegar al final de ese reporte.
"""
import argparse
import csv
import json
from pathlib import Path
from typing import Dict

import verificar_repetidos

HEADER = [
    "Nombre de los JSONs",
    "Nombre TA Config",
    "Nombre del subtipo",
    "Cantidad de archivos con ese subtipo",
    "Proceso",
    "s3_path",
    "Responsable ciencia",
    "Usuario responsable",
    "Lider responsable",
    "Unidad de Negocio",
    "Area",
    "VP Nivel 2",
    "Observaciones",
    "Dynamo Delete",
]


def leer_orden(orden_file: Path) -> set:
    if not orden_file.exists():
        raise FileNotFoundError(f"No existe el archivo de orden: {orden_file}")
    nombres = set()
    for line in orden_file.read_text(encoding="utf-8").splitlines():
        clean = line.strip()
        if clean:
            nombres.add(clean)
    return nombres


def leer_detalle_r3_vs_ta(detalle_csv: Path) -> Dict[str, Dict[str, str]]:
    """Lee detalle_r3_vs_ta.csv (salida de la etapa 2) por nombre de JSON."""
    out: Dict[str, Dict[str, str]] = {}
    if not detalle_csv or not detalle_csv.exists():
        return out

    with detalle_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter=";")
        header = next(reader, None)
        if not header:
            return out
        for row in reader:
            if len(row) < 6:
                continue
            nombre = row[0].strip()
            if not nombre:
                continue
            out[nombre] = {
                "ta_config": row[1].strip(),
                "subtipo": row[2].strip(),
                "cantidad": row[3].strip(),
                "observaciones": row[4].strip(),
                "s3_path": row[5].strip(),
            }
    return out


def leer_r3_por_archivo(r3_dir: Path) -> Dict[str, Dict[str, str]]:
    """Extrae subtipo/proceso/s3_path directo de cada JSON en R3."""
    out: Dict[str, Dict[str, str]] = {}
    for json_file in sorted(r3_dir.rglob("*.json")):
        raw = json_file.read_text(encoding="utf-8-sig", errors="replace")
        try:
            data = json.loads(raw)
        except Exception:
            data = {}

        subtipo = verificar_repetidos.get_tipo_documento(data) if isinstance(data, dict) else "SIN_TIPODOCUMENTO"
        proceso = verificar_repetidos.get_proceso(data) if isinstance(data, dict) else "SIN_PROCESO"
        s3_path = str(data.get("s3_path") or "").strip() if isinstance(data, dict) else ""

        out[json_file.name] = {
            "subtipo": subtipo,
            "proceso": proceso,
            "s3_path": s3_path,
        }
    return out


def contar_por_subtipo(r3_info: Dict[str, Dict[str, str]]) -> Dict[str, int]:
    conteos: Dict[str, int] = {}
    for info in r3_info.values():
        clave = verificar_repetidos.normalize_text(info["subtipo"])
        conteos[clave] = conteos.get(clave, 0) + 1
    return conteos


def generar(r3_dir: Path, orden_file: Path, out_csv: Path, detalle_csv: Path) -> int:
    orden_actual = leer_orden(orden_file)
    r3_info = leer_r3_por_archivo(r3_dir)
    detalle = leer_detalle_r3_vs_ta(detalle_csv) if detalle_csv else {}
    conteos_subtipo = contar_por_subtipo(r3_info)

    nuevos = sorted(nombre for nombre in r3_info if nombre not in orden_actual)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(HEADER)

        for nombre in nuevos:
            info = r3_info[nombre]
            det = detalle.get(nombre, {})

            subtipo = det.get("subtipo") or info["subtipo"]
            ta_config = det.get("ta_config", "")
            cantidad = det.get("cantidad") or str(conteos_subtipo.get(verificar_repetidos.normalize_text(subtipo), 1))
            proceso = info["proceso"]
            s3_path = det.get("s3_path") or info["s3_path"]
            observaciones = det.get("observaciones", "")

            writer.writerow([
                nombre,
                ta_config,
                subtipo,
                cantidad,
                proceso,
                s3_path,
                "", "", "", "", "", "",
                observaciones,
                "",
            ])

    return len(nuevos)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genera nuevos_items_R3.csv (mismas columnas del reporte base) con los JSON de R3 que no estan en Orden_R3_Base.txt."
    )
    parser.add_argument("--r3-dir", required=True)
    parser.add_argument("--orden-file", required=True)
    parser.add_argument("--out-csv", required=True)
    parser.add_argument("--detalle-csv", default="")
    args = parser.parse_args()

    total_nuevos = generar(
        r3_dir=Path(args.r3_dir),
        orden_file=Path(args.orden_file),
        out_csv=Path(args.out_csv),
        detalle_csv=Path(args.detalle_csv) if args.detalle_csv else None,
    )

    print(f"Nuevos vs Orden_RE_Base.txt: {total_nuevos}")
    print(f"CSV generado: {args.out_csv}")
    if total_nuevos > 0:
        print("Copia estas filas al final de reporte_documentos_encontrados_aid(Subtipos de flujos R3).csv")
        print("Recuerda tambien actualizar Orden_RE_Base.txt agregando estos nombres para mantener el orden.")


if __name__ == "__main__":
    main()
# fin

