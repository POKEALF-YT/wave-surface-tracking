"""Exporta el CSV y la grafica del seguimiento en pixeles."""

import argparse
import csv
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from seguimiento import CENTER_X, inputs, measure



def exportar(recortes, destination):
    rows = [(idx, ts, *measure(crop)) for idx, ts, crop in inputs(recortes)]
    if not rows:
        raise ValueError("No se encontraron recortes PNG.")
    if any(row[0] != i for i, row in enumerate(rows)):
        raise ValueError("La numeracion de cuadros no es consecutiva.")
    if any(a[1] >= b[1] for a, b in zip(rows, rows[1:])):
        raise ValueError("Los tiempos de video deben ser crecientes.")
    start = rows[0][1]
    referencia = [y for _, ts, y, *_, estado in rows if ts-start < 1 and estado == "candidato"]
    if not referencia:
        raise ValueError("El primer segundo no contiene candidatos para fijar la referencia.")
    baseline = float(np.median(referencia))
    destination.mkdir(parents=True, exist_ok=True)
    with (destination/'serie_waveanalysis.csv').open('w',encoding='utf-8',newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['frame','tiempo_video_s','x_px','y_imagen_px','desplazamiento_px','estado','soporte_borde','soporte_alternativo'])
        for i,t,y,strength,rival,_,_,s in rows:
            accepted = s == 'candidato'
            writer.writerow([i, f'{t:.7f}', CENTER_X, y if accepted else '', baseline-y if accepted else '', s, f'{strength:.3f}', f'{rival:.3f}'])

    counts = Counter(row[-1] for row in rows)
    img = Image.new('RGB', (1300,530), '#f8fafc')
    d=ImageDraw.Draw(img)
    def font(size, bold=False):
        return ImageFont.truetype('C:/Windows/Fonts/' + ('arialbd.ttf' if bold else 'arial.ttf'),size)
    ink, subdued, teal, no_data = '#122d3f','#435b6c','#087a78','#e4eaf0'
    d.text((33,24),'Movimiento de la superficie del agua', fill=ink, font=font(31,True))
    d.text((34,66),f'waveanalysis.mp4  |  x = {CENTER_X} px  |  Referencia inicial: fila {baseline:g} px',fill=subdued,font=font(19))
    left,right,top,bottom = 103,1258,145,411
    def x_for(t):
        return left + (right-left)*t/36.1
    def y_for(level):
        return top+(bottom-top)*(30-level)/80
    t0 = None
    for _,t,*_,s in rows + [(0, 36.1, None, 'candidato')]:
        if s != 'candidato' and t0 is None:
            t0 = t
        if s == 'candidato' and t0 is not None:
            d.rectangle((x_for(t0),top,x_for(t),bottom),fill=no_data)
            t0 = None
    for level in range(-50,31,10):
        y=y_for(level)
        d.line((left,y,right,y), fill='#90a5b4' if level==0 else '#cfd9e1',width=1)
        d.text((left-12,y),str(level),anchor='rm',fill=subdued,font=font(16))
    d.text((left,top-31),'Desplazamiento (px, positivo hacia arriba)',fill=subdued,font=font(17))
    for second in range(0,37,4):
        x=x_for(second)
        d.text((x,bottom+13),str(second),anchor='mt',fill=subdued,font=font(15))
    d.text(((left+right)/2,bottom+38),'Tiempo del video (s)',anchor='mt',fill=subdued,font=font(17))
    previous=None
    for _,t,y,*_,s in rows:
        if s != 'candidato':
            previous=None
            continue
        position=(x_for(t),y_for(baseline-y))
        if previous is not None:
            d.line((previous,position),fill=teal,width=2)
        d.point(position,fill=teal)
        previous=position
    d.line((104,494,133,494),fill=teal,width=3)
    d.text((145,494),f"Candidatos autom\u00e1ticos ({counts['candidato']})",anchor='lm',fill=ink,font=font(17))
    d.rectangle((476,486,505,501),fill=no_data)
    d.text((517,494),f"Cuadros sin medici\u00f3n aceptada ({len(rows)-counts['candidato']})",anchor='lm',fill=ink,font=font(17))
    img.save(destination/'serie_waveanalysis.png')



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recortes", type=Path)
    parser.add_argument("destino", type=Path)
    args = parser.parse_args()
    exportar(args.recortes, args.destino)
