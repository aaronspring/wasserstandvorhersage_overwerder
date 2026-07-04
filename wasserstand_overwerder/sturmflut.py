"""Sturmflut-Analyse am Pegel Over: Tidehochwasser erkennen und klassifizieren.

Aus der minuetlichen Rohreihe (cm ueber PNP) werden die **Tidehochwasser**
(Thw, lokale Maxima im ~12,4-h-Takt) extrahiert. Aus ihnen ergibt sich das
mittlere Tidehochwasser **MThw**, an dem die BSH-Sturmflut-Klassen haengen.

BSH-Definition fuer die **Nordseekueste** (Bezug: MThw des jeweiligen Pegels):

======================  ===========================
Klasse                  Scheitel ueber MThw
======================  ===========================
(leichte/mittlere)      1,5 .. 2,5 m
Sturmflut
schwere Sturmflut       2,5 .. 3,5 m
sehr schwere Sturmflut  > 3,5 m
======================  ===========================

Unterhalb von MThw + 1,5 m spricht das BSH nicht von einer Sturmflut.

Vorbehalt: die offizielle Klassifikation bezieht sich auf den Pegel **Hamburg
St. Pauli**; dieser ist nicht im Langzeitarchiv. Hier wird das MThw des Pegels
**Over** aus den Daten selbst geschaetzt und als Bezug genutzt (siehe
``docs/STURMFLUT_EDA.md``). Alles netzfrei und rein auf uebergebenen Reihen.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config

# BSH-Nordsee-Schwellen als Aufschlag auf das MThw (cm).
STURMFLUT_CM = 150.0  # ab hier "Sturmflut"
SCHWERE_CM = 250.0  # ab hier "schwere Sturmflut"
SEHR_SCHWERE_CM = 350.0  # ab hier "sehr schwere Sturmflut"

#: Klassennamen von der niedrigsten zur hoechsten Stufe.
KLASSEN = ("Sturmflut", "schwere Sturmflut", "sehr schwere Sturmflut")

# Erkennung der Tidehochwasser.
MIN_ABSTAND_MIN = 600  # Mindestabstand zweier Thw (< 745 min Halbtags-Tide)
MIN_HOEHE_CM = 200.0  # Untergrenze, unterhalb derer kein Thw gesucht wird
GLAETTUNG = "11min"  # rollierender Median gegen Ein-Minuten-Spikes
LUECKE_MIN = 60  # nur Luecken bis hierhin linear interpolieren


def _local_max(values: np.ndarray, distance: int, height: float) -> np.ndarray:
    """Indizes lokaler Maxima mit Mindestabstand (numpy-only, wie find_peaks).

    Greedy nach Hoehe: der hoechste Kandidat wird zuerst gesetzt, danach werden
    alle Kandidaten innerhalb von ``distance`` blockiert. So bleibt je Tidezyklus
    genau ein Scheitel uebrig.
    """
    inner = values[1:-1]
    is_peak = (inner > values[:-2]) & (inner >= values[2:]) & (inner >= height)
    cand = np.flatnonzero(is_peak) + 1
    if cand.size == 0:
        return cand
    order = cand[np.argsort(values[cand], kind="stable")[::-1]]
    taken = np.zeros(values.size, dtype=bool)
    keep: list[int] = []
    for i in order:
        lo = max(0, i - distance)
        hi = min(values.size, i + distance + 1)
        if not taken[lo:hi].any():
            taken[i] = True
            keep.append(int(i))
    keep.sort()
    return np.asarray(keep, dtype=int)


def tidal_highs(
    series: pd.Series,
    distance_min: int = MIN_ABSTAND_MIN,
    min_height_cm: float = MIN_HOEHE_CM,
    smooth: str | None = GLAETTUNG,
    gap_min: int = LUECKE_MIN,
) -> pd.Series:
    """Tidehochwasser (Thw) aus einer minuetlichen Reihe (cm ueber PNP).

    ``series`` hat einen tz-awaren DatetimeIndex. Rueckgabe: Serie der Scheitel
    (Wert = Wasserstand cm ueber PNP, Index = Scheitelzeitpunkt).
    """
    s = series[~series.index.duplicated(keep="last")].sort_index()
    if smooth:
        s = s.rolling(smooth, center=True).median()
    grid = pd.date_range(s.index.min(), s.index.max(), freq="1min", tz=s.index.tz)
    g = s.reindex(grid).interpolate(limit=gap_min)
    arr = g.to_numpy(dtype=float)
    filled = np.where(np.isnan(arr), -9_999.0, arr)
    idx = _local_max(filled, distance_min, min_height_cm)
    peaks = pd.Series(arr[idx], index=grid[idx])
    return peaks[~peaks.isna()]


def mean_high_water(highs: pd.Series) -> float:
    """Mittleres Tidehochwasser (MThw) als Mittel aller Thw (cm ueber PNP)."""
    return float(highs.mean())


def classify(above_mthw_cm: float) -> str | None:
    """BSH-Nordsee-Klasse fuer einen Scheitel ``above_mthw_cm`` cm ueber MThw."""
    if above_mthw_cm < STURMFLUT_CM:
        return None
    if above_mthw_cm < SCHWERE_CM:
        return KLASSEN[0]
    if above_mthw_cm < SEHR_SCHWERE_CM:
        return KLASSEN[1]
    return KLASSEN[2]


def _season(month: np.ndarray, year: np.ndarray) -> np.ndarray:
    """Sturmflut-Saison Jul(y)..Jun(y+1), benannt nach dem Startjahr y."""
    return np.where(month >= 7, year, year - 1)


def surge_tides(
    highs: pd.Series, mthw: float, tz: str = "Europe/Berlin"
) -> pd.DataFrame:
    """Alle Thw ueber MThw + 1,5 m als klassifizierte Sturmflut-Tiden.

    Rueckgabe (Index = Scheitelzeit UTC): ``peak_cm``, ``above_mthw`` (cm ueber
    MThw), ``klasse``, lokale Zeit ``local`` sowie ``year``/``month``/``season``
    in gesetzlicher Zeit.
    """
    above = highs - mthw
    mask = above >= STURMFLUT_CM
    peaks = highs[mask]
    local = peaks.index.tz_convert(tz)
    df = pd.DataFrame(
        {
            "peak_cm": peaks.to_numpy(),
            "above_mthw": above[mask].to_numpy(),
            "klasse": [classify(a) for a in above[mask].to_numpy()],
            "local": local,
            "year": local.year.to_numpy(),
            "month": local.month.to_numpy(),
        },
        index=peaks.index,
    )
    df["season"] = _season(df["month"].to_numpy(), df["year"].to_numpy())
    return df


def annual_mthw(highs: pd.Series, tz: str = "Europe/Berlin") -> pd.Series:
    """Jaehrliches MThw (Mittel aller Thw je Kalenderjahr, cm ueber PNP)."""
    year = highs.index.tz_convert(tz).year
    return highs.groupby(year).mean()


def linear_trend(x: np.ndarray, y: np.ndarray) -> dict[str, float]:
    """Lineare Regression ohne scipy: Steigung, Achsenabschnitt, r, p (t-Test).

    ``p`` ist der zweiseitige p-Wert der Steigung (t-Verteilung, n-2 df) ueber
    die numpy-eigene Fehlerfunktion-Approximation; fuer die grobe Signifikanz-
    Aussage der EDA ausreichend (kein scipy noetig).
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    n = x.size
    sx, sy = x - x.mean(), y - y.mean()
    ssx = float((sx * sx).sum())
    slope = float((sx * sy).sum() / ssx) if ssx else 0.0
    intercept = float(y.mean() - slope * x.mean())
    denom = float(np.sqrt(ssx * (sy * sy).sum()))
    r = float((sx * sy).sum() / denom) if denom else 0.0
    p = float("nan")
    if n > 2:
        if r * r >= 1.0:
            p = 0.0  # perfekter Fit
        else:
            t = r * np.sqrt((n - 2) / (1 - r * r))
            # zweiseitiger p-Wert via Student-t -> Normal-Approx (df>=20 reicht)
            p = float(2.0 * (1.0 - _norm_cdf(abs(t))))
    return {"slope": slope, "intercept": intercept, "r": r, "p": p, "n": float(n)}


def _norm_cdf(z: float) -> float:
    """Standardnormale Verteilungsfunktion ueber die Fehlerfunktion (math.erf)."""
    from math import erf, sqrt

    return 0.5 * (1.0 + erf(z / sqrt(2.0)))


# --- Ausrichtung Over <-> St. Pauli -----------------------------------------
# Die amtlichen BSH-Stufen und die Marke "Wasser auf dem Gelaende" gelten am
# Pegel St. Pauli. Over liegt bei Normaltide ~37 cm ueber St. Pauli (staerkere
# Tideverstaerkung stromauf), bei Sturmflut-Scheiteln naehern sich beide an. Der
# Zusammenhang wird linear aus Datums-Ankern (bekannte Sturmfluten, bei denen der
# St.-Pauli-Scheitel amtlich bekannt und der Over-Scheitel gemessen ist) plus dem
# MThw-Paar geschaetzt und auf die Definitionsschwellen angewandt.

#: Reihenfolge der Ueberflutungsstufen von niedrig nach hoch.
STUFEN = ("Wasser auf Gelände", *KLASSEN)


def stpauli_pnp_cm(nn_m: float) -> float:
    """St.-Pauli-Hoehe von m ueber NN in cm ueber PNP (PNP = NN - 5,00 m)."""
    return (nn_m - config.ST_PAULI_PNP_NN_M) * 100.0


def align_to_stpauli(
    highs: pd.Series,
    anchors: dict[str, float] | None = None,
    tz: str = "Europe/Berlin",
) -> dict[str, float]:
    """Linearer Zusammenhang ``Over_cm_pnp = slope * StPauli_cm_pnp + intercept``.

    Stuetzstellen: das MThw-Paar (St.-Pauli-MThw <-> Over-MThw) plus je ein
    Datums-Anker aus ``anchors`` (Default ``config.ST_PAULI_ANKER_NN_M``): fuer
    jedes Datum wird der hoechste Over-Thw dieses Tages dem amtlichen
    St.-Pauli-Scheitel gegenuebergestellt. Rueckgabe wie :func:`linear_trend`.
    """
    anchors = anchors if anchors is not None else config.ST_PAULI_ANKER_NN_M
    xs = [stpauli_pnp_cm(config.ST_PAULI_MThw_NN_M)]
    ys = [mean_high_water(highs)]
    local = highs.index.tz_convert(tz)
    for date, nn_m in anchors.items():
        day = pd.Timestamp(date, tz=tz)
        same_day = highs[(local >= day) & (local < day + pd.Timedelta("1D"))]
        if same_day.empty:
            continue
        xs.append(stpauli_pnp_cm(nn_m))
        ys.append(float(same_day.max()))
    return linear_trend(np.asarray(xs), np.asarray(ys))


def over_thresholds(fit: dict[str, float]) -> dict[str, float]:
    """St.-Pauli-Definitionsschwellen in cm ueber PNP am Pegel Over uebersetzen.

    Liefert je Stufe (``Wasser auf Gelände`` + BSH-Klassen) die untere
    Over-Schwelle in cm ueber PNP, gemaess der Ausrichtung ``fit``.
    """
    slope, intercept = fit["slope"], fit["intercept"]

    def to_over(nn_m: float) -> float:
        return slope * stpauli_pnp_cm(nn_m) + intercept

    thresholds = {"Wasser auf Gelände": to_over(config.WASSER_AUF_GELAENDE_NN_M)}
    for klasse, delta in config.BSH_STUFEN_UEBER_MThw_M.items():
        thresholds[klasse] = to_over(config.ST_PAULI_MThw_NN_M + delta)
    return thresholds


def classify_level(value_cm: float, thresholds: dict[str, float]) -> str | None:
    """Hoechste Stufe aus ``thresholds``, deren Schwelle ``value_cm`` erreicht."""
    hit = None
    for stufe in STUFEN:
        if stufe in thresholds and value_cm >= thresholds[stufe]:
            hit = stufe
    return hit


def flood_tides(
    highs: pd.Series, thresholds: dict[str, float], tz: str = "Europe/Berlin"
) -> pd.DataFrame:
    """Alle Thw ab "Wasser auf dem Gelaende" mit St.-Pauli-Stufe (aligned).

    Rueckgabe wie :func:`surge_tides`, aber ``stufe`` traegt die
    St.-Pauli-ausgerichtete Klasse (inkl. ``"Wasser auf Gelände"``).
    """
    floor = thresholds["Wasser auf Gelände"]
    peaks = highs[highs >= floor]
    local = peaks.index.tz_convert(tz)
    df = pd.DataFrame(
        {
            "peak_cm": peaks.to_numpy(),
            "stufe": [classify_level(v, thresholds) for v in peaks.to_numpy()],
            "local": local,
            "year": local.year.to_numpy(),
            "month": local.month.to_numpy(),
        },
        index=peaks.index,
    )
    df["season"] = _season(df["month"].to_numpy(), df["year"].to_numpy())
    return df


def cluster_events(times, gap: str = "36h") -> int:
    """Zahl eigenstaendiger Ereignisse: Scheitel < ``gap`` auseinander = ein Sturm."""
    ordered = sorted(pd.DatetimeIndex(times))
    if not ordered:
        return 0
    limit = pd.Timedelta(gap)
    count = 1
    last = ordered[0]
    for t in ordered[1:]:
        if t - last > limit:
            count += 1
        last = t
    return count
