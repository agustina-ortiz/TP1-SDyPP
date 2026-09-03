"""Pruebas del nodo C del Hit 8."""

from concurrent import futures

import grpc

from common.logger import Logger
from hit8 import nodos_pb2, nodos_pb2_grpc
from hit8.nodo_c import iniciar_servidor, registrar_en_d, saludar_peer


class RegistroDFalso(nodos_pb2_grpc.RegistroDServiceServicer):
    """Implementacion minima de D para probar el cliente C."""

    def __init__(self) -> None:
        self.nodo_recibido = None

    def Registrar(
        self,
        request: nodos_pb2.RegistroRequest,
        context: grpc.ServicerContext,
    ) -> nodos_pb2.RegistroResponse:
        self.nodo_recibido = request.nodo

        return nodos_pb2.RegistroResponse(
            ventana="ventana-prueba",
            peers=[
                nodos_pb2.Nodo(
                    host="127.0.0.1",
                    port=9100,
                )
            ],
        )

    def ObtenerPares(
        self,
        request: nodos_pb2.PeersRequest,
        context: grpc.ServicerContext,
    ) -> nodos_pb2.PeersResponse:
        return nodos_pb2.PeersResponse(
            ventana="ventana-prueba",
            peers=[],
        )


def test_nodo_c_responde_saludo_grpc(tmp_path):
    servidor, puerto, log = iniciar_servidor(
        host_publico="127.0.0.1",
        host_escucha="127.0.0.1",
        log_dir=str(tmp_path),
    )

    try:
        respuesta = saludar_peer(
            peer=nodos_pb2.Nodo(
                host="127.0.0.1",
                port=puerto,
            ),
            host_local="127.0.0.1",
            puerto_local=9999,
            log=log,
        )

        assert respuesta.origen.host == "127.0.0.1"
        assert respuesta.origen.port == puerto
        assert respuesta.ref
        assert respuesta.ts

        eventos = [
            registro["evento"]
            for registro in log.recientes()
        ]

        assert "saludo_grpc_recibido" in eventos
        assert "ack_grpc_enviado" in eventos
        assert "ack_grpc_recibido" in eventos

    finally:
        servidor.stop(grace=0).wait()


def test_c_se_registra_en_d_y_recibe_peers(tmp_path):
    servicio_d = RegistroDFalso()
    servidor_d = grpc.server(
        futures.ThreadPoolExecutor(max_workers=2)
    )

    nodos_pb2_grpc.add_RegistroDServiceServicer_to_server(
        servicio_d,
        servidor_d,
    )

    puerto_d = servidor_d.add_insecure_port("127.0.0.1:0")
    servidor_d.start()

    log = Logger(
        "nodo-c-hit8-test",
        log_dir=str(tmp_path),
    )

    try:
        respuesta = registrar_en_d(
            d_host="127.0.0.1",
            d_port=puerto_d,
            host_local="127.0.0.1",
            puerto_local=9200,
            log=log,
        )

        assert servicio_d.nodo_recibido.host == "127.0.0.1"
        assert servicio_d.nodo_recibido.port == 9200
        assert respuesta.ventana == "ventana-prueba"
        assert len(respuesta.peers) == 1
        assert respuesta.peers[0].port == 9100

    finally:
        servidor_d.stop(grace=0).wait()