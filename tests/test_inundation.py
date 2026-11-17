"""Synthetik-Tests fuer die Ueberflutungs-Zeitpunkte (netzfrei, ohne DGM1).

Gelaende: Strom (NaN) links, Vorland 2,5 m, Sommerdeich 3,0 m, Senke 2,0 m
dahinter, Hauptdeich 8 m. Prueft Ueberlaufhoehe, Beginn/Dauer und die
Erkennung der DGM1-Wasser-Platzhalter.
"""

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from wasserstand_overwerder import inundation


def terrain() -> np.ndarray:
    z = np.full((20, 50), 2.5)
    z[:, :10] = np.nan  # Strom
    z[:, 20] = 3.0  # Sommerdeich
    z[:, 21:30] = 2.0  # Senke hinter dem Sommerdeich
    z[:, 30] = 8.0  # Hauptdeich
    z[:, 31:] = 1.0  # Hinterland, tiefer als alles davor
    return z


def test_spill_elevation_respects_dikes():
    z = terrain()
    spill = inundation.spill_elevation(z, inundation.river_mask(z))
    np.testing.assert_allclose(spill[:, 10:20], 2.5)  # Vorland: eigene Hoehe
    np.testing.assert_allclose(spill[:, 21:30], 3.0)  # Senke: erst ab Deichkrone
    np.testing.assert_allclose(spill[:, 31:], 8.0)  # Hinterland: Hauptdeich
    assert np.isnan(spill[:, :10]).all()


def test_flood_timing_onset_duration_depth():
    z = terrain()
    spill = inundation.spill_elevation(z, inundation.river_mask(z))
    idx = pd.date_range("2026-01-01", periods=7, freq="1h", tz="UTC")
    level = pd.Series([2.0, 2.4, 2.6, 3.2, 2.9, 2.6, 2.0], index=idx)
    out = inundation.flood_timing(spill, z, level)

    # Vorland (2,5 m) nass ab 02:00 bis 05:00, 4 Schritte a 1 h
    assert out["onset"][0, 15] == np.datetime64("2026-01-01T02:00")
    assert out["end"][0, 15] == np.datetime64("2026-01-01T05:00")
    assert out["hours_wet"][0, 15] == 4.0
    np.testing.assert_allclose(out["max_depth"][0, 15], 0.7)
    assert out["residual_depth"][0, 15] == 0.0
    # Senke (2,0 m) erst mit Deichueberstroemung um 03:00, Tiefe 1,2 m; danach
    # bleibt sie bis zur Deichkrone (1,0 m) gefuellt bis zum Reihenende 07:00
    assert out["onset"][0, 25] == np.datetime64("2026-01-01T03:00")
    assert out["inflow_end"][0, 25] == np.datetime64("2026-01-01T04:00")
    assert out["end"][0, 25] == np.datetime64("2026-01-01T07:00")
    assert out["hours_wet"][0, 25] == 4.0
    np.testing.assert_allclose(out["max_depth"][0, 25], 1.2)
    np.testing.assert_allclose(out["residual_depth"][0, 25], 1.0)
    # Hinterland bleibt trocken, obwohl es tiefer liegt
    assert np.isnat(out["onset"][0, 40])
    assert np.isnan(out["hours_wet"][0, 40])


def test_pond_drains_with_rate():
    z = terrain()
    spill = inundation.spill_elevation(z, inundation.river_mask(z))
    idx = pd.date_range("2026-01-01", periods=7, freq="1h", tz="UTC")
    level = pd.Series([2.0, 2.4, 2.6, 3.2, 2.9, 2.6, 2.0], index=idx)
    out = inundation.flood_timing(spill, z, level, drain_m_per_h=0.5)
    # 1,0 m Stauwasser / 0,5 m/h = 2 h nach Kontaktende 04:00
    assert out["end"][0, 25] == np.datetime64("2026-01-01T06:00")
    assert out["hours_wet"][0, 25] == 3.0
    assert out["residual_depth"][0, 25] == 0.0

    at = pd.Timestamp("2026-01-01T05:00", tz="UTC")
    d0 = inundation.depth_at(spill, z, level, at)
    np.testing.assert_allclose(d0[0, 15], 0.1)  # Vorland folgt dem Strom
    np.testing.assert_allclose(d0[0, 25], 1.0)  # Senke bis zur Deichkrone voll
    assert np.isnan(d0[0, 40])
    d1 = inundation.depth_at(spill, z, level, at, drain_m_per_h=0.5)
    # 1 h Ablauf seit 04:00 -> 2,5 m, aber nicht unter Strom (2,6 m, Siel zu)
    np.testing.assert_allclose(d1[0, 25], 0.6)
    late = pd.Timestamp("2026-01-01T06:00", tz="UTC")
    assert np.isnan(inundation.depth_at(spill, z, level, late)[0, 15])
    assert np.isnan(inundation.depth_at(spill, z, level, late, 0.5)[0, 25])


def test_higher_ground_floods_later():
    z = np.tile(np.linspace(2.0, 4.0, 21), (3, 1))
    z = np.hstack([np.full((3, 2), np.nan), z])
    spill = inundation.spill_elevation(z, inundation.river_mask(z))
    idx = pd.date_range("2026-01-01", periods=61, freq="5min", tz="UTC")
    level = pd.Series(np.linspace(1.5, 4.5, 61), index=idx)  # 0,6 m/h Anstieg
    onset = inundation.flood_timing(spill, z, level)["onset"][1, 2:]
    minutes = (onset - onset[0]) / np.timedelta64(1, "m")
    # 0,1 m hoeher -> 10 min spaeter bei 0,6 m/h
    np.testing.assert_allclose(np.diff(minutes), 10.0)


def test_water_fill_mask_and_tile_names():
    rng = np.random.default_rng(0)
    z = 2.0 + rng.random((200, 200)).astype("float32") * 0.01 + 0.001
    z[:, :100] = 2.0  # Platzhalter-Wasserflaeche
    z[5, 150] = 3.0  # einzelner ganzzahliger Gelaendewert bleibt
    m = inundation.water_fill_mask(z, min_cells=1000)
    assert m[:, :100].all() and not m[:, 100:].any()

    names = inundation.tile_names((572400.0, 5919900.0, 574800.0, 5922200.0))
    assert "dgm1_32_572_5919_1_hh_2022.tif" in names
    assert "dgm1_32_574_5922_1_hh_2022.tif" in names
    assert len(names) == 3 * 4


def test_cm_pnp_to_m_nhn():
    s = pd.Series([834.0])
    np.testing.assert_allclose(inundation.cm_pnp_to_m_nhn(s, -5.098), 3.242)


def test_travel_distance_goes_over_dike_crest():
    z = terrain()
    river = inundation.river_mask(z)
    spill = inundation.spill_elevation(z, river)
    dist = inundation.travel_distance(spill, river)
    assert np.isnan(dist[:, :10]).all()  # Strom selbst
    # Mittelpunkt zu Mittelpunkt; die Uferkante zaehlt halb (Stromzelle ~0)
    np.testing.assert_allclose(dist[10, 10], 0.5, atol=0.01)
    np.testing.assert_allclose(dist[10, 15], 5.5, atol=0.01)
    # Senke hinter dem Sommerdeich: Weg ueber die Krone (Spalte 20)
    np.testing.assert_allclose(dist[10, 25], 15.5, atol=0.01)
    assert (np.diff(dist[10, 10:30]) > 0).all()
