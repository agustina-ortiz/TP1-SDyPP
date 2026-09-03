"""Pruebas de integracion del nodo C del Hit 4."""

import socket
import threading

from common.logger import Logger
from hit4.nodo_c import ENCODING, TAMANIO_BUFFER, atender


def test_atender_responde_y_registra(tmp_path):
    cliente, servidor = socket.socketpair()
    cliente.settimeout(1.0)

    log = Logger("nodo-c-test", log_dir=str(tmp_path))

    hilo = threading.Thread(
        target=atender,
        args=(servidor, ("local", 12345), 9001, log),
        daemon=True,
    )
    hilo.start()

    try:
        saludo = "hola desde la prueba"
        cliente.sendall(saludo.encode(ENCODING))

        respuesta = cliente.recv(TAMANIO_BUFFER).decode(ENCODING)

        assert respuesta == "hola, soy C en el puerto 9001"

    finally:
        cliente.close()

    hilo.join(timeout=1.0)

    assert not hilo.is_alive()

    eventos = [registro["evento"] for registro in log.recientes()]

    assert eventos == [
        "saludo_recibido",
        "respuesta_enviada",
        "conexion_cerrada",
    ]