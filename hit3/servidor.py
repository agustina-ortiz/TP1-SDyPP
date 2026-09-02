"""Hit 3 - Nodo B (servidor resiliente).

Si A se muere, B no se entera ni le importa: sigue en pie esperando al
proximo que lo salude.

===========================================================================
MACHETE
===========================================================================

LA IDEA EN UNA LINEA
--------------------
En el Hit 1 el servidor atendia UN saludo y se moria. Ahora tiene que
atender clientes para siempre. Eso se resuelve con DOS bucles anidados.


1) LOS DOS BUCLES: CUAL ES CUAL

   Es lo unico realmente nuevo del Hit 3, y confundirlos es el error
   clasico. Mirá la diferencia:

       while True:                          <-- BUCLE DE AFUERA
           conexion, direccion = accept()       "atiendo un cliente,
                                                 despues el siguiente,
                                                 despues el siguiente..."

           while True:                      <-- BUCLE DE ADENTRO
               datos = conexion.recv(1024)     "converso con ESTE cliente
               ...                              hasta que se vaya"

   El de afuera gira UNA VEZ POR CLIENTE.
   El de adentro gira UNA VEZ POR MENSAJE de ese cliente.

   Cuando el cliente se va, se sale del bucle de adentro pero NO del de
   afuera: se vuelve a accept() y el servidor queda esperando al proximo.

   En este archivo el bucle de adentro esta en la funcion atender(),
   para que no se mezclen.


2) COMO SE ENTERA B DE QUE A SE FUE

   Son exactamente los dos casos del Hit 2, pero del otro lado del canio:

     a) A cierra ordenado      -> recv() devuelve b"" (vacio). Sin error.
     b) A muere de golpe       -> recv() lanza ConnectionResetError.

   Los dos hay que manejarlos, o el servidor se cae igual que antes.
   El (a) con un `if not datos`, el (b) con un try/except.


3) DONDE VA EL try: ALREDEDOR DE LA CONVERSACION, NO DEL accept()

   Este es el punto fino del Hit 3. Si el try envuelve todo el bucle de
   afuera, un cliente que se muere te tira abajo el servidor igual,
   porque el error rompe el bucle entero.

   Lo que hay que envolver es la conversacion con UN cliente:

       while True:
           conexion, direccion = servidor.accept()
           try:
               atender(conexion, direccion)     <-- solo esto
           except OSError as error:
               print("ese cliente se cayo, sigo")
           finally:
               conexion.close()

   Asi, si un cliente explota, se pierde ESE cliente y nada mas.
   El bucle de afuera sigue girando.


4) finally SIEMPRE CIERRA

   `finally` corre haya salido bien o haya explotado. Es el lugar
   correcto para cerrar la conexion. Si no cerras, cada cliente que
   pasa te deja un descriptor de archivo abierto y con el tiempo el
   sistema operativo te corta el suministro.


5) LIMITACION QUE HAY QUE DOCUMENTAR (va al README)

   Este servidor atiende UN cliente por vez. Si mientras conversa con A
   se conecta otro, ese segundo queda esperando en la cola de listen()
   hasta que A se vaya.

   No es un bug del Hit 3: el enunciado pide sobrevivir, no atender en
   paralelo. Pero es una limitacion real y conviene escribirla en la
   seccion "Limitaciones conocidas" del README. Se resuelve con hilos
   (threading), que aparecen recien cuando un nodo tiene que escuchar y
   hablar al mismo tiempo, en los Hits 4 y 6.


6) POR QUE EL Ctrl+C NO FUNCIONABA EN WINDOWS (y esto TAMBIEN va al README)

   En Windows, Ctrl+C NO puede interrumpir una llamada de socket que esta
   bloqueada. Cuando el servidor espera en accept() sin ningun cliente, se
   queda adentro de Winsock y Python no llega a procesar la senial hasta
   que esa llamada devuelva. Y accept() sin clientes no devuelve nunca:
   el servidor parece ignorar el Ctrl+C.

   La solucion es no bloquear indefinidamente:

       servidor.settimeout(1.0)     # despertate cada 1 segundo

       try:
           conexion, direccion = servidor.accept()
       except TimeoutError:
           continue                 # no vino nadie, vuelvo a esperar

   Cada vez que accept() se rinde por timeout, Python vuelve a su bucle
   principal y ahi si atiende el Ctrl+C. El costo es despertarse una vez
   por segundo sin hacer nada, que es despreciable.

   OJO con el orden de los except: TimeoutError ES un OSError. Si pusieras
   `except OSError` antes, se comeria los timeouts y nunca llegarias al
   `continue`. Por eso el timeout se ataja aparte y arriba.

   Esto es material de informe: es la falacia "la latencia es cero".
   Un sistema distribuido no puede quedarse esperando para siempre a que
   el otro lado conteste; siempre hay que poner un limite de tiempo.

===========================================================================
COMO PROBARLO
===========================================================================

   Terminal 1:   python hit3/servidor.py
   Terminal 2:   python hit3/cliente.py

   La prueba de fuego:

     1. Arranca el servidor y despues el cliente.
        Tienen que saludarse cada 3 segundos, en loop.

     2. Mata el CLIENTE con Ctrl+C.
        El servidor NO se tiene que morir: tiene que avisar que A se fue
        y quedar esperando de nuevo.

     3. Volve a levantar el cliente.
        El servidor lo tiene que atender como si nada.

     4. Repeti el paso 2 y 3 tres o cuatro veces seguidas.
        El servidor tiene que seguir en pie despues de todas.

   Si el servidor aguanta eso sin cerrarse nunca, el Hit 3 esta.

===========================================================================
"""

import socket

HOST = "127.0.0.1"
PORT = 9001


def atender(conexion, direccion):
    """Conversa con UN cliente hasta que se va.

    Este es el bucle de ADENTRO (punto 1). Cuando termina -por return o
    por excepcion- el control vuelve a main(), que espera al proximo.
    """
    while True:
        # -------------------------------------------------------------
        # TODO 1 - Recibir el saludo, chequeando el corte limpio.
        #          Es identico a lo que hiciste en el cliente del Hit 2,
        #          pero aca leyendo de `conexion`:
        #            a) datos = conexion.recv(1024)
        #            b) si esta vacio -> A se fue ordenado: avisa y return
        #            c) si no, .decode() e imprimilo
        # -------------------------------------------------------------
        datos = conexion.recv(1024)
        if not datos:
            print(f"[B] A se fue ordenado. Volviendo a esperar clientes...")
            return
        print(f"[B] Recibido: {datos.decode()}")

        # -------------------------------------------------------------
        # TODO 2 - Responder el saludo.
        #          Igual que en el Hit 1: sendall con .encode()
        # -------------------------------------------------------------
        respuesta="hola A, soy B"
        conexion.sendall(respuesta.encode())


def main():
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    servidor.bind((HOST, PORT))
    servidor.listen()

    # Sin esto, en Windows el Ctrl+C no funciona (punto 6 del machete):
    # accept() se queda bloqueado para siempre y Python nunca llega a
    # procesar la senial. Con el timeout se despierta cada segundo.
    servidor.settimeout(1.0)

    print(f"[B] Escuchando en {HOST}:{PORT}. Listo para atender clientes.")

    try:
        # -----------------------------------------------------------------
        # TODO 3 - El bucle de AFUERA: un cliente tras otro, para siempre.
        #          Escribi el `while True:` y adentro:
        #
        #            a) conexion, direccion = servidor.accept()
        #            b) print avisando quien se conecto
        #            c) un try / except / finally con la estructura del
        #               punto 3 del machete:
        #                  try:      atender(conexion, direccion)
        #                  except:   OSError as error -> avisar y seguir
        #                  finally:  conexion.close()
        #
        #          OJO: el except NO lleva `return` ni `break`. La gracia
        #          del Hit 3 es justamente que el bucle siga girando.
        # -----------------------------------------------------------------
        while True:
            try:
                conexion, direccion = servidor.accept()
            except TimeoutError:
                # Paso un segundo y no vino nadie. Volvemos a esperar, pero
                # en el camino Python aprovecha para atender el Ctrl+C.
                continue

            print(f"[B] Cliente conectado desde {direccion}")

            try:
                atender(conexion, direccion)
            except OSError as error:
                print(f"[B] Ese cliente se cayo: {error}. Sigo esperando...")
            finally:
                conexion.close()

    except KeyboardInterrupt:
        # Ctrl+C sobre el servidor: este si lo cierra, y esta bien que lo haga.
        print("\n[B] Cortado por el usuario.")

    finally:
        servidor.close()


if __name__ == "__main__":
    main()
