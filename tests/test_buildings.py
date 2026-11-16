"""Tests fuer die LoD2-Gebaeude (netzfrei, Mini-CityGML + Synthetik-Gelaende)."""

import os
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from wasserstand_overwerder import buildings, inundation

GML = """<?xml version="1.0" encoding="UTF-8"?>
<core:CityModel xmlns:core="http://www.opengis.net/citygml/1.0"
 xmlns:bldg="http://www.opengis.net/citygml/building/1.0"
 xmlns:gml="http://www.opengis.net/gml"
 xmlns:xAL="urn:oasis:names:tc:ciq:xsdschema:xAL:2.0">
 <core:cityObjectMember><bldg:Building gml:id="B_EAST">
  <bldg:function>31001_1310</bldg:function>
  <bldg:measuredHeight uom="m">4.0</bldg:measuredHeight>
  <bldg:boundedBy><bldg:GroundSurface><bldg:lod2MultiSurface><gml:MultiSurface>
   <gml:surfaceMember><gml:Polygon><gml:exterior><gml:LinearRing><gml:posList>
    32 2 2.6 38 2 2.6 38 8 2.5 32 8 2.6 32 2 2.6
   </gml:posList></gml:LinearRing></gml:exterior></gml:Polygon></gml:surfaceMember>
  </gml:MultiSurface></bldg:lod2MultiSurface></bldg:GroundSurface></bldg:boundedBy>
 </bldg:Building></core:cityObjectMember>
 <core:cityObjectMember><bldg:Building gml:id="B_WEST">
  <bldg:function>31001_1010</bldg:function>
  <bldg:measuredHeight uom="m">7.5</bldg:measuredHeight>
  <bldg:boundedBy><bldg:GroundSurface><bldg:lod2MultiSurface><gml:MultiSurface>
   <gml:surfaceMember><gml:Polygon><gml:exterior><gml:LinearRing><gml:posList>
    12 2 2.5 18 2 2.5 18 8 2.5 12 8 2.5 12 2 2.5
   </gml:posList></gml:LinearRing></gml:exterior></gml:Polygon></gml:surfaceMember>
  </gml:MultiSurface></bldg:lod2MultiSurface></bldg:GroundSurface></bldg:boundedBy>
  <bldg:address><core:Address><core:xalAddress><xAL:AddressDetails><xAL:Country>
   <xAL:Locality><xAL:Thoroughfare><xAL:ThoroughfareNumber>7a</xAL:ThoroughfareNumber>
   <xAL:ThoroughfareName>Overwerder Bogen</xAL:ThoroughfareName></xAL:Thoroughfare>
   </xAL:Locality></xAL:Country></xAL:AddressDetails></core:xalAddress></core:Address>
  </bldg:address>
 </bldg:Building></core:cityObjectMember>
</core:CityModel>
"""


def lod2(tmp_path):
    p = tmp_path / "LoD2_32_0_0_1_HH.gml"
    p.write_text(GML)
    return buildings.parse_lod2([p])


def test_parse_lod2(tmp_path):
    df = lod2(tmp_path).set_index("alkis_id")
    assert df.loc["B_WEST", "address"] == "Overwerder Bogen 7a"
    assert df.loc["B_WEST", "kind"] == "Wohnhaus"
    assert df.loc["B_EAST", "address"] == ""
    assert df.loc["B_EAST", "base_m"] == 2.5  # tiefster Punkt der Grundflaeche
    assert df.loc["B_EAST", "height_m"] == 4.0
    assert df.loc["B_EAST", "footprint"].shape == (5, 2)


def test_numbering_along_axis(tmp_path):
    df = buildings.number_buildings(lod2(tmp_path), axis=(1.0, 0.0))
    assert list(df["alkis_id"]) == ["B_WEST", "B_EAST"]  # von West nach Ost
    assert list(df["nr"]) == [1, 2]


def test_flood_table(tmp_path):
    # Gelaende 10 x 50 m, Nordkante y = 10: Strom (NaN) x < 5, Vorland 2,5 m,
    # Sommerdeich 3,0 m bei x = 25, Senke 2,0 m dahinter.
    z = np.full((10, 50), 2.5)
    z[:, :5] = np.nan
    z[:, 25] = 3.0
    z[:, 26:] = 2.0
    terrain = inundation.Terrain(
        z=z, transform=SimpleNamespace(a=1.0, c=0.0, e=-1.0, f=10.0)
    )
    spill = inundation.spill_elevation(z, inundation.river_mask(z))
    idx = pd.date_range("2026-01-01", periods=5, freq="1h", tz="UTC")
    level = pd.Series([2.0, 2.6, 3.2, 2.6, 2.0], index=idx)
    timing = inundation.flood_timing(spill, z, level)

    out = buildings.flood_table(lod2(tmp_path), terrain, spill, timing, 3.2)
    out = out.set_index("alkis_id")
    assert out.loc["B_WEST", "spill_m"] == 2.5
    assert out.loc["B_WEST", "onset"] == pd.Timestamp("2026-01-01T01:00", tz="UTC")
    assert out.loc["B_EAST", "spill_m"] == 3.0  # hinter dem Sommerdeich
    assert out.loc["B_EAST", "onset"] == pd.Timestamp("2026-01-01T02:00", tz="UTC")
    np.testing.assert_allclose(out.loc["B_EAST", "depth_m"], 0.7)
    r, c = buildings.footprint_cells(terrain, out.loc["B_WEST", "footprint"])
    assert len(r) == 36  # 6 x 6 m Grundriss
