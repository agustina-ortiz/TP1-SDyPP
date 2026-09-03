"""Hit 4 - Nodo C bidireccional.

Cada instancia escucha conexiones TCP y, simultaneamente, se conecta
como cliente a otro nodo C.
"""

import socket
import threading
import time

from common.cli import parser_nodo_c
from common.logger import Logger

TAMANIO_BUFFER = 1024
ENCODING = "utf-8"
ESPERA_INICIAL = 1.0
ESPERA_MAXIMA = 16.0


def atender(
    conexion: socket.socket,
    direccion: tuple[str, int],
    puerto_local: int,
    log: Logger,
) -> None:
    """Recibe saludos de un cliente hasta que la conexion termina."""
    origen = f"{direccion[0]}:{direccion[1]}"

    try:
        while True:
            datos = conexion.recv(TAMANIO_BUFFER)

            if not datos:
                log.info("conexion_cerrada", origen=origen)
                return

            mensaje = datos.decode(ENCODING)
            log.info("saludo_recibido", origen=origen, mensaje=mensaje)

            respuesta = f"hola, soy C en el puerto {puerto_local}"
            respuesta_bytes = respuesta.encode(ENCODING)
            conexion.sendall(respuesta_bytes)

            log.info(
                "respuesta_enviada",
                destino=origen,
                bytes=len(respuesta_bytes),
            )

    except UnicodeDecodeError as error:
        log.warn("mensaje_invalido", origen=origen, error=str(error))

    except OSError as error:
        log.warn("conexion_interrumpida", origen=origen, error=str(error))

    finally:
        conexion.close()


def ejecutar_servidor(host: str, port: int, log: Logger) -> None:
    """Escucha conexiones y crea un hilo para atender cada cliente."""
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
                args=(conexion, direccion, port, log),
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
    puerto_local: int,
    intervalo: float,
    log: Logger,
) -> None:
    """Se conecta al otro C, envia saludos y reconecta ante fallos."""
    espera = ESPERA_INICIAL
    destino = f"{peer_host}:{peer_port}"

    while True:
        cliente = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            cliente.connect((peer_host, peer_port))
            log.info("conexion_establecida", destino=destino)
            espera = ESPERA_INICIAL

            while True:
                saludo = f"hola, soy C en el puerto {puerto_local}"
                saludo_bytes = saludo.encode(ENCODING)

                cliente.sendall(saludo_bytes)
                log.info(
                    "saludo_enviado",
                    destino=destino,
                    bytes=len(saludo_bytes),
                )

                datos = cliente.recv(TAMANIO_BUFFER)

                if not datos:
                    raise ConnectionError("el otro nodo C cerro la conexion")

                respuesta = datos.decode(ENCODING)
                log.info(
                    "respuesta_recibida",
                    origen=destino,
                    mensaje=respuesta,
                )

                time.sleep(intervalo)

        except (OSError, UnicodeDecodeError) as error:
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
    """Lee parametros e inicia los roles cliente y servidor del nodo C."""
    parser = parser_nodo_c("Hit 4 - Nodo C bidireccional")
    args = parser.parse_args()

    if args.peer_host is None or args.peer_port is None:
        parser.error("--peer-host y --peer-port son obligatorios para el Hit 4")

    if not 1 <= args.listen_port <= 65535:
        parser.error("--listen-port debe estar entre 1 y 65535")

    if not 1 <= args.peer_port <= 65535:
        parser.error("--peer-port debe estar entre 1 y 65535")

    if args.intervalo <= 0:
        parser.error("--intervalo debe ser mayor que cero")

    log = Logger(f"nodo-c-{args.listen_port}")

    hilo_cliente = threading.Thread(
        target=ejecutar_cliente,
        args=(
            args.peer_host,
            args.peer_port,
            args.listen_port,
            args.intervalo,
            log,
        ),
        daemon=True,
        name="cliente-saliente",
    )
    hilo_cliente.start()

    try:
        ejecutar_servidor(args.listen_host, args.listen_port, log)
    except KeyboardInterrupt:
        log.info(
            "nodo_detenido",
            motivo="interrupcion_del_usuario",
        )


if __name__ == "__main__":
    main()