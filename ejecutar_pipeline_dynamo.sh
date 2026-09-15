#!/usr/bin/env bash
set -euo pipefail

# Orquestador autocontenido: se ubica y trabaja siempre dentro de esta carpeta,
# para mantener descargas y reportes aislados del resto del repositorio.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="${SCRIPT_DIR}/script"
cd "$SCRIPT_DIR"

# Unicas tablas soportadas por este pipeline.
CONFIG_TABLE_FOLDER="nu0087001-aid-r2-ENV-dynamo-config-control"
TA_TABLE_FOLDER="nu0600001-plataforma-ia-ENV-text-analyzer-table"

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: comando requerido no disponible: $cmd" >&2
    exit 1
  fi
}

read_required_input() {
  local prompt="$1"
  local value=""
  while [[ -z "$value" ]]; do
    read -r -p "$prompt" value
    value="${value// /}"
  done
  printf '%s' "$value"
}

# Autodetecta la carpeta de fecha mas reciente ya descargada (distinta a hoy)
# para usarla como ruta_inventario_actual por defecto, sin preguntar al usuario.
find_default_reference_dir() {
  local table_folder="$1"
  local environment="$2"
  local today="$3"
  local base_dir="${SCRIPT_DIR}/${table_folder}/${environment}"

  [[ -d "$base_dir" ]] || return 0

  find "$base_dir" -maxdepth 1 -mindepth 1 -type d -printf '%f\n' 2>/dev/null \
    | grep -E '^[0-9]{8}$' \
    | grep -v "^${today}$" \
    | sort \
    | tail -n 1
}

require_cmd aws
require_cmd jq
require_cmd python3

if [[ -z "${AWS_ACCESS_KEY_ID:-}" || -z "${AWS_SECRET_ACCESS_KEY:-}" ]]; then
  echo "Error: credenciales AWS no estan configuradas en esta consola." >&2
  echo "Debes exportar AWS_ACCESS_KEY_ID y AWS_SECRET_ACCESS_KEY y AWS_SESSION_TOKEN." >&2
  exit 1
fi

if ! aws sts get-caller-identity >/dev/null 2>&1; then
  echo "Error: las credenciales AWS en consola no son validas o expiraron." >&2
  exit 1
fi

ENVIRONMENT="$(read_required_input "Ambiente (qa|pdn|dev): ")"
if [[ "$ENVIRONMENT" != "qa" && "$ENVIRONMENT" != "pdn" && "$ENVIRONMENT" != "dev" ]]; then
  echo "Error: ambiente invalido '$ENVIRONMENT'." >&2
  exit 1
fi

PARALLEL_SEGMENTS="${PARALLEL_SEGMENTS:-1}"

DATE_STAMP="$(date +%Y%m%d)"
TIME_STAMP="$(date +%H%M%S)"
ENV_LABEL="$(printf '%s' "$ENVIRONMENT" | tr '[:lower:]' '[:upper:]')"
TABLE_LABEL="CONFIG_CONTROL"
RUN_TAG="${TABLE_LABEL}_${ENV_LABEL}_${DATE_STAMP}_${TIME_STAMP}"

REPORT_ROOT="${SCRIPT_DIR}/reportes/${RUN_TAG}"
mkdir -p "$REPORT_ROOT"

COMPARE_OUTPUT_DIR="${REPORT_ROOT}/2_comparar_${TABLE_LABEL}_${ENV_LABEL}"
VERIFY_OUT_TXT="${REPORT_ROOT}/3_verificar_repetidos_${TABLE_LABEL}_${ENV_LABEL}.txt"
GROUP_OUT_CSV="${REPORT_ROOT}/4_agrupar_subtipos_${TABLE_LABEL}_${ENV_LABEL}.csv"
DETALLE_CSV="${COMPARE_OUTPUT_DIR}/detalle_r3_vs_ta.csv"
NUEVOS_R3_CSV="${SCRIPT_DIR}/nuevos_r3_${ENVIRONMENT}_${DATE_STAMP}.csv"

STEP1_STATUS="PENDIENTE"
STEP2_STATUS="NO_APLICA"
STEP3_STATUS="NO_APLICA"
STEP4_STATUS="NO_APLICA"
STEP5_STATUS="NO_APLICA"

CONFIG_REFERENCE_DIR="$(find_default_reference_dir "$CONFIG_TABLE_FOLDER" "$ENVIRONMENT" "$DATE_STAMP")"
TA_REFERENCE_DIR="$(find_default_reference_dir "$TA_TABLE_FOLDER" "$ENVIRONMENT" "$DATE_STAMP")"
if [[ -n "$CONFIG_REFERENCE_DIR" ]]; then
  CONFIG_REFERENCE_DIR="${SCRIPT_DIR}/${CONFIG_TABLE_FOLDER}/${ENVIRONMENT}/${CONFIG_REFERENCE_DIR}"
fi
if [[ -n "$TA_REFERENCE_DIR" ]]; then
  TA_REFERENCE_DIR="${SCRIPT_DIR}/${TA_TABLE_FOLDER}/${ENVIRONMENT}/${TA_REFERENCE_DIR}"
fi

echo "[1/4] Descargando Dynamo para config-control y text-analyzer (${ENVIRONMENT})"
echo "Referencia config-control: ${CONFIG_REFERENCE_DIR:-N/A (primera descarga)}"
echo "Referencia text-analyzer: ${TA_REFERENCE_DIR:-N/A (primera descarga)}"
"${SCRIPTS_DIR}/1_descarga_dynamo.sh" "$ENVIRONMENT" "config-control" "$CONFIG_REFERENCE_DIR"
"${SCRIPTS_DIR}/1_descarga_dynamo.sh" "$ENVIRONMENT" "text-analyzer" "$TA_REFERENCE_DIR"
STEP1_STATUS="OK_CONFIG_CONTROL_Y_TA"

CONFIG_DIR="${SCRIPT_DIR}/${CONFIG_TABLE_FOLDER}/${ENVIRONMENT}/${DATE_STAMP}"
R3_DIR="${CONFIG_DIR}/R3"
TA_DIR="${SCRIPT_DIR}/${TA_TABLE_FOLDER}/${ENVIRONMENT}/${DATE_STAMP}"

if [[ -d "$R3_DIR" ]]; then
  if [[ -d "$TA_DIR" ]]; then
    echo "[2/4] Comparando R3 vs Text Analyzer"
    "${SCRIPTS_DIR}/2_comparar.sh" "$R3_DIR" "$TA_DIR" "$COMPARE_OUTPUT_DIR"
    STEP2_STATUS="OK"

    echo "[3/4] Verificando subtipos repetidos"
    "${SCRIPTS_DIR}/3_verificar_repetidos.sh" "$R3_DIR" "$VERIFY_OUT_TXT"
    STEP3_STATUS="OK"

    echo "[4/4] Agrupando reporte por subtipos"
    "${SCRIPTS_DIR}/4_agrupar.sh" "$R3_DIR" "$DETALLE_CSV" "$GROUP_OUT_CSV"
    STEP4_STATUS="OK"

    echo "[5/5] Validando nuevos R3 vs Orden_RE_Base.txt"
    "${SCRIPTS_DIR}/5_validar_nuevos_r3.sh" "$R3_DIR" "$NUEVOS_R3_CSV" "$DETALLE_CSV"
    STEP5_STATUS="OK"
  else
    STEP2_STATUS="ERROR_TA_NO_DISPONIBLE"
    STEP3_STATUS="OMITIDO"
    STEP4_STATUS="OMITIDO"
    STEP5_STATUS="OMITIDO"
  fi
else
  STEP2_STATUS="NO_APLICA_SIN_R3"
  STEP3_STATUS="NO_APLICA_SIN_R3"
  STEP4_STATUS="NO_APLICA_SIN_R3"
  STEP5_STATUS="NO_APLICA_SIN_R3"
fi

echo
echo "Pipeline finalizado."
echo "Ambiente: ${ENVIRONMENT}"
echo "Carpeta reportes de la corrida: ${REPORT_ROOT}"
echo "Resultado nuevos R3 vs Orden_RE_Base (CSV): ${NUEVOS_R3_CSV}"
# fin
