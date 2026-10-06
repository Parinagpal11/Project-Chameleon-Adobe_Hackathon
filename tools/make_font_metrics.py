"""Build backend/engine/fonts.json: advance widths (in em) of the fonts the studio loads from Google Fonts.

The layout engine wraps text with these widths so its text boxes match what the browser draws.
Usage: python tools/make_font_metrics.py FONT_DIR
FONT_DIR holds the Google Fonts files (github.com/google/fonts, OFL):
  Inter[opsz,wght].ttf  PlayfairDisplay[wght].ttf  SpaceGrotesk[wght].ttf  Montserrat[wght].ttf
  DMSerifDisplay-Regular.ttf  Poppins-Regular.ttf ... Poppins-ExtraBold.ttf
"""
import json
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parents[1]
CHARS = ''.join(chr(c) for c in range(32, 127)) + '’‘“”–—…•€£¥©®™°éèêáàâíóöüñçÉ×·'
WEIGHTS = [400, 500, 600, 700, 800]
POPPINS = {400: 'Regular', 500: 'Medium', 600: 'SemiBold', 700: 'Bold', 800: 'ExtraBold'}


def widths(font: TTFont) -> dict:
    upem = font['head'].unitsPerEm
    cmap = font.getBestCmap()
    hmtx = font['hmtx']
    out = {}
    for ch in CHARS:
        g = cmap.get(ord(ch))
        if g is not None:
            out[ch] = round(hmtx[g][0] / upem, 4)
    return out


def variable(path: Path, weights, axes_extra=None):
    res = {}
    for w in weights:
        f = TTFont(path)
        axes = {a.axisTag: a for a in f['fvar'].axes}
        loc = {'wght': max(axes['wght'].minValue, min(axes['wght'].maxValue, w))}
        for tag, a in axes.items():
            if tag != 'wght':
                loc[tag] = (axes_extra or {}).get(tag, a.defaultValue)
        res[str(w)] = widths(instantiateVariableFont(f, loc))
    return res


def main(src: Path):
    data = {
        'Inter': variable(src / 'Inter[opsz,wght].ttf', WEIGHTS),
        'Playfair Display': variable(src / 'PlayfairDisplay[wght].ttf', WEIGHTS),
        'Space Grotesk': variable(src / 'SpaceGrotesk[wght].ttf', WEIGHTS),
        'Montserrat': variable(src / 'Montserrat[wght].ttf', WEIGHTS),
        'DM Serif Display': {'400': widths(TTFont(src / 'DMSerifDisplay-Regular.ttf'))},
        'Poppins': {str(w): widths(TTFont(src / f'Poppins-{n}.ttf')) for w, n in POPPINS.items()
                    if (src / f'Poppins-{n}.ttf').exists()},
    }
    out = ROOT / 'backend' / 'engine' / 'fonts.json'
    out.write_text(json.dumps(data, separators=(',', ':'), ensure_ascii=False))
    print(out, out.stat().st_size, 'bytes')


if __name__ == '__main__':
    main(Path(sys.argv[1] if len(sys.argv) > 1 else '.'))
