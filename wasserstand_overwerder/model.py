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
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .config import ELBE_KM

GRID = "1min"


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


def calibrate(
    up: pd.Series,
    down: pd.Series,
    target: pd.Series,
    base: Params | None = None,
    tau_grid: np.ndarray | None = None,
) -> tuple[Params, dict]:
    """Fit (tau, a_up, a_down, c) per Gittersuche + linearer Regression.

    target: Beobachtungen am Pegel Over (cm ueber PNP).
    Rueckgabe: (Params, Metriken des besten Fits).
    """
    base = base or Params()
    if tau_grid is None:
        tau_grid = np.arange(0.0, 181.0, 5.0)
    target_g = _on_grid(target)
    best: tuple[float, Params, dict] | None = None
    for tau in tau_grid:
        p = Params(
            **{
                **asdict(base),
                "tau_minutes": float(tau),
                "a_up": None,
                "a_down": None,
                "offset_cm": 0.0,
            }
        )
        f = p.frac
        up_g = _on_grid(up, shift_minutes=-tau * f)
        down_g = _on_grid(down, shift_minutes=+tau * (1.0 - f))
        df = pd.concat(
            {"up": up_g, "down": down_g, "obs": target_g}, axis=1, join="inner"
        ).dropna()
        if len(df) < 100:
            continue
        A = np.column_stack([df["up"], df["down"], np.ones(len(df))])
        coef, *_ = np.linalg.lstsq(A, df["obs"].to_numpy(), rcond=None)
        resid = df["obs"].to_numpy() - A @ coef
        rmse = float(np.sqrt(np.mean(resid**2)))
        if best is None or rmse < best[0]:
            fitted = Params(
                **{
                    **asdict(p),
                    "a_up": float(coef[0]),
                    "a_down": float(coef[1]),
                    "offset_cm": float(coef[2]),
                }
            )
            metrics = {
                "rmse_cm": rmse,
                "mae_cm": float(np.mean(np.abs(resid))),
                "bias_cm": float(np.mean(resid)),
                "corr": float(np.corrcoef(A @ coef, df["obs"])[0, 1]),
                "n": int(len(df)),
                "tau_minutes": float(tau),
            }
            best = (rmse, fitted, metrics)
    if best is None:
        raise RuntimeError("Kalibrierung fehlgeschlagen: zu wenig ueberlappende Daten.")
    return best[1], best[2]


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
