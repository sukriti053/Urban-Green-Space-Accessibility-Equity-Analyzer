# scripts/03_load_postgis.py
"""
Loads the cleaned vector layers into PostGIS.
Uses SQLAlchemy + psycopg2 (same connector that worked reliably
in the Varanasi project) via GeoPandas' to_postgis().
"""

import geopandas as gpd
from sqlalchemy import create_engine
from pathlib import Path
import getpass

BASE_DIR = Path(r"C:\Users\HARSH\Desktop\Urban Green Space Accessibility & Equity Analyzer")
PROCESSED_DIR = BASE_DIR / "data" / "processed"

DB_NAME = "delhi_green_space"
DB_USER = "postgres"
DB_HOST = "localhost"
DB_PORT = "5432"


def get_engine():
    password = getpass.getpass(f"Enter PostgreSQL password for user '{DB_USER}': ")
    conn_str = f"postgresql+psycopg2://{DB_USER}:{password}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    return create_engine(conn_str)


def load_layer(engine, filename, table_name):
    print(f"\n--- Loading {filename} -> {table_name} ---")
    gdf = gpd.read_file(PROCESSED_DIR / filename)
    gdf.to_postgis(table_name, engine, if_exists="replace", index=False)
    print(f"  Loaded {len(gdf)} rows into '{table_name}'")


def main():
    engine = get_engine()

    load_layer(engine, "parks_clean.geojson", "parks")
    load_layer(engine, "buildings_clean.geojson", "buildings")
    load_layer(engine, "building_centroids.geojson", "building_centroids")
    load_layer(engine, "roads_clean.geojson", "roads")

    print("\nAll layers loaded into PostGIS.")


if __name__ == "__main__":
    main()