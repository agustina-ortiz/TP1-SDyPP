"""Hit 2 - Nodo A (cliente con reconexion).

Si B se cae, A no se muere: espera, reconecta y vuelve a saludar.

===========================================================================
MACHETE
===========================================================================

LO NUEVO RESPECTO DEL HIT 1
---------------------------
En el Hit 1, si B no estaba, A explotaba con ConnectionRefusedError y
chau. Ahora A tiene que aguantar. Aparecen tres cosas nuevas:

    while True     - repetir para siempre
    try / except   - atajar el error en vez de morir
    time.sleep()   - esperar antes de reintentar


1) try / except: ATAJAR UN ERROR EN VEZ DE MORIR

       try:
           # codigo que puede fallar
           cliente.connect((HOST, PORT))
       except ConnectionRefusedError:
           # que hacer si justo ese error pasa
           print("no hay nadie del otro lado")

   Sin el try, el error corta el programa. Con el try, el programa
   sigue vivo y vos decidis que hacer.

   Se pueden atajar varios errores juntos con una tupla:

       except (ConnectionRefusedError, ConnectionResetError, OSError):


2) LOS TRES ERRORES QUE TE INTERESAN

   ConnectionRefusedError  B no esta levantado (todavia o ya no)
   ConnectionResetError    B se murio de golpe MIENTRAS conversaban
   OSError                 el error "padre" de los dos: los cubre a ambos
                           y a varios mas. Atajando OSError estas cubierta.


3) HAY UNA CAIDA QUE NO LANZA NINGUN ERROR

   Si B cierra la conexion de forma ordenada, recv() no explota:
   devuelve b"" (bytes vacios). Eso NO es un mensaje vacio, es el aviso
   de "se termino la conexion".

       datos = cliente.recv(1024)
       if not datos:
           # B cerro: hay que reconectar
           return

   Es la trampa clasica: si no chequeas esto, tu programa entra en un
   bucle infinito leyendo vacio a toda velocidad.


4) BACKOFF EXPONENCIAL: POR QUE NO REINTENTAR CADA 0.1 SEGUNDOS

   Si B esta caido y vos reintentas 10 veces por segundo, quemas CPU y
   red al pedo, y si fueran mil clientes tumbarian al servidor justo
   cuando intenta levantarse.

   La solucion estandar es esperar cada vez un poco mas, con un techo:

       1s -> 2s -> 4s -> 8s -> 16s -> 16s -> 16s ...

   En codigo:

       espera = min(espera * 2, ESPERA_MAXIMA)

   `min` agarra el menor de los dos, o sea que nunca pasa del techo.

   Y cuando la conexion vuelve a funcionar, hay que RESETEAR la espera
   a 1 segundo. Si no, la proxima caida te hace esperar 16 segundos de
   entrada.

   >>> Esto va derecho al informe: es la falacia "la red es confiable"
       del paper de Waldo [WAL94] que cita el enunciado. Escribir el
       backoff ES asumir que la red NO es confiable.


5) time.sleep(segundos) frena el programa ese rato. Necesita `import time`.

===========================================================================
COMO PROBARLO
===========================================================================

   Terminal 1:   python hit2/servidor.py
   Terminal 2:   python hit2/cliente.py

   OJO: el servidor del Hit 2 es el del Hit 1, o sea que atiende UN saludo,
   responde y se cierra solo. Eso es justo el caso que pide el enunciado
   ("en caso de que el proceso B cierre la conexion"), asi que te sirve.

   La prueba de fuego, en este orden:

     1. Arranca SOLO el cliente, sin servidor.
        Tiene que reintentar cada vez mas lento (1s, 2s, 4s, 8s, 16s...)
        sin explotar nunca.

     2. Ahora arranca el servidor, con el cliente todavia corriendo.
        El cliente tiene que engancharse solo y saludar.

     3. No toques nada. El servidor responde y termina por su cuenta.
        El cliente tiene que darse cuenta de que se corto y volver a
        reintentar, arrancando otra vez desde 1 segundo.

     4. Levanta el servidor de nuevo.
        El cliente tiene que reconectar y saludar como si nada.

   Probá tambien matar el servidor con Ctrl+C justo despues del paso 2,
   antes de que responda: ahi vas a ver ConnectionResetError en vez del
   corte limpio. Los dos caminos tienen que terminar en reintento.

   Si sobrevive a todo eso, el Hit 2 esta.

===========================================================================
"""

import socket
import time

HOST = "127.0.0.1"
PORT = 9001

ESPERA_INICIAL = 1     # segundos que espera tras el primer fallo
ESPERA_MAXIMA = 16     # techo: nunca espera mas que esto
INTERVALO_SALUDO = 3   # cada cuanto vuelve a saludar mientras esta conectado


def conversar(cliente):
    """Saluda cada INTERVALO_SALUDO segundos hasta que la conexion se corte.

    Cuando se corta, esta funcion termina (con return o con una excepcion)
    y el control vuelve a main(), que se encarga de reconectar.
    """
    while True:
        # -------------------------------------------------------------
        # TODO 1 - Enviar el saludo.
        #          Igual que en el Hit 1: sendall con .encode()
        # -------------------------------------------------------------
        saludo="hola B, soy A"
        cliente.sendall(saludo.encode())

        # -------------------------------------------------------------
        # TODO 2 - Recibir la respuesta, PERO chequeando el corte limpio.
        #          a) datos = cliente.recv(1024)
        #          b) si `datos` esta vacio -> B cerro la conexion.
        #             Imprimi un aviso y hace `return` (punto 3).
        #          c) si no, .decode() e imprimila.
        # -------------------------------------------------------------
        datos=cliente.recv(1024)
        if not datos:
            print("[A] B cerro la conexion. Volviendo a reconectar...")
            return
        print(f"[A] Recibido: {datos.decode()}")

        time.sleep(INTERVALO_SALUDO)


def main():
    espera = ESPERA_INICIAL

    # Bucle eterno: cada vuelta es UN intento de conexion.
    while True:
        # -----------------------------------------------------------------
        # TODO 3 - Crear el socket. Va ACA ADENTRO del while, no afuera.
        #          Un socket cerrado no se puede reusar: cada reconexion
        #          necesita uno nuevo. Es un error clasico ponerlo afuera.
        # -----------------------------------------------------------------
        cliente = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            # -------------------------------------------------------------
            # TODO 4 - Conectarse a (HOST, PORT).
            # -------------------------------------------------------------
            cliente.connect((HOST, PORT))

            print(f"[A] Conectado a {HOST}:{PORT}")

            # Conectamos bien, asi que la proxima caida arranca de nuevo
            # desde 1 segundo y no desde donde habiamos quedado.
            espera = ESPERA_INICIAL

            # Nos quedamos conversando. Vuelve cuando se corta.
            conversar(cliente)

        # -----------------------------------------------------------------
        # TODO 5 - Atajar el error.
        #          Escribi el `except` para OSError (punto 2), guardando
        #          el error en una variable para poder mostrarlo:
        #
        #              except OSError as error:
        #
        #          Adentro:
        #            a) avisar que fallo y cuanto va a esperar
        #            b) time.sleep(espera)
        #            c) subir la espera con el min() del punto 4
        # -----------------------------------------------------------------
        except OSError as error:
            print(f"[A] Fallo la conexion: {error}. Esperando {espera} segundos...")
            time.sleep(espera)
            espera = min(espera * 2, ESPERA_MAXIMA)

        finally:
            # `finally` corre SIEMPRE: haya salido bien o haya explotado.
            # Es el lugar correcto para cerrar el socket y no dejar
            # conexiones colgadas.
            cliente.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # Para que Ctrl+C corte limpio.
        print("\n[A] Cortado por el usuario.")
