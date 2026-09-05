"""Descubrimiento de la direccion local de un nodo.

Desde el Hit 6 los nodos C escuchan en 0.0.0.0, que no es una direccion que
puedan anunciar: significa "todas las interfaces". Para registrarse en D
necesitan saber que IP concreta veria D del otro lado.

El truco es un socket UDP. connect() sobre UDP no envia ni un byte, porque
UDP no tiene handshake: lo unico que hace es pedirle al kernel que resuelva
la ruta hacia ese destino y fije la direccion de origen del socket, que
despues se lee con getsockname(). Es una consulta a la tabla de ruteo del
sistema operativo disfrazada de socket.

Es preferible a gethostbyname(gethostname()), que en una maquina con varias
interfaces devuelve cualquiera de ellas, o 127.0.1.1 en varias distribuciones
de Linux.
"""

import socket


def descubrir_host_local(destino_host: str, destino_port: int) -> str:
    """IP local que el sistema usaria para alcanzar ese destino."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as consulta:
        consulta.connect((destino_host, destino_port))
        return consulta.getsockname()[0]
