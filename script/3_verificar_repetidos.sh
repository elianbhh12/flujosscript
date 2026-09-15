#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "Uso: $0 <r3_dir> <out_txt> [target_list_file]" >&2
  exit 1
fi

R3_DIR="$1"
OUT_TXT="$2"
TARGET_LIST_FILE="${3:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -n "$TARGET_LIST_FILE" ]]; then
  python3 "${SCRIPT_DIR}/verificar_repetidos.py" \
    --path "$R3_DIR" \
    --out-txt "$OUT_TXT" \
    --target-list-file "$TARGET_LIST_FILE"
else
  python3 "${SCRIPT_DIR}/verificar_repetidos.py" \
    --path "$R3_DIR" \
    --out-txt "$OUT_TXT"
fi