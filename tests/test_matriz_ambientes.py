import json

from python_pipeline import matriz_ambientes


def test_primer_ambiente_todo_presente(tmp_path, monkeypatch):
    monkeypatch.setattr(matriz_ambientes, "ESTADO_FILE", tmp_path / "matriz.json")

    filas = [{"file": "AAA.json", "subtipo": "carta"}]
    data = matriz_ambientes.actualizar("qa", filas, fecha="2026-09-15")

    assert data["AAA.json"]["qa"] == {"presente": True, "subtipo": "carta", "ultima_vez": "2026-09-15"}
    assert "pdn" not in data["AAA.json"]  # nunca visto en pdn -> ni siquiera aparece la clave


def test_segundo_ambiente_no_borra_el_primero(tmp_path, monkeypatch):
    monkeypatch.setattr(matriz_ambientes, "ESTADO_FILE", tmp_path / "matriz.json")

    matriz_ambientes.actualizar("qa", [{"file": "AAA.json", "subtipo": "carta"}], fecha="2026-09-15")
    data = matriz_ambientes.actualizar("pdn", [{"file": "AAA.json", "subtipo": "carta"}], fecha="2026-09-16")

    assert data["AAA.json"]["qa"]["presente"] is True
    assert data["AAA.json"]["pdn"]["presente"] is True


def test_flujo_desaparecido_queda_marcado_no_borrado(tmp_path, monkeypatch):
    monkeypatch.setattr(matriz_ambientes, "ESTADO_FILE", tmp_path / "matriz.json")

    matriz_ambientes.actualizar("qa", [{"file": "AAA.json", "subtipo": "carta"}], fecha="2026-09-15")
    data = matriz_ambientes.actualizar("qa", [], fecha="2026-09-16")

    assert data["AAA.json"]["qa"]["presente"] is False
    assert data["AAA.json"]["qa"]["subtipo"] == "carta"  # se conserva el ultimo subtipo conocido


def test_persiste_en_disco_entre_llamadas(tmp_path, monkeypatch):
    estado_file = tmp_path / "matriz.json"
    monkeypatch.setattr(matriz_ambientes, "ESTADO_FILE", estado_file)

    matriz_ambientes.actualizar("qa", [{"file": "AAA.json", "subtipo": "carta"}], fecha="2026-09-15")

    on_disk = json.loads(estado_file.read_text(encoding="utf-8"))
    assert on_disk["AAA.json"]["qa"]["presente"] is True


def test_cargar_estado(tmp_path, monkeypatch):
    monkeypatch.setattr(matriz_ambientes, "ESTADO_FILE", tmp_path / "matriz.json")
    matriz_ambientes.actualizar("qa", [{"file": "AAA.json", "subtipo": "carta"}], fecha="2026-09-15")

    assert matriz_ambientes.cargar_estado() == {
        "AAA.json": {"qa": {"presente": True, "subtipo": "carta", "ultima_vez": "2026-09-15"}}
    }
