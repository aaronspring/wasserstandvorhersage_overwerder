# Brief: Overhaken flood modelling — data sources & how to continue locally

Handoff for continuing the work on the branch
`claude/elbe-floods-overhaken-modeling-3x4pze`. Method, results and figures are in
[`INUNDATION.md`](INUNDATION.md); this page covers **where the data comes from** and
**how to run things on your own machine**.

## Quick start

```bash
git fetch origin claude/elbe-floods-overhaken-modeling-3x4pze
git checkout claude/elbe-floods-overhaken-modeling-3x4pze
uv sync --extra gelaende          # rasterio, remotezip, scikit-image, scipy
uv run pytest                     # offline, < 1 min
uv run python inundation.py --recent --animate   # highest tide of the last 31 days
```

The first run downloads about 35 MB of tiles into `out/dgm1/` and `out/lod2/`, which
are cached and gitignored. After that a run takes about 15 s, or about 1 min with
`--animate`. Outputs go to `out/inundation/`.

| Command | Water level source |
|---|---|
| `--recent` | Over gauge, last 31 days (PEGELONLINE REST); picks the highest tide |
| `--data web/public/data.json` | current measurements + forecast (from `export_web.py`, needs BSH access) |
| `--event 2013-12-06` | PEGELONLINE long-term archive (**returned 404 on 2026-11-16**, see below) |
| `--demo --peak-cm 960` | synthetic storm tide, no network for the water level |

Useful flags:
- `--drain-cm-h 10`: trapped water drains at 10 cm/h. The default is 0, which keeps it until the end of the tide.
- `--area-bbox XMIN YMIN XMAX YMAX`: the analysis area in EPSG:25832.
- `--gauge-zero -5.0`: overrides the PNP value.
- `--no-buildings`: skips the LoD2 buildings.

## Data sources

### 1. Terrain: DGM1 2022, LGV Hamburg

- **What:** an airborne laser-scan terrain model with buildings and vegetation removed.
  - **Grid:** 1 m, delivered as 1×1 km GeoTIFF tiles named `dgm1_32_<E km>_<N km>_1_hh_2022.tif`.
  - **CRS:** EPSG:25832.
  - **Heights:** m above NHN (DHHN2016), stored in 1 cm steps.
  - **Accuracy:** ±15 cm on well-defined surfaces such as roads.
- **Where:** the Transparenzportal dataset "Geländemodelle Hamburg – DGM". The working
  ZIP (1.3 GB) is
  `https://archiv.transparenz.hamburg.de/hmbtgarchive/HMDK/dgm1_hh_2022-04-30_258334_snap_1.zip`
  (`config.DGM1_URL`). The old `daten-hamburg.de/.../DGM1/...` links return **404**.
- **How:** `inundation.fetch_tiles` uses HTTP range requests (`remotezip`), so only the
  needed tiles are pulled from the ZIP.
- **Licence:** Datenlizenz Deutschland – Namensnennung 2.0, © LGV Hamburg.
- **Gotchas:**
  - **Water placeholders:** water surfaces are filled with flat values, the Elbe at exactly
    **2.00 m** and the Hohendeicher See at **1.00 m**. `water_fill_mask` masks them,
    otherwise the Elbe acts as a fake 2 m barrier.
  - **South bank:** the Niedersachsen bank is missing (−9999 → NaN). The largest NaN area is
    used as the river, which is where the water comes from.
- **Finding newer versions:** CKAN API
  `https://suche.transparenz.hamburg.de/api/3/action/package_search?q=Geländemodell`
  (also `package_show?id=gelaendemodelle-hamburg-dgm1`).

### 2. Buildings: 3D building model LoD2-DE 2026, LGV Hamburg

- **What:** CityGML **1.0** tiles named `LoD2_32_<E km>_<N km>_1_HH.gml`. They contain:
  - the footprint (from the cadastre)
  - the ground height
  - the measured height
  - the ALKIS building function
  - the address, where one exists
- **Where:**
  `https://www.daten-hamburg.de/opendata/3d_stadtmodell_lod2/LoD2-DE_HH_2026-04-28.zip`
  (`config.LOD2_URL`, 630 MB, loaded tile by tile via HTTP range).
- **Gotcha:** of the 502 buildings in the foreshore, only **4** have an ALKIS house number
  (Overwerder Bogen 32/76/78/80). The colony's huts have none. `buildings.py` therefore
  numbers them **NW→SE** (`nr`) and keeps `alkis_id` for matching, for example against a
  plot list from the Verein. The `nr` values shift when buildings are added.

### 3. Water level: Pegel OVER, PEGELONLINE (WSV)

- **Station:** OVER, UUID `b02ce5c0-64e9-4d24-90b9-269a28a1e9f9`, Elbe-km 605.273,
  opposite Overwerder.
- **REST (last 31 days):**
  `https://www.pegelonline.wsv.de/webservices/rest-api/v2/stations/<uuid>/W/measurements.json`
  via `pegelonline.observations("over", "P31D")`. The values are in cm above PNP.
- **Gauge zero:** **PNP = −5.098 m NHN**, valid from 2019-11-01 (`gaugeZero` in the station
  info, `config.OVER_PNP_NHN_M`). It is not the −5.00 m the repo uses as the general
  tidal-Elbe convention. Before 2019-11 the PNP may differ, so check it for historic events.
- **Long-term archive (since 2000):** `history.fetch_history` returned **HTTP 404** from
  `prepare-download` on 2026-11-16. Alternatives:
  - the repo's Hugging Face dataset `aaronspring/elbe-pegel-over-zollenspieker-minutely-since-2000`
  - downloading the data manually via the PEGELONLINE web form

### 4. Forecast: BSH (via the existing pipeline)

`export_web.py` writes `web/public/data.json` with Over measurements and the Overwerder
forecast, interpolated from the BSH forecasts for Zollenspieker and St. Pauli.
`inundation.py --data` reads it. I could not test this path in the cloud session because
`gdi.bsh.de` was not reachable there.

### Checked but not used

| Source | Why not |
|---|---|
| **GEM-15** (Google Earth Engine, 15 m DSM/DTM) | too coarse, with a vertical bias of up to several metres; would only be useful for comparison |
| INSPIRE address WFS `geodienste.hamburg.de/HH_WFS_INSPIRE_Adressen` | the BBOX query fails on the server side (`ST_Intersects: mixed SRID`) |
| OSM Overpass (buildings/house numbers) | blocked by the network in the cloud session; try it locally if needed |
| Bruchkanten (break lines, DXF/WFS) | not used yet; could sharpen dike crests and ditch edges |

## Network hosts needed

- `archiv.transparenz.hamburg.de`
- `www.daten-hamburg.de`
- `www.pegelonline.wsv.de`
- optionally: `suche.transparenz.hamburg.de` (discovery), `gdi.bsh.de` (forecast)

Locally these normally just work; in the cloud environment they had to be allowed explicitly.

## Code map

| File | Purpose |
|---|---|
| `wasserstand_overwerder/inundation.py` | tile download, terrain loading, `water_fill_mask`, `river_mask`, `spill_elevation` (threshold height per cell), `flood_timing`, `depth_at` (with trapped water) |
| `wasserstand_overwerder/buildings.py` | LoD2 parsing, numbering, flood timing per building |
| `wasserstand_overwerder/inundation_plot.py` | figures: summary, terrain, profile, hourly snapshots, building map, GIF |
| `inundation.py` | command-line script that ties everything together and writes CSV/GeoTIFF/PNG |
| `wasserstand_overwerder/config.py` | `OVER_PNP_NHN_M`, URLs, `INUNDATION_BBOX`, `OVERHAKEN_BBOX`, `INUNDATION_VIEW`, `INUNDATION_PROFILE`, labels, `VORLAND_MAX_SPILL_M`, `INUNDATION_DRAIN_M_PER_H` |
| `tests/test_inundation.py`, `tests/test_buildings.py` | offline tests on synthetic terrain and mini-CityGML |

Outputs in `out/inundation/`:

| File | Content |
|---|---|
| `inundation.png` | summary chart |
| `gelaende.png` | terrain map |
| `profil.png` | cross-section A–B |
| `verlauf.png` | hourly depth maps |
| `gebaeude.png` | numbered building map |
| `animation.gif` | animation (only with `--animate`) |
| `hoehe_zeitpunkt.csv` | timing per ground-height class |
| `gebaeude.csv` | per building: `nr`, `alkis_id`, address, `base_m`, `spill_m`, `onset`, `hours_wet`, `depth_m` |
| `spill_m_nhn.tif`, `onset_min_rel_peak.tif`, `hours_wet.tif`, `max_depth_m.tif`, `residual_depth_m.tif` | GeoTIFFs in EPSG:25832, e.g. for QGIS |

## Open points / next steps

1. **Validation:** compare the predicted onset and extent with photos or observations
   from the colony (26 Oct 2026, Over peak 957 cm).
2. **Plot numbers:** match the Verein's plot list to `alkis_id` so the figures show real
   numbers.
3. **Drainage rate:** use real values for the Overwerder sluices instead of
   `--drain-cm-h 0`.
4. **Historic events** (Xaver 2013, Tilo 2007): load the data via the HF dataset because the
   archive endpoint is broken, and check the PNP before 2019-11.
5. **Flow physics:** for real inflow times, a 2D model (LISFLOOD-FP or HEC-RAS 2D) on the
   DGM1, with Over as the boundary condition. The current model is a "bathtub" with
   connectivity, so onset is the earliest possible time.
6. **Integration:** flood-onset map or building list in the web app or in the alert issues.
7. **PR:** none opened yet; the branch is pushed.
