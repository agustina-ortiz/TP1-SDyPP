"""Hit 3 - Nodo A (cliente).

SIN CAMBIOS respecto del Hit 2: el enunciado pide modificar solo el nodo B.
Esta copia esta aca para poder matarlo y ver como el servidor sobrevive.

Para probar el Hit 3 vas a matar ESTE proceso con Ctrl+C, varias veces,
y el servidor tiene que seguir en pie.
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
