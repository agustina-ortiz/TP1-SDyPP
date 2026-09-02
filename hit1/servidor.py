"""Hit 1 - Nodo B (servidor).

Espera el saludo del nodo A y lo responde.

===========================================================================
MACHETE
===========================================================================

1) UN SOCKET ES UN "CANIO" ENTRE DOS PROCESOS
   Se crea asi:

       s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

   AF_INET      = direcciones IPv4 (las de toda la vida, 127.0.0.1)
   SOCK_STREAM  = TCP (el otro seria SOCK_DGRAM, que es UDP)

2) LAS DIRECCIONES SON TUPLAS, NO DOS ARGUMENTOS
   Se escribe con DOBLE parentesis:

       s.bind(("127.0.0.1", 9001))     <-- bien
       s.bind("127.0.0.1", 9001)       <-- error tipico

3) LOS SOCKETS SOLO HABLAN BYTES, NO TEXTO
   Un string de Python no se puede mandar tal cual. Hay que convertir:

       "hola".encode()   ->  b"hola"      (texto -> bytes, para ENVIAR)
       datos.decode()    ->  "hola"       (bytes -> texto, para LEER)

   Los bytes se notan con una b adelante: b"hola"

4) recv() ESPERA (BLOQUEA)
   conexion.recv(1024) frena el programa hasta que llegue algo.
   El 1024 significa "leeme como mucho 1024 bytes".
   Si devuelve b"" (vacio), significa que el otro lado CERRO la conexion.

5) LOS CUATRO PASOS DE UN SERVIDOR, SIEMPRE EN ESTE ORDEN

       bind()     "me reservo esta IP y este puerto"
       listen()   "quedo a la espera de conexiones"
       accept()   "acepto UNA conexion" -> devuelve (conexion, direccion)
       recv/send  "converso por esa conexion"

   Ojo: accept() devuelve DOS cosas a la vez. En Python eso se recibe asi:

       conexion, direccion = servidor.accept()

   servidor sigue escuchando; conexion es el canio hacia ESE cliente.
   Son dos objetos distintos y es la confusion mas comun al empezar.

6) SO_REUSEADDR
   Cuando cerras un servidor, el sistema operativo deja el puerto "en
   enfriamiento" unos segundos (estado TIME_WAIT). Si lo volves a levantar
   enseguida, explota con "Address already in use". Esta linea lo evita:

       servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

   Es una linea magica: ponela y segui. Te va a ahorrar un dolor de cabeza.

===========================================================================
COMO PROBARLO
===========================================================================

   Terminal 1:   python hit1/servidor.py      <-- este PRIMERO
   Terminal 2:   python hit1/cliente.py

   Para cortar el servidor: Ctrl+C

===========================================================================
"""

import socket

HOST = "127.0.0.1"   # localhost: solo acepta conexiones de esta misma maquina
PORT = 9001


def main():
    # -----------------------------------------------------------------
    # TODO 1 - Crear el socket del servidor (punto 1 de la chuleta).
    #          Guardalo en una variable que se llame `servidor`.
    # -----------------------------------------------------------------
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # -----------------------------------------------------------------
    # TODO 2 - Pegar la linea magica de SO_REUSEADDR (punto 6).
    # -----------------------------------------------------------------
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)


    # -----------------------------------------------------------------
    # TODO 3 - bind() y listen().
    #          bind lleva UNA tupla (HOST, PORT): doble parentesis.
    #          listen() puede ir sin argumentos.
    # -----------------------------------------------------------------
    servidor.bind((HOST, PORT))
    servidor.listen()

    print(f"[B] Escuchando en {HOST}:{PORT}. Esperando el saludo de A...")

    # -----------------------------------------------------------------
    # TODO 4 - Aceptar la conexion.
    #          accept() devuelve DOS valores (punto 5).
    #          Llamalos `conexion` y `direccion`.
    # -----------------------------------------------------------------
    conexion, direccion = servidor.accept()

    print(f"[B] Se conecto A desde {direccion}")

    # -----------------------------------------------------------------
    # TODO 5 - Recibir el saludo y mostrarlo.
    #          a) leer con conexion.recv(1024)  -> te da BYTES
    #          b) convertirlos a texto con .decode()
    #          c) imprimirlo
    # -----------------------------------------------------------------
    saludo = conexion.recv(1024).decode()
    print(f"[B] Recibido: {saludo}")

    # -----------------------------------------------------------------
    # TODO 6 - Responder el saludo.
    #          a) armar el texto, por ejemplo:
    #                 respuesta = "hola A, te escucho"
    #          b) enviarlo con conexion.sendall(...)
    #             Acordate de .encode(): sendall NO acepta texto (punto 3).
    # -----------------------------------------------------------------
    respuesta = "hola A, te escucho"
    conexion.sendall(respuesta.encode())

    print("[B] Respuesta enviada. Cierro y termino.")

    # Cerrar los dos sockets: primero la conversacion, despues la oreja.
    conexion.close()
    servidor.close()


if __name__ == "__main__":
    # Significa "si me ejecutan directamente, corre main()".
    # Si otro archivo importa este como modulo, main() NO se dispara.
    main()
