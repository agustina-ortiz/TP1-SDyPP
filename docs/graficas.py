# -*- coding: utf-8 -*-
"""Genera las graficas del informe a partir de la evidencia versionada.

No usa dependencias externas: escribe el SVG a mano con la biblioteca estandar.
Se eligio SVG en lugar de PNG por tres motivos: es texto, asi que versiona y se
diffea en Git como cualquier fuente; se ve nitido a cualquier zoom y al imprimir;
y GitHub lo renderiza dentro del Markdown sin herramientas externas. Sumar
matplotlib habria metido una dependencia pesada en requirements.txt, que es el
mismo archivo que instala la imagen Docker del nodo D.

Uso:
    python docs/graficas.py

Salida: docs/diagramas/*.svg
"""

import json
import math
import os

AQUI = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(AQUI, "diagramas")

# Paleta categorica validada para vision normal y para daltonismo
# (separacion CVD dE 24.7, muy por encima del piso de 8).
SUPERFICIE = "#fcfcfb"
TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
GRILLA = "#e5e4df"
EJE = "#c9c8c2"
AZUL = "#2a78d6"
NARANJA = "#eb6834"

TIPOGRAFIA = "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif"


def esc(texto):
    """Escapa los caracteres que romperian el XML."""
    return (str(texto).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def escala(vmax, n=4):
    """Devuelve marcas de eje 'redondas' y el tope, para no rotular 3,7142."""
    if vmax <= 0:
        return [0, 1], 1
    bruto = vmax / float(n)
    exp = math.floor(math.log10(bruto))
    base = bruto / (10 ** exp)
    for candidato in (1, 2, 2.5, 5, 10):
        if base <= candidato:
            paso = candidato * (10 ** exp)
            break
    tope = math.ceil(vmax / paso) * paso
    marcas, v = [], 0.0
    while v <= tope + paso / 1000.0:
        marcas.append(round(v, 10))
        v += paso
    return marcas, tope


def barra(x, y, ancho, alto, color, r=4):
    """Barra con las puntas superiores redondeadas, anclada a la linea base."""
    if alto <= 0.5:
        return ""
    r = min(r, ancho / 2.0, alto)
    d = ("M%.2f %.2f L%.2f %.2f Q%.2f %.2f %.2f %.2f "
         "L%.2f %.2f Q%.2f %.2f %.2f %.2f L%.2f %.2f Z") % (
        x, y + alto, x, y + r, x, y, x + r, y,
        x + ancho - r, y, x + ancho, y, x + ancho, y + r,
        x + ancho, y + alto)
    return '<path d="%s" fill="%s"/>' % (d, color)


ANCHO, ALTO = 760, 420
IZQ, DER, ARR, ABA = 74, 28, 92, 74


def _marco(titulo, subtitulo, piezas, alto=None):
    """Envuelve el contenido con superficie, titulo y subtitulo."""
    alto = alto or ALTO
    cab = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %d %d" font-family="%s">' % (ANCHO, alto, ANCHO, alto, TIPOGRAFIA),
        '<rect width="%d" height="%d" fill="%s"/>' % (ANCHO, alto, SUPERFICIE),
        '<text x="%d" y="34" font-size="17" font-weight="600" fill="%s">%s</text>'
        % (IZQ - 46, TINTA, esc(titulo)),
        '<text x="%d" y="56" font-size="12.5" fill="%s">%s</text>'
        % (IZQ - 46, TINTA_2, esc(subtitulo)),
    ]
    return "\n".join(cab + piezas + ["</svg>"]) + "\n"


def _ejes(marcas, tope, y0, y1, formato):
    """Grilla horizontal recesiva y rotulos del eje Y."""
    p = []
    for m in marcas:
        y = y1 - (m / float(tope)) * (y1 - y0)
        color = EJE if m == 0 else GRILLA
        p.append('<line x1="%d" y1="%.2f" x2="%d" y2="%.2f" stroke="%s" stroke-width="1"/>'
                 % (IZQ, y, ANCHO - DER, y, color))
        p.append('<text x="%d" y="%.2f" font-size="11.5" fill="%s" text-anchor="end">%s</text>'
                 % (IZQ - 10, y + 4, TINTA_2, esc(formato(m))))
    return p


def barras_agrupadas(titulo, subtitulo, categorias, series, formato, pie):
    """Dos series comparadas sobre un mismo eje. Un eje, nunca dos escalas."""
    y0, y1 = ARR, ALTO - ABA
    vmax = max(max(valores) for _, valores, _ in series)
    marcas, tope = escala(vmax)
    piezas = _ejes(marcas, tope, y0, y1, formato)

    # Leyenda: la identidad nunca queda solo en el color, tambien va rotulada.
    lx = IZQ - 46
    for nombre, _, color in series:
        piezas.append('<rect x="%d" y="66" width="10" height="10" rx="2" fill="%s"/>' % (lx, color))
        piezas.append('<text x="%d" y="75" font-size="12" fill="%s">%s</text>'
                      % (lx + 15, TINTA_2, esc(nombre)))
        lx += 22 + len(nombre) * 6.6

    grupo = (ANCHO - DER - IZQ) / float(len(categorias))
    ancho_barra = min(46.0, (grupo * 0.66 - 2) / len(series))

    for i, categoria in enumerate(categorias):
        centro = IZQ + grupo * (i + 0.5)
        total = ancho_barra * len(series) + 2 * (len(series) - 1)
        x = centro - total / 2.0
        for nombre, valores, color in series:
            v = valores[i]
            alto = (v / float(tope)) * (y1 - y0)
            piezas.append(barra(x, y1 - alto, ancho_barra, alto, color))
            piezas.append('<text x="%.2f" y="%.2f" font-size="11.5" font-weight="600" '
                          'fill="%s" text-anchor="middle">%s</text>'
                          % (x + ancho_barra / 2.0, y1 - alto - 7, TINTA, esc(formato(v))))
            x += ancho_barra + 2
        piezas.append('<text x="%.2f" y="%d" font-size="12.5" fill="%s" text-anchor="middle">%s</text>'
                      % (centro, y1 + 22, TINTA, esc(categoria)))

    piezas.append('<text x="%d" y="%d" font-size="11.5" fill="%s">%s</text>'
                  % (IZQ - 46, ALTO - 18, TINTA_2, esc(pie)))
    return _marco(titulo, subtitulo, piezas)


def ventanas(titulo, subtitulo, etiquetas, valores, pie, muere_en, arrastre_en):
    """Serie unica: no lleva leyenda, el titulo ya nombra lo que se mide.

    Las anotaciones van debajo del eje, no sobre las barras: ahi no compiten
    con los valores ni con el subtitulo, y las dos quedan en filas distintas
    para que sus textos no se pisen entre si.
    """
    alto_total = ALTO + 54
    y0, y1 = ARR, alto_total - ABA - 54
    marcas, tope = escala(max(valores), n=3)
    formato = lambda v: "%d" % v

    grupo = (ANCHO - DER - IZQ) / float(len(etiquetas))
    ancho_barra = min(58.0, grupo * 0.52)
    centros = [IZQ + grupo * (i + 0.5) for i in range(len(etiquetas))]

    # La punteada se dibuja ANTES que las barras: queda detras y solo asoma
    # por debajo del eje, sin cruzar el rotulo del valor.
    xm = centros[muere_en]
    # Dos tramos: el hueco del medio deja pasar el rotulo de la ventana sin tacharlo.
    piezas = ['<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" stroke-width="1.5" '
              'stroke-dasharray="4 3"/>' % (xm, a, xm, b, NARANJA)
              for a, b in ((y0, y1 + 8), (y1 + 27, y1 + 34))]
    piezas += _ejes(marcas, tope, y0, y1, formato)

    for i, etiqueta in enumerate(etiquetas):
        centro, v = centros[i], valores[i]
        altura = (v / float(tope)) * (y1 - y0)
        piezas.append(barra(centro - ancho_barra / 2.0, y1 - altura, ancho_barra, altura, AZUL))
        piezas.append('<text x="%.2f" y="%.2f" font-size="12" font-weight="600" fill="%s" '
                      'text-anchor="middle">%d</text>'
                      % (centro, (y1 - altura - 7) if v else (y1 - 7), TINTA, v))
        piezas.append('<text x="%.2f" y="%.2f" font-size="12" fill="%s" text-anchor="middle">%s</text>'
                      % (centro, y1 + 22, TINTA, esc(etiqueta)))

    # Fila 1 de anotaciones: cuando se mata el nodo.
    piezas.append('<circle cx="%.2f" cy="%.2f" r="3.5" fill="%s"/>' % (xm, y1 + 34, NARANJA))
    piezas.append('<text x="%.2f" y="%.2f" font-size="11.5" font-weight="600" fill="%s" '
                  'text-anchor="middle">se mata el nodo 22137</text>' % (xm, y1 + 51, NARANJA))

    # Fila 2: la ventana en la que el nodo muerto sigue siendo miembro.
    xa, semi = centros[arrastre_en], ancho_barra / 2.0 + 12
    base = y1 + 66
    piezas.append('<path d="M%.2f %.2f L%.2f %.2f L%.2f %.2f L%.2f %.2f" fill="none" '
                  'stroke="%s" stroke-width="1.5"/>'
                  % (xa - semi, base - 6, xa - semi, base, xa + semi, base, xa + semi, base - 6,
                     NARANJA))
    piezas.append('<text x="%.2f" y="%.2f" font-size="11.5" font-weight="600" fill="%s" '
                  'text-anchor="middle">sigue en /peers estando muerto</text>'
                  % (xa, base + 16, NARANJA))

    piezas.append('<text x="%d" y="%d" font-size="11.5" fill="%s">%s</text>'
                  % (IZQ - 46, alto_total - 14, TINTA_2, esc(pie)))
    return _marco(titulo, subtitulo, piezas, alto=alto_total)


# Numeros de la corrida documentada en informe.md 4.1: hit8/benchmark.py,
# 20 intercambios de calentamiento y 500 iteraciones sobre loopback.
HIT8_TAMANOS = [("Saludo", 117, 52), ("ACK", 122, 60), ("Total", 239, 112)]
HIT8_LATENCIAS = [("Media", 0.035, 0.097), ("Mediana", 0.035, 0.097), ("p95", 0.040, 0.110)]


def main():
    if not os.path.isdir(SALIDA):
        os.makedirs(SALIDA)
    generados = []

    # --- Hit 8: tamano y latencia van en graficas separadas, porque son
    # magnitudes distintas (bytes y milisegundos) y un eje doble mentiria.
    etiquetas = [e for e, _, _ in HIT8_TAMANOS]
    svg = barras_agrupadas(
        "Hit 8 — Tamaño del mensaje en la red",
        "Protocol Buffers recorta el payload total un 53,1 % frente a JSON sobre TCP.",
        etiquetas,
        [("JSON sobre TCP", [j for _, j, _ in HIT8_TAMANOS], AZUL),
         ("gRPC + Protobuf", [p for _, _, p in HIT8_TAMANOS], NARANJA)],
        lambda v: "%d" % v,
        "Bytes de payload. Excluye cabeceras TCP, HTTP/2 y framing gRPC.")
    generados.append(("hit8-tamanos.svg", svg))

    etiquetas = [e for e, _, _ in HIT8_LATENCIAS]
    svg = barras_agrupadas(
        "Hit 8 — Latencia de ida y vuelta",
        "El ahorro de bytes se paga en latencia: sobre loopback gRPC tarda casi el triple.",
        etiquetas,
        [("JSON sobre TCP", [j for _, j, _ in HIT8_LATENCIAS], AZUL),
         ("gRPC + Protobuf", [p for _, _, p in HIT8_LATENCIAS], NARANJA)],
        lambda v: ("%.3f" % v).rstrip("0").rstrip(".").replace(".", ","),
        "Milisegundos. 500 iteraciones sobre loopback, conexión persistente.")
    generados.append(("hit8-latencia.svg", svg))

    # --- Hit 7: se lee la evidencia del repositorio, no se transcribe a mano.
    ruta = os.path.join(AQUI, "evidencia-hit7.json")
    datos = json.load(open(ruta, encoding="utf-8"))["ventanas"]
    etiquetas = [v["ventana"][11:16] for v in datos]
    valores = [v["cantidad"] for v in datos]
    svg = ventanas(
        "Hit 7 — Miembros de cada ventana",
        "La membresía de una ventana en curso no se toca: el nodo muerto sobrevive una ventana más.",
        etiquetas, valores,
        "Nodos devueltos por /peers. Fuente: docs/evidencia-hit7.json (endpoint /ventanas).",
        muere_en=2, arrastre_en=3)
    generados.append(("hit7-ventanas.svg", svg))

    for nombre, contenido in generados:
        destino = os.path.join(SALIDA, nombre)
        with open(destino, "w", encoding="utf-8") as f:
            f.write(contenido)
        print("  %s (%d bytes)" % (nombre, len(contenido.encode("utf-8"))))
    print("%d graficas en docs/diagramas/" % len(generados))


if __name__ == "__main__":
    main()
