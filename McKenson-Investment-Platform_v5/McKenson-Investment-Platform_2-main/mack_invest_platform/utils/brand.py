# utils/brand.py  —  MAM v5.10 · Identité visuelle (logo) — source unique
"""
Fichiers (dossier assets/) :
  mam_mark.svg / .png      logo seul (le « M » en courbe de marché) — en-têtes, petites tailles
  mam_logo.svg / .png      logo avec « MAM » — photo de profil, icône
  mam_banner.svg / .png    bannière « MAM · McKenson Asset Management » — README, page d'accueil
  mam_favicon.png          icône d'onglet du navigateur

Utilisé par l'en-tête de la plateforme, l'écran de connexion, les rapports PDF et les images PNG.
"""
from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"
MARK_SVG = ASSETS / "mam_mark.svg"
MARK_PNG = ASSETS / "mam_mark.png"
LOGO_PNG = ASSETS / "mam_logo.png"
BANNER_PNG = ASSETS / "mam_banner.png"
FAVICON = ASSETS / "mam_favicon.png"


import itertools as _it
_UID = _it.count(1)


@lru_cache(maxsize=8)
def _read(path: str) -> bytes:
    try:
        return Path(path).read_bytes()
    except Exception:
        return b""


def mark_svg_inline(size: int = 40, css_class: str = "") -> str:
    """Logo en SVG intégré dans le HTML (net à toutes les tailles). Chaîne vide si le fichier manque."""
    raw = _read(str(MARK_SVG)).decode("utf-8", "ignore")
    if not raw:
        return ""
    cls = f' class="{css_class}"' if css_class else ""
    # une seule ligne : st.markdown n'interprète pas l'indentation comme un bloc de code
    raw = " ".join(line.strip() for line in raw.splitlines() if line.strip())
    uid = next(_UID)                      # identifiants de dégradé uniques (plusieurs logos par page)
    raw = raw.replace('id="mbg"', f'id="mbg{uid}"').replace("url(#mbg)", f"url(#mbg{uid})") \
             .replace('id="mm"', f'id="mm{uid}"').replace("url(#mm)", f"url(#mm{uid})")
    return raw.replace('width="512" height="512"', f'width="{size}" height="{size}"{cls}', 1)


def data_uri(path: Path) -> str:
    b = _read(str(path))
    if not b:
        return ""
    mime = "image/svg+xml" if path.suffix == ".svg" else "image/png"
    return f"data:{mime};base64,{base64.b64encode(b).decode()}"


def png_bytes(kind: str = "mark") -> bytes:
    """PNG du logo : 'mark' (sans texte), 'logo' (avec MAM) ou 'banner'."""
    return _read(str({"mark": MARK_PNG, "logo": LOGO_PNG, "banner": BANNER_PNG}[kind]))


def page_icon():
    """Icône d'onglet pour st.set_page_config (repli sur un emoji si le fichier manque)."""
    try:
        if FAVICON.exists():
            from PIL import Image
            return Image.open(FAVICON)
    except Exception:
        pass
    return "📈"


def add_to_figure(fig, x: float, y: float, h: float):
    """Place le logo (PNG) sur une figure matplotlib : coin bas-gauche (x, y), hauteur h en fraction de
    la figure. Ne fait rien si le fichier manque."""
    b = png_bytes("mark")
    if not b:
        return None
    import io
    import matplotlib.image as mpimg
    img = mpimg.imread(io.BytesIO(b), format="png")
    fw, fh = fig.get_size_inches()
    w = h * fh / fw
    ax = fig.add_axes([x, y, w, h])
    ax.imshow(img)
    ax.axis("off")
    return ax
