"""Pruebas del framing NDJSON.

Estas pruebas cubren la trampa central del TP: TCP no respeta los limites de
los mensajes. Si LectorDeLineas esta bien, ningun Hit vuelve a sufrirla.
"""

from common.protocol import LectorDeLineas, ack, codificar, decodificar, saludo


def test_codificar_y_decodificar_ida_y_vuelta():
    original = saludo("127.0.0.1", 9001)
    crudo = codificar(original)

    assert crudo.endswith(b"\n")
    assert decodificar(crudo[:-1]) == original


def test_mensaje_partido_en_dos_recv():
    """Un saludo cortado al medio no se entrega hasta estar completo."""
    lector = LectorDeLineas()
    crudo = codificar(saludo("10.0.0.5", 52341))
    mitad = len(crudo) // 2

    assert lector.alimentar(crudo[:mitad]) == []
    assert lector.pendiente > 0

    mensajes = lector.alimentar(crudo[mitad:])
    assert len(mensajes) == 1
    assert mensajes[0]["tipo"] == "saludo"
    assert lector.pendiente == 0


def test_dos_mensajes_pegados_en_un_recv():
    """Dos saludos que llegan juntos se separan en dos mensajes."""
    lector = LectorDeLineas()
    crudo = codificar(saludo("10.0.0.5", 1)) + codificar(saludo("10.0.0.6", 2))

    mensajes = lector.alimentar(crudo)

    assert len(mensajes) == 2
    assert mensajes[0]["from"]["port"] == 1
    assert mensajes[1]["from"]["port"] == 2


def test_mensaje_y_medio():
    """Caso mixto: uno completo y otro a medio llegar."""
    lector = LectorDeLineas()
    completo = codificar(saludo("10.0.0.5", 1))
    parcial = codificar(saludo("10.0.0.6", 2))[:10]

    mensajes = lector.alimentar(completo + parcial)

    assert len(mensajes) == 1
    assert lector.pendiente == 10


def test_ack_referencia_al_saludo():
    original = saludo("127.0.0.1", 9001)
    respuesta = ack("127.0.0.1", 9002, ref=original["ts"])

    assert respuesta["tipo"] == "ack"
    assert respuesta["ref"] == original["ts"]
