# scripts/02_clean_vectors.py
"""
Cleans and reprojects the three raw OSM layers:
- Reprojects everything to EPSG:32643 (UTM zone 43N — correct for Delhi),
  so distances are in meters, not degrees.
- Fixes invalid geometries.
- Filters roads down to actual line geometries (drops points/polygons
  that came from bus stops, benches, etc.).
- Generates building centroids (population proxy).
Outputs go to data/processed/.
"""

import geopandas as gpd
from pathlib import Path

# Base project folder — adjust here if you move the project
BASE_DIR = Path(r"C:\Users\HARSH\Desktop\Urban Green Space Accessibility & Equity Analyzer")
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

TARGET_CRS = "EPSG:32643"  # UTM 43N — correct metric CRS for Delhi


def fix_geometries(gdf):
    invalid_count = (~gdf.is_valid).sum()
    if invalid_count > 0:
        print(f"  Fixing {invalid_count} invalid geometries...")
        gdf["geometry"] = gdf["geometry"].buffer(0)
    return gdf


def clean_parks():
    print("\n--- Parks ---")
    gdf = gpd.read_file(RAW_DIR / "Parks_green_areas.geojson")
    gdf = gdf.to_crs(TARGET_CRS)
    gdf = fix_geometries(gdf)
    gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    gdf["area_m2"] = gdf.geometry.area
    print(f"  Rows: {len(gdf)}")
    gdf.to_file(PROCESSED_DIR / "parks_clean.geojson", driver="GeoJSON")
    return gdf


def clean_buildings():
    print("\n--- Buildings ---")
    gdf = gpd.read_file(RAW_DIR / "buildings.geojson")
    gdf = gdf.to_crs(TARGET_CRS)
    gdf = fix_geometries(gdf)
    gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]

    # Compute centroids separately, don't keep as a second geometry column
    centroids_geom = gdf.geometry.centroid

    print(f"  Rows: {len(gdf)}")
    gdf.to_file(PROCESSED_DIR / "buildings_clean.geojson", driver="GeoJSON")

    # Separate centroid-only layer for accessibility queries
    centroids = gdf.drop(columns="geometry").copy()
    centroids["geometry"] = centroids_geom
    centroids = gpd.GeoDataFrame(centroids, geometry="geometry", crs=TARGET_CRS)
    centroids.to_file(PROCESSED_DIR / "building_centroids.geojson", driver="GeoJSON")
    return gdf


def clean_roads():
    print("\n--- Roads ---")
    gdf = gpd.read_file(RAW_DIR / "road.geojson")
    gdf = gdf.to_crs(TARGET_CRS)
    gdf = fix_geometries(gdf)
    # Keep only actual line geometries — drop points/polygons
    # that came from bus stops, benches, tactile paving, etc.
    before = len(gdf)
    gdf = gdf[gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])]
    print(f"  Dropped {before - len(gdf)} non-line features")
    print(f"  Rows: {len(gdf)}")
    gdf.to_file(PROCESSED_DIR / "roads_clean.geojson", driver="GeoJSON")
    return gdf


def main():
    parks = clean_parks()
    buildings = clean_buildings()
    roads = clean_roads()
    print("\nAll layers cleaned and saved to data/processed/")
    return parks, buildings, roads


if __name__ == "__main__":
    main()
