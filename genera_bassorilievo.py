#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
genera_bassorilievo.py
======================
Genera tutto il materiale operativo per realizzare un bassorilievo in
mattoncini LEGO di una Porsche 911 GT3 RS di profilo, su pannello 190x100 cm.

Output prodotti nella cartella corrente:
  - tone_map.png          foto posterizzata a 6 toni, auto scontornata, sfondo bianco
  - maschera_debug.png    diagnostica dello scontorno (per tarare le soglie)
  - report_quantita.csv   aree, pezzi, peso e kg da ordinare per ogni tono
  - traccia_1a1.pdf       sagoma in scala 1:1 divisa in fogli A4 verticali
  - mappa_spessori.pdf    4 livelli di profondita' con retini e legenda
  - guida_montaggio.md    checklist operativa di montaggio

Dipendenze: Pillow, numpy, reportlab, scipy. Nessuna connessione internet.
Uso:  python3 genera_bassorilievo.py
"""

import csv
import math
import os
import subprocess
import sys

# ======================================================================
# ============================ PARAMETRI ===============================
# Tutto cio' che si puo' voler cambiare sta qui sotto.
# ======================================================================

# ---------------------------------------------------------------- input
FILE_IMMAGINE = "gt3rs.jpg"       # foto di profilo di partenza

# Ritaglio dell'immagine sorgente, in frazioni (sinistra, alto, destra, basso).
# Serve a togliere la barra di bottoni del configuratore Porsche in basso
# e le fasce bianche in alto. Metti (0.0, 0.0, 1.0, 1.0) per non ritagliare.
CROP_FRAZIONI = (0.0, 0.02, 1.0, 0.93)

# -------------------------------------------------------------- pannello
PANNELLO_LARGHEZZA_CM = 190.0     # lato lungo, orientamento orizzontale
PANNELLO_ALTEZZA_CM = 100.0
MARGINE_PANNELLO_CM = 6.0         # aria lasciata attorno alla sagoma

# ------------------------------------------------------------ risoluzioni
RISOLUZIONE_LAVORO_PX_CM = 8      # px/cm per i calcoli (toni, profondita')
RISOLUZIONE_SAGOMA_PX_CM = 40     # px/cm per i PDF -> 4.0 px/mm, ~101.6 dpi
RISOLUZIONE_OUTPUT_PX_CM = 10     # px/cm per tone_map.png

# ------------------------------------------------------------- scontorno
# Lo sfondo viene individuato come "chiaro e poco saturo, connesso al bordo
# dell'immagine". Poi si tiene solo la componente piu' grande e si tappano
# i buchi interni: cosi' la filigrana "GT3RS" dello sfondo sparisce da sola.
SOGLIA_SFONDO_LUMINANZA = 0.86    # sopra questa luminanza (0-1) = candidato sfondo
SOGLIA_SFONDO_SATURAZIONE = 0.18  # sotto questa saturazione = candidato sfondo
# Nella fascia bassa dell'immagine si usa una soglia piu' aggressiva, per
# mangiare l'ombra/riflesso a terra senza toccare gli pneumatici (molto scuri).
FASCIA_BASSA_FRAZIONE = 0.72      # sotto questa quota inizia la fascia bassa
SOGLIA_SFONDO_LUMINANZA_BASSO = 0.55
APERTURA_MASCHERA_PX = 2          # pulizia morfologica della maschera

# ----------------------------------------------------------------- toni
# Toni acromatici ordinati dal PIU' SCURO al PIU' CHIARO.
# L'indice in questa lista e' anche il "rango di profondita'": 0 = piu' scuro
# = piu' indietro. Aggiungendo o togliendo voci qui cambia il numero di toni,
# basta che SOGLIE_LUMINANZA abbia sempre un elemento in meno di TONI_GRIGI.
TONI_GRIGI = [
    {"nome": "nero",          "rgb": (26, 26, 26)},
    {"nome": "grigio scuro",  "rgb": (90, 90, 90)},
    {"nome": "grigio chiaro", "rgb": (166, 166, 166)},
    {"nome": "crema/tan",     "rgb": (216, 201, 168)},
    {"nome": "bianco",        "rgb": (246, 246, 243)},
]
# Soglie di luminanza (0-1) che separano i toni qui sopra, in ordine crescente.
SOGLIE_LUMINANZA = [0.17, 0.34, 0.56, 0.79]
# In alternativa, soglie ricavate dai quantili della luminanza dentro la sagoma:
# si adattano da sole a qualunque foto, utile se un tono si mangia meta' dell'auto.
# Metti None per usare SOGLIE_LUMINANZA fisse, oppure una lista di quantili 0-1
# lunga quanto SOGLIE_LUMINANZA, es. [0.12, 0.32, 0.60, 0.85].
SOGLIE_AUTO_PERCENTILI = None

# Tono di accento: il rosso. Riconosciuto per tinta+saturazione, non per luminanza.
TONO_ROSSO = {"nome": "rosso (accento)", "rgb": (198, 28, 28)}
SOGLIA_SATURAZIONE_ROSSO = 0.35   # sopra: colore acceso
SOGLIA_VALORE_ROSSO = 0.15        # sotto: troppo buio per essere rosso
AMPIEZZA_TINTA_ROSSO = 0.055      # tolleranza attorno a H=0 (0-1)

# ------------------------------------------------- mappa degli spessori
# La profondita' e' la somma pesata di quattro contributi, poi quantizzata.
PESO_TONO = 0.45          # tono chiaro = piu' in fuori
PESO_VERTICALE = 0.20     # fascia bassa indietro, fascia centrale in fuori
PESO_DISTANZA = 0.25      # bombatura: il centro della massa sporge, i bordi calano
PESO_RUOTE = 0.55         # quanto si scavano ruote e passaruota (sottrazione)

DISTANZA_SATURAZIONE_CM = 12.0    # entro quanti cm dal bordo sale la bombatura
RAMPA_CENTRO_VERTICALE = 0.50     # quota (0=alto, 1=basso) del massimo rilievo
RAMPA_SIGMA = 0.35                # larghezza della campana verticale
RAMPA_DECADIMENTO_BASSO = 0.50    # quanto si spinge indietro la parte bassa
SFUMATURA_PROFONDITA_CM = 2.0     # sigma della gaussiana sulla mappa continua

# Quantizzazione a 4 livelli per percentili dell'area della sagoma.
# Con [0.35, 0.62, 0.88]: L0 = 35% dell'area, L1 = 27%, L2 = 26%, L3 = 12%.
SOGLIE_PERCENTILI_LIVELLI = [0.35, 0.62, 0.88]

# Traduzione dei livelli in mattoncini reali. 1 plate = 3.2 mm, 1 brick = 3 plate.
SPESSORE_PLATE_MM = 3.2
LIVELLI_PLATE = [1, 4, 8, 12]     # -> 3.2 / 12.8 / 25.6 / 38.4 mm (~4 cm)

# Ruote e passaruota: rilevate in automatico come le due macchie scure piu'
# grandi nella meta' bassa. Per forzarle a mano metti una lista di tuple
# (centro_x_cm, centro_y_cm, raggio_cm) misurate sul pannello; None = automatico.
RUOTE_MANUALI = None
RUOTE_SOGLIA_SCURO = 0.22         # luminanza sotto cui un pixel e' "gomma"
RUOTE_RAGGIO_EXTRA = 1.12         # allarga un po' il cerchio per prendere il passaruota
# Il sottoporta nero unisce le due gomme in un unico blob: un'apertura
# morfologica di questo raggio scioglie la fascia sottile e lascia i dischi.
# Regola: piu' della meta' dello spessore del sottoporta, meno del raggio gomma.
RUOTE_APERTURA_CM = 2.5
RUOTE_AREA_MINIMA_CM2 = 80.0      # sotto quest'area non e' una ruota

# Decisione (a): padiglione, vetri e alettone sono scuri ma NON sono incavi.
# I pixel scuri sopra questa quota (0=alto della sagoma) e fuori dalle ruote
# non possono scendere sotto il livello 1.
QUOTA_PADIGLIONE_FRAZIONE = 0.45
LIVELLO_MINIMO_PADIGLIONE = 1

# Decisione (b): il rosso sporge di un livello rispetto al tono che lo circonda.
ROSSO_SPORGE_DI_LIVELLI = 1

# Pulizia della mappa a livelli.
MEDIANA_LIVELLI_CM = 1.5          # lato del filtro mediano
AREA_MINIMA_ISOLA_CM2 = 25.0      # isole piu' piccole vengono assorbite dal vicinato

# ------------------------------------------------- quantita' da ordinare
AREA_MEDIA_PEZZO_CM2 = 3.0        # area media coperta da un pezzo visto di faccia
FATTORE_STRATIFICAZIONE = 2.5     # pezzi sotto, non visibili
PESO_MEDIO_PEZZO_G = 1.3          # peso medio di un pezzo
MARGINE_ORDINE = 0.30             # 30% di scorta sull'ordine

# ------------------------------------------------------------ stampa PDF
A4_LARGHEZZA_MM = 210.0
A4_ALTEZZA_MM = 297.0
MARGINE_STAMPA_MM = 10.0          # margine non stampabile ai bordi del foglio
SOVRAPPOSIZIONE_MM = 10.0         # 1 cm di sovrapposizione tra fogli adiacenti
RISERVA_PIEDE_MM = 18.0           # striscia in basso per intestazione e righello
LINEA_CONTROLLO_MM = 100.0        # riga di verifica scala: 10 cm esatti
SPESSORE_LINEA_SAGOMA_MM = 0.8    # spessore del contorno stampato
MAPPA_SPESSORI_1A1 = True         # genera anche le tavole 1:1 della mappa spessori
LARGHEZZA_ANTEPRIMA_PX = 1600     # risoluzione dell'anteprima nella mappa d'insieme
SALTA_PAGINE_VUOTE = True         # non stampa i fogli in cui non passa la sagoma

# ------------------------------------------------------------ file output
OUT_TONE_MAP = "tone_map.png"
OUT_MASCHERA_DEBUG = "maschera_debug.png"
OUT_CSV = "report_quantita.csv"
OUT_TRACCIA = "traccia_1a1.pdf"
OUT_SPESSORI = "mappa_spessori.pdf"
OUT_GUIDA = "guida_montaggio.md"

# ======================================================================
# ========================= FINE PARAMETRI =============================
# ======================================================================


# ----------------------------------------------------------------------
# Import con installazione automatica se una libreria manca
# ----------------------------------------------------------------------
def _assicura(modulo, pacchetto):
    try:
        __import__(modulo)
    except ImportError:
        print("Libreria '%s' mancante: la installo..." % pacchetto)
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", pacchetto])


for _mod, _pkg in (("PIL", "Pillow"), ("numpy", "numpy"),
                   ("reportlab", "reportlab"), ("scipy", "scipy")):
    _assicura(_mod, _pkg)

import numpy as np                                              # noqa: E402
from PIL import Image, ImageDraw                                # noqa: E402
from scipy import ndimage                                       # noqa: E402
from reportlab.lib.pagesizes import A4, landscape               # noqa: E402
from reportlab.lib.utils import ImageReader                     # noqa: E402
from reportlab.pdfgen import canvas as rl_canvas                # noqa: E402

# Costanti derivate ----------------------------------------------------
PANNELLO_LARGHEZZA_MM = PANNELLO_LARGHEZZA_CM * 10.0
PANNELLO_ALTEZZA_MM = PANNELLO_ALTEZZA_CM * 10.0
PX_PER_MM_SAGOMA = RISOLUZIONE_SAGOMA_PX_CM / 10.0
PT_PER_MM = 72.0 / 25.4          # 1 mm in punti PostScript, calcolato a mano
N_LIVELLI = len(LIVELLI_PLATE)

assert len(SOGLIE_LUMINANZA) == len(TONI_GRIGI) - 1, \
    "SOGLIE_LUMINANZA deve avere un elemento in meno di TONI_GRIGI"
assert len(SOGLIE_PERCENTILI_LIVELLI) == N_LIVELLI - 1, \
    "SOGLIE_PERCENTILI_LIVELLI deve avere un elemento in meno di LIVELLI_PLATE"

INDICE_ROSSO = len(TONI_GRIGI)   # il rosso e' l'ultimo tono della tavolozza
TUTTI_I_TONI = TONI_GRIGI + [TONO_ROSSO]


def mm2pt(v_mm):
    """Converte millimetri in punti PostScript, esplicitamente."""
    return v_mm * PT_PER_MM


# ----------------------------------------------------------------------
# 1. Caricamento, scontorno, adattamento al pannello
# ----------------------------------------------------------------------
def carica_e_ritaglia(percorso):
    if not os.path.exists(percorso):
        sys.exit("ERRORE: non trovo '%s' nella cartella corrente.\n"
                 "Metti qui la foto di profilo e rilancia lo script." % percorso)
    img = Image.open(percorso).convert("RGB")
    l, t, r, b = CROP_FRAZIONI
    box = (int(l * img.width), int(t * img.height),
           int(r * img.width), int(b * img.height))
    return img.crop(box)


def luminanza_e_saturazione(rgb):
    """rgb float 0-1, shape (h,w,3) -> luminanza percettiva e saturazione HSV."""
    lum = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    mx = rgb.max(axis=2)
    mn = rgb.min(axis=2)
    sat = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    return lum, sat


def tinta(rgb):
    """Tinta HSV normalizzata 0-1."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx = rgb.max(axis=2)
    mn = rgb.min(axis=2)
    d = mx - mn
    h = np.zeros_like(mx)
    piatto = d < 1e-6
    rosso_max = (mx == r) & ~piatto
    verde_max = (mx == g) & ~piatto
    blu_max = (mx == b) & ~piatto
    with np.errstate(invalid="ignore", divide="ignore"):
        h[rosso_max] = ((g - b)[rosso_max] / d[rosso_max]) % 6.0
        h[verde_max] = ((b - r)[verde_max] / d[verde_max]) + 2.0
        h[blu_max] = ((r - g)[blu_max] / d[blu_max]) + 4.0
    return (h / 6.0) % 1.0


def scontorna(rgb):
    """Separa l'auto dallo sfondo.

    Lo sfondo e' l'insieme dei pixel chiari e poco saturi CONNESSI al bordo
    dell'immagine: cosi' il gradiente di fondo e la filigrana 'GT3RS' finiscono
    nello sfondo, mentre l'auto resta. Nella fascia bassa si alza la soglia per
    eliminare l'ombra a terra (decisione (c): niente ombra nella sagoma).
    """
    lum, sat = luminanza_e_saturazione(rgb)
    h = rgb.shape[0]

    soglia = np.full(lum.shape, SOGLIA_SFONDO_LUMINANZA, dtype=np.float64)
    riga_bassa = int(FASCIA_BASSA_FRAZIONE * h)
    soglia[riga_bassa:, :] = SOGLIA_SFONDO_LUMINANZA_BASSO

    candidato = (lum >= soglia) & (sat <= SOGLIA_SFONDO_SATURAZIONE)

    # Tiene solo le regioni di sfondo che toccano il bordo dell'immagine.
    etichette, n = ndimage.label(candidato)
    if n == 0:
        sfondo = np.zeros_like(candidato)
    else:
        bordo = np.concatenate([etichette[0, :], etichette[-1, :],
                                etichette[:, 0], etichette[:, -1]])
        id_bordo = set(int(v) for v in np.unique(bordo) if v != 0)
        sfondo = np.isin(etichette, list(id_bordo)) if id_bordo else np.zeros_like(candidato)

    maschera = ~sfondo
    maschera = ndimage.binary_fill_holes(maschera)
    if APERTURA_MASCHERA_PX > 0:
        maschera = ndimage.binary_opening(maschera, iterations=APERTURA_MASCHERA_PX)
        maschera = ndimage.binary_closing(maschera, iterations=APERTURA_MASCHERA_PX)

    # Solo la componente piu' grande: via i residui di filigrana e di UI.
    etichette, n = ndimage.label(maschera)
    if n > 1:
        aree = ndimage.sum(maschera, etichette, range(1, n + 1))
        maschera = etichette == (int(np.argmax(aree)) + 1)
    if not maschera.any():
        sys.exit("ERRORE: scontorno fallito, maschera vuota. Abbassa "
                 "SOGLIA_SFONDO_LUMINANZA e guarda maschera_debug.png.")
    return ndimage.binary_fill_holes(maschera)


def adatta_al_pannello(rgb, maschera):
    """Ritaglia sulla sagoma e la scala per riempire il pannello, centrata."""
    righe = np.where(maschera.any(axis=1))[0]
    colonne = np.where(maschera.any(axis=0))[0]
    y0, y1 = int(righe[0]), int(righe[-1]) + 1
    x0, x1 = int(colonne[0]), int(colonne[-1]) + 1
    rgb = rgb[y0:y1, x0:x1]
    maschera = maschera[y0:y1, x0:x1]

    W = int(round(PANNELLO_LARGHEZZA_CM * RISOLUZIONE_LAVORO_PX_CM))
    H = int(round(PANNELLO_ALTEZZA_CM * RISOLUZIONE_LAVORO_PX_CM))
    utile_w = int(round((PANNELLO_LARGHEZZA_CM - 2 * MARGINE_PANNELLO_CM) * RISOLUZIONE_LAVORO_PX_CM))
    utile_h = int(round((PANNELLO_ALTEZZA_CM - 2 * MARGINE_PANNELLO_CM) * RISOLUZIONE_LAVORO_PX_CM))

    fattore = min(utile_w / maschera.shape[1], utile_h / maschera.shape[0])
    nw = max(1, int(round(maschera.shape[1] * fattore)))
    nh = max(1, int(round(maschera.shape[0] * fattore)))

    rgb_img = Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8))
    rgb_r = np.asarray(rgb_img.resize((nw, nh), Image.LANCZOS), dtype=np.float64) / 255.0
    m_img = Image.fromarray((maschera * 255).astype(np.uint8))
    m_r = np.asarray(m_img.resize((nw, nh), Image.BILINEAR), dtype=np.float64) / 255.0 > 0.5

    tela_rgb = np.ones((H, W, 3), dtype=np.float64)
    tela_m = np.zeros((H, W), dtype=bool)
    ox = (W - nw) // 2
    oy = (H - nh) // 2
    tela_rgb[oy:oy + nh, ox:ox + nw] = rgb_r
    tela_m[oy:oy + nh, ox:ox + nw] = m_r
    tela_rgb[~tela_m] = 1.0          # sfondo bianco
    return tela_rgb, tela_m


# ----------------------------------------------------------------------
# 2. Posterizzazione a N toni
# ----------------------------------------------------------------------
def soglie_effettive(lum, maschera):
    """Soglie fisse, oppure ricavate dai quantili della luminanza nella sagoma."""
    if not SOGLIE_AUTO_PERCENTILI:
        return list(SOGLIE_LUMINANZA)
    dentro = lum[maschera]
    return [float(np.quantile(dentro, q)) for q in SOGLIE_AUTO_PERCENTILI]


def posterizza(rgb, maschera):
    """Restituisce indici di tono (int) e la maschera del rosso."""
    lum, sat = luminanza_e_saturazione(rgb)
    hue = tinta(rgb)
    rosso = (sat >= SOGLIA_SATURAZIONE_ROSSO) & (lum >= SOGLIA_VALORE_ROSSO) & \
            ((hue <= AMPIEZZA_TINTA_ROSSO) | (hue >= 1.0 - AMPIEZZA_TINTA_ROSSO)) & maschera

    soglie = soglie_effettive(lum, maschera)
    indici = np.digitize(lum, soglie).astype(np.int16)             # 0 = piu' scuro
    indici[rosso] = INDICE_ROSSO
    indici[~maschera] = -1                                        # sfondo
    return indici, rosso, lum


def immagine_toni(indici):
    h, w = indici.shape
    out = np.full((h, w, 3), 255, dtype=np.uint8)
    for i, tono in enumerate(TUTTI_I_TONI):
        out[indici == i] = tono["rgb"]
    return Image.fromarray(out)


# ----------------------------------------------------------------------
# 3. Mappa degli spessori
# ----------------------------------------------------------------------
def trova_ruote(lum, maschera):
    """Le due macchie scure piu' grandi nella meta' bassa = ruote/passaruota."""
    if RUOTE_MANUALI:
        return [(cx * RISOLUZIONE_LAVORO_PX_CM,
                 cy * RISOLUZIONE_LAVORO_PX_CM,
                 r * RISOLUZIONE_LAVORO_PX_CM) for cx, cy, r in RUOTE_MANUALI]

    righe = np.where(maschera.any(axis=1))[0]
    y_top, y_bot = int(righe[0]), int(righe[-1])
    meta = y_top + int(0.40 * (y_bot - y_top))

    scuro = (lum < RUOTE_SOGLIA_SCURO) & maschera
    scuro[:meta, :] = False
    # I cerchi sono piu' chiari della gomma: tappa i buchi, cosi' la ruota
    # diventa un disco pieno e l'area si converte davvero in un raggio.
    scuro = ndimage.binary_fill_holes(scuro)
    # Apertura: scioglie il sottoporta (fascia sottile) e lascia intatti i dischi.
    apertura = max(1, int(round(RUOTE_APERTURA_CM * RISOLUZIONE_LAVORO_PX_CM)))
    scuro = ndimage.binary_opening(scuro, iterations=apertura)

    etichette, n = ndimage.label(scuro)
    if n == 0:
        return []
    aree = ndimage.sum(scuro, etichette, range(1, n + 1))
    ordine = np.argsort(aree)[::-1][:2]
    area_min_px = RUOTE_AREA_MINIMA_CM2 * (RISOLUZIONE_LAVORO_PX_CM ** 2)
    ruote = []
    for idx in ordine:
        area = float(aree[idx])
        if area < area_min_px:
            continue
        cy, cx = ndimage.center_of_mass(scuro, etichette, int(idx) + 1)
        raggio = math.sqrt(area / math.pi) * RUOTE_RAGGIO_EXTRA
        ruote.append((float(cx), float(cy), float(raggio)))
    return ruote


def mappa_profondita(indici, lum, maschera, rosso):
    """Somma pesata di tono + rampa verticale + bombatura - ruote."""
    h, w = maschera.shape

    # (1) base tonale: 0 = tono piu' scuro, 1 = tono piu' chiaro.
    # Il rosso non ha una profondita' propria: usa la luminanza sottostante,
    # cosi' la scritta segue la quota della fascia su cui e' appoggiata.
    rango = np.clip(indici, 0, len(TONI_GRIGI) - 1).astype(np.float64)
    rango_rosso = np.digitize(lum, soglie_effettive(lum, maschera)).astype(np.float64)
    rango = np.where(rosso, rango_rosso, rango)
    base = rango / max(1.0, (len(TONI_GRIGI) - 1))

    # (2) rampa verticale asimmetrica dentro il bounding box della sagoma.
    righe = np.where(maschera.any(axis=1))[0]
    y_top, y_bot = int(righe[0]), int(righe[-1])
    yy = np.arange(h, dtype=np.float64).reshape(-1, 1)
    y_n = np.clip((yy - y_top) / max(1.0, (y_bot - y_top)), 0.0, 1.0)
    campana = np.exp(-((y_n - RAMPA_CENTRO_VERTICALE) ** 2) / (2 * RAMPA_SIGMA ** 2))
    rampa = np.repeat(campana * (1.0 - RAMPA_DECADIMENTO_BASSO * y_n), w, axis=1)

    # (3) bombatura: distanza dal bordo della sagoma, satura a N cm.
    dist = ndimage.distance_transform_edt(maschera)
    dist_max = DISTANZA_SATURAZIONE_CM * RISOLUZIONE_LAVORO_PX_CM
    bombatura = np.clip(dist / max(1.0, dist_max), 0.0, 1.0)

    prof = PESO_TONO * base + PESO_VERTICALE * rampa + PESO_DISTANZA * bombatura

    # (4) ruote e passaruota: scavo con caduta morbida verso il bordo del cerchio.
    ruote = trova_ruote(lum, maschera)
    if ruote:
        xs = np.arange(w, dtype=np.float64).reshape(1, -1)
        ys = np.arange(h, dtype=np.float64).reshape(-1, 1)
        scavo = np.zeros((h, w), dtype=np.float64)
        for cx, cy, r in ruote:
            d = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2) / max(1.0, r)
            scavo = np.maximum(scavo, np.clip(1.0 - d, 0.0, 1.0))
        prof -= PESO_RUOTE * scavo

    # Sfumatura: senza questa restano picchi da un solo stud, non costruibili.
    sigma = SFUMATURA_PROFONDITA_CM * RISOLUZIONE_LAVORO_PX_CM
    if sigma > 0:
        prof = ndimage.gaussian_filter(prof, sigma=sigma)

    dentro = prof[maschera]
    lo, hi = float(dentro.min()), float(dentro.max())
    if hi - lo > 1e-9:
        prof = (prof - lo) / (hi - lo)
    prof[~maschera] = 0.0
    return prof, ruote


def quantizza_livelli(prof, maschera, indici, rosso, ruote):
    """Da mappa continua a 4 livelli, con clamp padiglione e rosso sporgente."""
    valori = prof[maschera]
    tagli = [float(np.quantile(valori, q)) for q in SOGLIE_PERCENTILI_LIVELLI]
    livelli = np.digitize(prof, tagli).astype(np.int16)
    livelli[~maschera] = -1

    # Pulizia: mediana + assorbimento delle isole troppo piccole.
    lato = max(1, int(round(MEDIANA_LIVELLI_CM * RISOLUZIONE_LAVORO_PX_CM)))
    filtrati = ndimage.median_filter(livelli, size=lato)
    livelli = np.where(maschera, filtrati, -1)
    livelli = assorbi_isole(livelli, maschera)

    # Decisione (a): padiglione, vetri e alettone non scendono sotto L1.
    righe = np.where(maschera.any(axis=1))[0]
    y_top, y_bot = int(righe[0]), int(righe[-1])
    quota = y_top + QUOTA_PADIGLIONE_FRAZIONE * (y_bot - y_top)
    alto = np.zeros_like(maschera)
    alto[:int(quota), :] = True

    fuori_ruote = np.ones_like(maschera)
    if ruote:
        h, w = maschera.shape
        xs = np.arange(w, dtype=np.float64).reshape(1, -1)
        ys = np.arange(h, dtype=np.float64).reshape(-1, 1)
        for cx, cy, r in ruote:
            fuori_ruote &= (np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2) > r)

    da_alzare = maschera & alto & fuori_ruote & (livelli < LIVELLO_MINIMO_PADIGLIONE)
    livelli[da_alzare] = LIVELLO_MINIMO_PADIGLIONE

    # Decisione (b): il rosso sporge rispetto al tono che lo circonda.
    # Applicato DOPO la pulizia, altrimenti le lettere sottili verrebbero mangiate.
    if ROSSO_SPORGE_DI_LIVELLI:
        livelli[rosso] = np.minimum(livelli[rosso] + ROSSO_SPORGE_DI_LIVELLI, N_LIVELLI - 1)

    return livelli, tagli


def assorbi_isole(livelli, maschera):
    """Sostituisce le isole sotto AREA_MINIMA_ISOLA_CM2 col livello prevalente attorno."""
    px_min = AREA_MINIMA_ISOLA_CM2 * (RISOLUZIONE_LAVORO_PX_CM ** 2)
    out = livelli.copy()
    for liv in range(N_LIVELLI):
        zona = (out == liv) & maschera
        etichette, n = ndimage.label(zona)
        if n == 0:
            continue
        aree = ndimage.sum(zona, etichette, range(1, n + 1))
        for i, area in enumerate(aree):
            if area >= px_min:
                continue
            comp = etichette == (i + 1)
            anello = ndimage.binary_dilation(comp, iterations=3) & ~comp & maschera
            vicini = out[anello]
            vicini = vicini[vicini >= 0]
            if vicini.size:
                conteggi = np.bincount(vicini.astype(np.int64), minlength=N_LIVELLI)
                out[comp] = int(np.argmax(conteggi))
    return out


# ----------------------------------------------------------------------
# 4. Raster ad alta risoluzione per la stampa
# ----------------------------------------------------------------------
def alza_risoluzione(arr, is_maschera):
    """Porta un array dalla risoluzione di lavoro a quella di stampa."""
    W = int(round(PANNELLO_LARGHEZZA_CM * RISOLUZIONE_SAGOMA_PX_CM))
    H = int(round(PANNELLO_ALTEZZA_CM * RISOLUZIONE_SAGOMA_PX_CM))
    if is_maschera:
        img = Image.fromarray((arr * 255).astype(np.uint8))
        grande = np.asarray(img.resize((W, H), Image.BILINEAR), dtype=np.float64)
        return grande > 127.0
    img = Image.fromarray((arr + 1).astype(np.uint8))      # -1 -> 0 per il resize
    grande = np.asarray(img.resize((W, H), Image.NEAREST), dtype=np.int16)
    return grande - 1


def raster_contorno(maschera_grande):
    """Contorno della sagoma, spesso SPESSORE_LINEA_SAGOMA_MM."""
    spessore_px = max(1, int(round(SPESSORE_LINEA_SAGOMA_MM * PX_PER_MM_SAGOMA)))
    interno = ndimage.binary_erosion(maschera_grande, iterations=spessore_px)
    return maschera_grande & ~interno


def immagine_contorno(contorno_crop):
    arr = np.where(contorno_crop, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode="L")


def immagine_retino(livelli_crop, x0_px, y0_px, px_per_mm):
    """Disegna i 4 livelli con retini diversi + le linee di confine tra livelli."""
    h, w = livelli_crop.shape
    ys = (np.arange(h, dtype=np.int64) + y0_px).reshape(-1, 1)
    xs = (np.arange(w, dtype=np.int64) + x0_px).reshape(1, -1)
    out = np.full((h, w), 255, dtype=np.uint8)

    def linee(periodo_mm, spessore_mm, diagonale_positiva=True):
        periodo = max(2, int(round(periodo_mm * px_per_mm)))
        spess = max(1, int(round(spessore_mm * px_per_mm)))
        d = (xs + ys) if diagonale_positiva else (xs - ys)
        return (d % periodo) < spess

    # L0 = bianco (filo pannello, nessun retino)
    out[(livelli_crop == 1) & linee(3.5, 0.6, True)] = 60           # diagonali /
    incrociato = linee(3.5, 0.6, True) | linee(3.5, 0.6, False)
    out[(livelli_crop == 2) & incrociato] = 40                       # reticolo
    denso = linee(1.6, 0.6, True) | linee(1.6, 0.6, False)
    out[(livelli_crop == 3) & denso] = 0                             # reticolo fitto

    # Confini tra livelli diversi (e col fondo): linea nera continua.
    liv = livelli_crop
    bordo = np.zeros((h, w), dtype=bool)
    bordo[:, :-1] |= liv[:, :-1] != liv[:, 1:]
    bordo[:-1, :] |= liv[:-1, :] != liv[1:, :]
    spess = max(1, int(round(SPESSORE_LINEA_SAGOMA_MM * px_per_mm)))
    if spess > 1:
        bordo = ndimage.binary_dilation(bordo, iterations=spess - 1)
    out[bordo] = 0
    out[livelli_crop < 0] = 255                                      # fuori sagoma
    return Image.fromarray(out, mode="L")


# ----------------------------------------------------------------------
# 5. Impaginazione A4
# ----------------------------------------------------------------------
def griglia_pagine():
    """Divide il pannello in fogli A4 verticali con 1 cm di sovrapposizione."""
    utile_w = A4_LARGHEZZA_MM - 2 * MARGINE_STAMPA_MM
    utile_h = A4_ALTEZZA_MM - 2 * MARGINE_STAMPA_MM - RISERVA_PIEDE_MM
    passo_w = utile_w - SOVRAPPOSIZIONE_MM
    passo_h = utile_h - SOVRAPPOSIZIONE_MM
    n_col = max(1, int(math.ceil((PANNELLO_LARGHEZZA_MM - SOVRAPPOSIZIONE_MM) / passo_w)))
    n_rig = max(1, int(math.ceil((PANNELLO_ALTEZZA_MM - SOVRAPPOSIZIONE_MM) / passo_h)))

    pagine = []
    for r in range(n_rig):
        for c in range(n_col):
            x0 = c * passo_w
            y0 = r * passo_h
            pagine.append({
                "riga": r + 1, "colonna": c + 1,
                "x0_mm": x0, "y0_mm": y0,
                "w_mm": min(utile_w, PANNELLO_LARGHEZZA_MM - x0),
                "h_mm": min(utile_h, PANNELLO_ALTEZZA_MM - y0),
            })
    return pagine, n_rig, n_col, utile_w, utile_h


def _ritaglia(arr, pag):
    """Ritaglia il raster di stampa sulla finestra di una pagina."""
    px0 = int(round(pag["x0_mm"] * PX_PER_MM_SAGOMA))
    py0 = int(round(pag["y0_mm"] * PX_PER_MM_SAGOMA))
    px1 = min(arr.shape[1], px0 + int(round(pag["w_mm"] * PX_PER_MM_SAGOMA)))
    py1 = min(arr.shape[0], py0 + int(round(pag["h_mm"] * PX_PER_MM_SAGOMA)))
    return arr[py0:py1, px0:px1], px0, py0


def _disegna_piede(c, testo, etichetta_scala):
    """Intestazione e riga di controllo da 10 cm esatti."""
    c.setFont("Helvetica-Bold", 8)
    c.drawString(mm2pt(MARGINE_STAMPA_MM), mm2pt(MARGINE_STAMPA_MM + 12.0), testo)

    y = mm2pt(MARGINE_STAMPA_MM + 4.0)
    x = mm2pt(MARGINE_STAMPA_MM)
    c.setLineWidth(0.6)
    c.line(x, y, x + mm2pt(LINEA_CONTROLLO_MM), y)                  # 100 mm esatti
    for k in range(11):                                             # tacche ogni cm
        xt = x + mm2pt(k * 10.0)
        alta = mm2pt(2.5) if k % 5 == 0 else mm2pt(1.5)
        c.line(xt, y, xt, y + alta)
    c.setFont("Helvetica", 6.5)
    c.drawString(x + mm2pt(LINEA_CONTROLLO_MM + 3.0), y - mm2pt(0.6), etichetta_scala)


def _disegna_crocini(c, x_mm, y_mm, w_mm, h_mm):
    """Crocini di allineamento ai quattro angoli dell'area disegnata."""
    braccio = mm2pt(4.0)
    c.setLineWidth(0.4)
    for cx, cy in ((x_mm, y_mm), (x_mm + w_mm, y_mm),
                   (x_mm, y_mm + h_mm), (x_mm + w_mm, y_mm + h_mm)):
        px, py = mm2pt(cx), mm2pt(cy)
        c.line(px - braccio, py, px + braccio, py)
        c.line(px, py - braccio, px, py + braccio)


def _pagina_tavola(c, pag, immagine, num, tot, titolo):
    """Una tavola 1:1: immagine in scala esatta + crocini + piede."""
    crop_w_mm = immagine.width / PX_PER_MM_SAGOMA        # scala esplicita, niente default
    crop_h_mm = immagine.height / PX_PER_MM_SAGOMA
    area_top_mm = MARGINE_STAMPA_MM + RISERVA_PIEDE_MM + \
        (A4_ALTEZZA_MM - 2 * MARGINE_STAMPA_MM - RISERVA_PIEDE_MM)
    x_mm = MARGINE_STAMPA_MM
    y_mm = area_top_mm - crop_h_mm

    c.drawImage(ImageReader(immagine), mm2pt(x_mm), mm2pt(y_mm),
                width=mm2pt(crop_w_mm), height=mm2pt(crop_h_mm))
    _disegna_crocini(c, x_mm, y_mm, crop_w_mm, crop_h_mm)

    # Guide tratteggiate: dove inizia il foglio successivo (banda di sovrapposizione).
    c.setDash(2, 3)
    c.setLineWidth(0.3)
    if crop_w_mm > SOVRAPPOSIZIONE_MM + 1:
        xg = mm2pt(x_mm + crop_w_mm - SOVRAPPOSIZIONE_MM)
        c.line(xg, mm2pt(y_mm), xg, mm2pt(y_mm + crop_h_mm))
    if crop_h_mm > SOVRAPPOSIZIONE_MM + 1:
        yg = mm2pt(y_mm + SOVRAPPOSIZIONE_MM)
        c.line(mm2pt(x_mm), yg, mm2pt(x_mm + crop_w_mm), yg)
    c.setDash()

    testo = "%s  |  pag. %d/%d  |  riga %d, colonna %d  |  origine X=%.1f cm  Y=%.1f cm" % (
        titolo, num, tot, pag["riga"], pag["colonna"], pag["x0_mm"] / 10.0, pag["y0_mm"] / 10.0)
    _disegna_piede(c, testo, "10 cm esatti - se misura diverso la stampa e' scalata")
    c.showPage()


def _geometria_insieme(con_legenda):
    """Posizione e dimensione, in mm di carta, del disegno nella mappa d'insieme.

    Serve anche a chi prepara l'anteprima: il passo dei retini va calcolato in
    millimetri di CARTA, non di pannello, altrimenti sulla mappa ridotta i
    quattro retini diventano un grigio indistinto.
    """
    foglio_w, foglio_h = A4_ALTEZZA_MM, A4_LARGHEZZA_MM      # A4 orizzontale
    margine = 14.0
    disp_w = foglio_w - 2 * margine
    disp_h = foglio_h - 2 * margine - (34.0 if con_legenda else 20.0)
    k = min(disp_w / PANNELLO_LARGHEZZA_MM, disp_h / PANNELLO_ALTEZZA_MM)
    dis_w, dis_h = PANNELLO_LARGHEZZA_MM * k, PANNELLO_ALTEZZA_MM * k
    return margine, foglio_h - margine - 12.0 - dis_h, dis_w, dis_h, k, foglio_h


def _pagina_insieme(c, pagine, stampate, n_rig, n_col, anteprima, titolo, legenda=None):
    """Mappa d'insieme: come disporre i fogli sul pannello."""
    c.setPageSize(landscape(A4))
    margine = 14.0
    x0, y0, dis_w, dis_h, k, foglio_h = _geometria_insieme(legenda is not None)

    c.setFont("Helvetica-Bold", 13)
    c.drawString(mm2pt(margine), mm2pt(foglio_h - margine - 4.0), titolo)
    c.setFont("Helvetica", 8)
    c.drawString(mm2pt(margine), mm2pt(foglio_h - margine - 10.0),
                 "Pannello %.0f x %.0f cm - %d fogli A4 verticali, sovrapposizione %.0f cm. "
                 "Stampare al 100%%, senza adatta alla pagina."
                 % (PANNELLO_LARGHEZZA_CM, PANNELLO_ALTEZZA_CM, len(stampate),
                    SOVRAPPOSIZIONE_MM / 10.0))

    c.drawImage(ImageReader(anteprima), mm2pt(x0), mm2pt(y0),
                width=mm2pt(dis_w), height=mm2pt(dis_h))
    c.setLineWidth(1.0)
    c.rect(mm2pt(x0), mm2pt(y0), mm2pt(dis_w), mm2pt(dis_h))

    numeri = {(p["riga"], p["colonna"]): i + 1 for i, p in enumerate(stampate)}
    c.setLineWidth(0.3)
    for pag in pagine:
        gx = x0 + pag["x0_mm"] * k
        gy = y0 + dis_h - (pag["y0_mm"] + pag["h_mm"]) * k
        gw, gh = pag["w_mm"] * k, pag["h_mm"] * k
        chiave = (pag["riga"], pag["colonna"])
        if chiave in numeri:
            c.setDash()
            c.rect(mm2pt(gx), mm2pt(gy), mm2pt(gw), mm2pt(gh))
            c.setFont("Helvetica-Bold", 9)
            c.drawCentredString(mm2pt(gx + gw / 2), mm2pt(gy + gh / 2 - 1.2),
                                str(numeri[chiave]))
        else:
            c.setDash(1, 2)
            c.rect(mm2pt(gx), mm2pt(gy), mm2pt(gw), mm2pt(gh))
            c.setDash()
            c.setFont("Helvetica", 6)
            c.setFillGray(0.55)
            c.drawCentredString(mm2pt(gx + gw / 2), mm2pt(gy + gh / 2 - 1.0), "vuoto")
            c.setFillGray(0.0)

    if legenda:
        yl = y0 - 8.0
        c.setFont("Helvetica-Bold", 8)
        c.drawString(mm2pt(margine), mm2pt(yl), "LEGENDA LIVELLI")
        yl -= 6.0
        for voce in legenda:
            c.drawImage(ImageReader(voce["campione"]), mm2pt(margine), mm2pt(yl - 4.0),
                        width=mm2pt(14.0), height=mm2pt(7.0))
            c.setLineWidth(0.3)
            c.rect(mm2pt(margine), mm2pt(yl - 4.0), mm2pt(14.0), mm2pt(7.0))
            c.setFont("Helvetica", 7.5)
            c.drawString(mm2pt(margine + 17.0), mm2pt(yl - 1.5), voce["testo"])
            yl -= 9.0

    c.showPage()
    c.setPageSize(A4)


def _anteprima_contorno(maschera_grande):
    """Contorno ricalcolato alla risoluzione dell'anteprima.

    Ridurre il contorno gia' disegnato lo assottiglierebbe fino a farlo sparire:
    si riduce prima la maschera, poi si ricava il bordo con spessore giusto.
    """
    w = LARGHEZZA_ANTEPRIMA_PX
    h = int(round(w * PANNELLO_ALTEZZA_CM / PANNELLO_LARGHEZZA_CM))
    piccola = np.asarray(Image.fromarray((maschera_grande * 255).astype(np.uint8))
                         .resize((w, h), Image.BILINEAR), dtype=np.uint8) > 127
    bordo = piccola & ~ndimage.binary_erosion(piccola, iterations=2)
    return Image.fromarray(np.where(bordo, 0, 255).astype(np.uint8), mode="L")


def genera_pdf_traccia(contorno_grande, maschera_grande):
    pagine, n_rig, n_col, _, _ = griglia_pagine()
    stampate = []
    for pag in pagine:
        crop, _, _ = _ritaglia(maschera_grande, pag)
        if SALTA_PAGINE_VUOTE and not crop.any():
            continue
        stampate.append(pag)

    c = rl_canvas.Canvas(OUT_TRACCIA, pagesize=A4)
    c.setTitle("Traccia 1:1 - bassorilievo LEGO 911 GT3 RS")

    anteprima = _anteprima_contorno(maschera_grande)
    _pagina_insieme(c, pagine, stampate, n_rig, n_col, anteprima,
                    "TRACCIA 1:1 - MAPPA D'INSIEME DEI FOGLI")

    for i, pag in enumerate(stampate):
        crop, _, _ = _ritaglia(contorno_grande, pag)
        _pagina_tavola(c, pag, immagine_contorno(crop), i + 1, len(stampate), "TRACCIA 1:1")
    c.save()
    return len(stampate) + 1, len(pagine)


def genera_pdf_spessori(livelli_grande, maschera_grande):
    pagine, n_rig, n_col, _, _ = griglia_pagine()
    stampate = []
    for pag in pagine:
        crop, _, _ = _ritaglia(maschera_grande, pag)
        if SALTA_PAGINE_VUOTE and not crop.any():
            continue
        stampate.append(pag)
    if not MAPPA_SPESSORI_1A1:
        stampate = []

    c = rl_canvas.Canvas(OUT_SPESSORI, pagesize=A4)
    c.setTitle("Mappa spessori - bassorilievo LEGO 911 GT3 RS")

    # Anteprima: il passo dei retini si calcola sui mm di CARTA occupati dal
    # disegno ridotto, altrimenti i quattro livelli diventano indistinguibili.
    _, _, dis_w_mm, _, _, _ = _geometria_insieme(True)
    w_ant = LARGHEZZA_ANTEPRIMA_PX
    h_ant = int(round(w_ant * PANNELLO_ALTEZZA_CM / PANNELLO_LARGHEZZA_CM))
    px_mm_carta = w_ant / dis_w_mm
    liv_ant = np.asarray(Image.fromarray((livelli_grande + 1).astype(np.uint8))
                         .resize((w_ant, h_ant), Image.NEAREST), dtype=np.int16) - 1
    anteprima = immagine_retino(liv_ant, 0, 0, px_mm_carta)

    legenda = []
    for liv in range(N_LIVELLI):
        mm_alt = LIVELLI_PLATE[liv] * SPESSORE_PLATE_MM
        campione_liv = np.full((70, 140), liv, dtype=np.int16)
        legenda.append({
            "campione": immagine_retino(campione_liv, 0, 0, 10.0),
            "testo": "Livello %d - %d plate = %.1f mm (%s)" % (
                liv, LIVELLI_PLATE[liv], mm_alt,
                "filo pannello" if liv == 0 else "rilievo massimo" if liv == N_LIVELLI - 1
                else "rilievo intermedio"),
        })

    _pagina_insieme(c, pagine, stampate, n_rig, n_col, anteprima,
                    "MAPPA SPESSORI - 4 LIVELLI DI PROFONDITA'", legenda=legenda)

    for i, pag in enumerate(stampate):
        crop, px0, py0 = _ritaglia(livelli_grande, pag)
        img = immagine_retino(crop, px0, py0, PX_PER_MM_SAGOMA)
        _pagina_tavola(c, pag, img, i + 1, len(stampate), "MAPPA SPESSORI 1:1")
    c.save()
    return len(stampate) + 1


# ----------------------------------------------------------------------
# 6. Report quantita'
# ----------------------------------------------------------------------
def calcola_quantita(indici):
    area_px = 1.0 / (RISOLUZIONE_LAVORO_PX_CM ** 2)      # cm2 per pixel
    righe = []
    totale_cm2 = float((indici >= 0).sum()) * area_px
    for i, tono in enumerate(TUTTI_I_TONI):
        cm2 = float((indici == i).sum()) * area_px
        if cm2 <= 0:
            continue
        pezzi = cm2 / AREA_MEDIA_PEZZO_CM2 * FATTORE_STRATIFICAZIONE
        peso_kg = pezzi * PESO_MEDIO_PEZZO_G / 1000.0
        righe.append({
            "tono": tono["nome"],
            "area_cm2": cm2,
            "perc": 100.0 * cm2 / totale_cm2 if totale_cm2 else 0.0,
            "pezzi": pezzi,
            "peso_kg": peso_kg,
            "kg_ordine": peso_kg * (1.0 + MARGINE_ORDINE),
        })
    return righe, totale_cm2


def scrivi_csv(righe):
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["tono", "area_cm2", "percentuale", "pezzi_stimati",
                    "peso_stimato_kg", "kg_da_ordinare_con_margine_%d%%" % int(MARGINE_ORDINE * 100)])
        for r in righe:
            w.writerow([r["tono"], "%.1f" % r["area_cm2"], "%.1f" % r["perc"],
                        "%d" % round(r["pezzi"]), "%.2f" % r["peso_kg"], "%.2f" % r["kg_ordine"]])


# ----------------------------------------------------------------------
# 7. Guida di montaggio
# ----------------------------------------------------------------------
def scrivi_guida(righe, totale_cm2, aree_livelli, pagine_traccia, pagine_spessori, ruote):
    liv_txt = "\n".join(
        "| %d | %d plate | %.1f mm | %.0f cm2 | %.1f%% |" % (
            i, LIVELLI_PLATE[i], LIVELLI_PLATE[i] * SPESSORE_PLATE_MM,
            aree_livelli[i], 100.0 * aree_livelli[i] / max(1e-9, sum(aree_livelli)))
        for i in range(N_LIVELLI))
    ord_txt = "\n".join(
        "| %s | %.0f cm2 | %.1f%% | %d | %.2f kg | **%.2f kg** |" % (
            r["tono"], r["area_cm2"], r["perc"], round(r["pezzi"]), r["peso_kg"], r["kg_ordine"])
        for r in righe)
    totale_ordine = sum(r["kg_ordine"] for r in righe)

    testo = """# Guida di montaggio - Bassorilievo LEGO Porsche 911 GT3 RS

Pannello **%(pw).0f x %(ph).0f cm**, sagoma **%(area).0f cm2** di superficie visibile,
rilievo massimo **%(max_mm).1f mm**.

Tutti i numeri di questo documento sono stati generati da `genera_bassorilievo.py`:
se cambi i parametri in cima allo script, rilancialo e questa guida si riscrive.

---

## 1. Preparazione del pannello

- [ ] Pannello rigido %(pw).0f x %(ph).0f cm: multistrato da 10-12 mm o MDF da 16 mm.
      Il compensato sottile si imbarca sotto il peso (stimato **%(peso).1f kg** di sola plastica,
      piu' colla e cornice).
- [ ] Irrigidisci il retro con due traverse verticali se usi MDF sotto i 16 mm.
- [ ] Carteggia, sverniciatore leggero, poi **due mani di primer bianco opaco**: il bianco
      e' il fondo che si vede tra i pezzi ai bordi della sagoma.
- [ ] Predisponi **ora** l'aggancio a muro (due staffe a scomparsa) mentre il pannello e' leggero.
- [ ] Stampa `traccia_1a1.pdf` (%(pt)d pagine) al **100%%**, senza "adatta alla pagina".
      Su ogni foglio c'e' una riga da 10 cm: **misurala col metro prima di tagliare**.
      Se non misura 10,0 cm la stampa e' scalata e la sagoma non tornera'.
- [ ] Assembla i fogli seguendo la mappa d'insieme (prima pagina), sovrapponendo 1 cm
      e allineando i crocini agli angoli. Nastro carta sul retro.
- [ ] Riporta la sagoma sul pannello: carta carbone, oppure buca il profilo con uno spillo
      ogni 2 cm e unisci i punti a matita.
- [ ] Riporta anche i confini dei 4 livelli da `mappa_spessori.pdf` (%(ps)d pagine),
      con matite di colore diverso. Scrivi il numero del livello dentro ogni zona.

## 2. Livelli di profondita'

| Livello | Spessore | Altezza | Area | Quota |
|---|---|---|---|---|
%(liv)s

Il livello 0 e' a filo pannello (una sola plate o tile). Ogni gradino successivo
aggiunge 4 plate, cioe' %(passo).1f mm. Non serve che lo strato sotto sia pieno:
va bene una struttura a nido d'ape di brick 2x4 con il pieno solo dove appoggia
la superficie visibile.

## 3. Ordine delle zone da riempire

Si lavora **dal fondo verso l'alto e dal centro verso i bordi**: ogni zona nuova
appoggia contro una gia' incollata e non puo' scivolare.

1. **Ruote e passaruota** (livello 0-1, le zone piu' incassate).
   %(ruote)s
   Sono le due ancore geometriche di tutto il quadro: se sono nel punto giusto,
   il resto dell'auto si posiziona da solo. Verificale col metro prima di incollare.
2. **Fascia bassa**: minigonna, sottoporta, diffusore. Livelli 0-1, tanto nero e grigio scuro.
3. **Volumi centrali della carrozzeria**: fiancata, portiera, spalla del parafango.
   Sono i livelli 2-3, la parte che sporge di piu' e che da' il volume al pezzo.
4. **Padiglione, vetri e montanti**: scuri ma **mai a livello 0**, restano almeno a livello 1.
   E' la correzione che impedisce al tetto di sembrare un buco.
5. **Alettone posteriore**: livello 2-3, staccato dal corpo. Lascia visibile il bianco
   del pannello nella feritoia sotto l'ala: e' quel vuoto che lo fa "galleggiare".
6. **Accenti rossi** (scritta GT3 RS sulla fiancata, fanali): per ultimi, e sporgono
   di %(rosso)d livello rispetto al tono su cui appoggiano. Vanno posati sopra la
   fascia gia' finita, non annegati dentro.

## 4. Tecnica dei grappoli pre-incollati

Non incollare pezzo per pezzo sul pannello: si perde il controllo del disegno
e la colla tira prima che tu abbia sistemato la zona.

- [ ] Lavora a **grappoli di 10-20 x 10-20 cm**, montati a secco su una base staccabile.
- [ ] Componi il grappolo **fuori dal pannello**, appoggiandolo sopra la traccia per
      controllare forma e tono. Fotografalo prima di incollare: e' l'unico modo
      per rimontarlo identico se si sfascia.
- [ ] Colla: **cianoacrilica gel** tra pezzo e pezzo (presa in pochi secondi, riempie
      i giochi), oppure colla a caldo a bassa temperatura per i volumi interni.
      Niente vinilica: sul plastico non tiene.
- [ ] Incolla solo i punti di contatto interni al grappolo, **non tutti i punti**:
      un grappolo troppo rigido non si adatta alle irregolarita' del pannello.
- [ ] Fissa il grappolo al pannello con cordoli di **colla a caldo** o **silicone neutro**
      lungo il perimetro e in 3-4 punti centrali. Il silicone resta leggermente
      elastico e assorbe le dilatazioni: su un pannello da %(pw).0f cm servono.
- [ ] Pressa 30 secondi e passa al grappolo adiacente, incastrandolo contro il precedente.

## 5. Gestione dei bordi

- Il bordo esterno della sagoma **non deve essere una scaletta di studs**. Alterna
  pezzi di lunghezza diversa (1x1, 1x2, 1x3, 2x2, slope) in modo che il profilo
  risulti frastagliato in modo irregolare: e' il collage, non il mosaico.
- Sul bordo il rilievo deve **scendere**: l'ultimo centimetro di sagoma sta a livello 0-1
  anche dove il livello interno e' 3. Un bordo tagliato di netto a 4 cm sembra un blocco.
- Usa **tile lisce** (senza stud) sul filo estremo: chiudono il profilo e lo rendono netto.
- Dove il profilo e' curvo (passaruota, cofano), usa slope e curved slope orientate
  a seguire la curva. Le ruote sono il posto dove un bordo a gradini si nota di piu'.
- Tieni **1-2 mm di bianco** tra la sagoma e il pezzo piu' esterno: uno stacco netto
  legge meglio di un bordo che sbava sul fondo.

## 6. Elementi che sporgono oltre la sagoma - effetto scia

E' il dettaglio che trasforma un pannello descrittivo in un pezzo con movimento.
**Vanno fuori dalla traccia, verso il retro dell'auto**, e non sono nella sagoma stampata.

- [ ] **Aste orizzontali**: barre lisce (Technic axle, antenne, bar 1x4) montate
      orizzontali che escono dal profilo posteriore per **10-25 cm**, a lunghezze
      irregolari. Piu' lunghe in alto vicino all'alettone, piu' corte in basso.
- [ ] **Sfilacciamento dei toni**: nei 15 cm dietro l'auto, continua i colori della
      carrozzeria con pezzi sempre piu' radi e piccoli, che si diradano fino al bianco.
      La densita' deve calare in modo graduale, non troncato.
- [ ] **Scia rossa dei fanali**: due o tre barre rosse lunghe che escono dalla fascia
      dei fanali, sono la firma dell'effetto. Falle uscire di piu' di tutte le altre.
- [ ] **Distacco dal pannello**: gli elementi della scia possono stare a livello 2-3
      anche se il pannello attorno e' vuoto, montati su un singolo pilastrino nascosto.
      L'ombra che proiettano sul bianco fa meta' del lavoro.
- [ ] Monta la scia **per ultima**, a quadro finito e in verticale, guardandolo da
      3-4 metri. E' l'unico modo per dosarla: da vicino sembrera' sempre troppo poca.

## 7. Ordine materiale

| Tono | Area | %% | Pezzi stimati | Peso stimato | Da ordinare (+%(margine)d%%) |
|---|---|---|---|---|---|
%(ord)s

**Totale da ordinare: %(tot_ord).2f kg.**

I pezzi si comprano **a peso in lotti misti** (bulk/sfusi), non per singolo stampo:
il collage vive proprio della varieta' di forme. Ordina per **colore**, non per pezzo.
Il fattore di stratificazione %(strat).1f copre i pezzi sotto, che non si vedono:
per quelli puoi usare qualsiasi colore, quindi una parte del peso puo' essere
coperta da lotti misti economici.
""" % {
        "pw": PANNELLO_LARGHEZZA_CM, "ph": PANNELLO_ALTEZZA_CM,
        "area": totale_cm2,
        "max_mm": LIVELLI_PLATE[-1] * SPESSORE_PLATE_MM,
        "peso": sum(r["peso_kg"] for r in righe),
        "pt": pagine_traccia, "ps": pagine_spessori,
        "liv": liv_txt, "ord": ord_txt,
        "passo": 4 * SPESSORE_PLATE_MM,
        "rosso": ROSSO_SPORGE_DI_LIVELLI,
        "margine": int(MARGINE_ORDINE * 100),
        "tot_ord": totale_ordine,
        "strat": FATTORE_STRATIFICAZIONE,
        "ruote": ("Centri rilevati: " + "; ".join(
            "x=%.0f cm, y=%.0f cm, raggio %.0f cm" % (
                cx / RISOLUZIONE_LAVORO_PX_CM, cy / RISOLUZIONE_LAVORO_PX_CM,
                r / RISOLUZIONE_LAVORO_PX_CM) for cx, cy, r in ruote))
        if ruote else "Nessuna ruota rilevata: impostale a mano in RUOTE_MANUALI.",
    }
    with open(OUT_GUIDA, "w", encoding="utf-8") as f:
        f.write(testo)


# ----------------------------------------------------------------------
# 8. Main
# ----------------------------------------------------------------------
def main():
    print("Bassorilievo LEGO - Porsche 911 GT3 RS")
    print("=" * 62)

    img = carica_e_ritaglia(FILE_IMMAGINE)
    print("Immagine: %s  ->  %d x %d px dopo il ritaglio" % (FILE_IMMAGINE, img.width, img.height))

    rgb_src = np.asarray(img, dtype=np.float64) / 255.0
    maschera_src = scontorna(rgb_src)
    perc = 100.0 * maschera_src.mean()
    print("Scontorno: la sagoma occupa il %.1f%% dell'immagine ritagliata" % perc)
    if perc < 5 or perc > 85:
        print("  ATTENZIONE: valore sospetto. Controlla maschera_debug.png e rivedi")
        print("  SOGLIA_SFONDO_LUMINANZA / SOGLIA_SFONDO_SATURAZIONE.")

    debug = (rgb_src * 255).astype(np.uint8).copy()
    debug[~maschera_src] = (debug[~maschera_src] * 0.35 + np.array([160, 0, 110]) * 0.65).astype(np.uint8)
    Image.fromarray(debug).save(OUT_MASCHERA_DEBUG)

    rgb, maschera = adatta_al_pannello(rgb_src, maschera_src)
    indici, rosso, lum = posterizza(rgb, maschera)
    immagine_toni(indici).resize(
        (int(round(PANNELLO_LARGHEZZA_CM * RISOLUZIONE_OUTPUT_PX_CM)),
         int(round(PANNELLO_ALTEZZA_CM * RISOLUZIONE_OUTPUT_PX_CM))),
        Image.NEAREST).save(OUT_TONE_MAP)
    print("Toni: %d (%s)" % (len(TUTTI_I_TONI), ", ".join(t["nome"] for t in TUTTI_I_TONI)))

    prof, ruote = mappa_profondita(indici, lum, maschera, rosso)
    livelli, tagli = quantizza_livelli(prof, maschera, indici, rosso, ruote)
    print("Ruote rilevate: %d   soglie di quantizzazione: %s"
          % (len(ruote), ", ".join("%.3f" % t for t in tagli)))

    area_px = 1.0 / (RISOLUZIONE_LAVORO_PX_CM ** 2)
    aree_livelli = [float((livelli == i).sum()) * area_px for i in range(N_LIVELLI)]

    print("Preparo i raster di stampa a %d px/cm..." % RISOLUZIONE_SAGOMA_PX_CM)
    maschera_g = alza_risoluzione(maschera, True)
    livelli_g = alza_risoluzione(livelli, False)
    contorno_g = raster_contorno(maschera_g)

    pag_traccia, pag_totali = genera_pdf_traccia(contorno_g, maschera_g)
    pag_spessori = genera_pdf_spessori(livelli_g, maschera_g)
    print("PDF: %s (%d pag.)   %s (%d pag.)   griglia %d fogli teorici"
          % (OUT_TRACCIA, pag_traccia, OUT_SPESSORI, pag_spessori, pag_totali))

    righe, totale_cm2 = calcola_quantita(indici)
    scrivi_csv(righe)
    scrivi_guida(righe, totale_cm2, aree_livelli, pag_traccia, pag_spessori, ruote)

    riepilogo(righe, totale_cm2, aree_livelli)


def riepilogo(righe, totale_cm2, aree_livelli):
    print("")
    print("=" * 62)
    print("RIEPILOGO - COSA ORDINARE")
    print("=" * 62)
    print("Pannello %.0f x %.0f cm  =  %.0f cm2" % (
        PANNELLO_LARGHEZZA_CM, PANNELLO_ALTEZZA_CM,
        PANNELLO_LARGHEZZA_CM * PANNELLO_ALTEZZA_CM))
    print("Sagoma dell'auto        =  %.0f cm2  (%.1f%% del pannello)" % (
        totale_cm2, 100.0 * totale_cm2 / (PANNELLO_LARGHEZZA_CM * PANNELLO_ALTEZZA_CM)))
    print("")
    print("%-18s %10s %7s %10s %10s %12s" % (
        "TONO", "AREA cm2", "%", "PEZZI", "PESO kg", "ORDINE kg"))
    print("-" * 72)
    for r in righe:
        print("%-18s %10.0f %6.1f%% %10d %10.2f %12.2f" % (
            r["tono"], r["area_cm2"], r["perc"], round(r["pezzi"]), r["peso_kg"], r["kg_ordine"]))
    print("-" * 72)
    print("%-18s %10.0f %6.1f%% %10d %10.2f %12.2f" % (
        "TOTALE", totale_cm2, 100.0,
        round(sum(r["pezzi"] for r in righe)),
        sum(r["peso_kg"] for r in righe),
        sum(r["kg_ordine"] for r in righe)))
    print("")
    print("Ordine calcolato con: area media pezzo %.1f cm2, stratificazione %.1f, "
          "peso medio %.1f g, margine %d%%." % (
              AREA_MEDIA_PEZZO_CM2, FATTORE_STRATIFICAZIONE,
              PESO_MEDIO_PEZZO_G, int(MARGINE_ORDINE * 100)))
    print("")
    print("LIVELLI DI PROFONDITA'")
    tot_liv = max(1e-9, sum(aree_livelli))
    plate_medie = sum(a * LIVELLI_PLATE[i] for i, a in enumerate(aree_livelli)) / tot_liv
    for i, a in enumerate(aree_livelli):
        print("  L%d  %2d plate = %4.1f mm   %7.0f cm2   %5.1f%%" % (
            i, LIVELLI_PLATE[i], LIVELLI_PLATE[i] * SPESSORE_PLATE_MM,
            a, 100.0 * a / tot_liv))
    print("  Spessore medio del rilievo: %.1f plate = %.1f mm" % (
        plate_medie, plate_medie * SPESSORE_PLATE_MM))
    print("  Verifica indipendente della stratificazione: %.1f brick sovrapposti in media"
          % (plate_medie / 3.0))
    print("  (la costante FATTORE_STRATIFICAZIONE che hai impostato vale %.1f)"
          % FATTORE_STRATIFICAZIONE)
    print("")
    print("FILE GENERATI")
    for f in (OUT_TONE_MAP, OUT_MASCHERA_DEBUG, OUT_CSV,
              OUT_TRACCIA, OUT_SPESSORI, OUT_GUIDA):
        stato = "%8.1f kB" % (os.path.getsize(f) / 1024.0) if os.path.exists(f) else "  MANCANTE"
        print("  %-22s %s" % (f, stato))
    print("")
    print("Prima di tagliare: stampa traccia_1a1.pdf al 100% e misura col metro")
    print("la riga di controllo da 10 cm che trovi in fondo a ogni foglio.")


if __name__ == "__main__":
    main()
