#!/usr/bin/env bash
set -euo pipefail

# Compara use_case (R3 config-control) vs cu_name (text-analyzer)
# y guarda resultados en coincidencia/clasificados y coincidencia/no_clasificados.
#
# Uso:
#   ./compare_r3_vs_text_analyzer.sh [R3_DIR] [TA_DIR] [OUTPUT_DIR]
#
# Defaults:
#   R3_DIR=nu0087001-aid-r2-ENV-dynamo-config-control/pdn/20260624/R3
#   TA_DIR=nu0600001-plataforma-ia-ENV-text-analyzer-table/pdn/20260624
#   OUTPUT_DIR=coincidencia

R3_DIR="${1:-nu0087001-aid-r2-ENV-dynamo-config-control/pdn/20260624/R3}"
TA_DIR="${2:-nu0600001-plataforma-ia-ENV-text-analyzer-table/pdn/20260624}"
OUTPUT_DIR="${3:-coincidencia}"

CLASSIFIED_DIR="${OUTPUT_DIR}/clasificados"
UNCLASSIFIED_DIR="${OUTPUT_DIR}/no_clasificados"

CLASSIFIED_FILE="${CLASSIFIED_DIR}/ta_cu_name.txt"
UNCLASSIFIED_FILE="${UNCLASSIFIED_DIR}/r3_sin_ta.txt"
DETAIL_FILE="${OUTPUT_DIR}/detalle_r3_vs_ta.csv"

TMP_MATCHED_RAW="$(mktemp)"
TMP_CLASSIFIED_WITH_SHARE="$(mktemp)"
TMP_UNCLASSIFIED_RAW="$(mktemp)"
TMP_DETAIL_RAW="$(mktemp)"
trap 'rm -f "$TMP_MATCHED_RAW" "$TMP_CLASSIFIED_WITH_SHARE" "$TMP_UNCLASSIFIED_RAW" "$TMP_DETAIL_RAW"' EXIT

if ! command -v jq >/dev/null 2>&1; then
  echo "Error: jq no esta instalado o no esta en PATH." >&2
  exit 1
fi

if [[ ! -d "$R3_DIR" ]]; then
  echo "Error: no existe el directorio R3: $R3_DIR" >&2
  exit 1
fi

if [[ ! -d "$TA_DIR" ]]; then
  echo "Error: no existe el directorio Text Analyzer: $TA_DIR" >&2
  exit 1
fi

sanitize_csv_field() {
  local value="${1:-}"
  value="${value//$'\r'/ }"
  value="${value//$'\n'/ }"
  value="${value//;/,}"
  echo "$value"
}

mkdir -p "$CLASSIFIED_DIR" "$UNCLASSIFIED_DIR"
: > "$CLASSIFIED_FILE"
: > "$UNCLASSIFIED_FILE"
: > "$DETAIL_FILE"
: > "$TMP_MATCHED_RAW"
: > "$TMP_CLASSIFIED_WITH_SHARE"
: > "$TMP_UNCLASSIFIED_RAW"
: > "$TMP_DETAIL_RAW"
echo "Nombre de los JSONs;Nombre TA config (cu_name);Nombre del subtipo;Comparte TA;Ruta JSON R3" >> "$CLASSIFIED_FILE"
echo "Nombre de los JSONs;Nombre TA config;Nombre del subtipo;Cantidad de archivos con ese subtipo;Observaciones;Ruta JSON R3" >> "$DETAIL_FILE"

declare -A ta_by_cuname
declare -A manual_observations

manual_observations["BIZAGI_COBRANZASCALIDADEMITIDADOCS.json"]="NO usa TA en su configuracion (USA TEXT EXTRACTOR)"
manual_observations["LANDING_ZONE_ONPREMISSE_GENERACIONCOMENTARIOSLIQUIDEZ_000174.json"]="Tiene una config mal"
manual_observations["MASIVIAN_FRAUDESCALIDADEMITIDADOCS.json"]="NO usa TA en su configuracion (USA TEXT EXTRACTOR)"
manual_observations["OUTLOOK_REQLEGCALIDADEMITIDADOCS.json"]="NO usa TA en su configuracion (USA TEXT EXTRACTOR)"
manual_observations["OUTLOOK_SECRELACIONALCALIDADEMITIDADOCS.json"]="NO usa TA en su configuracion (USA TEXT EXTRACTOR)"
manual_observations["SAP_CRM_SUFICALIDADEMITIDADOCS.json"]="NO usa TA en su configuracion (USA TEXT EXTRACTOR)"
manual_observations["aid_test_000079.json"]="Caso de prueba, usa TA con la config en el mismo archivo"
manual_observations["EVOLUCIONDIGITAL_CARTANOTIFICACION.json"]="ta_carta_de_notificacion"
manual_observations["EVOLUCIONDIGITAL_F1535ANEXOCONOCIMIENTO.json"]="ta_f1535anexoconocimiento"
manual_observations["TEAMS_OFFSHORECAMARACOMERCIO.json"]="ta_camara_comercio_offshore"

total_ta_files=0
total_ta_with_cuname=0

# Cargar cu_name de text-analyzer (busqueda recursiva)
while IFS= read -r -d '' ta_file; do
  total_ta_files=$((total_ta_files + 1))
  cu_name="$(jq -r '.cu_name // empty' "$ta_file")"
  if [[ -n "$cu_name" ]]; then
    ta_by_cuname["$cu_name"]="$ta_file"
    total_ta_with_cuname=$((total_ta_with_cuname + 1))
  fi
done < <(find "$TA_DIR" -type f -name '*.json' -print0)

if [[ ${#ta_by_cuname[@]} -eq 0 ]]; then
  echo "Advertencia: no se encontraron cu_name en $TA_DIR" >&2
fi

total_r3=0
matched=0
unmatched=0
missing_use_case=0

while IFS= read -r -d '' r3_file; do
  total_r3=$((total_r3 + 1))

  use_case="$(jq -r '
    [.. | objects | .STEP_VARIABLES? | .use_case? // empty]
    | map(select(. != ""))
    | .[0] // ""
  ' "$r3_file")"

  subtipo="$(jq -r '
    [.. | objects | .workflow_variables? | .tipoDocumento? // empty]
    | map(select(. != ""))
    | .[0] // "REVISAR_MANUAL"
  ' "$r3_file")"

  r3_s3_path="$(jq -r '.s3_path // ""' "$r3_file")"

  r3_name="$(basename "$r3_file")"

  r3_name="$(sanitize_csv_field "$r3_name")"
  use_case="$(sanitize_csv_field "$use_case")"
  subtipo="$(sanitize_csv_field "$subtipo")"
  r3_s3_path="$(sanitize_csv_field "$r3_s3_path")"

  if [[ -z "$use_case" ]]; then
    missing_use_case=$((missing_use_case + 1))
    unmatched=$((unmatched + 1))
    observation="${manual_observations[$r3_name]:-Validar Manualmente}"
    observation="$(sanitize_csv_field "$observation")"
    echo "$r3_name;SIN_USE_CASE;$subtipo;$observation;$r3_s3_path" >> "$TMP_UNCLASSIFIED_RAW"
    echo "$r3_name;SIN_USE_CASE;$subtipo;$observation;$r3_s3_path" >> "$TMP_DETAIL_RAW"
    continue
  fi

  if [[ -n "${ta_by_cuname[$use_case]:-}" ]]; then
    matched=$((matched + 1))
    echo "$r3_name;$use_case;$subtipo;$r3_s3_path" >> "$TMP_MATCHED_RAW"
    matched_observation=""
    if [[ "$subtipo" == "REVISAR_MANUAL" ]]; then
      matched_observation="Validar Manualmente"
    fi
    matched_observation="$(sanitize_csv_field "$matched_observation")"
    echo "$r3_name;$use_case;$subtipo;$matched_observation;$r3_s3_path" >> "$TMP_DETAIL_RAW"
  else
    unmatched=$((unmatched + 1))
    observation="${manual_observations[$r3_name]:-Validar Manualmente}"
    observation="$(sanitize_csv_field "$observation")"
    echo "$r3_name;$use_case;$subtipo;$observation;$r3_s3_path" >> "$TMP_UNCLASSIFIED_RAW"
    echo "$r3_name;$use_case;$subtipo;$observation;$r3_s3_path" >> "$TMP_DETAIL_RAW"
  fi
done < <(find "$R3_DIR" -type f -name '*.json' -print0)

# Agrega columna "Comparte TA" cuando un cu_name esta asociado a mas de un json R3.
awk -F';' '
  NR==FNR {
    cu=$2
    r3=$1
    count[cu]++
    if (group[cu] == "") {
      group[cu] = r3
    } else {
      group[cu] = group[cu] ", " r3
    }
    next
  }
  {
    r3=$1
    cu=$2
    subtipo=$3
    r3_path=$4
    comparte=""
    if (count[cu] > 1) {
      others=group[cu]
      gsub(r3 ", ", "", others)
      gsub(", " r3, "", others)
      if (others == r3) {
        others=""
      }
      comparte="Si: " others
    }
    print r3 ";" cu ";" subtipo ";" comparte ";" r3_path
  }
' "$TMP_MATCHED_RAW" "$TMP_MATCHED_RAW" > "$TMP_CLASSIFIED_WITH_SHARE"

sort -t';' -k1,1 "$TMP_CLASSIFIED_WITH_SHARE" >> "$CLASSIFIED_FILE"
sort -t';' -k1,1 "$TMP_UNCLASSIFIED_RAW" > "$UNCLASSIFIED_FILE"

# Reporte detalle (todos los R3): cantidad por subtipo y observaciones.
awk -F';' '
  NR==FNR {
    subtipo=$3
    subtype_count[subtipo]++
    next
  }
  {
    r3=$1
    cu=$2
    subtipo=$3
    observation=$4
    r3_path=$5
    print r3 ";" cu ";" subtipo ";" subtype_count[subtipo] ";" observation ";" r3_path
  }
' "$TMP_DETAIL_RAW" "$TMP_DETAIL_RAW" | sort -t';' -k1,1 >> "$DETAIL_FILE"

echo "Comparacion finalizada"
echo "R3 analizados: $total_r3"
echo "TA analizados (json): $total_ta_files"
echo "TA con cu_name: $total_ta_with_cuname"
echo "Coincidencias: $matched"
echo "R3 sin config TA: $unmatched"
echo "R3 sin use_case: $missing_use_case"
echo "Clasificados (Nombre JSON;TA config;Subtipo;Comparte TA;Ruta JSON R3): $CLASSIFIED_FILE"
echo "Sin TA (Nombre JSON;TA config faltante/SIN_USE_CASE;Subtipo;Observacion;Ruta JSON R3): $UNCLASSIFIED_FILE"
echo "Detalle: $DETAIL_FILE"
# fin
