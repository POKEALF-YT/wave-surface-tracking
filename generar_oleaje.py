"""Genera un video AVI de oleaje sintético. Dependencia: Pillow."""

from io import BytesIO
from math import sin, tau
from pathlib import Path
from struct import pack

from PIL import Image, ImageDraw


ANCHO_PX = 640
ALTO_PX = 240
FPS = 30
DURACION_S = 20
NIVEL_REPOSO_PX = 120
PIXELES_POR_CM = 4
ALTURA_CM = 10
PERIODO_S = 2
LONGITUD_ONDA_PX = 320


def fila_superficie(columna, tiempo_s):
    """Devuelve la fila de la superficie para una columna y un instante."""
    amplitud_px = ALTURA_CM * PIXELES_POR_CM / 2
    fase = tau * (columna / LONGITUD_ONDA_PX - tiempo_s / PERIODO_S)
    return round(NIVEL_REPOSO_PX - amplitud_px * sin(fase))


def generar_cuadro(tiempo_s):
    """Dibuja el fondo blanco y rellena de negro bajo la superficie."""
    imagen = Image.new("L", (ANCHO_PX, ALTO_PX), 255)
    superficie = [(x, fila_superficie(x, tiempo_s)) for x in range(ANCHO_PX)]
    poligono = superficie + [(ANCHO_PX - 1, ALTO_PX - 1), (0, ALTO_PX - 1)]
    ImageDraw.Draw(imagen).polygon(poligono, fill=0)
    return imagen


def bloque_avi(etiqueta, datos):
    relleno = b"\0" if len(datos) % 2 else b""
    return etiqueta + pack("<I", len(datos)) + datos + relleno


def guardar_avi(destino):
    """Codifica cada cuadro como JPEG y lo guarda en un AVI a FPS fijos."""
    total_cuadros = DURACION_S * FPS
    datos_video = bytearray(b"movi")
    indice = bytearray()
    tamano_maximo = 0

    for numero in range(total_cuadros):
        cuadro = generar_cuadro(numero / FPS)
        with BytesIO() as memoria:
            # JPEG en tres canales mejora la compatibilidad de Motion JPEG.
            cuadro.convert("RGB").save(memoria, format="JPEG", quality=95)
            jpeg = memoria.getvalue()
        indice.extend(pack("<4sIII", b"00dc", 0x10, len(datos_video), len(jpeg)))
        datos_video.extend(bloque_avi(b"00dc", jpeg))
        tamano_maximo = max(tamano_maximo, len(jpeg))

    encabezado_avi = pack(
        "<14I", round(1_000_000 / FPS), (tamano_maximo + 9) * FPS, 0, 0x10,
        total_cuadros, 0, 1, tamano_maximo, ANCHO_PX, ALTO_PX, 0, 0, 0, 0,
    )
    encabezado_video = pack(
        "<4s4sIHH8I4h", b"vids", b"MJPG", 0, 0, 0, 0, 1, FPS, 0,
        total_cuadros, tamano_maximo, 0xFFFFFFFF, 0, 0, 0, ANCHO_PX, ALTO_PX,
    )
    formato_video = pack(
        "<IiiHH4sIiiII", 40, ANCHO_PX, ALTO_PX, 1, 24, b"MJPG",
        ANCHO_PX * ALTO_PX * 3, 0, 0, 0, 0,
    )
    flujo = b"strl" + bloque_avi(b"strh", encabezado_video) + bloque_avi(b"strf", formato_video)
    cabecera = b"hdrl" + bloque_avi(b"avih", encabezado_avi) + bloque_avi(b"LIST", flujo)
    contenido = (
        b"AVI " + bloque_avi(b"LIST", cabecera)
        + bloque_avi(b"LIST", datos_video) + bloque_avi(b"idx1", indice)
    )
    destino.write_bytes(bloque_avi(b"RIFF", contenido))


if __name__ == "__main__":
    destino = Path(__file__).with_name("oleaje_sintetico.avi")
    guardar_avi(destino)
    print(f"Video generado: {destino}")
