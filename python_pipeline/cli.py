"""
Punto de entrada unico del pipeline.

Antes: ejecutar_pipeline_dynamo.sh + 5 wrappers `N_paso.sh` que solo
reenviaban argumentos a un script real. Ahora: un CLI con subcomandos.

Ejemplos:
  python -m python_pipeline.cli                                    (menu interactivo)
  python -m python_pipeline.cli run-all --env qa
  python -m python_pipeline.cli descargar --env qa --tabla config-control
  python -m python_pipeline.cli comparar --r3-dir X --ta-dir Y --out-dir Z
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import common, compare, config, download, events_analysis, excel_report, group_report, historial, matriz_ambientes, new_vs_baseline, verify_repeated
from .aws_client import CredentialsError, load_credentials_file
from .download import TableNotFoundError

logger = logging.getLogger("pipeline")


def _configure_logging(verbose: bool) -> None:
    # stdout (no el stderr por defecto de basicConfig): asi el orden con
    # los print() de las cabeceras de paso ("=== Paso N/7 ===") queda
    # siempre correcto, sin que la terminal intercale dos flujos distintos.
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
    if not verbose:
        # boto3/botocore/urllib3 son muy verbosos en INFO ("Found
        # credentials in environment variables.", detalles HTTP, etc.);
        # eso no le sirve al usuario final, solo ensucia la pantalla.
        for noisy_logger in ("boto3", "botocore", "urllib3", "s3transfer"):
            logging.getLogger(noisy_logger).setLevel(logging.WARNING)


def _abrir_excel(path: Path) -> None:
    """Abre el Excel con la aplicacion por defecto de Windows (normalmente
    Excel) al terminar el pipeline, para no tener que ir a buscarlo."""
    try:
        os.startfile(str(path))  # type: ignore[attr-defined]
    except AttributeError:
        logger.info("No se pudo abrir el Excel automaticamente en este sistema. Abrelo manualmente: %s", path)
    except OSError as exc:
        logger.warning("No se pudo abrir el Excel automaticamente (%s). Abrelo manualmente: %s", exc, path)


_DATE_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATE_LEGACY_RE = re.compile(r"^\d{8}$")


def _latest_subdir(base_dir: Path, pattern: re.Pattern, exclude: str) -> Optional[Path]:
    if not base_dir.is_dir():
        return None
    candidates = sorted(
        p.name for p in base_dir.iterdir()
        if p.is_dir() and pattern.match(p.name) and p.name != exclude
    )
    return base_dir / candidates[-1] if candidates else None


def _find_default_reference_dir(table_key: str, environment: str, today: str) -> Optional[Path]:
    """Autodetecta la carpeta de fecha mas reciente ya descargada (distinta
    a hoy) para usarla como referencia. Busca primero en la estructura
    nueva (descargas/<tabla>/<ambiente>/) y, si no hay nada, en la carpeta
    vieja (nombre completo de la tabla en la raiz del proyecto) para no
    perder el beneficio de descargas incrementales ya hechas."""
    new_base = config.DESCARGAS_DIR / table_key / environment
    found = _latest_subdir(new_base, _DATE_ISO_RE, today)
    if found:
        return found

    legacy_folder = config.LEGACY_FOLDERS.get(table_key)
    if not legacy_folder:
        return None
    legacy_today = today.replace("-", "")
    legacy_base = config.BASE_DIR / legacy_folder / environment
    return _latest_subdir(legacy_base, _DATE_LEGACY_RE, legacy_today)


def cmd_descargar(args: argparse.Namespace) -> None:
    if args.credenciales_file:
        load_credentials_file(Path(args.credenciales_file))

    if args.tabla == "ambas":
        tablas = ["config-control", "text-analyzer"]
    elif args.tabla == "todas":
        tablas = list(config.TABLE_DEFS)
    else:
        tablas = [args.tabla]
    today = datetime.now().strftime(config.DATE_FORMAT)

    completo = args.modo_descarga == "completo"
    for tabla in tablas:
        reference_dir = None if completo else (Path(args.referencia) if args.referencia else _find_default_reference_dir(tabla, args.env, today))
        logger.info(
            "Descargando %s (%s, modo %s). Referencia: %s",
            tabla, args.env, args.modo_descarga, reference_dir or "N/A (primera descarga o modo completo)",
        )
        download.download(
            environment=args.env, table_key=tabla, reference_dir=reference_dir,
            segments=args.segmentos, profile=args.perfil,
            max_attempts=args.reintentos, dry_run=args.dry_run, completo=completo,
        )


def cmd_comparar(args: argparse.Namespace) -> None:
    compare.compare(Path(args.r3_dir), Path(args.ta_dir), Path(args.out_dir))


def cmd_verificar(args: argparse.Namespace) -> None:
    verify_repeated.verify_repeated(
        args.r3_dir, Path(args.out_txt),
        Path(args.lista) if args.lista else None,
    )


def cmd_agrupar(args: argparse.Namespace) -> None:
    group_report.generate(Path(args.r3_dir), Path(args.detalle_csv), Path(args.out_csv))


def cmd_identificar_eventos(args: argparse.Namespace) -> None:
    events_analysis.generate(Path(args.events_dir), Path(args.out_xlsx))


def cmd_validar_nuevos(args: argparse.Namespace) -> None:
    new_vs_baseline.generate(
        Path(args.r3_dir), Path(args.orden_file), Path(args.out_csv),
        Path(args.detalle_csv) if args.detalle_csv else None,
    )


def cmd_run_all(args: argparse.Namespace) -> None:
    if args.credenciales_file:
        load_credentials_file(Path(args.credenciales_file))

    environment = args.env
    now = datetime.now()
    date_stamp = now.strftime(config.DATE_FORMAT)
    # Solo fecha, sin hora: reportes/qa/2026-09-15/. Si corres el pipeline
    # mas de una vez el mismo dia, la corrida mas reciente pisa la anterior.
    report_root = config.REPORTES_DIR / environment / date_stamp
    report_root.mkdir(parents=True, exist_ok=True)
    run_tag = common.human_datetime(now)

    compare_output_dir = report_root / "comparacion"
    verify_out_txt = report_root / "subtipos_repetidos.txt"
    group_out_csv = report_root / "reporte_agrupado.csv"
    detalle_csv = compare_output_dir / "detalle_r3_vs_ta.csv"
    nuevos_r3_csv = report_root / "nuevos_vs_baseline.csv"

    modo_descarga = getattr(args, "modo_descarga", "incremental")
    completo = modo_descarga == "completo"
    config_reference_dir = None if completo else _find_default_reference_dir("config-control", environment, date_stamp)
    ta_reference_dir = None if completo else _find_default_reference_dir("text-analyzer", environment, date_stamp)
    events_reference_dir = None if completo else _find_default_reference_dir("events-manager", environment, date_stamp)

    print()
    print(f"=== Paso 1/7: descargando config-control, text-analyzer y events-manager ({environment}, modo {modo_descarga}) ===")
    if not completo and (config_reference_dir or ta_reference_dir):
        print("(descarga rapida: solo trae lo nuevo desde la ultima vez; el maestro global no depende de esto)")
    elif completo:
        print("(descarga completa: trae todo, mas lenta, pero necesaria para detectar eliminados de verdad)")

    try:
        config_summary = download.download(environment, "config-control", config_reference_dir, args.segmentos, args.perfil, date_stamp, args.reintentos, completo=completo)
        download.download(environment, "text-analyzer", ta_reference_dir, args.segmentos, args.perfil, date_stamp, args.reintentos, completo=completo)
    except (CredentialsError, TableNotFoundError) as exc:
        logger.error(str(exc))
        sys.exit(1)

    # events-manager (UDZ) solo sirve para la columna "Transmisiones"; si
    # falla (tabla no existe en este ambiente, sin permiso, etc.) no debe
    # tumbar el resto del pipeline, solo esa columna queda vacia.
    resultados_basenames: Optional[set] = None
    try:
        download.download(environment, "events-manager", events_reference_dir, args.segmentos, args.perfil, date_stamp, args.reintentos, completo=completo)
        resultados_basenames = events_analysis.resultados_basenames(
            config.download_dir("events-manager", environment, date_stamp)
        )
    except (CredentialsError, TableNotFoundError) as exc:
        logger.warning("No se pudo descargar events-manager (%s); se omite la columna Transmisiones.", exc)

    r3_dir = config.download_dir("config-control", environment, date_stamp) / "R3"
    r2_dir = config.download_dir("config-control", environment, date_stamp) / "R2"
    ta_dir = config.download_dir("text-analyzer", environment, date_stamp)
    r2_rows = group_report.list_flat(r2_dir)

    if not r3_dir.is_dir():
        logger.warning("No hay flujos R3 en la descarga (%s); se omiten los pasos 2-7.", r3_dir)
        return
    if not ta_dir.is_dir():
        logger.error("No hay datos de Text Analyzer en la descarga (%s); se omiten los pasos 2-7.", ta_dir)
        return

    print()
    print("=== Paso 2/7: comparando R3 vs Text Analyzer ===")
    compare_summary = compare.compare(r3_dir, ta_dir, compare_output_dir)

    print()
    print("=== Paso 3/7: buscando subtipos de documento repetidos ===")
    verify_summary = verify_repeated.verify_repeated(str(r3_dir), verify_out_txt)

    print()
    print("=== Paso 4/7: agrupando el reporte por subtipo ===")
    total_r3, _suma, total_subtipos = group_report.generate(r3_dir, detalle_csv, group_out_csv, resultados_basenames)

    print()
    print(f"=== Paso 5/7: actualizando el maestro global del ambiente (modo {modo_descarga}) ===")
    filas_actuales = group_report.snapshot_rows(r3_dir, detalle_csv, resultados_basenames)
    historial_resumen = historial.actualizar(environment, filas_actuales, modo=modo_descarga)
    if any(historial_resumen.values()):
        print(
            f"  {len(historial_resumen['nuevos'])} nuevos, "
            f"{len(historial_resumen['cambios'])} con cambios, "
            f"{len(historial_resumen['eliminados'])} eliminados desde la ultima corrida."
        )
    else:
        print("  Sin cambios desde la ultima corrida.")
    if not completo:
        print("  (modo incremental: no se calculan eliminados -- corre 'completo' de vez en cuando para eso)")

    historial_path = config.REPORTES_DIR / f"historial_{environment}.xlsx"
    try:
        excel_report.build_historial_workbook(historial_path, historial.eventos_completos(environment))
    except RuntimeError as exc:
        logger.warning("No se genero el Excel de historial: %s", exc)
        historial_path = None

    # Maestro global del ambiente: fuera de esta corrida, acumula TODO lo
    # conocido (mismos campos que Reporte Agrupado), sin importar si hoy
    # se descargo completo o solo lo nuevo.
    maestro_path = config.REPORTES_DIR / f"maestro_{environment}.xlsx"
    try:
        flujos_maestro = historial.flujos_presentes(environment)
        rows_maestro = group_report.group_rows(flujos_maestro)
        maestro_csv = report_root / "_maestro_tmp.csv"
        group_report.write_grouped_csv(rows_maestro, maestro_csv, incluir_transmisiones=True)
        excel_report.build_maestro_workbook(
            maestro_path, maestro_csv,
            resumen={
                "Ambiente": environment,
                "Actualizado": run_tag,
                "Total de flujos conocidos (presentes)": len(flujos_maestro),
            },
        )
        maestro_csv.unlink(missing_ok=True)
    except RuntimeError as exc:
        logger.warning("No se genero el Excel maestro: %s", exc)
        maestro_path = None

    matriz_data = matriz_ambientes.actualizar(environment, filas_actuales)

    print()
    print("=== Paso 6/7: comparando contra el catalogo (Orden_RE_Base.txt) ===")
    total_nuevos = None
    try:
        total_nuevos = new_vs_baseline.generate(r3_dir, config.ORDEN_BASE_FILE, nuevos_r3_csv, detalle_csv)
    except FileNotFoundError:
        print(
            "  Paso omitido: todavia no existe referencias/Orden_RE_Base.txt.\n"
            "  Los pasos 1-4 y el Excel se generan igual; crea ese archivo y\n"
            "  vuelve a correr esta opcion cuando lo tengas listo."
        )

    print()
    print("=== Paso 7/7: generando el Excel final ===")
    excel_path = report_root / "reporte_completo.xlsx"
    try:
        resumen = {
            "Ambiente": environment,
            "Fecha de la corrida": run_tag,
            "R3 analizados": compare_summary["total_r3"],
            "Coincidencias R3 con Text Analyzer": compare_summary["matched"],
            "R3 sin Text Analyzer (revisar)": compare_summary["unmatched"],
            "Subtipos de documento repetidos": verify_summary["repeated_subtypes"],
            "Subtipos distintos (reporte agrupado)": total_subtipos,
            "Nuevos R3 vs Orden_RE_Base": total_nuevos if total_nuevos is not None else "No calculado (falta Orden_RE_Base.txt)",
            "Flujos con Transmisiones": (
                len(resultados_basenames) if resultados_basenames is not None
                else "No calculado (fallo la descarga de events-manager)"
            ),
            "Nuevos vs corrida anterior": len(historial_resumen["nuevos"]),
            "Cambiaron vs corrida anterior": len(historial_resumen["cambios"]),
            "Eliminados vs corrida anterior": len(historial_resumen["eliminados"]),
            "Nombres repetidos en config-control": len(config_summary.nombres_repetidos),
            "Items en R2 (no procesados en el reporte agrupado)": len(r2_rows),
        }
        excel_report.build_workbook(
            excel_path, resumen=resumen,
            classified_file=compare_summary["classified_file"],
            unclassified_file=compare_summary["unclassified_file"],
            repeated=verify_summary["repeated"],
            group_csv=group_out_csv,
            nuevos_csv=nuevos_r3_csv if total_nuevos is not None else None,
            historial_resumen=historial_resumen,
            r2_rows=r2_rows,
            nombres_repetidos=config_summary.nombres_repetidos,
        )

        matriz_path = config.REPORTES_DIR / "matriz_ambientes.xlsx"
        excel_report.build_matriz_workbook(matriz_path, matriz_data, environments=config.ENVIRONMENTS)
    except RuntimeError as exc:
        logger.warning("No se genero el Excel: %s", exc)
        excel_path = None
        matriz_path = None

    if excel_path:
        # Ya todo quedo embebido en el Excel; no dejamos los CSV/TXT
        # intermedios sueltos en la carpeta de reportes.
        shutil.rmtree(compare_output_dir, ignore_errors=True)
        for leftover in (group_out_csv, nuevos_r3_csv, verify_out_txt):
            leftover.unlink(missing_ok=True)

    print()
    print("=" * 60)
    print("RESUMEN")
    print("=" * 60)
    print(f"  Ambiente:                    {environment}")
    print(f"  Flujos R3 analizados:        {compare_summary['total_r3']}")
    print(f"  Coinciden con Text Analyzer: {compare_summary['matched']}")
    print(f"  Por revisar (sin match):     {compare_summary['unmatched']}")
    print(f"  Subtipos repetidos:          {verify_summary['repeated_subtypes']}")
    if total_nuevos is not None:
        print(f"  Nuevos vs catalogo:          {total_nuevos}")
    if resultados_basenames is not None:
        print(f"  Flujos con transmisiones:    {len(resultados_basenames)}")
    if any(historial_resumen.values()):
        print(
            f"  Vs corrida anterior:         {len(historial_resumen['nuevos'])} nuevos, "
            f"{len(historial_resumen['cambios'])} cambios, "
            f"{len(historial_resumen['eliminados'])} eliminados"
        )
    if config_summary.nombres_repetidos:
        total_afectados = sum(len(v) for v in config_summary.nombres_repetidos.values())
        print(
            f"  Nombres repetidos:           {len(config_summary.nombres_repetidos)} grupos "
            f"({total_afectados} archivos afectados, ver hoja 'Nombres Repetidos')"
        )
    if excel_path:
        print()
        print(f"  Reporte para revisar: {excel_path}")
    if maestro_path:
        print(f"  Maestro global del ambiente (acumulable): {maestro_path}")
    if matriz_path:
        print(f"  Matriz de ambientes (acumulable): {matriz_path}")
    if historial_path:
        print(f"  Historial completo (acumulable): {historial_path}")
    print("=" * 60)

    if not getattr(args, "no_abrir", False):
        if excel_path:
            _abrir_excel(excel_path)
        if maestro_path:
            _abrir_excel(maestro_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pipeline", description="Pipeline Dynamo config-control / text-analyzer.")
    parser.add_argument("--verbose", action="store_true", help="Logging detallado (DEBUG).")
    sub = parser.add_subparsers(dest="comando", required=False)

    common_aws = argparse.ArgumentParser(add_help=False)
    common_aws.add_argument("--env", choices=config.ENVIRONMENTS, required=True, help="Ambiente.")
    common_aws.add_argument("--segmentos", type=int, default=None,
                             help="Segmentos paralelos de scan. Si se omite, se elige solo segun el tamano de la tabla.")
    common_aws.add_argument("--perfil", default=None, help="Perfil de AWS (~/.aws/credentials). Si se omite, usa variables de entorno.")
    common_aws.add_argument("--reintentos", type=int, default=download.DEFAULT_MAX_ATTEMPTS,
                             help=f"Reintentos maximos ante throttling de Dynamo (default {download.DEFAULT_MAX_ATTEMPTS}).")
    common_aws.add_argument("--credenciales-file", default=None,
                             help="Archivo con credenciales AWS (JSON o texto con 'export AWS_...='), "
                                  "para no pegarlas a mano en la terminal. Ver aws_credentials.json de ejemplo.")
    common_aws.add_argument(
        "--modo-descarga", choices=["incremental", "completo"], default="incremental",
        help="'incremental' (default): rapido, solo trae lo nuevo desde la ultima descarga. "
             "'completo': trae todo, ignora la descarga anterior (mas lento, pero necesario de vez en "
             "cuando para que el maestro pueda detectar flujos eliminados de verdad).",
    )

    p_descargar = sub.add_parser("descargar", parents=[common_aws], help="Descarga una tabla DynamoDB.")
    p_descargar.add_argument(
        "--tabla",
        choices=[*config.TABLE_DEFS, "ambas", "todas"],
        required=True,
        help="'ambas' = config-control + text-analyzer (para el flujo de comparacion). 'todas' = las 3 tablas.",
    )
    p_descargar.add_argument("--referencia", default=None, help="Carpeta de una descarga previa, para marcar que es nuevo (ignorado si --modo-descarga completo).")
    p_descargar.add_argument("--dry-run", action="store_true", help="Escanea y clasifica pero no escribe nada a disco.")
    p_descargar.set_defaults(func=cmd_descargar)

    p_comparar = sub.add_parser("comparar", help="Compara R3 (use_case) vs Text Analyzer (cu_name).")
    p_comparar.add_argument("--r3-dir", required=True)
    p_comparar.add_argument("--ta-dir", required=True)
    p_comparar.add_argument("--out-dir", required=True)
    p_comparar.set_defaults(func=cmd_comparar)

    p_verificar = sub.add_parser("verificar", help="Detecta subtipos R3 repetidos.")
    p_verificar.add_argument("--r3-dir", required=True)
    p_verificar.add_argument("--out-txt", required=True)
    p_verificar.add_argument("--lista", default=None, help="Archivo opcional con nombres de JSON a validar (uno por linea).")
    p_verificar.set_defaults(func=cmd_verificar)

    p_agrupar = sub.add_parser("agrupar", help="Reporte agrupado de subtipos.")
    p_agrupar.add_argument("--r3-dir", required=True)
    p_agrupar.add_argument("--detalle-csv", required=True)
    p_agrupar.add_argument("--out-csv", required=True)
    p_agrupar.set_defaults(func=cmd_agrupar)

    p_validar = sub.add_parser("validar-nuevos", help="Nuevos R3 vs Orden_RE_Base.txt.")
    p_validar.add_argument("--r3-dir", required=True)
    p_validar.add_argument("--orden-file", default=str(config.ORDEN_BASE_FILE))
    p_validar.add_argument("--out-csv", required=True)
    p_validar.add_argument("--detalle-csv", default=None)
    p_validar.set_defaults(func=cmd_validar_nuevos)

    p_run_all = sub.add_parser("run-all", parents=[common_aws], help="Corre el pipeline completo (los 6 pasos).")
    p_run_all.add_argument("--no-abrir", action="store_true", help="No abrir el Excel automaticamente al terminar.")
    p_run_all.set_defaults(func=cmd_run_all)

    p_eventos = sub.add_parser(
        "identificar-eventos",
        help="En events-manager (UDZ): identifica por flujo si tiene crudos, transmisiones o ambos.",
    )
    p_eventos.add_argument("--events-dir", required=True, help="Carpeta descargada de events-manager (crudos/ y resultados/).")
    p_eventos.add_argument("--out-xlsx", required=True)
    p_eventos.set_defaults(func=cmd_identificar_eventos)

    sub.add_parser("menu", help="Menu interactivo (tambien se activa si no das ningun comando).")

    return parser


def main(argv: Optional[list] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(getattr(args, "verbose", False))

    # Un solo comando simple sin flags: `python -m python_pipeline.cli`
    # (o `aid-pipeline` si esta instalado) abre el menu interactivo en vez
    # de exigir memorizar subcomandos y flags.
    if args.comando is None or args.comando == "menu":
        from . import menu
        menu.run()
        return

    try:
        args.func(args)
    except (CredentialsError, TableNotFoundError, FileNotFoundError) as exc:
        logger.error(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
