"""Pruebas de integracion del nodo C del Hit 5."""

import socket
import threading

from common.logger import Logger
from common.protocol import LectorDeLineas, codificar, saludo
from hit5.nodo_c import TAMANIO_BUFFER, atender


def test_atender_separa_saludos_json_y_responde_acks(tmp_path):
    cliente, servidor = socket.socketpair()
    cliente.settimeout(1.0)

    log = Logger("nodo-c-hit5-test", log_dir=str(tmp_path))

    hilo = threading.Thread(
        target=atender,
        args=(
            servidor,
            ("local", 12345),
            "127.0.0.1",
            9001,
            log,
        ),
        daemon=True,
    )
    hilo.start()

    mensaje_uno = saludo("127.0.0.1", 9002, "uno")
    mensaje_dos = saludo("127.0.0.1", 9002, "dos")

    mensaje_uno["ts"] = "ref-uno"
    mensaje_dos["ts"] = "ref-dos"

    try:
        cliente.sendall(
            codificar(mensaje_uno) + codificar(mensaje_dos)
        )

        lector = LectorDeLineas()
        respuestas = []

        while len(respuestas) < 2:
            datos = cliente.recv(TAMANIO_BUFFER)
            respuestas.extend(lector.alimentar(datos))

        assert [respuesta["tipo"] for respuesta in respuestas] == [
            "ack",
            "ack",
        ]
        assert [respuesta["ref"] for respuesta in respuestas] == [
            "ref-uno",
            "ref-dos",
        ]

    finally:
        cliente.close()

    hilo.join(timeout=1.0)

    assert not hilo.is_alive()

    eventos = [registro["evento"] for registro in log.recientes()]

    assert eventos == [
        "saludo_recibido",
        "ack_enviado",
        "saludo_recibido",
        "ack_enviado",
        "conexion_cerrada",
    ]