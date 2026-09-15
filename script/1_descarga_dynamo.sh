#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "Uso: $0 <qa|pdn|dev> <config-control|text-analyzer> [ruta_inventario_actual]" >&2
  exit 1
fi

ENVIRONMENT="$1"
TABLE_KEY="$2"
REFERENCE_DIR="${3:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"${SCRIPT_DIR}/download_from_dynamo.sh" "$ENVIRONMENT" "$TABLE_KEY" "$REFERENCE_DIR"