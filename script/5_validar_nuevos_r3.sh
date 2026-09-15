#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 3 ]]; then
  echo "Uso: $0 <r3_dir> [out_csv] [detalle_r3_vs_ta_csv]" >&2
  exit 1
fi

R3_DIR="$1"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "${SCRIPT_DIR}")"
ORDEN_FILE="${BASE_DIR}/referencias/Orden_RE_Base.txt"
OUT_CSV="${2:-${BASE_DIR}/nuevos_items_R3.csv}"
DETALLE_CSV="${3:-}"

python3 "${SCRIPT_DIR}/nuevos_r3_vs_orden.py" \
  --r3-dir "$R3_DIR" \
  --orden-file "$ORDEN_FILE" \
  --out-csv "$OUT_CSV" \
  --detalle-csv "$DETALLE_CSV"
# fin
