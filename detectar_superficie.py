"""Detecta con Canny la superficie del agua en el video sintético."""

import argparse
import csv
from collections import deque
from contextlib import closing
from io import BytesIO
from pathlib import Path
from struct import unpack_from

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from generar_oleaje import FPS


def leer_cuadros(video):
    """Lee los cuadros del AVI Motion JPEG de generar_oleaje.py en orden."""
    with video.open("rb") as archivo:
        if archivo.read(12)[8:12] != b"AVI ":
            raise ValueError("Se esperaba un archivo AVI.")
        while encabezado := archivo.read(8):
            etiqueta, longitud = unpack_from("<4sI", encabezado)
            inicio = archivo.tell()
            if etiqueta == b"LIST" and archivo.read(4) == b"movi":
                fin = inicio + longitud
                while archivo.tell() < fin:
                    etiqueta, longitud_cuadro = unpack_from("<4sI", archivo.read(8))
                    contenido = archivo.read(longitud_cuadro)
                    archivo.read(longitud_cuadro % 2)
                    if etiqueta == b"00dc":
                        with Image.open(BytesIO(contenido)) as cuadro:
                            yield cuadro.convert("L")
                return
            archivo.seek(inicio + longitud + longitud % 2)
    raise ValueError("El AVI no contiene la lista de cuadros Motion JPEG esperada.")


def leer_primer_cuadro(video):
    with closing(leer_cuadros(video)) as cuadros:
        cuadro = next(cuadros, None)
    if cuadro is None:
        raise ValueError("El AVI no contiene cuadros Motion JPEG.")
    return cuadro


def canny(cuadro, umbral_bajo=50, umbral_alto=100):
    """Aplica suavizado, Sobel, supresión de máximos e histéresis."""
    gris = np.asarray(cuadro.filter(ImageFilter.GaussianBlur(1)), dtype=float)
    p = np.pad(gris, 1, mode="edge")
    superior = p[:-2, :-2] + 2 * p[:-2, 1:-1] + p[:-2, 2:]
    inferior = p[2:, :-2] + 2 * p[2:, 1:-1] + p[2:, 2:]
    izquierda = p[:-2, :-2] + 2 * p[1:-1, :-2] + p[2:, :-2]
    derecha = p[:-2, 2:] + 2 * p[1:-1, 2:] + p[2:, 2:]
    dx, dy = derecha - izquierda, inferior - superior
    magnitud = np.hypot(dx, dy)
    direccion = np.rint(np.degrees(np.arctan2(dy, dx)) / 45).astype(int) % 4

    maximos = np.zeros_like(magnitud)
    for angulo, (fila, columna) in enumerate(((0, 1), (1, 1), (1, 0), (1, -1))):
        anterior = np.roll(magnitud, (fila, columna), axis=(0, 1))
        siguiente = np.roll(magnitud, (-fila, -columna), axis=(0, 1))
        conservar = (direccion == angulo) & (magnitud >= anterior) & (magnitud > siguiente)
        maximos[conservar] = magnitud[conservar]
    maximos[[0, -1], :] = 0
    maximos[:, [0, -1]] = 0

    bordes = maximos >= umbral_alto
    candidatos = maximos >= umbral_bajo
    pendientes = deque(zip(*np.nonzero(bordes)))
    while pendientes:
        y, x = pendientes.popleft()
        for vecino_y in range(y - 1, y + 2):
            for vecino_x in range(x - 1, x + 2):
                if candidatos[vecino_y, vecino_x] and not bordes[vecino_y, vecino_x]:
                    bordes[vecino_y, vecino_x] = True
                    pendientes.append((vecino_y, vecino_x))
    return bordes


def superficie_por_columna(bordes):
    """Devuelve los puntos del borde detectado dentro de la región de interés."""
    fila_inicio, fila_fin = 80, 161
    puntos = []
    for x in range(bordes.shape[1]):
        filas = np.flatnonzero(bordes[fila_inicio:fila_fin, x])
        if filas.size:
            puntos.append((x, fila_inicio + int(np.median(filas))))
    return puntos


def graficar_serie(registros, columna, destino):
    """Grafica la fila detectada y deja huecos donde falte una detección."""
    imagen = Image.new("RGB", (1200, 440), "white")
    dibujo = ImageDraw.Draw(imagen)
    fuente = ImageFont.load_default(size=16)
    titulo = ImageFont.load_default(size=24)
    izquierda, derecha, arriba, abajo = 82, 1160, 100, 368
    fin_s = max(1, np.ceil(registros[-1][1]))
    minimo_px, maximo_px = 80, 160

    def coordenadas(tiempo_s, y_px):
        x = izquierda + (derecha - izquierda) * tiempo_s / fin_s
        y = arriba + (abajo - arriba) * (y_px - minimo_px) / (maximo_px - minimo_px)
        return x, y

    dibujo.text((izquierda, 22), f"Superficie detectada en x = {columna} px", fill="#142536", font=titulo)
    dibujo.text((izquierda, 63), "Fila de la imagen (px, aumenta hacia abajo)", fill="#45566a", font=fuente)
    for y_px in range(minimo_px, maximo_px + 1, 20):
        _, y = coordenadas(0, y_px)
        dibujo.line((izquierda, y, derecha, y), fill="#d6dfe7")
        dibujo.text((izquierda - 12, y), str(y_px), fill="#45566a", font=fuente, anchor="rm")
    for tiempo_s in np.linspace(0, fin_s, 6):
        x, _ = coordenadas(tiempo_s, minimo_px)
        dibujo.text((x, abajo + 10), f"{tiempo_s:g}", fill="#45566a", font=fuente, anchor="mt")
    dibujo.text(((izquierda + derecha) / 2, 404), "Tiempo (s)", fill="#45566a", font=fuente, anchor="mt")

    previo = None
    for _, tiempo_s, y_px, valida in registros:
        if not valida:
            previo = None
            continue
        punto = coordenadas(tiempo_s, y_px)
        dibujo.point(punto, fill="#007f87")
        if previo is not None:
            dibujo.line((previo, punto), fill="#007f87", width=3)
        previo = punto
    imagen.save(destino)


def guardar_serie(video, carpeta):
    registros = []
    for numero, cuadro in enumerate(leer_cuadros(video)):
        columna = cuadro.width // 2
        # Conserva un margen lateral para que Canny evalúe la columna central.
        recorte = cuadro.crop((columna - 16, 0, columna + 17, cuadro.height))
        y_px = dict(superficie_por_columna(canny(recorte))).get(16)
        registros.append((numero, numero / FPS, y_px, y_px is not None))
    if not registros:
        raise ValueError("El AVI no contiene cuadros Motion JPEG.")

    destino_csv = carpeta / "serie_oleaje.csv"
    with destino_csv.open("w", newline="", encoding="utf-8") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(("frame", "tiempo_s", "y_px", "deteccion_valida"))
        escritor.writerows(registros)
    graficar_serie(registros, columna, carpeta / "serie_oleaje.png")
    validos = sum(registro[3] for registro in registros)
    print(f"Superficie detectada en {validos}/{len(registros)} cuadros (x={columna} px).")


def main():
    argumentos = argparse.ArgumentParser(description=__doc__)
    argumentos.add_argument("--serie", action="store_true", help="Exporta el CSV y la gráfica del video completo.")
    opciones = argumentos.parse_args()
    carpeta = Path(__file__).resolve().parent
    video = carpeta / "oleaje_sintetico.avi"
    if opciones.serie:
        guardar_serie(video, carpeta)
        return

    cuadro = leer_primer_cuadro(video)
    superficie = superficie_por_columna(canny(cuadro))
    superpuesto = cuadro.convert("RGB")
    ImageDraw.Draw(superpuesto).point(superficie, fill=(230, 25, 45))
    destino = carpeta / "superficie_detectada.png"
    superpuesto.save(destino)
    print(f"Superficie detectada en {len(superficie)}/{cuadro.width} columnas.")
    print(f"Imagen guardada en {destino}")


if __name__ == "__main__":
    main()
