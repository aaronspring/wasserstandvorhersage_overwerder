"""Grafiken zu den Ueberflutungs-Zeitpunkten (``inundation.py``).

* ``summary``: Beginn-Karte, Wasserstand, Hoehe -> Zeitpunkt
* ``terrain_map``: Gelaende mit Schummerung, Gelaende-Marke, Profillinie
* ``profile``: Querprofil A -> B, Wasserspiegel stuendlich (Auf- und Ablauf)
* ``snapshots``: Wassertiefe stuendlich um den Scheitel
* ``animation``: GIF der Sturmtide in 10-min-Schritten
* ``buildings_map``: Gebaeude mit Nummer, eingefaerbt nach Ueberflutungsbeginn

``bldg`` ist optional die Tabelle aus ``buildings.flood_table`` (mit ``nr``,
``footprint``); dann werden die Grundrisse ueberall eingezeichnet.

matplotlib wird lazy importiert (Agg-Backend, ohne Display).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .inundation import Terrain, depth_at

CREDIT = "Gelaende: DGM1 (c) LGV Hamburg, dl-de/by-2-0"
WATER = "#a9cfe8"
TZ = "Europe/Berlin"


def _plt():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def crop(terrain: Terrain, view, *arrays: np.ndarray, step: int = 1):
    """Schneidet ``terrain.z`` und weitere gleich grosse Raster auf ``view``
    (xmin, ymin, xmax, ymax) zu; ``step`` > 1 duennt fuer schnelle Grafiken aus.
    Rueckgabe: (extent, z, *arrays)."""
    t = terrain.transform
    xmin, ymin, xmax, ymax = view
    c0, c1 = int((xmin - t.c) / t.a), int((xmax - t.c) / t.a)
    r0, r1 = int((ymax - t.f) / t.e), int((ymin - t.f) / t.e)
    sl = (slice(r0, r1, step), slice(c0, c1, step))
    extent = (t.c + c0 * t.a, t.c + c1 * t.a, t.f + r1 * t.e, t.f + r0 * t.e)
    return (extent, terrain.z[sl], *(a[sl] for a in arrays))


def _base(ax, z: np.ndarray, river: np.ndarray, extent) -> None:
    """Schummerung + Strom als Hintergrund."""
    from matplotlib import colors

    hs = colors.LightSource(315, 35).hillshade(np.nan_to_num(z, nan=2.0), vert_exag=4)
    ax.imshow(hs, cmap="gray", extent=extent)
    ax.imshow(
        np.where(river, 1.0, np.nan),
        cmap=colors.ListedColormap([WATER]),
        extent=extent,
    )
    ax.set_xticks([])
    ax.set_yticks([])


def _outlines(ax, bldg, color="k", lw=0.4, facecolors="none", **kw):
    """Gebaeude-Grundrisse als PolyCollection."""
    from matplotlib.collections import PolyCollection

    if bldg is None or len(bldg) == 0:
        return None
    pc = PolyCollection(
        list(bldg["footprint"]),
        edgecolors=color,
        facecolors=facecolors,
        linewidths=lw,
        **kw,
    )
    ax.add_collection(pc)
    return pc


def _local(ts: pd.Timestamp) -> str:
    return f"{ts.tz_convert(TZ):%d.%m. %H:%M}"


def summary(terrain, timing, level, tide, table, peak, area_bbox, out: Path) -> Path:
    """Beginn-Karte, Wasserstand um den Scheitel, Hoehe -> Zeitpunkt/Dauer."""
    plt = _plt()
    rel_min = (
        timing["onset"] - peak.tz_localize(None).to_datetime64()
    ) / np.timedelta64(1, "m")
    fig, axes = plt.subplots(1, 3, figsize=(18, 6), width_ratios=[1.2, 1, 1])
    ax = axes[0]
    ax.imshow(terrain.z, cmap="gray", vmin=0, vmax=9, extent=terrain.extent)
    im = ax.imshow(
        rel_min, cmap="viridis", vmin=np.nanmin(rel_min), vmax=0, extent=terrain.extent
    )
    fig.colorbar(im, ax=ax, shrink=0.8, label="Beginn relativ zum Scheitel [min]")
    xmin, ymin, xmax, ymax = area_bbox
    ax.plot([xmin, xmax, xmax, xmin, xmin], [ymin, ymin, ymax, ymax, ymin], "r--", lw=1)
    ax.set_title("Ueberflutungsbeginn in der Sturmtide (DGM1 2022)")
    ax.ticklabel_format(useOffset=False, style="plain")
    ax.tick_params(labelsize=7)

    ax = axes[1]
    win = pd.Timedelta(hours=18)
    loc = level[peak - win : peak + win].tz_convert(TZ)
    ax.plot(loc.index, loc.values, color="#1f77b4")
    ax.axvspan(tide.index[0], tide.index[-1], color="C1", alpha=0.1, label="Sturmtide")
    ax.legend(loc="upper right", fontsize=8)
    for zc in np.arange(2.5, 4.51, 0.5):
        ax.axhline(zc, color="0.6", lw=0.6, ls=":")
        ax.text(loc.index[0], zc, f" {zc:.1f} m", fontsize=7, va="bottom", color="0.4")
    ax.set_ylabel("Wasserstand Over [m NHN]")
    ax.set_title("Wasserstand und Gelaendehoehen")
    fig.autofmt_xdate()

    ax = axes[2]
    tab = table[table["cells"] >= 50]
    rel = (tab["onset_median"] - peak).dt.total_seconds() / 60.0
    ax.plot(tab.index, rel, "o-", label="Beginn - Scheitel [min]")
    ax.plot(tab.index, tab["hours_wet_median"] * 60.0, "s-", label="nasse Dauer [min]")
    ax.axhline(0, color="k", lw=0.5)
    ax.set_xlabel("Gelaendehoehe [m NHN] (0,1-m-Klassen, Auswerteflaeche)")
    ax.set_ylabel("Minuten")
    ax2 = ax.twinx()
    ax2.bar(tab.index, tab["wet_share"], width=0.08, alpha=0.2, color="C2")
    ax2.set_ylabel("Anteil nass", color="C2")
    ax2.set_ylim(0, 1.05)
    ax.legend(loc="upper left", fontsize=8)
    ax.set_xlim(1.5, max(5.0, float(tab.index.max()) + 0.2))
    ax.set_title("Wie die Gelaendehoehe den Zeitpunkt steuert")
    fig.text(0.99, 0.01, CREDIT, ha="right", fontsize=7)
    fig.tight_layout()
    p = out / "inundation.png"
    fig.savefig(p, dpi=110)
    plt.close(fig)
    return p


def terrain_map(
    terrain, river, spill, area_bbox, gelaende_m, out: Path, bldg=None
) -> Path:
    """Gelaende mit Schummerung, Marke "Wasser auf dem Gelaende" (rot),
    Auswerteflaeche (gestrichelt) und Profillinie A -> B."""
    plt = _plt()
    z = terrain.z
    fig, ax = plt.subplots(figsize=(10, 9.5))
    _base(ax, z, river, terrain.extent)
    im = ax.imshow(z, cmap="terrain", vmin=-1, vmax=9, alpha=0.6, extent=terrain.extent)
    vorland = np.where(spill < config.VORLAND_MAX_SPILL_M, z, np.nan)
    ax.contour(
        np.flipud(vorland),
        levels=[gelaende_m],
        colors="crimson",
        linewidths=0.8,
        extent=terrain.extent,
        origin="lower",
    )
    _outlines(ax, bldg, color="0.15", lw=0.3, facecolors="0.35")
    xmin, ymin, xmax, ymax = area_bbox
    ax.plot(
        [xmin, xmax, xmax, xmin, xmin], [ymin, ymin, ymax, ymax, ymin], "k--", lw=0.8
    )
    (ax_, ay), (bx, by) = config.INUNDATION_PROFILE
    ax.plot([ax_, bx], [ay, by], "w-", lw=2.5)
    ax.plot([ax_, bx], [ay, by], "k-", lw=1)
    for txt, x, y, dx in (("A", ax_, ay, -14), ("B", bx, by, 5)):
        ax.annotate(
            txt, (x, y), xytext=(dx, -4), textcoords="offset points", weight="bold"
        )
    for txt, x, y in config.INUNDATION_MAP_LABELS:
        ax.annotate(
            txt,
            (x, y),
            fontsize=11,
            weight="bold",
            ha="center",
            bbox={"fc": "w", "alpha": 0.6, "lw": 0},
        )
    fig.colorbar(im, ax=ax, shrink=0.6, label="Gelaende [m NHN]")
    ax.set_title(
        "DGM1 2022 Overwerder - rot: Marke Wasser auf dem Gelaende "
        f"({gelaende_m:.2f} m NHN)"
    )
    fig.text(0.99, 0.01, CREDIT, ha="right", fontsize=7)
    fig.tight_layout()
    p = out / "gelaende.png"
    fig.savefig(p, dpi=110)
    plt.close(fig)
    return p


def _profile_cells(terrain: Terrain, *arrays: np.ndarray, n: int | None = None):
    """Werte entlang ``config.INUNDATION_PROFILE`` (1-m-Abtastung)."""
    (x0, y0), (x1, y1) = config.INUNDATION_PROFILE
    n = n or int(np.hypot(x1 - x0, y1 - y0)) + 1
    t = terrain.transform
    rows = ((np.linspace(y0, y1, n) - t.f) / t.e).astype(int)
    cols = ((np.linspace(x0, x1, n) - t.c) / t.a).astype(int)
    return np.arange(n), terrain.z[rows, cols], *(a[rows, cols] for a in arrays)


def _profile_buildings(bldg, dist):
    """Gebaeude, die die Profillinie schneiden: (nr, Distanz von, bis, Zeile)."""
    from matplotlib.path import Path as MplPath

    if bldg is None:
        return []
    (x0, y0), (x1, y1) = config.INUNDATION_PROFILE
    f = dist / dist[-1]
    pts = np.c_[x0 + f * (x1 - x0), y0 + f * (y1 - y0)]
    hits = []
    for _, b in bldg.iterrows():
        inside = MplPath(b["footprint"]).contains_points(pts)
        if inside.any():
            hits.append((dist[inside].min(), dist[inside].max(), b))
    return hits


def profile(
    terrain,
    river,
    spill,
    level,
    tide,
    peak,
    gelaende_m,
    drain_m_per_h,
    out: Path,
    bldg=None,
) -> Path:
    """Querprofil A -> B: oben Auflauf (stuendlich bis zum Scheitel), unten Ablauf
    (Scheitel und stuendlich danach) mit Stauwasser hinter dem Sommerdeich."""
    plt = _plt()
    dist, zp, sp, rv = _profile_cells(terrain, spill, river)
    other = np.isnan(zp) & ~rv
    ground = np.where(np.isnan(zp), np.where(rv, -2.0, 1.0), zp)
    land = np.isfinite(zp)
    houses = _profile_buildings(bldg, dist)
    fig, axes = plt.subplots(2, 1, figsize=(13, 9), sharex=True)
    rising = [peak + pd.Timedelta(hours=h) for h in (0, -1, -2, -3, -4)]
    falling = [peak + pd.Timedelta(hours=h) for h in (0, 1, 2, 3, 4)]
    falling = [t for t in falling if t <= tide.index[-1]]
    colors_ = ["#c6dbef", "#9ecae1", "#6baed6", "#3182bd", "#08519c"]
    for ax, times, title in (
        (axes[0], rising, "Auflauf: Wasserspiegel stuendlich bis zum Scheitel"),
        (
            axes[1],
            falling,
            "Ablauf: Priele laufen leer, abflusslose Mulden behalten Stauwasser",
        ),
    ):
        for when, col in zip(times, colors_, strict=False):
            depth = depth_at(sp, zp, tide, when, drain_m_per_h)
            h = float(tide.asof(when))
            surface = np.where(rv, h, np.where(land, zp + depth, np.nan))
            rel = round((when - peak) / pd.Timedelta(hours=1))
            tag = "Scheitel" if rel == 0 else f"{rel:+d} h"
            ax.fill_between(
                dist,
                ground,
                surface,
                where=np.isfinite(surface) & (surface > ground),
                color=col,
                lw=0,
                interpolate=True,
                label=f"{_local(when)} ({tag}): Over {h:.2f} m NHN",
            )
        ax.fill_between(
            dist, -2, ground, where=land, color="#8c6d46", lw=0, label="Gelaende"
        )
        ax.fill_between(
            dist, -2, 1.0, where=other, color="0.75", lw=0, label="Binnengewaesser"
        )
        ax.axhline(gelaende_m, color="crimson", ls="--", lw=0.8)
        ax.text(
            dist[-1] + 5,
            gelaende_m,
            " Wasser auf\n dem Gelaende",
            color="crimson",
            fontsize=8,
            va="center",
        )
        for d0, d1, b in houses:
            ax.add_patch(
                plt.Rectangle(
                    (d0, b["base_m"]),
                    max(d1 - d0, 1.0),
                    b["height_m"],
                    fc="0.85",
                    ec="0.3",
                    lw=0.6,
                    zorder=3,
                )
            )
            ax.text(
                (d0 + d1) / 2,
                b["base_m"] + b["height_m"] + 0.1,
                f"#{b['nr']}",
                ha="center",
                va="bottom",
                fontsize=7,
                zorder=4,
            )
        for txt, x in config.INUNDATION_PROFILE_LABELS:
            ax.text(
                x,
                11.2 if houses else 9.0,
                txt,
                ha="center",
                va="top",
                fontsize=9,
                weight="bold",
            )
        ax.set_xlim(0, dist[-1])
        ax.set_ylim(-2, 11.5 if houses else 9.4)
        ax.set_ylabel("m NHN")
        ax.set_title(title, fontsize=10)
        ax.legend(fontsize=8, loc="center right", bbox_to_anchor=(1.0, 0.6))
    axes[1].set_xlabel(
        "Distanz A -> B [m] (Elbe -> Overhaken -> Hauptdeich -> Binnenland)"
    )
    fig.suptitle(f"Querprofil durch Overhaken - Sturmflut {_local(peak)[:6]}{peak:%Y}")
    fig.text(0.99, 0.005, CREDIT, ha="right", fontsize=7)
    fig.tight_layout()
    p = out / "profil.png"
    fig.savefig(p, dpi=110)
    plt.close(fig)
    return p


def snapshots(
    terrain, river, spill, tide, peak, drain_m_per_h, out: Path, bldg=None
) -> Path:
    """Wassertiefe stuendlich von -3 h bis +4 h um den Scheitel (2 Reihen)."""
    plt = _plt()
    extent, z, rv, sp = crop(terrain, config.INUNDATION_VIEW, river, spill)
    times = [peak + pd.Timedelta(hours=h) for h in range(-3, 5)]
    times = [t for t in times if tide.index[0] <= t <= tide.index[-1]]
    ncol = 4
    nrow = int(np.ceil(len(times) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(20, 4.8 * nrow), squeeze=False)
    for ax in axes.ravel()[len(times) :]:
        ax.axis("off")
    for ax, when in zip(axes.ravel(), times, strict=False):
        depth = depth_at(sp, z, tide, when, drain_m_per_h)
        _base(ax, z, rv, extent)
        im = ax.imshow(depth, cmap="Blues", vmin=0, vmax=2.5, extent=extent)
        _outlines(ax, bldg, color="0.1", lw=0.25)
        ax.set_xlim(extent[:2])
        ax.set_ylim(extent[2:])
        rel = round((when - peak) / pd.Timedelta(hours=1))
        tag = "Scheitel" if rel == 0 else f"{rel:+d} h"
        ax.set_title(
            f"{_local(when)} ({tag}) - Over {float(tide.asof(when)):.2f} m NHN"
        )
    fig.colorbar(im, ax=axes, shrink=0.7, label="Wassertiefe [m]")
    fig.suptitle("Ueberflutungsverlauf Overwerder Vorland (oben Auflauf, unten Ablauf)")
    p = out / "verlauf.png"
    fig.savefig(p, dpi=90, bbox_inches="tight")
    plt.close(fig)
    return p


def animation(
    terrain, river, spill, tide, gelaende_m, drain_m_per_h, out: Path, bldg=None
) -> Path:
    """GIF der Sturmtide (10-min-Schritte) mit Wasserstandskurve darunter."""
    plt = _plt()
    import matplotlib.dates as mdates
    from matplotlib import animation as anim

    extent, z, rv, sp = crop(terrain, config.INUNDATION_VIEW, river, spill, step=2)
    frames = tide.resample("10min").mean().dropna()
    loc = frames.tz_convert(TZ)
    vorland = sp < config.VORLAND_MAX_SPILL_M

    fig = plt.figure(figsize=(9, 7.5))
    gs = fig.add_gridspec(2, 1, height_ratios=[4, 1])
    ax = fig.add_subplot(gs[0])
    _base(ax, z, rv, extent)
    im = ax.imshow(
        np.full_like(z, np.nan), cmap="Blues", vmin=0, vmax=2.5, extent=extent
    )
    _outlines(ax, bldg, color="0.1", lw=0.25)
    ax.set_xlim(extent[:2])
    ax.set_ylim(extent[2:])
    fig.colorbar(im, ax=ax, shrink=0.7, label="Wassertiefe [m]")
    title = ax.set_title("")
    bx = fig.add_subplot(gs[1])
    bx.plot(loc.index, loc.values)
    bx.axhline(gelaende_m, color="crimson", ls="--", lw=0.8)
    (dot,) = bx.plot([], [], "ro")
    bx.set_ylabel("Over [m NHN]")
    bx.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=loc.index.tz))

    def update(i):
        when, h = frames.index[i], frames.iloc[i]
        depth = depth_at(sp, z, tide, when, drain_m_per_h)
        im.set_data(depth)
        dot.set_data([loc.index[i]], [h])
        wet_ha = (np.isfinite(depth) & vorland).sum() * 4 / 1e4  # 2-m-Zellen
        title.set_text(f"{_local(when)}  Over {h:.2f} m NHN - {wet_ha:.0f} ha nass")
        return im, dot, title

    ani = anim.FuncAnimation(fig, update, frames=len(frames), blit=False)
    p = out / "animation.gif"
    ani.save(p, writer=anim.PillowWriter(fps=7), dpi=70)
    plt.close(fig)
    return p


def buildings_map(terrain, river, bldg, peak, out: Path) -> Path:
    """Detailkarte aller Gebaeude im Vorland mit laufender Nummer, eingefaerbt
    nach Ueberflutungsbeginn relativ zum Scheitel (grau = bleibt trocken).
    Gebaeude mit ALKIS-Hausnummer tragen sie zusaetzlich (rot)."""
    plt = _plt()
    from matplotlib import colormaps, colors

    pad = 40.0
    view = (
        bldg["x"].min() - pad,
        bldg["y"].min() - pad,
        bldg["x"].max() + pad,
        bldg["y"].max() + pad,
    )
    extent, z, rv = crop(terrain, view, river)
    w, h = extent[1] - extent[0], extent[3] - extent[2]
    fig, ax = plt.subplots(figsize=(16, 16 * h / w + 1.5))
    _base(ax, z, rv, extent)
    rel = (bldg["onset"] - peak).dt.total_seconds() / 60.0
    norm = colors.Normalize(vmin=float(np.nanmin(rel)), vmax=0.0)
    cmap = colormaps["viridis"]
    face = [
        "0.7" if np.isnan(r) else colors.to_hex(cmap(norm(r))) for r in rel.to_numpy()
    ]
    _outlines(ax, bldg, color="k", lw=0.4, facecolors=face)
    for (_, b), r in zip(bldg.iterrows(), rel, strict=True):
        ax.text(
            b["x"],
            b["y"],
            str(b["nr"]),
            fontsize=4.5,
            ha="center",
            va="center",
            color="w" if np.isfinite(r) and norm(r) < 0.45 else "k",
        )
        if b["number"]:
            ax.text(
                b["x"],
                b["y"] - 6,
                f"Nr. {b['number']}",
                fontsize=4.5,
                ha="center",
                va="top",
                color="crimson",
                weight="bold",
            )
    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    fig.colorbar(
        sm, ax=ax, shrink=0.5, label="Wasser am Gebaeude: Minuten vor Scheitel"
    )
    ax.set_xlim(extent[:2])
    ax.set_ylim(extent[2:])
    ax.set_title(
        f"Gebaeude im Overwerder Vorland ({len(bldg)}, laufende Nr. NW -> SO; "
        f"grau = trocken) - Sturmflut {_local(peak)}"
    )
    fig.text(
        0.99,
        0.005,
        "Gebaeude: LoD2-DE, " + CREDIT,
        ha="right",
        fontsize=7,
    )
    fig.tight_layout()
    p = out / "gebaeude.png"
    fig.savefig(p, dpi=170, bbox_inches="tight")
    plt.close(fig)
    return p
