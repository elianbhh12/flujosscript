"""
Script para cruzar el CSV reporte_documentos_encontrados_aid(Inventario R3).csv con el archivo
Inventario_udz.xlsx, llenando las columnas "ID TXS (CRUDOS)" y "ID TXS (TRANS)".
"""
import pandas as pd
import re
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CSV_PATH = os.path.join(BASE_DIR, "reporte_documentos_encontrados_aid(Inventario R3).csv")
UDZ_XLSX = os.path.join(BASE_DIR, "Inventario_udz.xlsx")

OUTPUT_CSV = os.path.join(BASE_DIR, "INVENTARIO_transmisiones_r3.csv")
OUTPUT_NO_USADOS = os.path.join(BASE_DIR, "IDS_RAW_NO_USADOS_r3.csv")

NO_MATCH = "N/A"


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


def ruta_a_transmisiones(ruta_normalizada: str) -> str:
    """Convierte el primer segmento '/crudos/' de la ruta en '/transmisiones/'."""
    if ruta_normalizada.startswith("/crudos/"):
        return "/transmisiones/" + ruta_normalizada[len("/crudos/"):]
    return ruta_normalizada


def cargar_mapa(xlsx_path: str, col_idx_path: int, col_idx_id: int) -> dict:
    """
    Carga la pestaña 'Detalle_Schedules' y arma un diccionario
    {ruta_normalizada: id_txs}, usando posición de columna (0-indexed).
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


def generar_reporte_no_usados(xlsx_path: str, col_idx_destino: int, col_idx_origen: int,
                               rutas_crudos: set, rutas_trans: set, output_path: str):
    """
    Carga TODAS las columnas de 'Detalle_Schedules' y exporta las filas cuya
    ruta (Destino y Origen) no se usó en ninguna coincidencia del CSV.
    """
    df = pd.read_excel(xlsx_path, sheet_name="Detalle_Schedules", header=0)
    df["ruta_destino_normalizada"] = df.iloc[:, col_idx_destino].apply(normalizar_path)
    df["ruta_origen_normalizada"] = df.iloc[:, col_idx_origen].apply(normalizar_path)
    usado_crudos = df["ruta_destino_normalizada"].isin(rutas_crudos)
    usado_trans = df["ruta_origen_normalizada"].isin(rutas_trans)
    df_no_usados = df[~usado_crudos & ~usado_trans]
    df_no_usados.to_csv(output_path, index=False)
    print(f"Registros no usados ({os.path.basename(xlsx_path)}): {len(df_no_usados)} -> {output_path}")


def main():
    df_csv = pd.read_csv(
        CSV_PATH,
        dtype=str,
        sep=";",
        encoding="latin-1",
        engine="python",
        on_bad_lines="warn",
    )

    columnas = df_csv.columns.tolist()
    col_s3_path = columnas[5]  # s3_path
    col_crudos = columnas[6]  # ID TXS (CRUDOS)
    col_trans = columnas[7]  # ID TXS (TRANS)

    total_registros = len(df_csv)
    print(f"Total de registros en CSV: {total_registros}")

    # Columna C = 2 (Id de transmisión), Columna E = 4 (Ruta Origen), Columna G = 6 (Ruta Destino)
    mapa_crudos = cargar_mapa(UDZ_XLSX, col_idx_path=6, col_idx_id=2)
    mapa_trans = cargar_mapa(UDZ_XLSX, col_idx_path=4, col_idx_id=2)

    print(f"Registros cargados para CRUDOS (Ruta Destino): {len(mapa_crudos)}")
    print(f"Registros cargados para TRANS (Ruta Origen): {len(mapa_trans)}")

    valores_crudos = []
    valores_trans = []
    contador_match_crudos = 0
    contador_match_trans = 0
    contador_no_match_crudos = 0
    contador_no_match_trans = 0
    contador_ambos_no_match = 0

    rutas_crudos_usadas = set()
    rutas_trans_usadas = set()

    for _, row in df_csv.iterrows():
        ruta_csv = normalizar_path(row[col_s3_path])
        ruta_trans_csv = ruta_a_transmisiones(ruta_csv)

        id_crudos = mapa_crudos.get(ruta_csv, NO_MATCH)
        id_trans = mapa_trans.get(ruta_trans_csv, NO_MATCH)

        if id_crudos != NO_MATCH:
            contador_match_crudos += 1
            rutas_crudos_usadas.add(ruta_csv)
        else:
            contador_no_match_crudos += 1

        if id_trans != NO_MATCH:
            contador_match_trans += 1
            rutas_trans_usadas.add(ruta_trans_csv)
        else:
            contador_no_match_trans += 1

        if id_crudos == NO_MATCH and id_trans == NO_MATCH:
            contador_ambos_no_match += 1

        valores_crudos.append(id_crudos)
        valores_trans.append(id_trans)

    df_csv[col_crudos] = valores_crudos
    df_csv[col_trans] = valores_trans

    df_csv.to_csv(OUTPUT_CSV, index=False)

    generar_reporte_no_usados(
        UDZ_XLSX,
        col_idx_destino=6,
        col_idx_origen=4,
        rutas_crudos=rutas_crudos_usadas,
        rutas_trans=rutas_trans_usadas,
        output_path=OUTPUT_NO_USADOS,
    )

    print("\n===== Resumen de Trazabilidad =====")
    print(f"Total de registros procesados: {total_registros}")
    print(f"Coincidencias en CRUDOS: {contador_match_crudos}")
    print(f"Sin coincidencia en CRUDOS: {contador_no_match_crudos}")
    print(f"Coincidencias en TRANS: {contador_match_trans}")
    print(f"Sin coincidencia en TRANS: {contador_no_match_trans}")
    print(f"Registros sin coincidencia en ambas columnas: {contador_ambos_no_match}")
    print("====================================\n")
    print(f"Archivo generado en: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()