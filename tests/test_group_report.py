import csv
import json
from pathlib import Path

from python_pipeline import group_report


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_detalle(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow(["Nombre de los JSONs", "Nombre TA config", "Nombre del subtipo",
                          "Cantidad de archivos con ese subtipo", "Observaciones", "Ruta JSON R3"])
        for row in rows:
            writer.writerow(row)


def test_agrupa_una_fila_por_json_y_totaliza(tmp_path):
    r3_dir = tmp_path / "R3"
    _write_json(r3_dir / "AAA.json", {"workflow_variables": {"tipoDocumento": "carta", "proceso": "p1"}, "s3_path": "s3://x/AAA"})
    _write_json(r3_dir / "BBB.json", {"workflow_variables": {"tipoDocumento": "carta", "proceso": "p2"}, "s3_path": "s3://x/BBB"})
    _write_json(r3_dir / "CCC.json", {"workflow_variables": {"tipoDocumento": "otro", "proceso": "p3"}, "s3_path": "s3://x/CCC"})

    detalle_csv = tmp_path / "detalle.csv"
    _write_detalle(detalle_csv, [
        ["AAA.json", "ta1", "carta", "2", "", "s3://x/AAA"],
        ["BBB.json", "ta1", "carta", "2", "", "s3://x/BBB"],
        ["CCC.json", "", "otro", "1", "Validar Manualmente", "s3://x/CCC"],
    ])

    out_csv = tmp_path / "out.csv"
    total_r3, suma_grupos, total_subtipos = group_report.generate(r3_dir, detalle_csv, out_csv)

    assert total_r3 == 3
    assert suma_grupos == 3
    assert total_subtipos == 2

    rows = list(csv.reader(out_csv.open(encoding="utf-8"), delimiter=";"))
    data_rows = {r[0]: r for r in rows if r and r[0] not in ("Nombre de los JSONs", "TOTAL_R3", "")}
    # Solo la primera fila del grupo "carta" trae subtipo/cantidad.
    assert data_rows["AAA.json"][2] == "carta"
    assert data_rows["AAA.json"][3] == "2"
    assert data_rows["BBB.json"][2] == ""
    assert data_rows["BBB.json"][3] == ""

    total_row = next(r for r in rows if r and r[0] == "TOTAL_R3")
    assert total_row[3] == "3"


def test_columna_transmisiones_es_opcional(tmp_path):
    r3_dir = tmp_path / "R3"
    _write_json(r3_dir / "AAA.json", {"workflow_variables": {"tipoDocumento": "carta"}, "s3_path": "s3://x/AAA"})
    _write_json(r3_dir / "BBB.json", {"workflow_variables": {"tipoDocumento": "otro"}, "s3_path": "s3://x/BBB"})

    detalle_csv = tmp_path / "detalle.csv"
    _write_detalle(detalle_csv, [
        ["AAA.json", "ta1", "carta", "1", "", "s3://x/AAA"],
        ["BBB.json", "ta1", "otro", "1", "", "s3://x/BBB"],
    ])

    out_csv = tmp_path / "out.csv"
    group_report.generate(r3_dir, detalle_csv, out_csv, resultados_basenames={"AAA"})

    rows = list(csv.reader(out_csv.open(encoding="utf-8"), delimiter=";"))
    assert rows[0][-1] == "Transmisiones"
    data_rows = {r[0]: r for r in rows if r and r[0] not in ("Nombre de los JSONs", "TOTAL_R3", "")}
    assert data_rows["AAA.json"][-1] == "Si"
    assert data_rows["BBB.json"][-1] == "No"


def test_snapshot_rows_para_historial(tmp_path):
    r3_dir = tmp_path / "R3"
    _write_json(r3_dir / "AAA.json", {"workflow_variables": {"tipoDocumento": "carta"}, "s3_path": "s3://x/AAA"})

    detalle_csv = tmp_path / "detalle.csv"
    _write_detalle(detalle_csv, [["AAA.json", "ta1", "carta", "1", "", "s3://x/AAA"]])

    rows = group_report.snapshot_rows(r3_dir, detalle_csv, resultados_basenames={"AAA"})

    assert rows == [{"file": "AAA.json", "subtipo": "carta", "ta_config": "ta1", "transmisiones": "Si"}]
