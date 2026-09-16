import json

from python_pipeline import historial


def test_primera_corrida_todo_es_nuevo(tmp_path, monkeypatch):
    monkeypatch.setattr(historial, "HISTORIAL_DIR", tmp_path)

    filas = [
        {"file": "AAA.json", "subtipo": "carta", "ta_config": "ta1", "transmisiones": "Si"},
        {"file": "BBB.json", "subtipo": "otro", "ta_config": "", "transmisiones": "No"},
    ]
    resumen = historial.actualizar("qa", filas, fecha="2026-09-15")

    assert set(resumen["nuevos"]) == {"AAA.json", "BBB.json"}
    assert resumen["eliminados"] == []
    assert resumen["cambios"] == []

    estado = json.loads((tmp_path / "qa" / "estado_actual.json").read_text(encoding="utf-8"))
    assert estado["AAA.json"]["subtipo"] == "carta"
    assert estado["AAA.json"]["primera_vez"] == "2026-09-15"


def test_segunda_corrida_detecta_nuevo_eliminado_y_cambio(tmp_path, monkeypatch):
    monkeypatch.setattr(historial, "HISTORIAL_DIR", tmp_path)

    primera = [
        {"file": "AAA.json", "subtipo": "carta", "ta_config": "ta1", "transmisiones": "Si"},
        {"file": "BBB.json", "subtipo": "otro", "ta_config": "", "transmisiones": "No"},
    ]
    historial.actualizar("qa", primera, fecha="2026-09-15")

    segunda = [
        {"file": "AAA.json", "subtipo": "carta_editada", "ta_config": "ta1", "transmisiones": "Si"},  # cambio subtipo
        {"file": "CCC.json", "subtipo": "nuevo_flujo", "ta_config": "", "transmisiones": "No"},        # nuevo
        # BBB.json desaparece -> eliminado
    ]
    resumen = historial.actualizar("qa", segunda, fecha="2026-09-16")

    assert resumen["nuevos"] == ["CCC.json"]
    assert resumen["eliminados"] == ["BBB.json"]
    assert resumen["cambios"] == ["AAA.json"]

    estado = json.loads((tmp_path / "qa" / "estado_actual.json").read_text(encoding="utf-8"))
    assert "BBB.json" not in estado
    assert estado["AAA.json"]["subtipo"] == "carta_editada"
    assert estado["AAA.json"]["primera_vez"] == "2026-09-15"  # se conserva
    assert estado["AAA.json"]["ultima_vez"] == "2026-09-16"


def test_sin_cambios_no_genera_eventos(tmp_path, monkeypatch):
    monkeypatch.setattr(historial, "HISTORIAL_DIR", tmp_path)

    filas = [{"file": "AAA.json", "subtipo": "carta", "ta_config": "ta1", "transmisiones": "Si"}]
    historial.actualizar("qa", filas, fecha="2026-09-15")
    resumen = historial.actualizar("qa", filas, fecha="2026-09-16")

    assert resumen == {"nuevos": [], "eliminados": [], "cambios": []}


def test_eventos_csv_es_append_only(tmp_path, monkeypatch):
    monkeypatch.setattr(historial, "HISTORIAL_DIR", tmp_path)

    historial.actualizar("qa", [{"file": "AAA.json", "subtipo": "carta", "ta_config": "", "transmisiones": ""}], fecha="2026-09-15")
    historial.actualizar("qa", [{"file": "BBB.json", "subtipo": "otro", "ta_config": "", "transmisiones": ""}], fecha="2026-09-16")

    eventos_file = tmp_path / "qa" / "eventos.csv"
    lineas = eventos_file.read_text(encoding="utf-8").splitlines()
    assert lineas[0] == "Fecha;Flujo;Tipo de cambio;Detalle"
    # AAA nuevo el 15, luego eliminado el 16 (ya no aparece), BBB nuevo el 16
    assert any("AAA.json;NUEVO" in l for l in lineas)
    assert any("AAA.json;ELIMINADO" in l for l in lineas)
    assert any("BBB.json;NUEVO" in l for l in lineas)


def test_ambientes_no_se_mezclan(tmp_path, monkeypatch):
    monkeypatch.setattr(historial, "HISTORIAL_DIR", tmp_path)

    historial.actualizar("qa", [{"file": "AAA.json", "subtipo": "x", "ta_config": "", "transmisiones": ""}], fecha="2026-09-15")
    resumen_pdn = historial.actualizar("pdn", [{"file": "AAA.json", "subtipo": "x", "ta_config": "", "transmisiones": ""}], fecha="2026-09-15")

    # Mismo flujo, pero pdn no tiene historial previo -> sigue siendo "nuevo" ahi
    assert resumen_pdn["nuevos"] == ["AAA.json"]
