"""Hit 7 - Nodo D con inscripciones por ventanas.

El Hit 6 responde "quien esta vivo" con un TTL: la respuesta puede cambiar
en cualquier instante, y dos nodos C que preguntan con medio segundo de
diferencia reciben listas distintas. Aca el tiempo se corta en ventanas
fijas alineadas al reloj de pared, y durante toda una ventana la membresia
es inmutable: todos los C ven exactamente lo mismo.

Tres reglas sostienen el mecanismo:

  1. Alineacion por truncamiento. La ventana que contiene el instante t
     empieza en (t // duracion) * duracion. Nadie negocia nada: cada nodo
     mira su propio reloj y coincide con los demas.

  2. Dos registros. Quien se inscribe durante la ventana W queda anotado en
     W+1 y recibe los pares de W. No entra a la ventana en curso, y por eso
     la ventana en curso no cambia de integrantes a mitad de camino.

  3. La rotacion reemplaza al TTL. En el borde, el futuro pasa a ser el
     presente y el futuro queda vacio. Sobrevivir exige re-inscribirse en
     cada ventana: quien no renueva simplemente no esta en el proximo
     presente.

Cada ventana cerrada se persiste en un archivo JSON, que es la evidencia
que pide el informe.

Este modulo no importa nada de hit6 a proposito: el Dockerfile copia solo
common/ y hit7/, asi que cualquier import a hit6 construiria una imagen que
explota al arrancar.
"""

import functools
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from common.cli import parser_nodo_d
from common.logger import Logger, iso_desde

PUERTO_MINIMO = 1
PUERTO_MAXIMO = 65535
LIMITE_CUERPO = 8192
ARCHIVO_POR_DEFECTO = "data/inscripciones.json"
ENCODING = "utf-8"


def validar_nodo(mensaje: dict) -> tuple[str, int]:
    """Valida el cuerpo de una inscripcion y devuelve (host, port)."""
    host = mensaje.get("host")
    port = mensaje.get("port")

    if not isinstance(host, str) or not host.strip():
        raise ValueError("host debe ser una cadena no vacia")

    # bool es subclase de int en Python: True pasaria como puerto 1.
    if isinstance(port, bool) or not isinstance(port, int):
        raise ValueError("port debe ser un entero")

    if not PUERTO_MINIMO <= port <= PUERTO_MAXIMO:
        raise ValueError(
            f"port debe estar entre {PUERTO_MINIMO} y {PUERTO_MAXIMO}"
        )

    return host.strip(), port


class Ventanas:
    """Registro presente, registro futuro y el historial de lo cerrado.

    Los conjuntos guardan tuplas (host, port). No hace falta el timestamp de
    cada nodo, como en el Hit 6: la pertenencia ya no la decide un TTL sino
    la ventana, y el conjunto hace la inscripcion idempotente por si solo.

    El reloj se recibe por parametro para poder rotar ventanas en las
    pruebas sin dormir sesenta segundos: pytest.ini corta a los treinta.
    """

    def __init__(
        self,
        duracion: float,
        archivo: str,
        log: Logger,
        reloj=time.time,
    ):
        self.duracion = duracion
        self.archivo = archivo
        self.log = log
        self.reloj = reloj

        self._presente: set[tuple[str, int]] = set()
        self._futuro: set[tuple[str, int]] = set()
        self._historial: list[dict] = self._cargar()
        self._ventana_actual = self.id_de_ventana(self.reloj())
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Aritmetica de ventanas
    # ------------------------------------------------------------------

    def inicio_de_ventana(self, instante: float) -> float:
        """Epoch en que empieza la ventana que contiene ese instante."""
        return (instante // self.duracion) * self.duracion

    def id_de_ventana(self, instante: float) -> str:
        """Nombre de la ventana: el ISO de su instante de inicio."""
        return iso_desde(self.inicio_de_ventana(instante))

    def _fin_de_ventana(self, instante: float) -> float:
        return self.inicio_de_ventana(instante) + self.duracion

    # ------------------------------------------------------------------
    # Rotacion
    # ------------------------------------------------------------------

    def rotar_si_corresponde(self) -> None:
        """Cierra la ventana vencida y promueve el futuro a presente.

        Es idempotente: si la ventana calculada es la que ya esta abierta,
        no hace nada. Eso permite llamarla desde dos lugares sin
        coordinarlos, que es justamente lo que hace falta: el hilo del borde
        garantiza que las ventanas se cierren aunque no llegue ningun
        request, y la llamada al principio de cada request garantiza que un
        pedido que entra tres milisegundos despues del borde se atienda con
        la ventana correcta.
        """
        with self._lock:
            id_ahora = self.id_de_ventana(self.reloj())

            if id_ahora == self._ventana_actual:
                return

            cerrada = {
                "ventana": self._ventana_actual,
                "inicio": self._ventana_actual,
                "fin": id_ahora,
                "cantidad": len(self._presente),
                "nodos": [
                    {"host": host, "port": port}
                    for host, port in sorted(self._presente)
                ],
            }
            self._historial.append(cerrada)

            self._presente = self._futuro
            self._futuro = set()
            self._ventana_actual = id_ahora

            abiertos = len(self._presente)
            # Se copia para poder escribir a disco sin el lock tomado.
            historial = list(self._historial)

        self._persistir(historial)

        self.log.info(
            "ventana_cerrada",
            ventana=cerrada["ventana"],
            nodos=cerrada["cantidad"],
        )
        self.log.info("ventana_abierta", ventana=id_ahora, nodos=abiertos)

    # ------------------------------------------------------------------
    # Operaciones que expone el servidor
    # ------------------------------------------------------------------

    def inscribir(self, host: str, port: int) -> dict:
        """Anota el nodo en la ventana futura y devuelve los pares actuales."""
        self.rotar_si_corresponde()
        clave = (host, port)

        with self._lock:
            nuevo = clave not in self._futuro
            self._futuro.add(clave)
            inscriptos = len(self._futuro)
            ventana = self._ventana_actual
            presente = sorted(self._presente)

        ahora = self.reloj()
        siguiente = self._fin_de_ventana(ahora)

        self.log.info(
            "nodo_inscripto",
            host=host,
            port=port,
            nuevo=nuevo,
            ventana=iso_desde(siguiente),
            inscriptos=inscriptos,
        )

        return {
            # `ventana` y `peers` son el contrato del README: la ventana es
            # la del presente, la que corresponde a esos pares.
            "ventana": ventana,
            "peers": [{"host": h, "port": p} for h, p in presente],
            # Campos agregados: no rompen el contrato y le permiten a C
            # alinearse con el borde en lugar de sondear a ciegas.
            "inscripto_en": iso_desde(siguiente),
            "proxima_ventana_en_s": round(siguiente - ahora, 3),
        }

    def pares(self) -> dict:
        """Los nodos de la ventana presente."""
        self.rotar_si_corresponde()

        with self._lock:
            ventana = self._ventana_actual
            presente = sorted(self._presente)

        return {
            "ventana": ventana,
            "peers": [{"host": h, "port": p} for h, p in presente],
        }

    def resumen(self) -> dict:
        """Los contadores que alimentan /health."""
        self.rotar_si_corresponde()
        ahora = self.reloj()

        with self._lock:
            return {
                "nodos_activos": len(self._presente),
                "ventana_actual": self._ventana_actual,
                "ventana_futura": iso_desde(self._fin_de_ventana(ahora)),
                "inscriptos_futuros": len(self._futuro),
                "ventanas_cerradas": len(self._historial),
            }

    def historial(self) -> list[dict]:
        """Las ventanas ya cerradas, en orden cronologico."""
        self.rotar_si_corresponde()

        with self._lock:
            return list(self._historial)

    # ------------------------------------------------------------------
    # Persistencia
    # ------------------------------------------------------------------

    def _cargar(self) -> list[dict]:
        """Recupera el historial del disco. Un archivo roto no tumba el nodo."""
        if not os.path.exists(self.archivo):
            return []

        try:
            with open(self.archivo, encoding=ENCODING) as archivo:
                datos = json.load(archivo)
        except (OSError, ValueError) as error:
            self.log.warn(
                "historial_ilegible",
                archivo=self.archivo,
                error=str(error),
            )
            return []

        if not isinstance(datos, list):
            self.log.warn("historial_con_forma_inesperada", archivo=self.archivo)
            return []

        self.log.info(
            "historial_recuperado",
            archivo=self.archivo,
            ventanas=len(datos),
        )

        return datos

    def _persistir(self, historial: list[dict]) -> None:
        """Escribe el historial completo de forma atomica.

        Se escribe a un temporal y recien despues se hace os.replace, que es
        atomico tanto en POSIX como en Windows. Escribir directamente sobre
        el archivo final dejaria un JSON truncado si el proceso muriera a
        mitad de la escritura, y ese archivo ya no se podria releer.
        """
        carpeta = os.path.dirname(self.archivo)

        if carpeta:
            os.makedirs(carpeta, exist_ok=True)

        temporal = f"{self.archivo}.tmp"

        try:
            with open(temporal, "w", encoding=ENCODING) as archivo:
                json.dump(historial, archivo, ensure_ascii=False, indent=2)

            os.replace(temporal, self.archivo)
        except OSError as error:
            self.log.error(
                "fallo_persistencia",
                archivo=self.archivo,
                error=str(error),
            )


def rotar_periodicamente(ventanas: Ventanas, detener: threading.Event) -> None:
    """Fuerza la rotacion en cada borde, aunque no llegue ningun request.

    Duerme hasta el proximo borde recalculandolo en cada vuelta. Un
    sleep(duracion) fijo acumularia deriva y terminaria desalineado del
    reloj de pared, que es exactamente la propiedad que sostiene todo.
    """
    while not detener.is_set():
        ahora = ventanas.reloj()
        falta = ventanas.inicio_de_ventana(ahora) + ventanas.duracion - ahora

        if detener.wait(max(0.05, falta)):
            return

        ventanas.rotar_si_corresponde()


class ManejadorHTTP(BaseHTTPRequestHandler):
    """Traduce HTTP a llamadas sobre Ventanas.

    La stdlib instancia esta clase una vez por request y resuelve el pedido
    completo dentro de __init__, asi que las dependencias se inyectan como
    argumentos posicionales con functools.partial y se asignan antes de
    llamar al __init__ del padre.
    """

    def __init__(
        self,
        ventanas: Ventanas,
        log: Logger,
        arranque: float,
        *args,
        **kwargs,
    ):
        self.ventanas = ventanas
        self.log = log
        self.arranque = arranque
        super().__init__(*args, **kwargs)

    def log_message(self, formato: str, *args) -> None:
        """Silencia el log estilo Apache: los eventos van por common.logger."""
        return

    # ------------------------------------------------------------------
    # Ruteo
    # ------------------------------------------------------------------

    def do_POST(self) -> None:
        if self.path == "/register":
            self._registrar()
        elif self.path in ("/peers", "/health", "/ventanas"):
            self._responder(405, {"error": "esa ruta solo acepta GET"})
        else:
            self._responder(404, {"error": "ruta desconocida", "ruta": self.path})

    def do_GET(self) -> None:
        if self.path == "/peers":
            self._responder(200, self.ventanas.pares())
        elif self.path == "/health":
            self._health()
        elif self.path == "/ventanas":
            self._responder(200, {"ventanas": self.ventanas.historial()})
        elif self.path == "/register":
            self._responder(405, {"error": "/register solo acepta POST"})
        else:
            self._responder(404, {"error": "ruta desconocida", "ruta": self.path})

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------

    def _registrar(self) -> None:
        try:
            mensaje = self._leer_cuerpo()
            host, port = validar_nodo(mensaje)
        except (ValueError, UnicodeDecodeError) as error:
            self.log.warn(
                "inscripcion_rechazada",
                origen=self.client_address[0],
                error=str(error),
            )
            self._responder(400, {"error": str(error)})
            return

        self._responder(200, self.ventanas.inscribir(host, port))

    def _health(self) -> None:
        """Los cinco campos del contrato, mas los que hacen visible el mecanismo.

        Los cinco originales no se renombran ni se quitan: son los que mira
        el evaluador y el health check del despliegue.
        """
        resumen = self.ventanas.resumen()

        self._responder(
            200,
            {
                "servicio": "registro-d",
                "estado": "ok",
                "nodos_activos": resumen["nodos_activos"],
                "uptime_s": int(self.ventanas.reloj() - self.arranque),
                "ventana_actual": resumen["ventana_actual"],
                "ventana_futura": resumen["ventana_futura"],
                "inscriptos_futuros": resumen["inscriptos_futuros"],
                "ventanas_cerradas": resumen["ventanas_cerradas"],
                "duracion_ventana_s": self.ventanas.duracion,
            },
        )

    # ------------------------------------------------------------------
    # Entrada y salida
    # ------------------------------------------------------------------

    def _leer_cuerpo(self) -> dict:
        try:
            largo = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            raise ValueError("Content-Length invalido")

        if largo <= 0:
            raise ValueError("el cuerpo esta vacio")

        if largo > LIMITE_CUERPO:
            raise ValueError("el cuerpo excede el limite permitido")

        # Hay que leer exactamente Content-Length bytes: read() sin argumento
        # se quedaria esperando un fin de archivo que en HTTP no llega.
        mensaje = json.loads(self.rfile.read(largo).decode(ENCODING))

        if not isinstance(mensaje, dict):
            raise ValueError("el cuerpo debe ser un objeto JSON")

        return mensaje

    def _responder(self, codigo: int, cuerpo: dict) -> None:
        datos = json.dumps(cuerpo, ensure_ascii=False).encode(ENCODING)

        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)


class ServidorD(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def crear_servidor(
    host: str,
    port: int,
    ventanas: Ventanas,
    log: Logger,
) -> ServidorD:
    """Arma el servidor HTTP con las dependencias ya inyectadas."""
    manejador = functools.partial(
        ManejadorHTTP,
        ventanas,
        log,
        ventanas.reloj(),
    )

    return ServidorD((host, port), manejador)


def main() -> None:
    """Lee parametros, arranca la rotacion y atiende hasta la interrupcion."""
    parser = parser_nodo_d("Hit 7 - Nodo D con inscripciones por ventanas")
    parser.add_argument(
        "--archivo",
        default=os.environ.get("ARCHIVO_INSCRIPCIONES", ARCHIVO_POR_DEFECTO),
        help="Donde se persisten las ventanas cerradas",
    )
    args = parser.parse_args()

    if not PUERTO_MINIMO <= args.port <= PUERTO_MAXIMO:
        parser.error("--port debe estar entre 1 y 65535")

    if args.ventana <= 0:
        parser.error("--ventana debe ser mayor que cero")

    log = Logger("nodo-d")
    ventanas = Ventanas(
        duracion=args.ventana,
        archivo=args.archivo,
        log=log,
    )
    servidor = crear_servidor(args.host, args.port, ventanas, log)

    detener = threading.Event()
    hilo = threading.Thread(
        target=rotar_periodicamente,
        args=(ventanas, detener),
        daemon=True,
        name="rotacion-de-ventanas",
    )
    hilo.start()

    log.info(
        "servidor_iniciado",
        host=args.host,
        port=servidor.server_address[1],
        ventana_s=args.ventana,
        ventana_actual=ventanas.id_de_ventana(ventanas.reloj()),
        archivo=args.archivo,
    )

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        log.info("nodo_detenido", motivo="interrupcion_del_usuario")
    finally:
        detener.set()
        servidor.server_close()
        log.info("servidor_detenido", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
