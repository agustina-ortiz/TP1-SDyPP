"""Hit 6 - Nodo D, registro de contactos.

Hasta el Hit 5 cada nodo C recibia por linea de comandos la direccion de su
par. Eso obliga a conocer la topologia de antemano y no sobrevive a que
cambie. Aca aparece D: un registro central en RAM al que cada C se anuncia y
que le devuelve quienes mas estan activos. Recien entonces C puede escuchar
en un puerto que le asigna el sistema operativo, porque ya nadie necesita
saberlo por adelantado.

Un nodo esta activo mientras siga registrandose: el POST /register es a la
vez alta y latido, y quien no vuelve dentro del TTL se considera caido. No
hay endpoint de keep-alive separado.
"""

import functools
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from common.cli import parser_nodo_d
from common.logger import Logger, iso_desde

PUERTO_MINIMO = 1
PUERTO_MAXIMO = 65535
LIMITE_CUERPO = 8192
ENCODING = "utf-8"


def ventana_actual(duracion: float, instante: float) -> str:
    """Identificador de la ventana de tiempo que contiene ese instante.

    En el Hit 6 el campo `ventana` del contrato todavia no tiene semantica:
    se informa el minuto en curso para que la forma del mensaje sea
    identica a la del Hit 7, que si lo usa. hit8/nodo_c.py ya lee este
    campo, asi que cambiarlo despues costaria tocar codigo ajeno.
    """
    return iso_desde((instante // duracion) * duracion)


def validar_nodo(mensaje: dict) -> tuple[str, int]:
    """Valida el cuerpo de un registro y devuelve (host, port) normalizados."""
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


class Registro:
    """Nodos C activos, en memoria, con expiracion por TTL.

    La clave del diccionario es la tupla (host, port). Esa eleccion hace que
    el alta y el refresco sean la misma operacion: un C que se re-registra
    cada tres segundos no genera duplicados ni obliga a recorrer nada.

    El reloj se recibe por parametro para poder probar la expiracion sin
    dormir: pytest.ini corta cualquier prueba a los 30 segundos.
    """

    def __init__(self, ttl: float, log: Logger, reloj=time.time):
        self.ttl = ttl
        self.log = log
        self.reloj = reloj
        self._nodos: dict[tuple[str, int], float] = {}

        # ThreadingHTTPServer atiende un request por hilo: dos nodos C pueden
        # registrarse exactamente al mismo tiempo.
        self._lock = threading.Lock()

    def registrar(self, host: str, port: int) -> None:
        """Da de alta el nodo o refresca su ultimo visto."""
        clave = (host, port)

        with self._lock:
            nuevo = clave not in self._nodos
            self._nodos[clave] = self.reloj()
            total = len(self._nodos)

        self.log.info(
            "nodo_registrado",
            host=host,
            port=port,
            nuevo=nuevo,
            activos=total,
        )

    def activos(self) -> list[dict]:
        """Purga los vencidos y devuelve los nodos vivos, ordenados."""
        limite = self.reloj() - self.ttl

        with self._lock:
            # La lista de vencidos se arma antes de borrar: no se puede
            # modificar un diccionario mientras se lo itera.
            vencidos = [
                clave
                for clave, visto in self._nodos.items()
                if visto < limite
            ]

            for clave in vencidos:
                del self._nodos[clave]

            claves = sorted(self._nodos)

        # Escribir en el log toca disco. Se hace fuera del lock para no
        # frenar a los demas hilos durante la escritura.
        for host, port in vencidos:
            self.log.info("nodo_expirado", host=host, port=port)

        return [{"host": host, "port": port} for host, port in claves]

    def cantidad(self) -> int:
        """Cantidad de nodos activos, para /health."""
        return len(self.activos())


class ManejadorHTTP(BaseHTTPRequestHandler):
    """Traduce HTTP a llamadas sobre Registro.

    La stdlib instancia esta clase una vez por request y resuelve el pedido
    completo dentro de __init__, asi que las dependencias se inyectan como
    argumentos posicionales con functools.partial y se asignan antes de
    llamar al __init__ del padre.
    """

    def __init__(
        self,
        registro: Registro,
        log: Logger,
        arranque: float,
        duracion_ventana: float,
        *args,
        **kwargs,
    ):
        self.registro = registro
        self.log = log
        self.arranque = arranque
        self.duracion_ventana = duracion_ventana
        super().__init__(*args, **kwargs)

    def log_message(self, formato: str, *args) -> None:
        """Silencia el log estilo Apache de la stdlib.

        Los eventos del nodo se emiten por common.logger en formato JSON;
        mezclar los dos formatos en stderr haria ilegible la evidencia.
        """
        return

    # ------------------------------------------------------------------
    # Ruteo
    # ------------------------------------------------------------------

    def do_POST(self) -> None:
        if self.path == "/register":
            self._registrar()
        elif self.path in ("/peers", "/health"):
            self._responder(405, {"error": "esa ruta solo acepta GET"})
        else:
            self._responder(404, {"error": "ruta desconocida", "ruta": self.path})

    def do_GET(self) -> None:
        if self.path == "/peers":
            self._responder(200, self._cuerpo_peers())
        elif self.path == "/health":
            self._health()
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
                "registro_rechazado",
                origen=self.client_address[0],
                error=str(error),
            )
            self._responder(400, {"error": str(error)})
            return

        self.registro.registrar(host, port)
        self._responder(200, self._cuerpo_peers())

    def _health(self) -> None:
        ahora = self.registro.reloj()

        self._responder(
            200,
            {
                "servicio": "registro-d",
                "estado": "ok",
                "nodos_activos": self.registro.cantidad(),
                "uptime_s": int(ahora - self.arranque),
                "ventana_actual": ventana_actual(self.duracion_ventana, ahora),
            },
        )

    def _cuerpo_peers(self) -> dict:
        """La respuesta que comparten /register y /peers.

        D devuelve siempre la lista completa, incluido quien pregunta: /peers
        no sabe quien es el que llama, asi que no podria excluirlo, y hacer
        que /register se comportara distinto le daria dos significados a la
        misma palabra. Es el nodo C el que se saltea a si mismo.
        """
        return {
            "ventana": ventana_actual(
                self.duracion_ventana,
                self.registro.reloj(),
            ),
            "peers": self.registro.activos(),
        }

    # ------------------------------------------------------------------
    # Entrada y salida
    # ------------------------------------------------------------------

    def _leer_cuerpo(self) -> dict:
        """Lee el cuerpo del request como objeto JSON."""
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
    registro: Registro,
    log: Logger,
    duracion_ventana: float,
) -> ServidorD:
    """Arma el servidor HTTP con las dependencias ya inyectadas."""
    manejador = functools.partial(
        ManejadorHTTP,
        registro,
        log,
        registro.reloj(),
        duracion_ventana,
    )

    return ServidorD((host, port), manejador)


def main() -> None:
    """Lee parametros y atiende hasta que se interrumpe el proceso."""
    parser = parser_nodo_d("Hit 6 - Nodo D, registro de contactos")
    args = parser.parse_args()

    if not PUERTO_MINIMO <= args.port <= PUERTO_MAXIMO:
        parser.error("--port debe estar entre 1 y 65535")

    if args.ventana <= 0:
        parser.error("--ventana debe ser mayor que cero")

    log = Logger("nodo-d")

    # En el Hit 6 --ventana se usa como TTL. El mismo numero pasa a ser la
    # duracion de la ventana en el Hit 7.
    registro = Registro(ttl=args.ventana, log=log)
    servidor = crear_servidor(args.host, args.port, registro, log, args.ventana)

    log.info(
        "servidor_iniciado",
        host=args.host,
        port=servidor.server_address[1],
        ttl_s=args.ventana,
    )

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        log.info("nodo_detenido", motivo="interrupcion_del_usuario")
    finally:
        servidor.server_close()
        log.info("servidor_detenido", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
