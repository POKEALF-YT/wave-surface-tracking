"""Compara la serie detectada con el generador de la onda sintética."""

import csv
from pathlib import Path

import numpy as np

from generar_oleaje import ANCHO_PX, DURACION_S, FPS, PIXELES_POR_CM, fila_superficie


def validar(csv_path):
    with csv_path.open(encoding="utf-8", newline="") as archivo:
        cuadros = list(csv.DictReader(archivo))
    esp_cuadros = FPS * DURACION_S
    if len(cuadros) != esp_cuadros:
        raise ValueError(f"Se esperaban {esp_cuadros} cuadros, se leyeron {len(cuadros)}.")
    if any(fila["deteccion_valida"] != "True" for fila in cuadros):
        raise ValueError("Hay cuadros sin detección. Revise el CSV.")

    tiempos = np.array([float(fila["tiempo_s"]) for fila in cuadros])
    posiciones = np.array([int(fila["y_px"]) for fila in cuadros])
    np.testing.assert_allclose(tiempos, np.arange(esp_cuadros) / FPS)
    referencia = np.array([fila_superficie(ANCHO_PX // 2, t) for t in tiempos])
    error = np.abs(posiciones - referencia)
    altura = np.ptp(posiciones) / PIXELES_POR_CM
    centro = (posiciones.max() + posiciones.min()) / 2
    cruces = np.flatnonzero((posiciones[:-1] < centro) & (posiciones[1:] >= centro))
    if len(cruces) < 2:
        raise ValueError("La señal necesita al menos dos cruces del nivel medio para medir el período.")
    periodo = np.diff(tiempos[cruces]).mean()

    print(f"Cuadros detectados: {len(cuadros)}/{esp_cuadros}")
    print(f"Error medio: {error.mean():.2f} px | Error máximo: {error.max()} px")
    print(f"Altura: {altura:.2f} cm | Periodo: {periodo:.2f} s | Frecuencia: {1 / periodo:.2f} Hz")


if __name__ == "__main__":
    validar(Path(__file__).with_name("serie_oleaje.csv"))
