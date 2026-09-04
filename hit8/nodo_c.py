"""Hit 8 - Nodo C con gRPC y Protocol Buffers.

Cada nodo C levanta un servidor gRPC en un puerto aleatorio, se registra
en el nodo D, obtiene sus pares y les envia saludos mediante RPC.
"""

from concurrent import futures
import socket
import time

import grpc

from common.cli import parser_nodo_c_con_registro
from common.logger import Logger, ahora_iso
from hit8 import nodos_pb2, nodos_pb2_grpc


MAX_TRABAJADORES = 10
TIMEOUT_RPC = 5.0
ESPERA_INICIAL = 1.0
ESPERA_MAXIMA = 16.0


class ServicioNodoC(nodos_pb2_grpc.NodoCServiceServicer):
    """Implementa los RPC que otro nodo C puede invocar."""

    def __init__(
        self,
        host_local: str,
        puerto_local: int,
        log: Logger,
    ) -> None:
        self.host_local = host_local
        self.puerto_local = puerto_local
        self.log = log

    def Saludar(
        self,
        request: nodos_pb2.SaludoRequest,
        context: grpc.ServicerContext,
    ) -> nodos_pb2.AckResponse:
        """Recibe un saludo y devuelve un ACK relacionado por timestamp."""
        if not request.origen.host or request.origen.port == 0:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "el saludo debe indicar host y puerto de origen",
            )

        if not request.ts:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "el saludo debe incluir un timestamp",
            )

        origen = f"{request.origen.host}:{request.origen.port}"

        self.log.info(
            "saludo_grpc_recibido",
            origen=origen,
            mensaje=request.mensaje,
            ref=request.ts,
            bytes=request.ByteSize(),
        )

        respuesta = nodos_pb2.AckResponse(
            origen=nodos_pb2.Nodo(
                host=self.host_local,
                port=self.puerto_local,
            ),
            ref=request.ts,
            ts=ahora_iso(),
        )

        self.log.info(
            "ack_grpc_enviado",
            destino=origen,
            ref=request.ts,
            bytes=respuesta.ByteSize(),
        )

        return respuesta


def descubrir_host_local(d_host: str, d_port: int) -> str:
    """Obtiene la IP local usada para llegar hasta el nodo D."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as consulta:
        consulta.connect((d_host, d_port))
        return consulta.getsockname()[0]


def iniciar_servidor(
    host_publico: str,
    host_escucha: str = "0.0.0.0",
    log_dir: str | None = None,
) -> tuple[grpc.Server, int, Logger]:
    """Inicia el servidor gRPC de C en un puerto aleatorio."""
    servidor = grpc.server(
        futures.ThreadPoolExecutor(max_workers=MAX_TRABAJADORES)
    )

    puerto = servidor.add_insecure_port(f"{host_escucha}:0")

    if puerto == 0:
        raise RuntimeError("gRPC no pudo reservar un puerto")

    log = Logger(
        nodo=f"nodo-c-hit8-{puerto}",
        log_dir=log_dir,
    )

    servicio = ServicioNodoC(
        host_local=host_publico,
        puerto_local=puerto,
        log=log,
    )

    nodos_pb2_grpc.add_NodoCServiceServicer_to_server(
        servicio,
        servidor,
    )

    servidor.start()

    log.info(
        "servidor_grpc_iniciado",
        host=host_escucha,
        host_publico=host_publico,
        port=puerto,
    )

    return servidor, puerto, log


def registrar_en_d(
    d_host: str,
    d_port: int,
    host_local: str,
    puerto_local: int,
    log: Logger,
) -> nodos_pb2.RegistroResponse:
    """Registra este nodo C en D y devuelve los pares disponibles."""
    destino = f"{d_host}:{d_port}"

    with grpc.insecure_channel(destino) as canal:
        cliente_d = nodos_pb2_grpc.RegistroDServiceStub(canal)

        respuesta = cliente_d.Registrar(
            nodos_pb2.RegistroRequest(
                nodo=nodos_pb2.Nodo(
                    host=host_local,
                    port=puerto_local,
                )
            ),
            timeout=TIMEOUT_RPC,
        )

    log.info(
        "registro_grpc_confirmado",
        destino=destino,
        ventana=respuesta.ventana,
        cantidad_peers=len(respuesta.peers),
    )

    return respuesta


def saludar_peer(
    peer: nodos_pb2.Nodo,
    host_local: str,
    puerto_local: int,
    log: Logger,
) -> nodos_pb2.AckResponse:
    """Invoca el RPC Saludar de otro nodo C y valida su ACK."""
    destino = f"{peer.host}:{peer.port}"

    saludo = nodos_pb2.SaludoRequest(
        origen=nodos_pb2.Nodo(
            host=host_local,
            port=puerto_local,
        ),
        mensaje="hola desde C mediante gRPC",
        ts=ahora_iso(),
    )

    inicio_ns = time.perf_counter_ns()

    with grpc.insecure_channel(destino) as canal:
        cliente_c = nodos_pb2_grpc.NodoCServiceStub(canal)
        respuesta = cliente_c.Saludar(
            saludo,
            timeout=TIMEOUT_RPC,
        )

    latencia_ms = (time.perf_counter_ns() - inicio_ns) / 1_000_000

    if respuesta.ref != saludo.ts:
        raise ValueError(
            f"ACK incorrecto: se esperaba {saludo.ts} "
            f"y se recibio {respuesta.ref}"
        )

    log.info(
        "ack_grpc_recibido",
        origen=destino,
        ref=respuesta.ref,
        bytes_saludo=saludo.ByteSize(),
        bytes_ack=respuesta.ByteSize(),
        latencia_ms=round(latencia_ms, 3),
    )

    return respuesta


def es_el_mismo_nodo(
    peer: nodos_pb2.Nodo,
    host_local: str,
    puerto_local: int,
) -> bool:
    """Evita que C se envie saludos a si mismo."""
    return (
        peer.host == host_local
        and peer.port == puerto_local
    )


def main() -> None:
    """Inicia C y ejecuta el ciclo registro, pares y saludos."""
    parser = parser_nodo_c_con_registro(
        "Hit 8 - Nodo C con gRPC y Protocol Buffers"
    )
    args = parser.parse_args()

    if not 1 <= args.d_port <= 65535:
        parser.error("--d-port debe estar entre 1 y 65535")

    if args.intervalo <= 0:
        parser.error("--intervalo debe ser mayor que cero")

    try:
        host_local = descubrir_host_local(
            args.d_host,
            args.d_port,
        )
    except OSError as error:
        parser.error(f"no se pudo determinar la IP local: {error}")

    servidor, puerto_local, log = iniciar_servidor(host_local)
    espera = ESPERA_INICIAL

    try:
        while True:
            try:
                registro = registrar_en_d(
                    d_host=args.d_host,
                    d_port=args.d_port,
                    host_local=host_local,
                    puerto_local=puerto_local,
                    log=log,
                )
                espera = ESPERA_INICIAL

                for peer in registro.peers:
                    if es_el_mismo_nodo(
                        peer,
                        host_local,
                        puerto_local,
                    ):
                        continue

                    try:
                        saludar_peer(
                            peer=peer,
                            host_local=host_local,
                            puerto_local=puerto_local,
                            log=log,
                        )
                    except grpc.RpcError as error:
                        log.warn(
                            "fallo_saludo_grpc",
                            destino=f"{peer.host}:{peer.port}",
                            codigo=error.code().name,
                            error=error.details(),
                        )
                    except ValueError as error:
                        log.warn(
                            "ack_grpc_invalido",
                            destino=f"{peer.host}:{peer.port}",
                            error=str(error),
                        )

                time.sleep(args.intervalo)

            except grpc.RpcError as error:
                log.warn(
                    "fallo_registro_grpc",
                    destino=f"{args.d_host}:{args.d_port}",
                    codigo=error.code().name,
                    error=error.details(),
                    reintento_s=espera,
                )
                time.sleep(espera)
                espera = min(espera * 2, ESPERA_MAXIMA)

    except KeyboardInterrupt:
        log.info(
            "nodo_detenido",
            motivo="interrupcion_del_usuario",
        )

    finally:
        servidor.stop(grace=1).wait()
        log.info(
            "servidor_grpc_detenido",
            host=host_local,
            port=puerto_local,
        )


if __name__ == "__main__":
    main()