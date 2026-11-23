"""Puntua la continuidad espacial del borde en el recorte."""

import numpy as np
from PIL import Image

from detectar_superficie import canny

ROI = (155, 140, 265, 216)
ROI_X, ROI_Y, _, _ = ROI
CENTER_X = 210
X = np.arange(35, 76)
Y = np.arange(13, 72)
SLOPES = np.linspace(-0.5, 0.5, 31)
LINE_Y = Y[None, :, None] + np.rint(SLOPES[:, None, None] * (X - (CENTER_X - ROI_X))).astype(int)
LINE_IN_BOUNDS = (LINE_Y >= 13) & (LINE_Y <= 72)
LINE_INDEX = np.clip(LINE_Y, 0, 75)

def measure(crop):
    edges = canny(crop.convert('L'), 55, 120)
    expanded = edges.copy()
    expanded[1:] |= edges[:-1]
    expanded[:-1] |= edges[1:]
    matches = expanded[LINE_INDEX, X] & LINE_IN_BOUNDS
    scores = matches.mean(axis=2)
    order = np.argsort(scores.max(axis=0))[::-1]
    best = order[0]
    line_scores = scores[:, best]
    slope_options = np.flatnonzero(line_scores == line_scores.max())
    slope = int(slope_options[len(slope_options) // 2])
    strength = line_scores[slope_options[0]]
    rival = next(y for y in order if abs(y - best) >= 8)
    rival_strength = scores[:,rival].max()
    near_y = LINE_INDEX[slope,best]
    area_x = X[5:-5]
    area_y = near_y[5:-5] + np.arange(-5, 9)[:,None]
    area_y = np.clip(area_y, 0, 75)
    dense = edges[area_y,area_x].mean()
    saturated = (np.asarray(crop)[area_y,area_x].min(axis=2) >= 245).mean()
    if strength < 0.67:
        status = 'borde_debil'
    elif dense >= 0.23 or saturated >= 0.24 or rival_strength >= max(0.67, strength*0.83):
        status = 'ambiguo'
    else:
        status = 'candidato'
    return ROI_Y + int(Y[best]), strength, rival_strength, dense, saturated, status

def inputs(folder):
    for file in sorted(folder.glob('*.png')):
        frame, time = file.stem.split('-')
        with Image.open(file) as crop:
            yield int(frame), float(time), crop.copy()
