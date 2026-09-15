import argparse
import json
import re
import sys
import unicodedata
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Ruta de archivos R3
DEFAULT_PATH = "/home/danramgo97/AID_flujos/nu0087001-aid-r2-ENV-dynamo-config-control/pdn/20260624/R3"

DEFAULT_OUT_TXT = "subtipos_repetidos_r3_con_procesos.txt"

# Si no se pasa una lista, se analizan todos los JSON encontrados en --path.
TARGET_JSON_FILES_V3: List[str] = []


def load_target_list_from_file(file_path: str) -> List[str]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"No existe el archivo de lista: {path}")

    lines = path.read_text(encoding="utf-8").splitlines()
    target_list: List[str] = []
    for line in lines:
        clean_line = line.strip()
        if not clean_line or clean_line.startswith("#"):
            continue
        target_list.append(clean_line)

    return target_list


def select_r3_files(
    all_json_files: List[Tuple[str, str]],
    target_files: Optional[List[str]] = None,
) -> Tuple[List[Tuple[str, str]], List[str], int]:
    if target_files:
        filtered_files, missing_files = filter_target_files(
            all_json_files=all_json_files,
            target_files=target_files,
        )
        return filtered_files, missing_files, len(target_files)

    return all_json_files, [], len(all_json_files)


def normalize_text(value: Any) -> str:
    value = str(value or "")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def basename(path: str) -> str:
    return path.replace("\\", "/").split("/")[-1]


def normalize_file_name(path: str) -> str:
    return basename(path).strip().lower()


def split_zip_path(path_str: str) -> Tuple[Optional[str], Optional[str]]:
    clean_path = path_str.strip().strip('"')
    lower_path = clean_path.lower()
    zip_index = lower_path.find(".zip")

    if zip_index == -1:
        return None, None

    zip_path = clean_path[: zip_index + 4]
    inner_prefix = clean_path[zip_index + 4 :].lstrip("\\/").replace("\\", "/")

    return zip_path, inner_prefix


def decode_bytes(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            pass

    return content.decode("utf-8", errors="replace")


def iter_json_files(path_str: str) -> List[Tuple[str, str]]:
    zip_path, inner_prefix = split_zip_path(path_str)
    results: List[Tuple[str, str]] = []

    if zip_path:
        zip_file = Path(zip_path)

        if not zip_file.exists():
            raise FileNotFoundError(f"No existe el ZIP: {zip_file}")

        with zipfile.ZipFile(zip_file, "r") as zf:
            for member in zf.namelist():
                member_normalized = member.replace("\\", "/")

                if inner_prefix:
                    wanted_prefix = inner_prefix.rstrip("/") + "/"

                    if not member_normalized.startswith(wanted_prefix):
                        continue

                if not member_normalized.lower().endswith(".json"):
                    continue

                with zf.open(member) as f:
                    results.append((member_normalized, decode_bytes(f.read())))

        return results

    path = Path(path_str.strip().strip('"'))

    if path.is_file() and path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path, "r") as zf:
            for member in zf.namelist():
                if member.lower().endswith(".json"):
                    with zf.open(member) as f:
                        results.append((member, decode_bytes(f.read())))

        return results

    if path.is_dir():
        for json_file in path.rglob("*.json"):
            raw_text = json_file.read_text(encoding="utf-8-sig", errors="replace")
            results.append((str(json_file), raw_text))

        return results

    raise FileNotFoundError(f"No existe la ruta o no es válida: {path_str}")


def filter_target_files(
    all_json_files: List[Tuple[str, str]],
    target_files: List[str],
) -> Tuple[List[Tuple[str, str]], List[str]]:
    actual_by_basename: Dict[str, List[Tuple[str, str]]] = {}

    for file_path, raw_text in all_json_files:
        key = normalize_file_name(file_path)
        actual_by_basename.setdefault(key, []).append((file_path, raw_text))

    filtered_files: List[Tuple[str, str]] = []
    missing_files: List[str] = []

    for requested_name in target_files:
        clean_name = requested_name.strip()

        if not clean_name:
            continue

        key = clean_name.lower()
        matches = actual_by_basename.get(key, [])

        if not matches:
            missing_files.append(clean_name)
            continue

        for match in matches:
            filtered_files.append(match)

    return filtered_files, missing_files


def find_key_recursive(data: Any, target_key: str) -> Optional[Any]:
    if isinstance(data, dict):
        for key, value in data.items():
            if key == target_key:
                return value

        for value in data.values():
            found = find_key_recursive(value, target_key)

            if found is not None:
                return found

    elif isinstance(data, list):
        for item in data:
            found = find_key_recursive(item, target_key)

            if found is not None:
                return found

    return None


def get_workflow_variable(data: Dict[str, Any], key: str) -> str:
    workflow_variables = data.get("workflow_variables", {})

    if isinstance(workflow_variables, dict):
        value = workflow_variables.get(key)

        if value is not None and str(value).strip():
            return str(value).strip()

    value = find_key_recursive(data, key)

    if value is not None and str(value).strip():
        return str(value).strip()

    return ""


def get_tipo_documento(data: Dict[str, Any]) -> str:
    value = get_workflow_variable(data, "tipoDocumento")

    if value:
        return value

    return "SIN_TIPODOCUMENTO"


def get_proceso(data: Dict[str, Any]) -> str:
    value = get_workflow_variable(data, "proceso")

    if value:
        return value

    return "SIN_PROCESO"


def analyze_repeated_subtypes_r3(
    files: List[Tuple[str, str]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    parse_errors: List[Dict[str, str]] = []

    for file_path, raw_text in files:
        file_name = basename(file_path)

        try:
            data = json.loads(raw_text)
        except Exception as exc:
            parse_errors.append(
                {
                    "archivo": file_name,
                    "error": str(exc),
                }
            )
            continue

        tipo_documento = get_tipo_documento(data)
        proceso = get_proceso(data)
        normalized_subtipo = normalize_text(tipo_documento)

        if not normalized_subtipo:
            normalized_subtipo = "sin tipodocumento"
            tipo_documento = "SIN_TIPODOCUMENTO"

        if normalized_subtipo not in grouped:
            grouped[normalized_subtipo] = {
                "subtipo": tipo_documento,
                "variantes_tipoDocumento": [],
                "cantidad_archivos": 0,
                "archivos": [],
            }

        if tipo_documento not in grouped[normalized_subtipo]["variantes_tipoDocumento"]:
            grouped[normalized_subtipo]["variantes_tipoDocumento"].append(tipo_documento)

        grouped[normalized_subtipo]["archivos"].append(
            {
                "archivo": file_name,
                "proceso": proceso,
            }
        )

    subtipos = list(grouped.values())

    for item in subtipos:
        item["cantidad_archivos"] = len(item["archivos"])
        item["variantes_tipoDocumento"].sort()

    repeated = [
        item for item in subtipos
        if item["cantidad_archivos"] > 1
    ]

    repeated.sort(
        key=lambda item: (
            -item["cantidad_archivos"],
            normalize_text(item["subtipo"]),
        )
    )

    return repeated, parse_errors


def write_simple_txt(
    out_txt: str,
    repeated_subtypes: List[Dict[str, Any]],
    missing_files: List[str],
    parse_errors: List[Dict[str, str]],
    total_requested: int,
    total_found: int,
) -> None:
    lines: List[str] = []

    lines.append("SUBTIPOS REPETIDOS R3 / V3")
    lines.append("==========================")
    lines.append("")
    lines.append(f"Archivos solicitados R3: {total_requested}")
    lines.append(f"Archivos encontrados R3: {total_found}")
    lines.append(f"Archivos faltantes R3: {len(missing_files)}")
    lines.append(f"Errores de parseo: {len(parse_errors)}")
    lines.append(f"Subtipos repetidos encontrados: {len(repeated_subtypes)}")
    lines.append("")

    if missing_files:
        lines.append("ARCHIVOS FALTANTES")
        lines.append("------------------")

        for file_name in missing_files:
            lines.append(f"- {file_name}")

        lines.append("")

    if parse_errors:
        lines.append("ERRORES DE PARSEO")
        lines.append("-----------------")

        for error in parse_errors:
            lines.append(f"- {error['archivo']}: {error['error']}")

        lines.append("")

    if not repeated_subtypes:
        lines.append("No se encontraron subtipos repetidos en R3.")
    else:
        lines.append("DETALLE")
        lines.append("-------")
        lines.append("")

        for index, item in enumerate(repeated_subtypes, start=1):
            lines.append(f"{index}. Subtipo: {item['subtipo']}")
            lines.append(f"   Cantidad de archivos: {item['cantidad_archivos']}")

            if len(item["variantes_tipoDocumento"]) > 1:
                lines.append("   Variantes tipoDocumento:")

                for variant in item["variantes_tipoDocumento"]:
                    lines.append(f"   - {variant}")

            lines.append("   Archivos:")

            for file_info in item["archivos"]:
                lines.append(f"   - Archivo: {file_info['archivo']}")
                lines.append(f"     Proceso: {file_info['proceso']}")

            lines.append("")

    Path(out_txt).write_text("\n".join(lines), encoding="utf-8")


def print_summary(
    out_txt: str,
    repeated_subtypes: List[Dict[str, Any]],
    missing_files: List[str],
    parse_errors: List[Dict[str, str]],
    total_requested: int,
    total_found: int,
) -> None:
    print()
    print("=" * 90)
    print("ANÁLISIS DE SUBTIPOS REPETIDOS R3 / V3")
    print("=" * 90)
    print()
    print(f"Archivos solicitados R3: {total_requested}")
    print(f"Archivos encontrados R3: {total_found}")
    print(f"Archivos faltantes R3: {len(missing_files)}")
    print(f"Errores de parseo: {len(parse_errors)}")
    print(f"Subtipos repetidos encontrados: {len(repeated_subtypes)}")
    print()
    print(f"TXT generado: {out_txt}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Analiza únicamente flujos R3/V3, identifica subtipos repetidos "
            "por workflow_variables.tipoDocumento y lista archivos/procesos."
        )
    )

    parser.add_argument(
        "--path",
        default=DEFAULT_PATH,
        help="Ruta a carpeta, ZIP o ruta interna dentro de ZIP.",
    )

    parser.add_argument(
        "--out-txt",
        default=DEFAULT_OUT_TXT,
        help="TXT de salida con subtipos repetidos R3 y procesos por archivo.",
    )

    parser.add_argument(
        "--target-list-file",
        default="",
        help=(
            "Archivo de texto con nombres de JSON a validar (uno por linea). "
            "Si no se indica, se toman todos los JSON encontrados en --path."
        ),
    )

    args = parser.parse_args()

    all_json_files = iter_json_files(args.path)

    target_files: List[str] = []
    if args.target_list_file.strip():
        target_files = load_target_list_from_file(args.target_list_file)
    elif TARGET_JSON_FILES_V3:
        target_files = TARGET_JSON_FILES_V3

    r3_files, r3_missing, total_requested = select_r3_files(
        all_json_files=all_json_files,
        target_files=target_files,
    )

    repeated_subtypes, parse_errors = analyze_repeated_subtypes_r3(r3_files)

    write_simple_txt(
        out_txt=args.out_txt,
        repeated_subtypes=repeated_subtypes,
        missing_files=r3_missing,
        parse_errors=parse_errors,
        total_requested=total_requested,
        total_found=len(r3_files),
    )

    print_summary(
        out_txt=args.out_txt,
        repeated_subtypes=repeated_subtypes,
        missing_files=r3_missing,
        parse_errors=parse_errors,
        total_requested=total_requested,
        total_found=len(r3_files),
    )


if __name__ == "__main__":
    main()