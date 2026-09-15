#!/usr/bin/env bash
set -euo pipefail

# Darle permisos al script: chmod +x download_from_dynamo.sh
# Uso desde WSL: ./download_from_dynamo.sh <qa|pdn|dev> <tabla>
#
# Tablas disponibles (unicas soportadas por este pipeline):
#   config-control   -> nu0087001-aid-r2-ENV-dynamo-config-control
#   text-analyzer    -> nu0600001-plataforma-ia-ENV-text-analyzer-table

if [[ $# -lt 2 ]]; then
  echo "Error: debes indicar el ambiente y la tabla." >&2
  echo "Uso: $0 <qa|pdn|dev> <config-control|text-analyzer> [ruta_inventario_actual]" >&2
  exit 1
fi

# Ruta opcional con un inventario ya descargado (misma tabla), para comparar
# por s3_path/cu_name y descargar unicamente lo que aun no exista en local.
REFERENCE_DIR="${3:-}"

ENVIRONMENT="$1"
if [[ "$ENVIRONMENT" != "qa" && "$ENVIRONMENT" != "pdn" && "$ENVIRONMENT" != "dev" ]]; then
  echo "Error: ambiente invalido '$ENVIRONMENT'. Usa 'qa', 'pdn' o 'dev'." >&2
  exit 1
fi

TABLE_KEY="$2"
case "$TABLE_KEY" in
  config-control)
    TABLE_NAME="nu0087001-aid-r2-${ENVIRONMENT}-dynamo-config-control"
    TABLE_FOLDER="nu0087001-aid-r2-ENV-dynamo-config-control"
    ;;
  text-analyzer)
    TABLE_NAME="nu0600001-plataforma-ia-${ENVIRONMENT}-text-analyzer-table"
    TABLE_FOLDER="nu0600001-plataforma-ia-ENV-text-analyzer-table"
    ;;
  *)
    echo "Error: tabla invalida '$TABLE_KEY'." >&2
    echo "Opciones: config-control, text-analyzer" >&2
    exit 1
    ;;
esac

# DynamoDB table ARN (source of records)
TABLE_ARN="arn:aws:dynamodb:us-east-1:084657397209:table/${TABLE_NAME}"

# Initial test mode: download only one specific Dynamo item.
# Change to false to download every item from the table.
ONLY_ONE_FOR_TEST=false
TARGET_S3_PATH="s3://nu0087001-aid-r2-pdn-s3-raw/caso_uno/declaracion_renta"

# Aceleracion opcional: usa scan paralelo de DynamoDB por segmentos.
# Ejemplo: PARALLEL_SEGMENTS=8 ./download_from_dynamo.sh qa config-control
PARALLEL_SEGMENTS="${PARALLEL_SEGMENTS:-1}"
if ! [[ "$PARALLEL_SEGMENTS" =~ ^[0-9]+$ ]] || [[ "$PARALLEL_SEGMENTS" -lt 1 ]]; then
  echo "Error: PARALLEL_SEGMENTS debe ser un entero >= 1." >&2
  exit 1
fi

# Output folder base: ./<tabla_ENV>/<ambiente>/YYYYMMDD
DATE_STAMP="$(date +%Y%m%d)"
OUTPUT_BASE_DIR="./${TABLE_FOLDER}/${ENVIRONMENT}/${DATE_STAMP}"
mkdir -p "${OUTPUT_BASE_DIR}"

if ! command -v aws >/dev/null 2>&1; then
  echo "Error: aws cli no esta instalado o no esta en PATH." >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "Error: jq no esta instalado o no esta en PATH." >&2
  echo "Instala jq y vuelve a ejecutar. Ejemplo en Ubuntu/WSL: sudo apt-get install -y jq" >&2
  exit 1
fi

if [[ -z "${AWS_ACCESS_KEY_ID:-}" || -z "${AWS_SECRET_ACCESS_KEY:-}" ]]; then
  echo "Error: credenciales AWS no configuradas en la terminal." >&2
  echo "Debes exportar AWS_ACCESS_KEY_ID y AWS_SECRET_ACCESS_KEY y AWS_SESSION_TOKEN si aplica)." >&2
  exit 1
fi

if ! aws sts get-caller-identity >/dev/null 2>&1; then
  echo "Error: credenciales AWS invalidas o expiradas. Vuelve a autenticarte y ejecuta de nuevo." >&2
  exit 1
fi

sanitize_filename() {
  local input="$1"
  # Replace slash and any unsafe filename chars.
  input="${input//\//_}"
  input="${input//:/_}"
  input="${input// /_}"
  input="${input//\?/}"
  input="${input//\*/}"
  input="${input//\"/}"
  input="${input//\</}"
  input="${input//\>/}"
  input="${input//\|/}"
  printf '%s' "$input"
}

echo "Tabla DynamoDB: ${TABLE_NAME}"
echo "Ambiente: ${ENVIRONMENT}"
echo "Destino base: ${OUTPUT_BASE_DIR}"
echo "Solo prueba 1 archivo: ${ONLY_ONE_FOR_TEST}"
echo "Segmentos paralelos: ${PARALLEL_SEGMENTS}"
if [[ "$ONLY_ONE_FOR_TEST" == "true" ]]; then
  echo "s3_path objetivo: ${TARGET_S3_PATH}"
fi
if [[ -n "$REFERENCE_DIR" ]]; then
  echo "Ruta de inventario de referencia: ${REFERENCE_DIR}"
fi

echo "Consultando cantidad de items en la tabla (aproximado segun DynamoDB)..."
table_item_count="$(aws dynamodb describe-table \
  --table-name "$TABLE_NAME" \
  --query 'Table.ItemCount' \
  --output text 2>/dev/null || echo "N/D")"
echo "Items en tabla (aprox): ${table_item_count}"

# Construye el set de identificadores ya existentes en la ruta de referencia
# (s3_path para tablas con esa clave, cu_name para text-analyzer).
declare -A existing_keys
reference_keys_count=0
if [[ -n "$REFERENCE_DIR" ]]; then
  if [[ ! -d "$REFERENCE_DIR" ]]; then
    echo "Error: la ruta de inventario de referencia no existe: ${REFERENCE_DIR}" >&2
    exit 1
  fi

  reference_field="s3_path"
  if [[ "$TABLE_KEY" == "text-analyzer" ]]; then
    reference_field="cu_name"
  fi

  while IFS= read -r key_value; do
    [[ -z "$key_value" ]] && continue
    existing_keys["$key_value"]=1
    reference_keys_count=$((reference_keys_count + 1))
  done < <(find "$REFERENCE_DIR" -type f -name '*.json' -print0 2>/dev/null \
    | xargs -0 -r jq -r ".${reference_field}? // empty" 2>/dev/null || true)

  echo "Identificadores unicos en referencia (${reference_field}): ${reference_keys_count}"
fi

NEW_ITEMS_REPORT="${OUTPUT_BASE_DIR}/nuevos_vs_referencia.txt"
if [[ -n "$REFERENCE_DIR" ]]; then
  : > "$NEW_ITEMS_REPORT"
fi

scan_tmp_dir="$(mktemp -d)"
trap 'rm -rf "$scan_tmp_dir"' EXIT

scan_segment_to_file() {
  local segment="$1"
  local total_segments="$2"
  local out_file="$3"
  local page=0
  local last_evaluated_key=''

  : > "$out_file"
  while true; do
    page=$((page + 1))

    if [[ -n "$last_evaluated_key" ]]; then
      response="$(aws dynamodb scan \
        --table-name "$TABLE_NAME" \
        --segment "$segment" \
        --total-segments "$total_segments" \
        --exclusive-start-key "$last_evaluated_key" \
        --output json)"
    else
      response="$(aws dynamodb scan \
        --table-name "$TABLE_NAME" \
        --segment "$segment" \
        --total-segments "$total_segments" \
        --output json)"
    fi

    items_count="$(jq '.Items | length' <<<"$response")"
    jq -c '.Items[]?' <<<"$response" >> "$out_file"
    echo "Segmento ${segment}: pagina ${page} (items ${items_count})"

    last_evaluated_key="$(jq -c '.LastEvaluatedKey // empty' <<<"$response")"
    if [[ -z "$last_evaluated_key" ]]; then
      break
    fi
  done
}

if [[ "$PARALLEL_SEGMENTS" -eq 1 || "$ONLY_ONE_FOR_TEST" == "true" ]]; then
  scan_segment_to_file 0 1 "$scan_tmp_dir/segment_0.ndjson"
else
  pids=()
  for ((segment = 0; segment < PARALLEL_SEGMENTS; segment++)); do
    scan_segment_to_file "$segment" "$PARALLEL_SEGMENTS" "$scan_tmp_dir/segment_${segment}.ndjson" &
    pids+=("$!")
  done
  for pid in "${pids[@]}"; do
    wait "$pid"
  done
fi

# Trackea nombres usados en ESTE escaneo para detectar duplicados
declare -A used_in_scan

total_saved=0
total_existentes_referencia=0
while IFS= read -r item_json; do
  s3_path_value="$(jq -r '.s3_path.S // empty' <<<"$item_json")"

  if [[ "$ONLY_ONE_FOR_TEST" == "true" && "$s3_path_value" != "$TARGET_S3_PATH" ]]; then
    continue
  fi

  # Convertir DynamoDB JSON a JSON normal (unmarshal)
  item_plain="$(jq '
    def unmarshal:
      if type == "object" then
        if   has("S")    then .S
        elif has("N")    then .N | tonumber
        elif has("BOOL") then .BOOL
        elif has("NULL") then null
        elif has("L")    then .L | map(unmarshal)
        elif has("M")    then .M | with_entries(.value |= unmarshal)
        elif has("SS")   then .SS
        elif has("NS")   then .NS | map(tonumber)
        else with_entries(.value |= unmarshal)
        end
      elif type == "array" then map(unmarshal)
      else .
      end;
    with_entries(.value |= unmarshal)
  ' <<<"$item_json")"

  if [[ "$TABLE_KEY" == "text-analyzer" ]]; then
    # Para text-analyzer usar cu_name (primary key) como nombre; s3_path puede no existir
    cu_name_value="$(jq -r '.cu_name.S // empty' <<<"$item_json")"
    safe_name="$(sanitize_filename "${cu_name_value:-item_${total_saved}}")"
    use_case_value="$(jq -r '.. | objects | select(has("use_case")) | .use_case.S // empty' <<<"$item_json" 2>/dev/null | head -1 || true)"
    if [[ -n "$use_case_value" ]]; then
      flow_folder="use_case"
    else
      flow_folder="use_case_TA"
    fi
  elif [[ -z "$s3_path_value" ]]; then
    safe_name="item_${total_saved}"
    flow_folder="R3_Nuevos"
  else
    normalized_s3_path="${s3_path_value%/}"
    last_segment="${normalized_s3_path##*/}"
    safe_name="$(sanitize_filename "$last_segment")"
    if [[ -z "$safe_name" ]]; then
      safe_name="item_${total_saved}"
    fi
    # Separa por flujo: R2 cuando contiene r2-raw/s3-raw, R3 cuando contiene udz.
    if [[ "$s3_path_value" == *"r2-raw"* || "$s3_path_value" == *"s3-raw"* ]]; then
      flow_folder="R2"
    elif [[ "$s3_path_value" == *"udz"* ]]; then
      # Subclasifica R3: topics si algun step tiene TYPE==topic, ms en caso contrario
      has_topic="$(jq -r '
        [ .workflow_definition[]? | .THREADS[]?.STEPS[]?.TYPE // empty ]
        | map(select(. == "topic"))
        | length > 0
      ' <<<"$item_plain" 2>/dev/null || echo 'false')"
      if [[ "$has_topic" == "true" ]]; then
        flow_folder="R3/topics"
      else
        flow_folder="R3/ms"
      fi
    else
      flow_folder="R3_Nuevos"
    fi
  fi

  if [[ -n "$REFERENCE_DIR" ]]; then
    reference_key_value="$s3_path_value"
    if [[ "$TABLE_KEY" == "text-analyzer" ]]; then
      reference_key_value="$(jq -r '.cu_name.S // empty' <<<"$item_json")"
    fi
    if [[ -n "$reference_key_value" && -n "${existing_keys[$reference_key_value]:-}" ]]; then
      total_existentes_referencia=$((total_existentes_referencia + 1))
      continue
    fi
  fi

  output_dir="${OUTPUT_BASE_DIR}/${flow_folder}"
  mkdir -p "${output_dir}"

  file_path="${output_dir}/${safe_name}.json"

  # Si este nombre ya fue usado en ESTA descarga, usar s3_path sanitizado para diferenciarlo
  if [[ -n "${used_in_scan[$safe_name]:-}" ]]; then
    if [[ -n "$s3_path_value" ]]; then
      path_no_proto="${s3_path_value#s3://}"
      path_after_bucket="${path_no_proto#*/}"
      full_path_sanitized="$(sanitize_filename "$path_after_bucket")"
      file_path="${output_dir}/${full_path_sanitized}.json"
    fi
  fi

  jq '.' <<<"$item_plain" > "$file_path"
  used_in_scan[$safe_name]=1
  total_saved=$((total_saved + 1))

  if [[ -n "$REFERENCE_DIR" ]]; then
    echo "${flow_folder};${safe_name};${s3_path_value};${file_path}" >> "$NEW_ITEMS_REPORT"
  fi

  if [[ "$ONLY_ONE_FOR_TEST" == "true" ]]; then
    break
  fi
done < <(cat "$scan_tmp_dir"/segment_*.ndjson)

echo "Proceso finalizado. Total de registros guardados (nuevos): ${total_saved}"
if [[ -n "$REFERENCE_DIR" ]]; then
  echo "Ya existian en referencia (omitidos): ${total_existentes_referencia}"
  echo "Informe de nuevos: ${NEW_ITEMS_REPORT}"
fi
echo "Carpeta de salida base: ${OUTPUT_BASE_DIR}"

# Resumen final por categoria
r2_count=0
r3_topics_count=0
r3_ms_count=0
r3_nuevos_count=0

if [[ -d "${OUTPUT_BASE_DIR}/R2" ]]; then
  r2_count="$(find "${OUTPUT_BASE_DIR}/R2" -type f -name '*.json' | wc -l)"
fi
if [[ -d "${OUTPUT_BASE_DIR}/R3/topics" ]]; then
  r3_topics_count="$(find "${OUTPUT_BASE_DIR}/R3/topics" -type f -name '*.json' | wc -l)"
fi
if [[ -d "${OUTPUT_BASE_DIR}/R3/ms" ]]; then
  r3_ms_count="$(find "${OUTPUT_BASE_DIR}/R3/ms" -type f -name '*.json' | wc -l)"
fi
if [[ -d "${OUTPUT_BASE_DIR}/R3_Nuevos" ]]; then
  r3_nuevos_count="$(find "${OUTPUT_BASE_DIR}/R3_Nuevos" -type f -name '*.json' | wc -l)"
fi

echo
echo "Resumen descarga en ${OUTPUT_BASE_DIR}:"
echo "- R2: ${r2_count}"
echo "- R3/topics: ${r3_topics_count}"
echo "- R3/ms: ${r3_ms_count}"
echo "- R3_Nuevos: ${r3_nuevos_count}"

if [[ "$ONLY_ONE_FOR_TEST" == "true" && "$total_saved" -eq 0 ]]; then
  echo "No se encontro el s3_path objetivo en la tabla." >&2
  exit 2
fi
# fin
