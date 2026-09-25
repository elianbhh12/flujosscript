"""
Script para cruzar el CSV INVENTARIO_r2_general_r2.csv con los archivos
Inventario_ids_S3RAW_r2.xlsx e Inventario_ids_S3RESULTS_r2.xlsx, llenando
las columnas F (ID TXS RAW) y G (ID TXS RESULTS).
"""
import pandas as pd
import re
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CSV_PATH = os.path.join(BASE_DIR, "INVENTARIO_r2_general_r2.csv")
RAW_XLSX = os.path.join(BASE_DIR, "Inventario_ids_S3RAW_r2.xlsx")
RESULTS_XLSX = os.path.join(BASE_DIR, "Inventario_ids_S3RESULTS_r2.xlsx")
OUTPUT_CSV = os.path.join(BASE_DIR, "INVENTARIO_r2_transmisiones_r2.csv")
OUTPUT_RAW_NO_USADOS = os.path.join(BASE_DIR, "IDS_RAW_NO_USADOS_r2.csv")
OUTPUT_RESULTS_NO_USADOS = os.path.join(BASE_DIR, "IDS_RESULTS_NO_USADOS_r2.csv")

NO_MATCH = "No Coincidencia"


def normalizar_path(path: str) -> str:
    """Extrae y normaliza la ruta relativa (sin bucket, sin barras extremas)."""
    if pd.isna(path):
        return ""
    path = str(path).strip()
    path = path.replace("\\", "/")
    path = re.sub(r"^s3://[^/]+/?", "/", path, flags=re.IGNORECASE)
    path = re.sub(r"/+", "/", path)
    if not path.startswith("/"):
        path = "/" + path
    path = re.sub(r"^/aid/", "/", path, flags=re.IGNORECASE)
    path = path.rstrip("/")
    return path.lower()


def cargar_mapa(xlsx_path: str, col_idx_path: int, col_idx_id: int) -> dict:
    """
    Carga la pestaña 'Detalle_Schedules' y arma un diccionario
    {ruta_normalizada: id_txs}, usando posición de columna (0-indexed)
    en lugar de nombre de encabezado.
    """
    df = pd.read_excel(xlsx_path, sheet_name="Detalle_Schedules", header=0)
    mapa = {}
    for _, row in df.iterrows():
        ruta = normalizar_path(row.iloc[col_idx_path])
        id_txs = row.iloc[col_idx_id]
        if ruta and not pd.isna(id_txs):
            try:
                mapa[ruta] = int(id_txs)
            except (ValueError, TypeError):
                continue
    return mapa


def generar_reporte_no_usados(xlsx_path: str, col_idx_path: int, rutas_csv: set, output_path: str):
    """
    Carga TODAS las columnas de 'Detalle_Schedules' y exporta las filas cuya
    ruta (normalizada) no aparece en el CSV, para revisar campos adicionales.
    """
    df = pd.read_excel(xlsx_path, sheet_name="Detalle_Schedules", header=0)
    df["ruta_normalizada"] = df.iloc[:, col_idx_path].apply(normalizar_path)
    df_no_usados = df[~df["ruta_normalizada"].isin(rutas_csv)]
    df_no_usados.to_csv(output_path, index=False)
    print(f"Registros no usados ({os.path.basename(xlsx_path)}): {len(df_no_usados)} -> {output_path}")


def main():
    # Cargar CSV: separador ';', encoding latin-1 (contiene tildes/ñ),
    # y manejo de saltos de línea dentro de celdas con comillas.
    df_csv = pd.read_csv(
        CSV_PATH,
        dtype=str,
        sep=";",
        encoding="latin-1",
        engine="python",
        on_bad_lines="warn",
    )

    # Aseguramos que existan al menos 7 columnas (A-G)
    columnas = df_csv.columns.tolist()
    col_e = columnas[4]  # s3_path
    col_f = columnas[5]  # ID TXS (RAW)
    col_g = columnas[6]  # ID TXS (RESULTS)

    total_registros = len(df_csv)
    print(f"Total de registros en CSV: {total_registros}")

    # Columna C = 2 (ID TXS), Columna E = 4 (Ruta Origen), Columna G = 6 (Ruta Destino)
    mapa_raw = cargar_mapa(RAW_XLSX, col_idx_path=6, col_idx_id=2)
    mapa_results = cargar_mapa(RESULTS_XLSX, col_idx_path=4, col_idx_id=2)

    print(f"Registros cargados desde S3RAW_r2.xlsx: {len(mapa_raw)}")
    print(f"Registros cargados desde S3RESULTS_r2.xlsx: {len(mapa_results)}")

    # Procesar cada fila
    valores_f = []
    valores_g = []
    contador_match_raw = 0
    contador_match_results = 0
    contador_no_match_raw = 0
    contador_no_match_results = 0
    contador_ambos_no_match = 0

    for _, row in df_csv.iterrows():
        ruta_csv = normalizar_path(row[col_e])

        id_raw = mapa_raw.get(ruta_csv, NO_MATCH)
        id_results = mapa_results.get(ruta_csv, NO_MATCH)

        if id_raw != NO_MATCH:
            contador_match_raw += 1
        else:
            contador_no_match_raw += 1

        if id_results != NO_MATCH:
            contador_match_results += 1
        else:
            contador_no_match_results += 1

        if id_raw == NO_MATCH and id_results == NO_MATCH:
            contador_ambos_no_match += 1

        valores_f.append(id_raw)
        valores_g.append(id_results)

    df_csv[col_f] = valores_f
    df_csv[col_g] = valores_g

    df_csv.to_csv(OUTPUT_CSV, index=False)

    # Generar reportes de IDs no usados (rutas del Excel sin match en el CSV)
    rutas_csv = set(df_csv[col_e].apply(normalizar_path))
    generar_reporte_no_usados(RAW_XLSX, col_idx_path=6, rutas_csv=rutas_csv, output_path=OUTPUT_RAW_NO_USADOS)
    generar_reporte_no_usados(RESULTS_XLSX, col_idx_path=4, rutas_csv=rutas_csv, output_path=OUTPUT_RESULTS_NO_USADOS)

    # Resumen de trazabilidad
    print("\n===== Resumen de Trazabilidad =====")
    print(f"Total de registros procesados: {total_registros}")
    print(f"Coincidencias en RAW (col F): {contador_match_raw}")
    print(f"Sin coincidencia en RAW (col F): {contador_no_match_raw}")
    print(f"Coincidencias en RESULTS (col G): {contador_match_results}")
    print(f"Sin coincidencia en RESULTS (col G): {contador_no_match_results}")
    print(f"Registros sin coincidencia en ambas columnas: {contador_ambos_no_match}")
    print("====================================\n")
    print(f"Archivo generado en: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()