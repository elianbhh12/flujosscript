#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "Uso: $0 <r3_dir> <ta_dir> <output_dir>" >&2
  exit 1
fi

R3_DIR="$1"
TA_DIR="$2"
OUTPUT_DIR="$3"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"${SCRIPT_DIR}/compare_r3_vs_text_analyzer.sh" "$R3_DIR" "$TA_DIR" "$OUTPUT_DIR"
