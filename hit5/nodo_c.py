"""Hit 5 - Nodo C con mensajes JSON sobre TCP.

Mantiene el comportamiento bidireccional del Hit 4, pero reemplaza los
mensajes de texto por objetos JSON delimitados por saltos de linea.
"""

import json
import socket
import threading
import time

from common.cli import parser_nodo_c
from common.logger import Logger
from common.protocol import LectorDeLineas, ack, codificar, saludo

TAMANIO_BUFFER = 4096
ESPERA_INICIAL = 1.0
ESPERA_MAXIMA = 16.0


def atender(
    conexion: socket.socket,
    direccion: tuple[str, int],
    host_local: str,
    puerto_local: int,
    log: Logger,
) -> None:
    """Recibe saludos JSON y responde con mensajes ack."""
    origen = f"{direccion[0]}:{direccion[1]}"
    lector = LectorDeLineas()

    try:
        while True:
            datos = conexion.recv(TAMANIO_BUFFER)

            if not datos:
                log.info("conexion_cerrada", origen=origen)
                return

            for mensaje in lector.alimentar(datos):
                if not isinstance(mensaje, dict):
                    log.warn("mensaje_no_es_objeto", origen=origen)
                    continue

                if mensaje.get("tipo") != "saludo":
                    log.warn(
                        "tipo_inesperado",
                        origen=origen,
                        tipo=mensaje.get("tipo"),
                    )
                    continue

                referencia = mensaje.get("ts")

                if not isinstance(referencia, str):
                    log.warn("saludo_sin_timestamp", origen=origen)
                    continue

                log.info(
                    "saludo_recibido",
                    origen=origen,
                    mensaje=mensaje.get("msg"),
                    ref=referencia,
                )

                respuesta = ack(
                    host=host_local,
                    port=puerto_local,
                    ref=referencia,
                )
                respuesta_bytes = codificar(respuesta)
                conexion.sendall(respuesta_bytes)

                log.info(
                    "ack_enviado",
                    destino=origen,
                    ref=referencia,
                    bytes=len(respuesta_bytes),
                )

    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        log.warn(
            "json_invalido",
            origen=origen,
            error=str(error),
        )

    except OSError as error:
        log.warn(
            "conexion_interrumpida",
            origen=origen,
            error=str(error),
        )

    finally:
        conexion.close()


def ejecutar_servidor(host: str, port: int, log: Logger) -> None:
    """Escucha conexiones y crea un hilo para cada cliente."""
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    servidor.bind((host, port))
    servidor.listen()
    servidor.settimeout(1.0)

    log.info("servidor_iniciado", host=host, port=port)

    try:
        while True:
            try:
                conexion, direccion = servidor.accept()
            except TimeoutError:
                continue

            log.info(
                "conexion_aceptada",
                origen=f"{direccion[0]}:{direccion[1]}",
            )

            hilo = threading.Thread(
                target=atender,
                args=(conexion, direccion, host, port, log),
                daemon=True,
                name=f"cliente-{direccion[0]}-{direccion[1]}",
            )
            hilo.start()

    finally:
        servidor.close()
        log.info("servidor_detenido", host=host, port=port)


def ejecutar_cliente(
    peer_host: str,
    peer_port: int,
    host_local: str,
    puerto_local: int,
    intervalo: float,
    log: Logger,
) -> None:
    """Envia saludos JSON, espera sus acks y reconecta ante fallos."""
    espera = ESPERA_INICIAL
    destino = f"{peer_host}:{peer_port}"

    while True:
        cliente = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            cliente.connect((peer_host, peer_port))
            log.info("conexion_establecida", destino=destino)
            espera = ESPERA_INICIAL
            lector = LectorDeLineas()

            while True:
                mensaje = saludo(
                    host=host_local,
                    port=puerto_local,
                    msg="hola desde C",
                )
                mensaje_bytes = codificar(mensaje)
                cliente.sendall(mensaje_bytes)

                log.info(
                    "saludo_enviado",
                    destino=destino,
                    ref=mensaje["ts"],
                    bytes=len(mensaje_bytes),
                )

                confirmado = False

                while not confirmado:
                    datos = cliente.recv(TAMANIO_BUFFER)

                    if not datos:
                        raise ConnectionError(
                            "el otro nodo C cerro la conexion"
                        )

                    for respuesta in lector.alimentar(datos):
                        if not isinstance(respuesta, dict):
                            log.warn(
                                "respuesta_no_es_objeto",
                                origen=destino,
                            )
                            continue

                        if (
                            respuesta.get("tipo") == "ack"
                            and respuesta.get("ref") == mensaje["ts"]
                        ):
                            log.info(
                                "ack_recibido",
                                origen=destino,
                                ref=respuesta["ref"],
                            )
                            confirmado = True
                        else:
                            log.warn(
                                "respuesta_inesperada",
                                origen=destino,
                                respuesta=respuesta,
                            )

                time.sleep(intervalo)

        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as error:
            log.warn(
                "fallo_comunicacion",
                destino=destino,
                error=str(error),
                reintento_s=espera,
            )
            time.sleep(espera)
            espera = min(espera * 2, ESPERA_MAXIMA)

        finally:
            cliente.close()


def main() -> None:
    """Lee parametros e inicia los roles cliente y servidor."""
    parser = parser_nodo_c("Hit 5 - Nodo C con JSON sobre TCP")
    args = parser.parse_args()

    if args.peer_host is None or args.peer_port is None:
        parser.error("--peer-host y --peer-port son obligatorios para el Hit 5")

    if not 1 <= args.listen_port <= 65535:
        parser.error("--listen-port debe estar entre 1 y 65535")

    if not 1 <= args.peer_port <= 65535:
        parser.error("--peer-port debe estar entre 1 y 65535")

    if args.intervalo <= 0:
        parser.error("--intervalo debe ser mayor que cero")

    log = Logger(f"nodo-c-hit5-{args.listen_port}")

    hilo_cliente = threading.Thread(
        target=ejecutar_cliente,
        args=(
            args.peer_host,
            args.peer_port,
            args.listen_host,
            args.listen_port,
            args.intervalo,
            log,
        ),
        daemon=True,
        name="cliente-saliente",
    )
    hilo_cliente.start()

    try:
        ejecutar_servidor(
            args.listen_host,
            args.listen_port,
            log,
        )
    except KeyboardInterrupt:
        log.info(
            "nodo_detenido",
            motivo="interrupcion_del_usuario",
        )


if __name__ == "__main__":
    main()