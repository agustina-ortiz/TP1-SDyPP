"""Hit 7 - Nodo C alineado a las ventanas de D.

Es el nodo C del Hit 6 con un solo cambio conceptual: en vez de sondear a D
cada intervalo a ciegas, usa el campo `proxima_ventana_en_s` de la
respuesta para despertarse justo despues del borde de la ventana. Asi la
re-inscripcion cae en la ventana correcta y el cambio de ventana queda
registrado en el log, que es la evidencia de que la coordinacion funciona.
"""

import json
import socket
import threading
import time
import urllib.request

from common.cli import parser_nodo_c_con_registro
from common.logger import Logger
from common.protocol import LectorDeLineas, ack, codificar, saludo
from common.red import descubrir_host_local

TAMANIO_BUFFER = 4096
ESPERA_INICIAL = 1.0
ESPERA_MAXIMA = 16.0
TIMEOUT_HTTP = 5.0
TIMEOUT_SALUDO = 5.0
MARGEN_VENTANA = 0.2
ENCODING = "utf-8"


def atender(
    conexion: socket.socket,
    direccion: tuple[str, int],
    host_local: str,
    puerto_local: int,
    log: Logger,
) -> None:
    """Recibe saludos JSON de otro nodo C y responde con mensajes ack."""
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
        log.warn("json_invalido", origen=origen, error=str(error))

    except OSError as error:
        log.warn("conexion_interrumpida", origen=origen, error=str(error))

    finally:
        conexion.close()


def crear_servidor(host_escucha: str = "0.0.0.0") -> tuple[socket.socket, int]:
    """Reserva un puerto libre y devuelve el socket ya escuchando."""
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    servidor.bind((host_escucha, 0))
    servidor.listen()
    servidor.settimeout(1.0)

    return servidor, servidor.getsockname()[1]


def atender_conexiones(
    servidor: socket.socket,
    host_local: str,
    puerto_local: int,
    log: Logger,
) -> None:
    """Acepta conexiones entrantes y crea un hilo por cada una."""
    log.info("servidor_iniciado", host=host_local, port=puerto_local)

    try:
        while True:
            try:
                conexion, direccion = servidor.accept()
            except TimeoutError:
                continue
            except OSError:
                return

            log.info(
                "conexion_aceptada",
                origen=f"{direccion[0]}:{direccion[1]}",
            )

            hilo = threading.Thread(
                target=atender,
                args=(conexion, direccion, host_local, puerto_local, log),
                daemon=True,
                name=f"cliente-{direccion[0]}-{direccion[1]}",
            )
            hilo.start()

    finally:
        servidor.close()
        log.info("servidor_detenido", host=host_local, port=puerto_local)


def inscribirse_en_d(
    d_host: str,
    d_port: int,
    host_local: str,
    puerto_local: int,
    log: Logger,
) -> dict:
    """Se inscribe en la ventana futura y recibe los pares de la presente."""
    destino = f"http://{d_host}:{d_port}/register"
    cuerpo = json.dumps(
        {"host": host_local, "port": puerto_local}
    ).encode(ENCODING)

    pedido = urllib.request.Request(
        destino,
        data=cuerpo,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(pedido, timeout=TIMEOUT_HTTP) as respuesta:
        datos = json.loads(respuesta.read().decode(ENCODING))

    if not isinstance(datos, dict):
        raise ValueError("D respondio algo que no es un objeto JSON")

    log.info(
        "inscripcion_confirmada",
        destino=destino,
        ventana=datos.get("ventana"),
        inscripto_en=datos.get("inscripto_en"),
        cantidad_peers=len(datos.get("peers", [])),
    )

    return datos


def es_el_mismo_nodo(peer: dict, host_local: str, puerto_local: int) -> bool:
    """Evita que C se salude a si mismo: D devuelve la lista completa."""
    return peer.get("host") == host_local and peer.get("port") == puerto_local


def saludar_peer(
    peer: dict,
    host_local: str,
    puerto_local: int,
    log: Logger,
) -> dict:
    """Abre una conexion efimera, saluda al par y espera su ack."""
    destino = f"{peer['host']}:{peer['port']}"
    mensaje = saludo(host=host_local, port=puerto_local, msg="hola desde C")
    lector = LectorDeLineas()
    inicio_ns = time.perf_counter_ns()

    with socket.create_connection(
        (peer["host"], peer["port"]),
        timeout=TIMEOUT_SALUDO,
    ) as conexion:
        mensaje_bytes = codificar(mensaje)
        conexion.sendall(mensaje_bytes)

        log.info(
            "saludo_enviado",
            destino=destino,
            ref=mensaje["ts"],
            bytes=len(mensaje_bytes),
        )

        while True:
            datos = conexion.recv(TAMANIO_BUFFER)

            if not datos:
                raise ConnectionError("el par cerro la conexion sin confirmar")

            for respuesta in lector.alimentar(datos):
                if (
                    isinstance(respuesta, dict)
                    and respuesta.get("tipo") == "ack"
                    and respuesta.get("ref") == mensaje["ts"]
                ):
                    latencia_ms = (
                        time.perf_counter_ns() - inicio_ns
                    ) / 1_000_000

                    log.info(
                        "ack_recibido",
                        origen=destino,
                        ref=respuesta["ref"],
                        latencia_ms=round(latencia_ms, 3),
                    )

                    return respuesta

                log.warn(
                    "respuesta_inesperada",
                    origen=destino,
                    respuesta=respuesta,
                )


def saludar_a_todos(
    peers: list,
    host_local: str,
    puerto_local: int,
    log: Logger,
) -> int:
    """Saluda a cada par de la ventana y devuelve cuantos confirmaron."""
    saludados = 0

    for peer in peers:
        if not isinstance(peer, dict) or "host" not in peer or "port" not in peer:
            log.warn("peer_con_forma_invalida", peer=peer)
            continue

        if es_el_mismo_nodo(peer, host_local, puerto_local):
            continue

        try:
            saludar_peer(peer, host_local, puerto_local, log)
            saludados += 1
        except (OSError, ValueError, UnicodeDecodeError) as error:
            log.warn(
                "fallo_saludo",
                destino=f"{peer['host']}:{peer['port']}",
                error=str(error),
            )

    return saludados


def proxima_espera(intervalo: float, respuesta: dict) -> float:
    """Cuanto dormir antes del proximo ciclo.

    Se duerme el intervalo normal, salvo que la ventana este por cambiar
    antes: en ese caso se despierta apenas cruzado el borde, para
    re-inscribirse en la ventana correcta y ver el presente nuevo cuanto
    antes. El margen evita despertarse un microsegundo antes del borde y
    tener que dar otra vuelta.
    """
    falta = respuesta.get("proxima_ventana_en_s")

    if not isinstance(falta, (int, float)) or isinstance(falta, bool):
        return intervalo

    if falta <= 0:
        return intervalo

    return min(intervalo, falta + MARGEN_VENTANA)


def main() -> None:
    """Levanta el servidor de C y corre el ciclo alineado a las ventanas."""
    parser = parser_nodo_c_con_registro(
        "Hit 7 - Nodo C alineado a las ventanas de D"
    )
    args = parser.parse_args()

    if not 1 <= args.d_port <= 65535:
        parser.error("--d-port debe estar entre 1 y 65535")

    if args.intervalo <= 0:
        parser.error("--intervalo debe ser mayor que cero")

    try:
        host_local = descubrir_host_local(args.d_host, args.d_port)
    except OSError as error:
        parser.error(f"no se pudo determinar la IP local: {error}")

    servidor, puerto_local = crear_servidor()
    log = Logger(f"nodo-c-hit7-{puerto_local}")

    hilo = threading.Thread(
        target=atender_conexiones,
        args=(servidor, host_local, puerto_local, log),
        daemon=True,
        name="servidor-entrante",
    )
    hilo.start()

    log.info(
        "nodo_iniciado",
        host=host_local,
        port=puerto_local,
        registro=f"{args.d_host}:{args.d_port}",
    )

    espera = ESPERA_INICIAL
    ventana_conocida = None

    try:
        while True:
            try:
                respuesta = inscribirse_en_d(
                    d_host=args.d_host,
                    d_port=args.d_port,
                    host_local=host_local,
                    puerto_local=puerto_local,
                    log=log,
                )
                espera = ESPERA_INICIAL

                peers = respuesta.get("peers", [])
                ventana = respuesta.get("ventana")

                if ventana != ventana_conocida:
                    log.info(
                        "ventana_cambio",
                        anterior=ventana_conocida,
                        nueva=ventana,
                        pares=len(peers),
                    )
                    ventana_conocida = ventana

                saludar_a_todos(peers, host_local, puerto_local, log)

                time.sleep(proxima_espera(args.intervalo, respuesta))

            # URLError, HTTPError y TimeoutError son subclases de OSError;
            # JSONDecodeError lo es de ValueError. Con dos entradas alcanza.
            except (OSError, ValueError) as error:
                log.warn(
                    "fallo_inscripcion",
                    destino=f"{args.d_host}:{args.d_port}",
                    error=str(error),
                    reintento_s=espera,
                )
                time.sleep(espera)
                espera = min(espera * 2, ESPERA_MAXIMA)

    except KeyboardInterrupt:
        log.info("nodo_detenido", motivo="interrupcion_del_usuario")

    finally:
        servidor.close()


if __name__ == "__main__":
    main()
