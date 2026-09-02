"""Pruebas del registro en memoria y disco."""

import json

from common.logger import MAX_EN_RAM, Logger


def test_escribe_en_disco_una_linea_json(tmp_path):
    log = Logger("nodo-test", log_dir=str(tmp_path))
    log.info("saludo_enviado", destino="127.0.0.1:9002", bytes=87)

    contenido = (tmp_path / "nodo-test.log").read_text(encoding="utf-8").strip()
    registro = json.loads(contenido)

    assert registro["evento"] == "saludo_enviado"
    assert registro["nivel"] == "INFO"
    assert registro["nodo"] == "nodo-test"
    assert registro["bytes"] == 87
    assert registro["ts"].endswith("Z")


def test_guarda_en_memoria(tmp_path):
    log = Logger("nodo-test", log_dir=str(tmp_path))
    log.info("uno")
    log.warn("dos")

    recientes = log.recientes()
    assert [r["evento"] for r in recientes] == ["uno", "dos"]
    assert recientes[1]["nivel"] == "WARN"


def test_la_memoria_no_crece_sin_limite(tmp_path):
    """El deque acota el uso de RAM: es un nodo que corre indefinidamente."""
    log = Logger("nodo-test", log_dir=str(tmp_path))
    for i in range(MAX_EN_RAM + 50):
        log.info("evento", i=i)

    recientes = log.recientes(n=MAX_EN_RAM)
    assert len(recientes) == MAX_EN_RAM
    assert recientes[-1]["i"] == MAX_EN_RAM + 49
