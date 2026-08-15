# scripts/06_zonal_stats.py
"""
Computes zonal statistics: average NDVI per grid cell.
Reads grid_cells from PostGIS, overlays with the NDVI raster,
and writes results (mean NDVI per cell) back to PostGIS as a new table.
"""

import geopandas as gpd
from sqlalchemy import create_engine
from rasterstats import zonal_stats
from pathlib import Path
import getpass

BASE_DIR = Path(r"C:\Users\HARSH\Desktop\Urban Green Space Accessibility & Equity Analyzer")
PROCESSED_DIR = BASE_DIR / "data" / "processed"
NDVI_PATH = PROCESSED_DIR / "ndvi.tif"

DB_NAME = "delhi_green_space"
DB_USER = "postgres"
DB_HOST = "localhost"
DB_PORT = "5432"


def get_engine():
    password = getpass.getpass(f"Enter PostgreSQL password for user '{DB_USER}': ")
    conn_str = f"postgresql+psycopg2://{DB_USER}:{password}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    return create_engine(conn_str)


def main():
    engine = get_engine()

    print("--- Loading grid cells from PostGIS ---")
    grid = gpd.read_postgis(
        "SELECT cell_id, geom FROM grid_cells", engine, geom_col="geom"
    )
    print(f"  Loaded {len(grid)} grid cells")

    print("\n--- Computing zonal statistics (mean NDVI per cell) ---")
    stats = zonal_stats(
        grid,
        str(NDVI_PATH),
        stats=["mean", "min", "max", "std"],
        geojson_out=False,
        nodata=-1.0,
    )

    grid["ndvi_mean"] = [s["mean"] for s in stats]
    grid["ndvi_min"] = [s["min"] for s in stats]
    grid["ndvi_max"] = [s["max"] for s in stats]
    grid["ndvi_std"] = [s["std"] for s in stats]

    # Drop cells with no raster coverage (outside Sentinel-2 tile extent)
    before = len(grid)
    grid = grid.dropna(subset=["ndvi_mean"])
    print(f"  Dropped {before - len(grid)} cells with no raster coverage")
    print(f"  Remaining: {len(grid)} cells")

    print("\n--- NDVI summary across cells ---")
    print(f"  Mean of means: {grid['ndvi_mean'].mean():.3f}")
    print(f"  Lowest NDVI cell: {grid['ndvi_mean'].min():.3f}")
    print(f"  Highest NDVI cell: {grid['ndvi_mean'].max():.3f}")

    print("\n--- Writing to PostGIS: grid_ndvi_stats ---")
    grid_to_save = grid[["cell_id", "ndvi_mean", "ndvi_min", "ndvi_max", "ndvi_std", "geom"]]
    grid_to_save.to_postgis("grid_ndvi_stats", engine, if_exists="replace", index=False)
    print("  Done.")


if __name__ == "__main__":
    main()