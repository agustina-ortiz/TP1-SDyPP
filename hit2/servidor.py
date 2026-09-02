"""Hit 2 - Nodo B (servidor).

SIN CAMBIOS respecto del Hit 1: el enunciado pide modificar solo el nodo A.
Esta copia esta aca para poder matarlo y ver como A reconecta.

Para probar el Hit 2 vas a matar este proceso con Ctrl+C y despues volver
a levantarlo. El cliente tiene que aguantar las dos cosas.
"""

import socket

HOST = "127.0.0.1"
PORT = 9001


def main():
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    servidor.bind((HOST, PORT))
    servidor.listen()

    print(f"[B] Escuchando en {HOST}:{PORT}. Esperando el saludo de A...")

    conexion, direccion = servidor.accept()

    print(f"[B] Se conecto A desde {direccion}")

    saludo = conexion.recv(1024).decode()
    print(f"[B] Recibido: {saludo}")

    respuesta = "hola A, te escucho"
    conexion.sendall(respuesta.encode())

    print("[B] Respuesta enviada. Cierro y termino.")

    conexion.close()
    servidor.close()


if __name__ == "__main__":
    main()
