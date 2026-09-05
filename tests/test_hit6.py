"""Pruebas del nodo D y del nodo C del Hit 6."""

import contextlib
import json
import threading
import urllib.error
import urllib.request

import pytest

from common.logger import Logger
from hit6.nodo_c import es_el_mismo_nodo, registrarse_en_d
from hit6.nodo_d import Registro, crear_servidor, ventana_actual

VENTANA = 60.0


class RelojFalso:
    """Reloj controlado a mano: evita dormir para probar la expiracion."""

    def __init__(self, inicio: float = 1_772_000_000.0):
        self.ahora = inicio

    def __call__(self) -> float:
        return self.ahora

    def avanzar(self, segundos: float) -> None:
        self.ahora += segundos


@contextlib.contextmanager
def nodo_d(tmp_path, ttl=VENTANA, reloj=None):
    """Levanta un D real en un puerto libre y lo apaga al salir."""
    log = Logger("nodo-d-hit6-test", log_dir=str(tmp_path))
    registro = Registro(ttl=ttl, log=log, reloj=reloj or RelojFalso())
    servidor = crear_servidor("127.0.0.1", 0, registro, log, VENTANA)

    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()

    try:
        yield servidor.server_address[1], registro
    finally:
        # Sin el shutdown el hilo queda vivo y pytest no termina nunca.
        servidor.shutdown()
        servidor.server_close()


def obtener(puerto: int, ruta: str) -> dict:
    url = f"http://127.0.0.1:{puerto}{ruta}"

    with urllib.request.urlopen(url, timeout=5) as respuesta:
        return json.loads(respuesta.read().decode("utf-8"))


def publicar(puerto: int, ruta: str, cuerpo) -> dict:
    pedido = urllib.request.Request(
        f"http://127.0.0.1:{puerto}{ruta}",
        data=json.dumps(cuerpo).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(pedido, timeout=5) as respuesta:
        return json.loads(respuesta.read().decode("utf-8"))


# --------------------------------------------------------------------------
# Registro
# --------------------------------------------------------------------------

def test_registrar_dos_veces_el_mismo_nodo_no_lo_duplica(tmp_path):
    log = Logger("nodo-d-hit6-test", log_dir=str(tmp_path))
    registro = Registro(ttl=VENTANA, log=log, reloj=RelojFalso())

    registro.registrar("10.0.0.5", 54321)
    registro.registrar("10.0.0.5", 54321)

    assert registro.activos() == [{"host": "10.0.0.5", "port": 54321}]

    eventos = [r["evento"] for r in log.recientes()]
    assert eventos == ["nodo_registrado", "nodo_registrado"]

    altas = [r["nuevo"] for r in log.recientes() if r["evento"] == "nodo_registrado"]
    assert altas == [True, False]


def test_el_nodo_que_deja_de_registrarse_expira(tmp_path):
    reloj = RelojFalso()
    log = Logger("nodo-d-hit6-test", log_dir=str(tmp_path))
    registro = Registro(ttl=10.0, log=log, reloj=reloj)

    registro.registrar("10.0.0.5", 54321)
    reloj.avanzar(9.0)
    assert registro.cantidad() == 1

    reloj.avanzar(2.0)
    assert registro.activos() == []

    eventos = [r["evento"] for r in log.recientes()]
    assert "nodo_expirado" in eventos


def test_activos_devuelve_la_forma_del_contrato_y_ordenada(tmp_path):
    log = Logger("nodo-d-hit6-test", log_dir=str(tmp_path))
    registro = Registro(ttl=VENTANA, log=log, reloj=RelojFalso())

    registro.registrar("10.0.0.9", 9002)
    registro.registrar("10.0.0.5", 9001)

    assert registro.activos() == [
        {"host": "10.0.0.5", "port": 9001},
        {"host": "10.0.0.9", "port": 9002},
    ]


def test_ventana_actual_trunca_al_minuto():
    # 2026-09-08T11:29:37Z
    instante = 1_788_866_977.0
    assert ventana_actual(60.0, instante).endswith(":00Z")
    assert ventana_actual(60.0, instante) == ventana_actual(60.0, instante + 22)
    assert ventana_actual(60.0, instante) != ventana_actual(60.0, instante + 60)


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

def test_register_devuelve_ventana_y_peers(tmp_path):
    with nodo_d(tmp_path) as (puerto, _):
        respuesta = publicar(puerto, "/register", {"host": "10.0.0.5", "port": 9001})

        assert set(respuesta) == {"ventana", "peers"}
        assert respuesta["peers"] == [{"host": "10.0.0.5", "port": 9001}]
        assert respuesta["ventana"].endswith("Z")

        assert obtener(puerto, "/peers") == respuesta


def test_health_tiene_los_cinco_campos_del_contrato(tmp_path):
    with nodo_d(tmp_path) as (puerto, _):
        publicar(puerto, "/register", {"host": "10.0.0.5", "port": 9001})
        salud = obtener(puerto, "/health")

        assert set(salud) == {
            "servicio",
            "estado",
            "nodos_activos",
            "uptime_s",
            "ventana_actual",
        }
        assert salud["servicio"] == "registro-d"
        assert salud["estado"] == "ok"
        assert salud["nodos_activos"] == 1
        assert isinstance(salud["uptime_s"], int)


@pytest.mark.parametrize(
    "cuerpo",
    [
        {"host": "", "port": 9001},
        {"host": "10.0.0.5"},
        {"host": "10.0.0.5", "port": "9001"},
        {"host": "10.0.0.5", "port": 70000},
        ["10.0.0.5", 9001],
    ],
)
def test_register_rechaza_cuerpos_invalidos(tmp_path, cuerpo):
    with nodo_d(tmp_path) as (puerto, registro):
        with pytest.raises(urllib.error.HTTPError) as fallo:
            publicar(puerto, "/register", cuerpo)

        assert fallo.value.code == 400
        assert registro.activos() == []


def test_rutas_y_metodos_desconocidos(tmp_path):
    with nodo_d(tmp_path) as (puerto, _):
        with pytest.raises(urllib.error.HTTPError) as fallo:
            obtener(puerto, "/inexistente")
        assert fallo.value.code == 404

        with pytest.raises(urllib.error.HTTPError) as fallo:
            obtener(puerto, "/register")
        assert fallo.value.code == 405


# --------------------------------------------------------------------------
# Nodo C contra un D real
# --------------------------------------------------------------------------

def test_c_se_registra_en_d_y_recibe_pares(tmp_path):
    with nodo_d(tmp_path) as (puerto, registro):
        log = Logger("nodo-c-hit6-test", log_dir=str(tmp_path))
        registro.registrar("10.0.0.9", 9002)

        respuesta = registrarse_en_d(
            d_host="127.0.0.1",
            d_port=puerto,
            host_local="10.0.0.5",
            puerto_local=54321,
            log=log,
        )

        assert {"host": "10.0.0.5", "port": 54321} in respuesta["peers"]
        assert {"host": "10.0.0.9", "port": 9002} in respuesta["peers"]

        eventos = [r["evento"] for r in log.recientes()]
        assert "registro_confirmado" in eventos


def test_c_se_reconoce_en_la_lista_de_pares():
    assert es_el_mismo_nodo({"host": "10.0.0.5", "port": 54321}, "10.0.0.5", 54321)
    assert not es_el_mismo_nodo({"host": "10.0.0.5", "port": 54322}, "10.0.0.5", 54321)
    assert not es_el_mismo_nodo({"host": "10.0.0.6", "port": 54321}, "10.0.0.5", 54321)
