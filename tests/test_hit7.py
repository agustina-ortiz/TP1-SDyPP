"""Pruebas del nodo D y del nodo C del Hit 7."""

import contextlib
import json
import threading
import urllib.request

from common.logger import Logger
from hit7.nodo_c import proxima_espera
from hit7.nodo_d import Ventanas, crear_servidor

VENTANA = 60.0

# 2026-09-08T11:29:37Z: cae a 37 segundos del inicio de su ventana.
INSTANTE = 1_788_866_977.0


class RelojFalso:
    """Reloj controlado a mano: rota ventanas sin dormir sesenta segundos."""

    def __init__(self, inicio: float = INSTANTE):
        self.ahora = inicio

    def __call__(self) -> float:
        return self.ahora

    def avanzar(self, segundos: float) -> None:
        self.ahora += segundos


def construir(tmp_path, reloj=None, archivo=None) -> tuple[Ventanas, Logger]:
    log = Logger("nodo-d-hit7-test", log_dir=str(tmp_path))
    ventanas = Ventanas(
        duracion=VENTANA,
        archivo=archivo or str(tmp_path / "inscripciones.json"),
        log=log,
        reloj=reloj or RelojFalso(),
    )

    return ventanas, log


@contextlib.contextmanager
def nodo_d(tmp_path, reloj=None):
    ventanas, log = construir(tmp_path, reloj=reloj)
    servidor = crear_servidor("127.0.0.1", 0, ventanas, log)

    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()

    try:
        yield servidor.server_address[1], ventanas
    finally:
        servidor.shutdown()
        servidor.server_close()


def obtener(puerto: int, ruta: str) -> dict:
    with urllib.request.urlopen(
        f"http://127.0.0.1:{puerto}{ruta}", timeout=5
    ) as respuesta:
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
# Aritmetica de ventanas
# --------------------------------------------------------------------------

def test_la_ventana_se_alinea_truncando_al_minuto(tmp_path):
    ventanas, _ = construir(tmp_path)

    assert ventanas.id_de_ventana(INSTANTE).endswith(":00Z")
    assert ventanas.inicio_de_ventana(INSTANTE) == INSTANTE - 37


def test_todo_el_minuto_pertenece_a_la_misma_ventana(tmp_path):
    ventanas, _ = construir(tmp_path)
    inicio = ventanas.inicio_de_ventana(INSTANTE)

    assert ventanas.id_de_ventana(inicio) == ventanas.id_de_ventana(inicio + 59.9)
    assert ventanas.id_de_ventana(inicio) != ventanas.id_de_ventana(inicio + 60)


# --------------------------------------------------------------------------
# Presente y futuro
# --------------------------------------------------------------------------

def test_el_que_se_inscribe_no_entra_a_la_ventana_en_curso(tmp_path):
    ventanas, _ = construir(tmp_path)

    respuesta = ventanas.inscribir("10.0.0.5", 9001)

    assert respuesta["peers"] == []
    assert respuesta["inscripto_en"] != respuesta["ventana"]
    assert ventanas.pares()["peers"] == []
    assert ventanas.resumen()["inscriptos_futuros"] == 1


def test_la_rotacion_promueve_el_futuro_a_presente(tmp_path):
    reloj = RelojFalso()
    ventanas, _ = construir(tmp_path, reloj=reloj)

    inscripcion = ventanas.inscribir("10.0.0.5", 9001)
    reloj.avanzar(VENTANA)

    pares = ventanas.pares()

    assert pares["peers"] == [{"host": "10.0.0.5", "port": 9001}]
    assert pares["ventana"] == inscripcion["inscripto_en"]
    assert ventanas.resumen()["inscriptos_futuros"] == 0


def test_el_que_no_renueva_desaparece_en_la_ventana_siguiente(tmp_path):
    reloj = RelojFalso()
    ventanas, _ = construir(tmp_path, reloj=reloj)

    ventanas.inscribir("10.0.0.5", 9001)

    reloj.avanzar(VENTANA)
    assert len(ventanas.pares()["peers"]) == 1

    reloj.avanzar(VENTANA)
    assert ventanas.pares()["peers"] == []


def test_inscribirse_dos_veces_no_duplica(tmp_path):
    reloj = RelojFalso()
    ventanas, _ = construir(tmp_path, reloj=reloj)

    ventanas.inscribir("10.0.0.5", 9001)
    ventanas.inscribir("10.0.0.5", 9001)
    reloj.avanzar(VENTANA)

    assert ventanas.pares()["peers"] == [{"host": "10.0.0.5", "port": 9001}]


def test_rotar_dos_veces_en_la_misma_ventana_no_cierra_dos(tmp_path):
    reloj = RelojFalso()
    ventanas, _ = construir(tmp_path, reloj=reloj)

    reloj.avanzar(VENTANA)
    ventanas.rotar_si_corresponde()
    ventanas.rotar_si_corresponde()

    assert ventanas.resumen()["ventanas_cerradas"] == 1


def test_proxima_ventana_en_s_cuenta_lo_que_falta(tmp_path):
    ventanas, _ = construir(tmp_path)
    respuesta = ventanas.inscribir("10.0.0.5", 9001)

    # El instante de prueba cae a 37 segundos del inicio de su ventana.
    assert respuesta["proxima_ventana_en_s"] == 23.0


# --------------------------------------------------------------------------
# Persistencia
# --------------------------------------------------------------------------

def test_persiste_dos_ventanas_consecutivas(tmp_path):
    reloj = RelojFalso()
    archivo = tmp_path / "inscripciones.json"
    ventanas, _ = construir(tmp_path, reloj=reloj, archivo=str(archivo))

    # Ventana W: se inscriben dos. Todavia no estan en ningun presente.
    ventanas.inscribir("10.0.0.5", 9001)
    ventanas.inscribir("10.0.0.9", 9002)

    # Ventana W+1: los dos pasan al presente y solo uno renueva.
    reloj.avanzar(VENTANA)
    ventanas.inscribir("10.0.0.5", 9001)

    # Ventana W+2: queda solo el que renovo, y renueva otra vez.
    reloj.avanzar(VENTANA)
    ventanas.inscribir("10.0.0.5", 9001)

    # Ventana W+3: se cierra W+2. Una ventana solo se persiste al cerrarse.
    reloj.avanzar(VENTANA)
    ventanas.rotar_si_corresponde()

    guardadas = json.loads(archivo.read_text(encoding="utf-8"))

    assert len(guardadas) == 3
    # La primera cerro vacia: nadie alcanzo a estar en el presente de W.
    assert guardadas[0]["cantidad"] == 0
    assert guardadas[1]["cantidad"] == 2
    assert guardadas[2]["cantidad"] == 1

    # Las ventanas son consecutivas: el fin de una es el nombre de la siguiente.
    assert guardadas[0]["fin"] == guardadas[1]["ventana"]
    assert guardadas[1]["fin"] == guardadas[2]["ventana"]
    assert guardadas[2]["nodos"] == [{"host": "10.0.0.5", "port": 9001}]


def test_recupera_el_historial_al_reiniciar(tmp_path):
    reloj = RelojFalso()
    archivo = str(tmp_path / "inscripciones.json")
    ventanas, _ = construir(tmp_path, reloj=reloj, archivo=archivo)

    ventanas.inscribir("10.0.0.5", 9001)
    reloj.avanzar(VENTANA)
    ventanas.rotar_si_corresponde()

    revivido, _ = construir(tmp_path, reloj=RelojFalso(), archivo=archivo)

    assert revivido.resumen()["ventanas_cerradas"] == 1


def test_un_archivo_corrupto_no_tumba_el_arranque(tmp_path):
    archivo = tmp_path / "inscripciones.json"
    archivo.write_text("{roto", encoding="utf-8")

    ventanas, log = construir(tmp_path, archivo=str(archivo))

    assert ventanas.resumen()["ventanas_cerradas"] == 0
    assert "historial_ilegible" in [r["evento"] for r in log.recientes()]


def test_la_escritura_no_deja_temporales(tmp_path):
    reloj = RelojFalso()
    archivo = tmp_path / "inscripciones.json"
    ventanas, _ = construir(tmp_path, reloj=reloj, archivo=str(archivo))

    reloj.avanzar(VENTANA)
    ventanas.rotar_si_corresponde()

    assert archivo.exists()
    assert not (tmp_path / "inscripciones.json.tmp").exists()


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

def test_health_conserva_los_cinco_campos_del_contrato(tmp_path):
    with nodo_d(tmp_path) as (puerto, _):
        salud = obtener(puerto, "/health")

        assert {
            "servicio",
            "estado",
            "nodos_activos",
            "uptime_s",
            "ventana_actual",
        } <= set(salud)
        assert salud["servicio"] == "registro-d"
        assert salud["estado"] == "ok"


def test_register_inscribe_en_la_ventana_siguiente(tmp_path):
    reloj = RelojFalso()

    with nodo_d(tmp_path, reloj=reloj) as (puerto, ventanas):
        respuesta = publicar(puerto, "/register", {"host": "10.0.0.5", "port": 9001})

        assert respuesta["peers"] == []
        assert respuesta["inscripto_en"] == ventanas.id_de_ventana(
            reloj() + VENTANA
        )
        assert obtener(puerto, "/health")["inscriptos_futuros"] == 1


def test_ventanas_expone_el_historial(tmp_path):
    reloj = RelojFalso()

    with nodo_d(tmp_path, reloj=reloj) as (puerto, _):
        publicar(puerto, "/register", {"host": "10.0.0.5", "port": 9001})
        reloj.avanzar(VENTANA)

        historial = obtener(puerto, "/ventanas")["ventanas"]

        assert len(historial) == 1
        assert historial[0]["cantidad"] == 0


# --------------------------------------------------------------------------
# Nodo C
# --------------------------------------------------------------------------

def test_c_se_despierta_en_el_borde_si_falta_menos_que_el_intervalo():
    assert proxima_espera(5.0, {"proxima_ventana_en_s": 1.0}) == 1.2
    assert proxima_espera(5.0, {"proxima_ventana_en_s": 23.0}) == 5.0
    assert proxima_espera(5.0, {}) == 5.0
    assert proxima_espera(5.0, {"proxima_ventana_en_s": "23"}) == 5.0
