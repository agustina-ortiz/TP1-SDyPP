"""Benchmark local: JSON/NDJSON sobre TCP contra Protobuf/gRPC.

Compara:
1. Tamaño serializado de saludo y ACK.
2. Latencia de ida y vuelta usando conexiones persistentes.
"""

import argparse
from concurrent import futures
from statistics import mean, median
import socket
import threading
import time

import grpc

from common.logger import ahora_iso
from common.protocol import LectorDeLineas, ack, codificar, saludo
from hit5.nodo_c import atender as atender_json
from hit8 import nodos_pb2, nodos_pb2_grpc
from hit8.nodo_c import ServicioNodoC


HOST = "127.0.0.1"
PUERTO_ORIGEN = 9001
MENSAJE = "hola desde C"
TIMEOUT = 5.0


class LoggerSilencioso:
    """Evita que escritura de logs altere medición."""

    def info(self, evento: str, **campos) -> None:
        pass

    def warn(self, evento: str, **campos) -> None:
        pass


def percentil_95(valores: list[float]) -> float:
    """Devuelve percentil 95 de lista de latencias."""
    ordenados = sorted(valores)
    indice = max(0, int(len(ordenados) * 0.95) - 1)
    return ordenados[indice]


def medir_tamanios() -> dict[str, int]:
    """Calcula bytes serializados sin cabeceras TCP, HTTP/2 o gRPC."""
    referencia = "2026-09-03T20:00:00Z"

    saludo_json = saludo(
        host=HOST,
        port=PUERTO_ORIGEN,
        msg=MENSAJE,
    )
    saludo_json["ts"] = referencia

    ack_json = ack(
        host=HOST,
        port=PUERTO_ORIGEN,
        ref=referencia,
    )
    ack_json["ts"] = referencia

    saludo_proto = nodos_pb2.SaludoRequest(
        origen=nodos_pb2.Nodo(
            host=HOST,
            port=PUERTO_ORIGEN,
        ),
        mensaje=MENSAJE,
        ts=referencia,
    )

    ack_proto = nodos_pb2.AckResponse(
        origen=nodos_pb2.Nodo(
            host=HOST,
            port=PUERTO_ORIGEN,
        ),
        ref=referencia,
        ts=referencia,
    )

    return {
        "json_saludo": len(codificar(saludo_json)),
        "json_ack": len(codificar(ack_json)),
        "proto_saludo": saludo_proto.ByteSize(),
        "proto_ack": ack_proto.ByteSize(),
    }


def iniciar_servidor_json(
    log: LoggerSilencioso,
) -> tuple[socket.socket, int, threading.Thread]:
    """Levanta servidor TCP del Hit 5 en puerto aleatorio."""
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1,
    )
    servidor.bind((HOST, 0))
    servidor.listen()

    puerto = servidor.getsockname()[1]

    def aceptar_cliente() -> None:
        conexion, direccion = servidor.accept()
        atender_json(
            conexion=conexion,
            direccion=direccion,
            host_local=HOST,
            puerto_local=puerto,
            log=log,
        )

    hilo = threading.Thread(
        target=aceptar_cliente,
        daemon=True,
        name="benchmark-json",
    )
    hilo.start()

    return servidor, puerto, hilo


def medir_json(
    iteraciones: int,
    calentamiento: int,
    log: LoggerSilencioso,
) -> list[float]:
    """Mide ida y vuelta JSON/NDJSON sobre TCP persistente."""
    servidor, puerto, hilo = iniciar_servidor_json(log)
    cliente = socket.create_connection(
        (HOST, puerto),
        timeout=TIMEOUT,
    )
    lector = LectorDeLineas()

    def intercambio() -> float:
        inicio_ns = time.perf_counter_ns()

        mensaje = saludo(
            host=HOST,
            port=PUERTO_ORIGEN,
            msg=MENSAJE,
        )
        cliente.sendall(codificar(mensaje))

        confirmado = False

        while not confirmado:
            datos = cliente.recv(4096)

            if not datos:
                raise ConnectionError(
                    "servidor JSON cerro la conexion"
                )

            for respuesta in lector.alimentar(datos):
                if (
                    respuesta.get("tipo") == "ack"
                    and respuesta.get("ref") == mensaje["ts"]
                ):
                    confirmado = True

        fin_ns = time.perf_counter_ns()
        return (fin_ns - inicio_ns) / 1_000_000

    try:
        for _ in range(calentamiento):
            intercambio()

        return [
            intercambio()
            for _ in range(iteraciones)
        ]

    finally:
        cliente.close()
        servidor.close()
        hilo.join(timeout=1.0)


def iniciar_servidor_grpc(
    log: LoggerSilencioso,
) -> tuple[grpc.Server, int]:
    """Levanta servidor gRPC local en puerto aleatorio."""
    servidor = grpc.server(
        futures.ThreadPoolExecutor(max_workers=4)
    )
    puerto = servidor.add_insecure_port(f"{HOST}:0")

    servicio = ServicioNodoC(
        host_local=HOST,
        puerto_local=puerto,
        log=log,
    )

    nodos_pb2_grpc.add_NodoCServiceServicer_to_server(
        servicio,
        servidor,
    )

    servidor.start()
    return servidor, puerto


def medir_grpc(
    iteraciones: int,
    calentamiento: int,
    log: LoggerSilencioso,
) -> list[float]:
    """Mide ida y vuelta Protobuf/gRPC sobre canal persistente."""
    servidor, puerto = iniciar_servidor_grpc(log)
    canal = grpc.insecure_channel(f"{HOST}:{puerto}")

    grpc.channel_ready_future(canal).result(timeout=TIMEOUT)
    cliente = nodos_pb2_grpc.NodoCServiceStub(canal)

    def intercambio() -> float:
        inicio_ns = time.perf_counter_ns()

        mensaje = nodos_pb2.SaludoRequest(
            origen=nodos_pb2.Nodo(
                host=HOST,
                port=PUERTO_ORIGEN,
            ),
            mensaje=MENSAJE,
            ts=ahora_iso(),
        )

        respuesta = cliente.Saludar(
            mensaje,
            timeout=TIMEOUT,
        )

        if respuesta.ref != mensaje.ts:
            raise ValueError("ACK gRPC no referencia al saludo")

        fin_ns = time.perf_counter_ns()
        return (fin_ns - inicio_ns) / 1_000_000

    try:
        for _ in range(calentamiento):
            intercambio()

        return [
            intercambio()
            for _ in range(iteraciones)
        ]

    finally:
        canal.close()
        servidor.stop(grace=0).wait()


def mostrar_latencias(
    nombre: str,
    valores: list[float],
) -> None:
    """Imprime promedio, mediana y percentil 95."""
    print(
        f"{nombre:<15}"
        f" promedio={mean(valores):.3f} ms"
        f" mediana={median(valores):.3f} ms"
        f" p95={percentil_95(valores):.3f} ms"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compara JSON/TCP contra Protobuf/gRPC"
    )
    parser.add_argument(
        "--iteraciones",
        type=int,
        default=500,
    )
    parser.add_argument(
        "--calentamiento",
        type=int,
        default=20,
    )
    args = parser.parse_args()

    if args.iteraciones <= 0:
        parser.error("--iteraciones debe ser mayor que cero")

    if args.calentamiento < 0:
        parser.error("--calentamiento no puede ser negativo")

    log = LoggerSilencioso()
    tamanios = medir_tamanios()

    total_json = (
        tamanios["json_saludo"]
        + tamanios["json_ack"]
    )
    total_proto = (
        tamanios["proto_saludo"]
        + tamanios["proto_ack"]
    )
    ahorro = (
        (total_json - total_proto)
        / total_json
        * 100
    )

    latencias_json = medir_json(
        args.iteraciones,
        args.calentamiento,
        log,
    )
    latencias_grpc = medir_grpc(
        args.iteraciones,
        args.calentamiento,
        log,
    )

    print("\nTAMAÑO SERIALIZADO")
    print(
        f"JSON/NDJSON     saludo={tamanios['json_saludo']} bytes"
        f" ack={tamanios['json_ack']} bytes"
        f" total={total_json} bytes"
    )
    print(
        f"Protobuf        saludo={tamanios['proto_saludo']} bytes"
        f" ack={tamanios['proto_ack']} bytes"
        f" total={total_proto} bytes"
    )
    print(f"Ahorro Protobuf: {ahorro:.1f}%")

    print(
        f"\nLATENCIA LOCAL"
        f" ({args.iteraciones} iteraciones,"
        f" {args.calentamiento} de calentamiento)"
    )
    mostrar_latencias("JSON/TCP", latencias_json)
    mostrar_latencias("Protobuf/gRPC", latencias_grpc)

    print(
        "\nNota: tamaños excluyen cabeceras TCP, HTTP/2 y gRPC."
    )


if __name__ == "__main__":
    main()