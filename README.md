# Urban-Green-Space-Accessibility-Equity-Analyzer

 Urban Green Space Accessibility & Equity Analyzer — Delhi (NCT)

A GIS pipeline that measures how equitably access to parks is distributed
across central Delhi, and tests whether underserved areas also tend to
have lower vegetation cover. Built as a portfolio project to demonstrate
an end-to-end vector + raster geospatial workflow: OSM data ingestion,
PostGIS spatial analysis, and satellite-derived NDVI processing.

---

## 1. Project Motivation

City planners often ask two related but distinct questions:

1. **Formal access** — how many residents live within a reasonable
   walking distance of a park?
2. **General greenness** — how much vegetation cover does a
   neighborhood actually have (street trees, private gardens, informal
   green space), regardless of whether there's a formal park nearby?

This project answers both questions for central Delhi and checks
whether they tell the same story — they turned out not to, which is
itself a useful finding (see [Section 7](#7-key-findings)).

---

## 2. Study Area

- **City:** Delhi (NCT) — core urban area only, not the wider NCR
  (Gurugram/Noida/Faridabad excluded to keep data volume manageable).
- **Bounding box:** `28.55–28.65°N, 77.15–77.25°E` (roughly Connaught
  Place, Karol Bagh, ITO, South Extension).
- **Aggregation unit:** a uniform **500m × 500m grid**, generated in
  PostGIS, rather than administrative ward boundaries. Wards were
  considered but rejected — OSM's ward-boundary coverage for Delhi is
  incomplete, and a uniform grid is a fairer basis for comparing
  accessibility scores against raster-derived NDVI, since ward polygons
  vary wildly in size and shape.

---

## 3. Data Sources

| Layer | Source | Notes |
|---|---|---|
| Parks / green areas | OpenStreetMap via Overpass Turbo | `leisure=park`, `landuse=grass`, `landuse=forest` |
| Roads | OpenStreetMap via Overpass Turbo | `highway=*`, filtered to line geometries only |
| Buildings | **Microsoft Building Footprints** (open dataset) | Used instead of OSM — Delhi's building layer was too large for Overpass Turbo to export via GeoJSON (repeated server timeouts even after splitting the bounding box). Downloaded via quadkey-indexed tile lookup, then clipped to the study bbox. |
| Satellite imagery | Sentinel-2 L2A, tile `T43RGM`, captured 2025-11-24 | Post-monsoon window — chosen deliberately for low cloud cover and peak vegetation greenness, avoiding both monsoon cloud cover and dry-season NDVI stress. Bands 4 (Red) and 8 (NIR) at 10m resolution. |

### Why Microsoft Building Footprints instead of OSM

Overpass Turbo's buildings query for Delhi failed repeatedly with
server-side timeouts, even after narrowing the bounding box twice and
switching Overpass mirrors. Microsoft's open building-footprint
dataset (AI-derived from satellite imagery) provided equivalent
coverage as a direct download, with no query-timeout risk. The correct
tile was located by computing the bbox's Bing Maps quadkey (level 9:
`123121303`) and cross-referencing Microsoft's `dataset-links.csv`
tile index.

---

## 4. Technical Stack

- **Vector processing:** GeoPandas, Shapely
- **Database:** PostgreSQL 13+ with PostGIS 3.6
- **Raster processing:** rasterio, NumPy
- **Database connectivity:** SQLAlchemy + psycopg2 + GeoAlchemy2
- **Zonal statistics:** rasterstats
- **CRS:** EPSG:32643 (UTM Zone 43N) used throughout for all metric
  distance/area calculations — matches the native CRS of the Sentinel-2
  tile, avoiding reprojection of the raster layer.

---

## 5. Pipeline Overview

```
data/raw/                          data/processed/                PostGIS (delhi_green_space)
├── parks.geojson          ─┐      ├── parks_clean.geojson    ─┐
├── road.geojson            ├─02─▶ ├── roads_clean.geojson     ├─03─▶  parks, roads,
├── buildings.geojson       │      ├── buildings_clean.geojson │       buildings,
└── sentinal2/ (Sentinel-2)─┘      └── building_centroids.geojson─┘    building_centroids
                                                                          │
                                                                          ▼ 04 (SQL)
                                                                    grid_cells (483 cells)
                                                                    building_park_distance
                                                                    grid_accessibility_score
                                    ┌── ndvi.tif       ◀─── 05 ─── Sentinel-2 B04 + B08
                                    └── veg_class.tif
                                          │
                                          ▼ 06
                                    grid_ndvi_stats (PostGIS)
                                          │
                                          ▼ 07
                            outputs/grid_final_scores.geojson
                            outputs/summary.csv
                            outputs/priority_zones.csv
```

### Script-by-script

| Script | Purpose |
|---|---|
| `02_clean_vectors.py` | Reprojects all three vector layers to EPSG:32643, fixes invalid geometries (via `.buffer(0)`), filters roads to line geometries only (dropping bus stops/benches/tactile paving that the OSM `highway` query swept in), and generates building centroids as a population proxy. |
| `03_load_postgis.py` | Loads the four cleaned layers into PostgreSQL/PostGIS using `GeoDataFrame.to_postgis()`. |
| `04_accessibility.sql` | Generates the 500m grid with `ST_SquareGrid`; for every building centroid, finds the nearest park via a `CROSS JOIN LATERAL` + `<->` KNN-indexed search; aggregates to a materialized view scoring each grid cell by % of buildings within 400m of a park. |
| `05_raster_ndvi.py` | Loads Sentinel-2 Red/NIR bands, clips to the study bbox, computes NDVI band math, and reclassifies into 4 vegetation classes (built-up/barren, sparse, moderate, dense). |
| `06_zonal_stats.py` | Computes zonal statistics (mean/min/max/std NDVI) per grid cell using `rasterstats`, writes results back to PostGIS. |
| `07_correlate.py` | Joins accessibility scores and NDVI stats on `cell_id`, computes the Pearson correlation between them, flags "priority zones" (zero accessibility + below-median NDVI), and exports final GeoJSON/CSV outputs. |
| `main.py` | Orchestrates scripts 02→07 in sequence (04 is a manual pgAdmin step, since it's SQL rather than Python); stops on first failure. |

---

## 6. Methodology Details

### 6.1 Accessibility scoring

For each of the 38,028 building centroids, the nearest park is found
using a PostGIS `LATERAL` join ordered by the `<->` KNN operator
(index-assisted nearest-neighbor search — far faster than a brute-force
`ST_Distance` cross join across 38,028 buildings × 4,740 parks).

Each 500m grid cell is then scored as:

```
accessibility_pct = 100 × (buildings within 400m of a park) / (total buildings in cell)
```

400m was used as the walkable-access threshold (a common planning
benchmark, roughly a 5-minute walk).

### 6.2 NDVI computation

Standard NDVI formula applied via NumPy band math:

```
NDVI = (NIR − Red) / (NIR + Red)
```

Reclassified into four bands:

| Class | NDVI range | Meaning |
|---|---|---|
| 1 | < 0.0 | Built-up / barren / water |
| 2 | 0.0 – 0.2 | Sparse vegetation |
| 3 | 0.2 – 0.4 | Moderate vegetation |
| 4 | ≥ 0.4 | Dense vegetation |

**Caveat:** built-up surfaces (concrete, asphalt) sometimes produce NDVI
values just above 0 rather than clearly negative, so a small share of
truly built-up area may fall into the "sparse vegetation" class rather
than "built-up/barren." This is a known NDVI limitation, not a
processing error.

### 6.3 Correlation & priority zones

Pearson correlation was computed between `accessibility_pct` and
`ndvi_mean` across all 448 grid cells with valid data in both layers.
"Priority zones" were defined as cells with `accessibility_pct = 0`
**and** `ndvi_mean` below the citywide median — i.e., areas lacking
both formal park access and general greenery.

---

## 7. Key Findings

- **483** grid cells generated; **448** had both accessibility and NDVI
  data (35 cells had no buildings and were excluded).
- **Average park accessibility: 84.6%** — most of central Delhi's
  building stock sits within 400m of a park.
- **36 cells (8%)** have **zero** buildings within 400m of a park.
- **310 cells (69%)** are fully served (100% accessibility).
- **Average distance to nearest park:** 193.5m citywide (min 0.0m,
  max 1,587.5m).
- **Mean NDVI:** 0.226 citywide (range 0.021–0.596 across cells).
- **Correlation between accessibility and NDVI: r = −0.152** — weak,
  and if anything, slightly negative. This indicates park accessibility
  and general vegetation cover are **largely independent** metrics in
  central Delhi: many well-vegetated areas (street trees, private
  gardens) lack a formal park nearby, and vice versa.
- **11 grid cells** are simultaneously underserved (zero park access)
  **and** below-median in greenness — these are the strongest,
  most defensible candidates for new park development, since they are
  disadvantaged on both measures rather than just one.

---

## 8. Known Limitations

- **Building data source mismatch:** buildings came from Microsoft's
  footprint dataset while parks/roads came from OSM — minor
  edge-boundary differences between the two sources are possible,
  though negligible at 500m grid resolution.
- **Straight-line distance, not network distance:** accessibility is
  based on Euclidean distance from building centroid to nearest park
  boundary, not actual walking-route distance along the road network.
  A pgRouting-based network-distance version would be a natural
  extension (see [Section 9](#9-possible-extensions)).
- **Single-date raster snapshot:** NDVI reflects conditions on one day
  (2025-11-24) and does not capture seasonal variation.
- **Grid vs. administrative units:** results are reported per 500m
  grid cell, not per ward — useful for uniform statistical comparison,
  but less immediately interpretable for policy audiences used to
  ward-level reporting.

---

## 9. Possible Extensions

- Add **pgRouting** to compute true walking-network distance instead
  of straight-line distance.
- Automate `04_accessibility.sql` into the Python orchestration
  pipeline via `psycopg2` execution rather than a manual pgAdmin step.
- Extend to the full NCR and compare Delhi's core against
  Gurugram/Noida/Faridabad.
- Add a regression model (e.g. scikit-learn) to test the
  accessibility–NDVI relationship more rigorously than a simple Pearson
  correlation, controlling for building density.

---

## 10. Repository Structure

```
Urban Green Space Accessibility & Equity Analyzer/
├── data/
│   ├── raw/              # OSM exports, Microsoft building footprints, Sentinel-2 imagery
│   └── processed/         # cleaned vectors, NDVI raster, vegetation classification
├── scripts/
│   ├── 02_clean_vectors.py
│   ├── 03_load_postgis.py
│   ├── 04_accessibility.sql
│   ├── 05_raster_ndvi.py
│   ├── 06_zonal_stats.py
│   ├── 07_correlate.py
│   └── main.py
├── outputs/
│   ├── grid_final_scores.geojson
│   ├── summary.csv
│   └── priority_zones.csv
└── README.md
```

---

## 11. How to Reproduce

1. Export/download the raw layers into `data/raw/` (see
   [Section 3](#3-data-sources) for sources).
2. Create a PostgreSQL database with the PostGIS extension enabled:
   ```sql
   CREATE EXTENSION postgis;
   ```
3. Run the pipeline in order:
   ```
   python scripts/02_clean_vectors.py
   python scripts/03_load_postgis.py
   -- run scripts/04_accessibility.sql manually in pgAdmin --
   python scripts/05_raster_ndvi.py
   python scripts/06_zonal_stats.py
   python scripts/07_correlate.py
   ```
   Or run `python scripts/main.py`, which pauses for step 4 and runs
   the rest automatically.
4. Final outputs land in `outputs/`. Load
   `outputs/grid_final_scores.geojson` into QGIS for visualization.

---

*Author: Sukriti Kumari — GIS Engineer. Built as a portfolio project
demonstrating a combined vector (GeoPandas/PostGIS) and raster
(NumPy/rasterio) geospatial analysis pipeline.*
