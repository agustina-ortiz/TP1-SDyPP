"""Registro de actividades en memoria y en disco.

El enunciado pide mantener logs "en memoria y disco". Este modulo resuelve
las dos cosas de una vez:

  - disco:   una linea JSON por evento en logs/<nodo>.log
  - memoria: los ultimos MAX_EN_RAM eventos en un deque, que el nodo D
             expone despues por /health

Se usa igual desde cualquier Hit:

    from common.logger import Logger
    log = Logger("nodo-c")
    log.info("saludo_enviado", destino="127.0.0.1:9002", bytes=87)
"""

import json
import os
import sys
import threading
from collections import deque
from datetime import datetime, timezone

MAX_EN_RAM = 500


def ahora_iso() -> str:
    """Timestamp UTC en ISO-8601. Todo el sistema usa UTC, sin excepciones."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class Logger:
    def __init__(self, nodo: str, log_dir: str = None):
        self.nodo = nodo
        self.log_dir = log_dir or os.environ.get("LOG_DIR", "logs")
        self.memoria = deque(maxlen=MAX_EN_RAM)
        self._lock = threading.Lock()

        os.makedirs(self.log_dir, exist_ok=True)
        self.ruta = os.path.join(self.log_dir, f"{nodo}.log")

    def _emitir(self, nivel: str, evento: str, campos: dict) -> dict:
        registro = {"ts": ahora_iso(), "nivel": nivel, "nodo": self.nodo, "evento": evento}
        registro.update(campos)
        linea = json.dumps(registro, ensure_ascii=False)

        # El lock importa: varios hilos escriben (un thread por conexion aceptada).
        with self._lock:
            self.memoria.append(registro)
            with open(self.ruta, "a", encoding="utf-8") as f:
                f.write(linea + "\n")
            print(linea, file=sys.stderr, flush=True)

        return registro

    def info(self, evento: str, **campos):
        return self._emitir("INFO", evento, campos)

    def warn(self, evento: str, **campos):
        return self._emitir("WARN", evento, campos)

    def error(self, evento: str, **campos):
        return self._emitir("ERROR", evento, campos)

    def recientes(self, n: int = 50) -> list:
        """Ultimos n eventos desde RAM, sin tocar el disco."""
        with self._lock:
            return list(self.memoria)[-n:]
