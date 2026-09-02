"""Formato de mensajes y framing sobre TCP.

TCP es un stream de bytes: no preserva los limites de los mensajes. Un recv()
puede devolver dos saludos pegados, o medio saludo. Por eso el contrato del
grupo es NDJSON: un objeto JSON por linea, terminado en "\n".

LectorDeLineas acumula lo que va llegando y solo entrega mensajes completos.
"""

import json

from common.logger import ahora_iso

ENCODING = "utf-8"
DELIMITADOR = b"\n"


# --------------------------------------------------------------------------
# Constructores de mensajes
# --------------------------------------------------------------------------

def saludo(host: str, port: int, msg: str = "hola") -> dict:
    return {
        "tipo": "saludo",
        "from": {"host": host, "port": port},
        "ts": ahora_iso(),
        "msg": msg,
    }


def ack(host: str, port: int, ref: str) -> dict:
    """Confirmacion de recepcion. `ref` es el ts del saludo que se responde."""
    return {
        "tipo": "ack",
        "from": {"host": host, "port": port},
        "ts": ahora_iso(),
        "ref": ref,
    }


def codificar(mensaje: dict) -> bytes:
    """dict -> bytes listos para enviar, con el delimitador incluido."""
    return json.dumps(mensaje, ensure_ascii=False).encode(ENCODING) + DELIMITADOR


def decodificar(linea: bytes) -> dict:
    return json.loads(linea.decode(ENCODING))


# --------------------------------------------------------------------------
# Framing
# --------------------------------------------------------------------------

class LectorDeLineas:
    """Acumula bytes de un socket y entrega mensajes completos.

    Uso tipico:

        lector = LectorDeLineas()
        while True:
            datos = sock.recv(4096)
            if not datos:
                break              # el par cerro la conexion
            for mensaje in lector.alimentar(datos):
                manejar(mensaje)
    """

    def __init__(self):
        self._buffer = b""

    def alimentar(self, datos: bytes):
        """Devuelve la lista de mensajes completos que se pudieron armar."""
        self._buffer += datos
        mensajes = []

        while DELIMITADOR in self._buffer:
            linea, self._buffer = self._buffer.split(DELIMITADOR, 1)
            if linea.strip():
                mensajes.append(decodificar(linea))

        return mensajes

    @property
    def pendiente(self) -> int:
        """Bytes de un mensaje incompleto que todavia esperan su delimitador."""
        return len(self._buffer)
