"""Flussbett (DGM-W) in der Gelaende-Pipeline: netzfrei, synthetisch."""

import numpy as np
import pytest

pytest.importorskip("skimage")

from wasserstand_overwerder.inundation import (  # noqa: E402
    channel_mask,
    fill_riverbed,
    spill_elevation,
)


def _profile():
    """Querprofil West->Ost: Rinne -4 m, Strand -1..+1 m, Vorland 2 m,
    Sommerdeich 4 m, Senke 1,5 m. DGM1 hat den Strom (Spalten 0-5) als NaN."""
    bed = np.array([-4.0, -4.0, -3.0, -1.0, 0.0, 1.0, 2.0, 2.0, 4.0, 1.5, 1.5, 4.0])
    z_row = bed.copy()
    z_row[:6] = np.nan
    z = np.tile(z_row, (5, 1))
    river = np.isnan(z)
    return z, river, np.tile(bed, (5, 1))


def test_fill_riverbed_only_in_river():
    z, river, bed = _profile()
    z[0, 9] = np.nan  # See-Fehlwert ausserhalb des Stroms
    filled = fill_riverbed(z, river, bed)
    assert np.array_equal(filled[river], bed[river])
    assert np.isnan(filled[0, 9])
    assert np.array_equal(filled[~river & np.isfinite(z)], z[~river & np.isfinite(z)])


def test_channel_mask_takes_deep_connected_part():
    z, river, bed = _profile()
    filled = fill_riverbed(z, river, bed)
    filled[0, 4] = -3.5  # isoliertes Kolk-Loch im Strand: keine Quelle
    ch = channel_mask(filled, river, -2.5)
    assert ch[:, :3].all()
    assert not ch[:, 3:].any()
    with pytest.raises(ValueError):
        channel_mask(filled, river, -10.0)


def test_spill_with_riverbed_beach_dries_and_land_unchanged():
    z, river, bed = _profile()
    old = spill_elevation(z, river)
    filled = fill_riverbed(z, river, bed)
    new = spill_elevation(filled, channel_mask(filled, river, -2.5))
    # Strand: Ueberlaufhoehe = Sohle (faellt unter dieser Hoehe trocken)
    assert np.allclose(new[:, 3:6], bed[:, 3:6])
    # Rinne ist Quelle (keine Ueberlaufhoehe)
    assert np.isnan(new[:, :3]).all()
    # Vorland und Senke hinter dem Sommerdeich wie bisher
    assert np.allclose(new[:, 6:], old[:, 6:])
    assert np.allclose(new[:, 9:11], 4.0)
