"""Interpolationsmodell Overwerder und Kalibrierung am Pegel Over.

Modell:
    O(t) = a_up * Z(t + f*tau) + a_down * P(t - (1-f)*tau) + c

Z = Zollenspieker (stromauf), P = St. Pauli (stromab). Die Tidewelle laeuft
stromauf (St. Pauli zuerst, dann Overwerder, dann Zollenspieker); tau ist die
Laufzeit St. Pauli -> Zollenspieker, f der Streckenanteil
Zollenspieker -> Overwerder an der Gesamtstrecke.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .config import ELBE_KM

GRID = "1min"

# Plausibilitaetsschranken fuer die Kalibrierung. Erwartet wird eine
# Konvexkombination beider Stuetzpegel plus kleiner Offset; alles andere ist
# ein entarteter Fit (siehe is_plausible).
WEIGHT_BOUNDS = (0.0, 1.0)
WEIGHT_SUM_BOUNDS = (0.8, 1.2)
OFFSET_LIMIT_CM = 50.0


@dataclass
class Params:
    km_target: float = ELBE_KM["overwerder"]
    km_up: float = ELBE_KM["zollenspieker"]
    km_down: float = ELBE_KM["st_pauli"]
    tau_minutes: float = 60.0  # Laufzeit St. Pauli -> Zollenspieker
    a_up: float | None = None  # None -> entfernungsgewichtet
    a_down: float | None = None
    offset_cm: float = 0.0

    @property
    def frac(self) -> float:
        """Streckenanteil Zollenspieker -> Overwerder (0..1)."""
        return (self.km_target - self.km_up) / (self.km_down - self.km_up)

    def weights(self) -> tuple[float, float]:
        if self.a_up is not None and self.a_down is not None:
            return self.a_up, self.a_down
        return 1.0 - self.frac, self.frac

    def save(self, path: str) -> None:
        with open(path, "w") as fh:
            json.dump(asdict(self), fh, indent=2)

    @classmethod
    def load(cls, path: str) -> Params:
        with open(path) as fh:
            return cls(**json.load(fh))

    def describe(self) -> str:
        """Kurzbeschreibung der Parameter fuer CLI-Ausgaben."""
        return (
            f"Modell: tau={self.tau_minutes:.0f} min, "
            f"Gewichte={tuple(round(w, 3) for w in self.weights())}, "
            f"Offset={self.offset_cm:+.1f} cm"
        )


def load_params(path: str | None = None) -> Params:
    """Params laden: expliziter Pfad, sonst ./params.json falls vorhanden,
    sonst Entfernungs-Defaults."""
    if path is None and os.path.exists("params.json"):
        path = "params.json"
    return Params.load(path) if path else Params()


def _on_grid(s: pd.Series, shift_minutes: float = 0.0) -> pd.Series:
    """Serie zeitverschieben und auf ein 1-Minuten-Raster interpolieren.

    shift_minutes > 0 verschiebt die Kurve in die Zukunft (Signal kommt am
    Zielort spaeter an als am Quellpegel).
    """
    s = s.sort_index()
    s.index = s.index + pd.Timedelta(minutes=shift_minutes)
    grid = pd.date_range(s.index[0].ceil(GRID), s.index[-1].floor(GRID), freq=GRID)
    union = s.index.union(grid)
    return s.reindex(union).interpolate(method="time").reindex(grid)


def interpolate(up: pd.Series, down: pd.Series, params: Params) -> pd.Series:
    """Vorhersage Overwerder (cm ueber PNP) aus den Pegeln stromauf/stromab."""
    f = params.frac
    # Zollenspieker laeuft dem Zielort um f*tau hinterher -> Kurve um f*tau
    # zurueckziehen; St. Pauli laeuft (1-f)*tau voraus -> vorschieben.
    up_g = _on_grid(up, shift_minutes=-params.tau_minutes * f)
    down_g = _on_grid(down, shift_minutes=+params.tau_minutes * (1.0 - f))
    a_up, a_down = params.weights()
    est = a_up * up_g + a_down * down_g + params.offset_cm
    est = est.dropna()
    est.name = "overwerder"
    return est


def is_plausible(params: Params) -> bool:
    """Liegen die gefitteten Parameter im physikalisch sinnvollen Bereich?

    Der freie Fit ist bei 30 Tagen Normaltide nicht immer identifizierbar: er
    kann auf "nur ein Stuetzpegel plus grosser Konstante" kollabieren
    (a_down ~ 0, Offset ~ -100 cm). In-sample sieht das gut aus, bei Sturmflut
    liegt es um Dezimeter daneben (Beleg: docs/OVER_ZOLLENSPIEKER.md).
    """
    a_up, a_down = params.weights()
    lo, hi = WEIGHT_BOUNDS
    if not (lo <= a_up <= hi and lo <= a_down <= hi):
        return False
    s_lo, s_hi = WEIGHT_SUM_BOUNDS
    if not (s_lo <= a_up + a_down <= s_hi):
        return False
    return abs(params.offset_cm) <= OFFSET_LIMIT_CM


def _design(
    up: pd.Series, down: pd.Series, target_g: pd.Series, base: Params, tau: float
) -> pd.DataFrame | None:
    """Beide Stuetzpegel um ``tau`` verschoben und mit dem Ziel gemeinsam auf
    ein Raster gebracht; None, wenn zu wenig Ueberlappung bleibt."""
    f = base.frac
    df = pd.concat(
        {
            "up": _on_grid(up, shift_minutes=-tau * f),
            "down": _on_grid(down, shift_minutes=+tau * (1.0 - f)),
            "obs": target_g,
        },
        axis=1,
        join="inner",
    ).dropna()
    return None if len(df) < 100 else df


def _metrics(pred: np.ndarray, obs: np.ndarray, tau: float) -> dict:
    resid = obs - pred
    return {
        "rmse_cm": float(np.sqrt(np.mean(resid**2))),
        "mae_cm": float(np.mean(np.abs(resid))),
        "bias_cm": float(np.mean(resid)),
        "corr": float(np.corrcoef(pred, obs)[0, 1]),
        "n": int(len(obs)),
        "tau_minutes": float(tau),
    }


def calibrate(
    up: pd.Series,
    down: pd.Series,
    target: pd.Series,
    base: Params | None = None,
    tau_grid: np.ndarray | None = None,
) -> tuple[Params, dict]:
    """Fit (tau, a_up, a_down, c) per Gittersuche + linearer Regression.

    target: Beobachtungen am Pegel Over (cm ueber PNP).

    Es gewinnt der beste Fit, der :func:`is_plausible` erfuellt — ein
    niedrigeres RMSE rettet entartete Parameter nicht. Findet die Gittersuche
    gar keinen plausiblen Fit, wird auf einen **eingeschraenkten** Fit
    zurueckgefallen (Gewichte fest auf den Entfernungsanteilen, nur tau und
    Offset frei); ``metrics["restricted"]`` sagt, welcher Weg genommen wurde.

    Rueckgabe: (Params, Metriken des besten Fits).
    """
    base = base or Params()
    if tau_grid is None:
        tau_grid = np.arange(0.0, 181.0, 5.0)
    target_g = _on_grid(target)
    best: tuple[float, Params, dict] | None = None
    rejected = 0
    for tau in tau_grid:
        df = _design(up, down, target_g, base, float(tau))
        if df is None:
            continue
        A = np.column_stack([df["up"], df["down"], np.ones(len(df))])
        obs = df["obs"].to_numpy()
        coef, *_ = np.linalg.lstsq(A, obs, rcond=None)
        fitted = Params(
            **{
                **asdict(base),
                "tau_minutes": float(tau),
                "a_up": float(coef[0]),
                "a_down": float(coef[1]),
                "offset_cm": float(coef[2]),
            }
        )
        if not is_plausible(fitted):
            rejected += 1
            continue
        metrics = _metrics(A @ coef, obs, float(tau))
        if best is None or metrics["rmse_cm"] < best[0]:
            best = (metrics["rmse_cm"], fitted, metrics)
    if best is not None:
        best[2].update(restricted=False, rejected=rejected)
        return best[1], best[2]
    fallback = _calibrate_restricted(up, down, target_g, base, tau_grid)
    if fallback is None:
        raise RuntimeError("Kalibrierung fehlgeschlagen: zu wenig ueberlappende Daten.")
    params, metrics = fallback
    metrics.update(restricted=True, rejected=rejected)
    return params, metrics


def _calibrate_restricted(
    up: pd.Series,
    down: pd.Series,
    target_g: pd.Series,
    base: Params,
    tau_grid: np.ndarray,
) -> tuple[Params, dict] | None:
    """Eingeschraenkter Fit: Gewichte fest, nur tau und Offset frei.

    Kann nicht entarten, weil die Gewichte nicht aus den Daten kommen: sie
    bleiben auf den Entfernungsanteilen (``Params.weights`` ohne a_up/a_down).
    """
    a_up, a_down = Params(**{**asdict(base), "a_up": None, "a_down": None}).weights()
    best: tuple[float, Params, dict] | None = None
    for tau in tau_grid:
        df = _design(up, down, target_g, base, float(tau))
        if df is None:
            continue
        obs = df["obs"].to_numpy()
        mix = a_up * df["up"].to_numpy() + a_down * df["down"].to_numpy()
        offset = float(np.mean(obs - mix))
        metrics = _metrics(mix + offset, obs, float(tau))
        if best is None or metrics["rmse_cm"] < best[0]:
            params = Params(
                **{
                    **asdict(base),
                    "tau_minutes": float(tau),
                    "a_up": a_up,
                    "a_down": a_down,
                    "offset_cm": offset,
                }
            )
            best = (metrics["rmse_cm"], params, metrics)
    return None if best is None else (best[1], best[2])


def recent_bias_cm(
    prediction: pd.Series, observation: pd.Series, hours: float = 6.0
) -> float:
    """Mittleres Residuum (Modell - Beobachtung) der letzten Stunden."""
    df = pd.concat(
        {"pred": _on_grid(prediction), "obs": _on_grid(observation)},
        axis=1,
        join="inner",
    ).dropna()
    if df.empty:
        return 0.0
    cutoff = df.index.max() - pd.Timedelta(hours=hours)
    df = df[df.index >= cutoff]
    return float((df["pred"] - df["obs"]).mean())
