"""Hit 1 - Nodo A (cliente).

Se conecta al nodo B y lo saluda.

===========================================================================
MACHETE
===========================================================================

El servidor hace bind + listen + accept porque ESPERA a que lo llamen.
El cliente no espera a nadie: crea el socket y se conecta. Nada mas.

    cliente = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    cliente.connect(("127.0.0.1", 9001))     <-- tupla, doble parentesis

Despues de connect(), ese mismo socket YA ES el canio: se usa directamente
con cliente.sendall(...) y cliente.recv(...).

Diferencia clave con el servidor: el cliente NO tiene una variable
`conexion` aparte, porque no acepta a nadie. Usa siempre el mismo socket.

Vale todo lo demas de la chuleta del servidor: bytes, .encode(), .decode().

EL ERROR QUE VAS A VER SEGURO
-----------------------------
    ConnectionRefusedError: [WinError 10061]

Significa "no hay nadie escuchando de ese lado". Casi siempre es una de dos:
te olvidaste de arrancar el servidor primero, o los puertos no coinciden.

===========================================================================
COMO PROBARLO
===========================================================================

   Terminal 1:   python hit1/servidor.py      <-- este PRIMERO
   Terminal 2:   python hit1/cliente.py

===========================================================================
"""

import socket

HOST = "127.0.0.1"   # tiene que ser el mismo que el del servidor
PORT = 9001          # este tambien


def main():
    # -----------------------------------------------------------------
    # TODO 1 - Crear el socket, igual que en el servidor.
    #          Guardalo en una variable llamada `cliente`.
    # -----------------------------------------------------------------
    cliente = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # -----------------------------------------------------------------
    # TODO 2 - Conectarse al servidor con connect().
    #          Acordate de la tupla (HOST, PORT).
    # -----------------------------------------------------------------
    cliente.connect((HOST, PORT))

    print(f"[A] Conectado a {HOST}:{PORT}")

    # -----------------------------------------------------------------
    # TODO 3 - Enviar el saludo.
    #          a) saludo = "hola B, soy A"
    #          b) cliente.sendall(...) con .encode()
    # -----------------------------------------------------------------
    saludo = "hola B, soy A"
    cliente.sendall(saludo.encode())

    print("[A] Saludo enviado. Esperando respuesta...")

    # -----------------------------------------------------------------
    # TODO 4 - Recibir la respuesta de B y mostrarla.
    #          a) cliente.recv(1024)
    #          b) .decode()
    #          c) imprimirla
    # -----------------------------------------------------------------
    respuesta = cliente.recv(1024).decode()
    print(f"[A] Recibido: {respuesta}")

    cliente.close()


if __name__ == "__main__":
    main()
