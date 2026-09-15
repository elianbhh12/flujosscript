#!/usr/bin/env python3
"""
Genera reporte agrupado de subtipos R3 con una fila por JSON.
- Nombre del subtipo y Cantidad solo aparecen en la primera fila de cada grupo.
- Columnas: Nombre de los JSONs | Nombre TA config | Nombre del subtipo
            | Cantidad de archivos con ese subtipo | Proceso | Ruta JSON R3 | Observaciones
"""
import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List, Tuple

import verificar_repetidos


DEFAULT_DETALLE_CSV = "coincidencia/detalle_r3_vs_ta.csv"
DEFAULT_OUT_CSV = "coincidencia/reporte_subtipos_agrupado_r3.csv"

ORDERED_JSON_FILES_TEXT = """
SALESFORCE_CARTERAMEAIRWAYBILL.json
SALESFORCE_CARTERAMEBILLOFLADING.json
SALESFORCE_CARTERAMECARTAPORTE.json
SALESFORCE_TRADEAIRWAYBILL.json
SALESFORCE_TRADEBILLOFLADING.json
SALESFORCE_TRADECARTAPORTE.json
SALESFORCE_TRADECARTAPORTE_000162.json
TEAMS_OFFSHOREAIRWAYBILL.json
TEAMS_OFFSHOREBILLOFLADING.json
TEAMS_OFFSHORECARTAPORTE.json
BIZAGI_CAMARACOMERCIONOVEDADESSVN.json
BIZAGI_ECOSISTEMASCAMARACOMERCIO.json
ORACLE_CONSUMOCAMARACOMERCIO.json
ORACLE_HIPOTECARIOCAMARACOMERCIO.json
SITIO_CONTENIDOS_DEPOSITOSCAMARACOMERCIO.json
TEAMS_OFFSHORECAMARACOMERCIO.json
BPO_HTCARTACONTADOR.json
BPO_INDCARTACONTADOR.json
BPO_PNCARTACONTADOR.json
ORACLE_CONSUMOCARTACONTADOR.json
ORACLE_HIPOTECARIOCARTACONTADOR.json
BIZAGI_COBRANZASCALIDADEMITIDADOCS.json
MASIVIAN_FRAUDESCALIDADEMITIDADOCS.json
OUTLOOK_REQLEGCALIDADEMITIDADOCS.json
OUTLOOK_SECRELACIONALCALIDADEMITIDADOCS.json
SAP_CRM_SUFICALIDADEMITIDADOCS.json
TCS_CONSUMOCARTALABORAL.json
TCS_HIPOTECARIOCARTALABORAL.json
aid_test.json
ns_test_mini.json
BPO_HTCARTAREVISORFISCAL.json
ORACLE_CONSUMOCARTAREVISORFISCAL.json
ORACLE_HIPOTECARIOCARTAREVISORFISCAL.json
CIF_ISERIES_AQRSDEBITONACIONALC.json
CIF_ISERIES_AQRSDEBITONACIONALNC.json
CIF_ISERIES_AQRSDEBITONACIONALPRECLASS.json
BIZAGI_ACUERDOECONOMICODERECIPROCIDAD.json
BIZAGI_ACUERDOECONOMICODERECIPROCIDADECO.json
EVOLUCIONDIGITAL_BENEFICIOTASA.json
ORACLE_BENEFICIOTASA.json
EVOLUCIONDIGITAL_DOCTONAUTORIZACIONDIAN.json
EVOLUCIONDIGITAL_DOCTONCALIFICACIONAVALISTAS.json
SALESFORCE_CARTERAMESEGMENTACION.json
SALESFORCE_TRADESEGMENTACION.json
ORACLE_CONTRATOSFIDUCIARIOS.json
ORACLE_CONTRATOSFIDUCIARIOS_000186.json
EVOLUCIONDIGITAL_DOCTONF3112SOLICITUDFINANCIACION.json
ORACLE_FINANCIACIONPARAUNINMUEBLE.json
LZT_NOTASAPROBACION.json
lzt_notasaprobacion.json
ORACLE_RELACIONACCIONISTA.json
ORACLE_RIESGOSRELACIONACCIONISTA.json
EVOLUCIONDIGITAL_DOCTONACTAAPROBACION.json
EVOLUCIONDIGITAL_ACTAENTREGA.json
PORTAL_PROCESOS_ASISTENTERIESGOS.json
ORACLE_ANEXO2FNGCYC.json
EVOLUCIONDIGITAL_F1535ANEXOCONOCIMIENTO.json
ORACLE_DESEMBOLSOSF2892.json
ORACLE_DESEMBOLSOSF472.json
EVOLUCIONDIGITAL_ANEXO2FNGVIPADES.json
EVOLUCIONDIGITAL_ANTECEDENTESDIS.json
CIF_ISERIES_AUTOMATIZACIONCESANTIASOE.json
CIF_ISERIES_AUTOMATIZACIONCESANTIASPQR.json
AID_DOCTONAUTORIZACIONADMONDATOS.json
EVOLUCIONDIGITAL_AUTORIZACIONINFO.json
ORACLE_AUTORIZACIONDEBIHIPO.json
OUTLOOK_AVALUO.json
ORACLE_BOLETAREGISTROHIPO.json
PANDORA_COBRANZADIFIERETUSPAGOS.json
AID_DOCTONcartaaprobacion.json
EVOLUCIONDIGITAL_DOCTONCARTABIENVENIDA.json
EVOLUCIONDIGITAL_CARTACUENTABANCARIA.json
OUTLOOK_CARTAACEPTACION.json
OUTLOOK_CARTACESION.json
ORACLE_CARTAINSTRUCCIONCYC.json
EVOLUCIONDIGITAL_DOCTONCARTARENUNCIAMICASAYA.json
EVOLUCIONDIGITAL_CARTASSUBSIDIOV.json
EVOLUCIONDIGITAL_CARTANOTIFICACION.json
EVOLUCIONDIGITAL_CARTARATIFICACION.json
BIZAGI_CEDULACIUDADANIANOVEDADESSVN.json
EVOLUCIONDIGITAL_DOCTONCERTIFICADODEF.json
ORACLE_TRADICIONLIBERTADHIPO.json
EVOLUCIONDIGITAL_CERTIFICADONODECLARANTE.json
TELEPERFORMANCE_ASESORIA_COMEX.json
BIZAGI_CONDICIONESECONOMICASECO.json
TEAMS_PTDISENOSOX.json
OUTLOOK_FILTRARCURRICULUMS.json
EVOLUCIONDIGITAL_ESCRITURAPUBLICA.json
ORACLE_CHESTIPULACIONPRIVADA.json
ORACLE_EXPEDIENTESTCPERSONAIND.json
ORACLE_EXTRACTOCARTERAHIPO.json
EVOLUCIONDIGITAL_F1366DESCUENTOPAGOCREDITO.json
EVOLUCIONDIGITAL_FORMATOAUTOCERTIFICACION.json
EVOLUCIONDIGITAL_F1458AUTORIZACIONDATOSPERSONALES.json
EVOLUCIONDIGITAL_F1487ANEXOOPERACIONACTIVA.json
EVOLUCIONDIGITAL_DOCTONF1493CONOCIMIENTOCLPJ.json
EVOLUCIONDIGITAL_DOCTONF1528ACEPTACIONPAGOS.json
EVOLUCIONDIGITAL_F1544REGLIBRANZAPN.json
EVOLUCIONDIGITAL_DOCTONF3045FORMATOENTREVISTA.json
AID_DOCTONF586CONVENIOVINCULACIONPN.json
BIZAGI_AFILIACIONRECAUDOSFISICOSYELECTRONICOSECO.json
DIAN_FACTURASNEGOCIOFIDUCIARIO.json
OUTLOOK_FACTURASREDEBAN.json
EVOLUCIONDIGITAL_DOCTONFORMATOAUTORIZACIONESVENTAS.json
AID_DOCTONformatoid.json
BIZAGI_FORMATONOVEDADESSVN.json
SALESFORCE_TRADEF58A.json
LANDING_ZONE_ONPREMISSE_GENERACIONCOMENTARIOSLIQUIDEZ.json
SITIO_CONTENIDOS_INVECOCOMERCIOGUIA.json
SITIO_CONTENIDOS_INVECOCOMERCIOINFORME.json
BIZAGI_CLASIFICACIONNOVEDADESSVN.json
LZT_MANTENIMIENTOPRODUCTOS.json
EVOLUCIONDIGITAL_DOCTONOFERTAMERCANTIL.json
ORACLE_OFERTAVICULANTEHIPO.json
AID_DOCTONPASAPORTE.json
AID_DOCTONPERFILCLIENTE.json
EVOLUCIONDIGITAL_DOCTON176PEP.json
BIZAGI_REGLAMENTODEUSUARIO.json
LANDING_ZONE_ONPREMISSE_REQUERIMIENTOSBREB.json
aid_test_000079.json
TEXT_ANALYZER_CAUSARAIZAQRS.json
LANDING_ZONE_ONPREMISSE_GENERACIONCOMENTARIOSLIQUIDEZ_000174.json
BIZAGI_ECOSISTEMASRUT.json
EVOLUCIONDIGITAL_SEGINCENDIOTERREMOTO.json
EVOLUCIONDIGITAL_SEGUROVIDA.json
EVOLUCIONDIGITAL_SOLICITUDTRASLADOSELECTIVO.json
"""

ORDERED_JSON_FILES: List[str] = [
    line.strip() for line in ORDERED_JSON_FILES_TEXT.splitlines() if line.strip()
]
ORDERED_JSON_INDEX: Dict[str, int] = {
    file_name: index for index, file_name in enumerate(ORDERED_JSON_FILES)
}


def file_order_key(file_name: str) -> Tuple[int, int, str]:
    if file_name in ORDERED_JSON_INDEX:
        return (0, ORDERED_JSON_INDEX[file_name], file_name)
    return (1, len(ORDERED_JSON_FILES), verificar_repetidos.normalize_text(file_name))


def cargar_detalle(path_csv: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with path_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            nombre = (row.get("Nombre de los JSONs") or "").strip()
            if not nombre:
                continue
            rows.append(row)
    return rows


def cargar_r3_desde_verificar_repetidos(path_r3: str) -> Dict[str, Dict[str, str]]:
    r3_raw = verificar_repetidos.iter_json_files(path_r3)
    filtrados, _missing, _total_requested = verificar_repetidos.select_r3_files(
        all_json_files=r3_raw,
        target_files=verificar_repetidos.TARGET_JSON_FILES_V3,
    )

    out: Dict[str, Dict[str, str]] = {}
    for file_path, raw in filtrados:
        file_name = verificar_repetidos.basename(file_path)
        try:
            data = json.loads(raw)
        except Exception:
            data = {}

        subtipo = verificar_repetidos.get_tipo_documento(data) if isinstance(data, dict) else "SIN_TIPODOCUMENTO"
        proceso = verificar_repetidos.get_proceso(data) if isinstance(data, dict) else ""
        s3_path = ""
        if isinstance(data, dict):
            s3_path = str(data.get("s3_path") or "").strip()

        out[file_name] = {
            "file": file_name,
            "subtipo_json": subtipo,
            "proceso": proceso,
            "s3_path": s3_path,
        }

    return out


def elegir_subtipo(detalle_row: Dict[str, str], subtipo_json: str) -> str:
    subtipo_detalle = (detalle_row.get("Nombre del subtipo") or "").strip()
    if subtipo_detalle:
        return subtipo_detalle
    if subtipo_json.strip():
        return subtipo_json.strip()
    return "REVISAR_MANUAL"


def generar(path_r3: str, detalle_csv: Path, out_csv: Path) -> Tuple[int, int, int]:
    detalle_rows = cargar_detalle(detalle_csv)
    r3 = cargar_r3_desde_verificar_repetidos(path_r3)

    # --- Paso 1: construir grupos ordenados por subtipo normalizado ---
    grupos: Dict[str, Dict[str, object]] = {}

    for detalle_row in detalle_rows:
        file_name = (detalle_row.get("Nombre de los JSONs") or "").strip()
        if not file_name:
            continue

        r3_info = r3.get(file_name)
        subtipo_json = r3_info["subtipo_json"] if r3_info else ""
        subtipo = elegir_subtipo(detalle_row, subtipo_json)

        ta_config = (detalle_row.get("Nombre TA config") or "").strip()
        observacion = (detalle_row.get("Observaciones") or "").strip()
        s3_path = (detalle_row.get("Ruta JSON R3") or "").strip()
        proceso = r3_info["proceso"] if r3_info else ""
        if not s3_path and r3_info:
            s3_path = str(r3_info["s3_path"])

        norm = verificar_repetidos.normalize_text(subtipo) or "revisar manual"
        if norm not in grupos:
            grupos[norm] = {
                "subtipo": subtipo,
                "rows": [],
                "count": 0,
            }

        grupos[norm]["rows"].append({
            "file": file_name,
            "ta_config": ta_config,
            "proceso": proceso,
            "s3_path": s3_path,
            "observacion": observacion,
            "order_key": file_order_key(file_name),
        })
        grupos[norm]["count"] = int(grupos[norm]["count"]) + 1

    filas_salida: List[Dict[str, object]] = []
    for norm, grupo in grupos.items():
        for row in grupo["rows"]:
            row_con_grupo = dict(row)
            row_con_grupo["subtipo_grupo"] = str(grupo["subtipo"])
            row_con_grupo["count_grupo"] = int(grupo["count"])
            row_con_grupo["norm_grupo"] = norm
            filas_salida.append(row_con_grupo)

    filas_salida.sort(
        key=lambda row: (
            row["order_key"],
            verificar_repetidos.normalize_text(str(row["file"])),
        )
    )

    # --- Paso 2: escribir CSV con una fila por JSON ---
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    total_r3 = 0

    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "Nombre de los JSONs",
            "Nombre TA config",
            "Nombre del subtipo",
            "Cantidad de archivos con ese subtipo",
            "Proceso",
            "Ruta JSON R3",
            "Observaciones",
        ])

        grupos_impresos = set()
        for row in filas_salida:
            norm_grupo = str(row["norm_grupo"])
            mostrar_grupo = norm_grupo not in grupos_impresos
            writer.writerow([
                row["file"],
                row["ta_config"],
                row["subtipo_grupo"] if mostrar_grupo else "",
                row["count_grupo"] if mostrar_grupo else "",
                row["proceso"],
                row["s3_path"],
                row["observacion"],
            ])
            grupos_impresos.add(norm_grupo)
            total_r3 += 1

        writer.writerow([])
        writer.writerow(["TOTAL_R3", "", "", total_r3, "", "", ""])

    suma_grupos = sum(int(g["count"]) for g in grupos.values())
    return total_r3, suma_grupos, len(grupos)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genera reporte agrupado de subtipos R3 con una fila por JSON."
    )
    parser.add_argument("--path-r3", default=verificar_repetidos.DEFAULT_PATH)
    parser.add_argument("--detalle-csv", default=DEFAULT_DETALLE_CSV)
    parser.add_argument("--out-csv", default=DEFAULT_OUT_CSV)
    args = parser.parse_args()

    total_r3, suma_grupos, total_subtipos = generar(
        path_r3=args.path_r3,
        detalle_csv=Path(args.detalle_csv),
        out_csv=Path(args.out_csv),
    )

    print(f"Reporte generado: {args.out_csv}")
    print(f"Total R3 procesados: {total_r3}")
    print(f"Suma de cantidades agrupadas: {suma_grupos}")
    print(f"Subtipos distintos: {total_subtipos}")

    if total_r3 != suma_grupos:
        raise SystemExit("Error: la suma de grupos no coincide con el total de R3")


if __name__ == "__main__":
    main()
# fin