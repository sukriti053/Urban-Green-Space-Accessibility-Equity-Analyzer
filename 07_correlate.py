# scripts/07_correlate.py
"""
Joins accessibility scores and NDVI stats per grid cell,
computes the correlation between park accessibility and vegetation,
and exports a final summary table + map-ready GeoDataFrame.
"""

import geopandas as gpd
import pandas as pd
from sqlalchemy import create_engine
from pathlib import Path
import getpass

BASE_DIR = Path(r"C:\Users\HARSH\Desktop\Urban Green Space Accessibility & Equity Analyzer")
OUTPUTS_DIR = BASE_DIR / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

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

    print("--- Loading accessibility scores ---")
    access = gpd.read_postgis(
        "SELECT cell_id, geom, total_buildings, buildings_within_400m, "
        "accessibility_pct, avg_distance_m FROM grid_accessibility_score",
        engine, geom_col="geom"
    )
    print(f"  {len(access)} cells")

    print("\n--- Loading NDVI stats ---")
    ndvi = pd.read_sql(
        "SELECT cell_id, ndvi_mean, ndvi_min, ndvi_max, ndvi_std FROM grid_ndvi_stats",
        engine
    )
    print(f"  {len(ndvi)} cells")

    print("\n--- Joining on cell_id ---")
    merged = access.merge(ndvi, on="cell_id", how="inner")
    print(f"  {len(merged)} cells matched")

    print("\n--- Correlation: accessibility_pct vs ndvi_mean ---")
    corr = merged["accessibility_pct"].corr(merged["ndvi_mean"])
    print(f"  Pearson correlation: {corr:.3f}")

    if corr > 0.3:
        interpretation = "Positive: better park access tends to align with more vegetation."
    elif corr < -0.3:
        interpretation = "Negative: better park access tends to align with LESS vegetation (unexpected)."
    else:
        interpretation = "Weak/no clear linear relationship."
    print(f"  Interpretation: {interpretation}")

    print("\n--- Priority zones: zero accessibility AND low NDVI ---")
    priority = merged[
        (merged["accessibility_pct"] == 0) & (merged["ndvi_mean"] < merged["ndvi_mean"].median())
    ]
    print(f"  {len(priority)} cells are both underserved and low-vegetation")
    print(f"  These are the strongest candidates for new park development.")

    print("\n--- Saving outputs ---")
    merged.to_file(OUTPUTS_DIR / "grid_final_scores.geojson", driver="GeoJSON")
    merged.drop(columns="geom").to_csv(OUTPUTS_DIR / "summary.csv", index=False)
    priority.drop(columns="geom").to_csv(OUTPUTS_DIR / "priority_zones.csv", index=False)
    print(f"  Saved: grid_final_scores.geojson, summary.csv, priority_zones.csv")


if __name__ == "__main__":
    main()
    