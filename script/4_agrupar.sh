#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "Uso: $0 <r3_dir> <detalle_csv> <out_csv>" >&2
  exit 1
fi

R3_DIR="$1"
DETALLE_CSV="$2"
OUT_CSV="$3"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${SCRIPT_DIR}/generar_reporte_subtipos_agrupado.py" \
  --path-r3 "$R3_DIR" \
  --detalle-csv "$DETALLE_CSV" \
  --out-csv "$OUT_CSV"
