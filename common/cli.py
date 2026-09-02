"""Parseo de parametros comun a todos los Hits.

El enunciado pide que los programas se ejecuten desde la terminal, sin IDE.
Todos los Hits usan las mismas banderas para no tener que recordar cual es cual.
"""

import argparse


def parser_nodo_c(descripcion: str) -> argparse.ArgumentParser:
    """Hits 4 y 5: C recibe donde escuchar y a que par conectarse."""
    p = argparse.ArgumentParser(description=descripcion)
    p.add_argument("--listen-host", default="0.0.0.0", help="IP donde escuchar")
    p.add_argument("--listen-port", type=int, required=True, help="Puerto donde escuchar")
    p.add_argument("--peer-host", help="IP del otro nodo C")
    p.add_argument("--peer-port", type=int, help="Puerto del otro nodo C")
    p.add_argument("--intervalo", type=float, default=5.0, help="Segundos entre saludos")
    return p


def parser_nodo_c_con_registro(descripcion: str) -> argparse.ArgumentParser:
    """Hits 6, 7 y 8: C solo conoce a D y escucha en un puerto aleatorio."""
    p = argparse.ArgumentParser(description=descripcion)
    p.add_argument("--d-host", required=True, help="IP del nodo D (registro)")
    p.add_argument("--d-port", type=int, required=True, help="Puerto HTTP del nodo D")
    p.add_argument("--intervalo", type=float, default=5.0, help="Segundos entre saludos")
    return p


def parser_nodo_d(descripcion: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=descripcion)
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--ventana", type=int, default=60, help="Duracion de la ventana en segundos")
    return p
