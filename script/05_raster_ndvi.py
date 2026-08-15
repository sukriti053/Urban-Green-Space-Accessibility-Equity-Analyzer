# scripts/05_raster_ndvi.py
"""
Computes NDVI from Sentinel-2 Red (B04) and NIR (B08) bands,
clips to the Delhi project bbox, and reclassifies into
vegetation/heat-risk zones using NumPy band math.

Sentinel-2 tile T43RGM is already in UTM Zone 43N (EPSG:32643) —
same CRS as your PostGIS project, so no reprojection needed.
"""

import os
from pathlib import Path

# Force rasterio to use its own bundled PROJ data, not PostgreSQL's
# (avoids conflict with C:\Program Files\PostgreSQL\...\proj)
import rasterio
_rasterio_proj_dir = Path(rasterio.__file__).parent / "proj_data"
if _rasterio_proj_dir.exists():
    os.environ["PROJ_DATA"] = str(_rasterio_proj_dir)
    os.environ["PROJ_LIB"] = str(_rasterio_proj_dir)

from rasterio.mask import mask
from rasterio.warp import transform_bounds
import numpy as np
from shapely.geometry import box

BASE_DIR = Path(r"C:\Users\HARSH\Desktop\Urban Green Space Accessibility & Equity Analyzer")
SENTINEL_DIR = (
    BASE_DIR / "data" / "raw" / "sentinal2"
    / "S2C_MSIL2A_20251124T053151_N0511_R105_T43RGM_20251124T090509.SAFE"
    / "GRANULE" / "L2A_T43RGM_A006367_20251124T053150" / "IMG_DATA" / "R10m"
)
PROCESSED_DIR = BASE_DIR / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

RED_BAND = SENTINEL_DIR / "T43RGM_20251124T053151_B04_10m.jp2"
NIR_BAND = SENTINEL_DIR / "T43RGM_20251124T053151_B08_10m.jp2"

# Delhi bbox in WGS84 (same as your earlier queries)
BBOX_WGS84 = (77.15, 28.55, 77.25, 28.65)  # (minx, miny, maxx, maxy)


def get_clip_geometry(target_crs):
    """Reproject the WGS84 bbox into the raster's CRS for clipping."""
    minx, miny, maxx, maxy = transform_bounds("EPSG:4326", target_crs, *BBOX_WGS84)
    return [box(minx, miny, maxx, maxy)]


def main():
    print("--- Loading Red and NIR bands ---")
    with rasterio.open(RED_BAND) as red_src:
        clip_geom = get_clip_geometry(red_src.crs)
        red_clipped, red_transform = mask(red_src, clip_geom, crop=True)
        red = red_clipped[0].astype("float32")
        profile = red_src.profile.copy()

    with rasterio.open(NIR_BAND) as nir_src:
        nir_clipped, _ = mask(nir_src, clip_geom, crop=True)
        nir = nir_clipped[0].astype("float32")

    print(f"  Clipped raster shape: {red.shape}")

    # --- NDVI computation ---
    print("\n--- Computing NDVI ---")
    np.seterr(divide="ignore", invalid="ignore")
    ndvi = (nir - red) / (nir + red)
    ndvi = np.nan_to_num(ndvi, nan=-1.0)  # NoData -> -1 (non-vegetation)

    print(f"  NDVI range: {ndvi.min():.3f} to {ndvi.max():.3f}")
    print(f"  NDVI mean: {ndvi.mean():.3f}")

    # --- Reclassification ---
    # NDVI thresholds (standard convention):
    #   < 0.0        -> water/built-up/barren
    #   0.0 - 0.2    -> sparse/no vegetation (heat-risk zone)
    #   0.2 - 0.4    -> moderate vegetation
    #   > 0.4        -> dense vegetation (parks, tree cover)
    print("\n--- Reclassifying ---")
    veg_class = np.zeros_like(ndvi, dtype="uint8")
    veg_class[(ndvi >= -1.0) & (ndvi < 0.0)] = 1   # built-up/barren
    veg_class[(ndvi >= 0.0) & (ndvi < 0.2)] = 2    # sparse vegetation
    veg_class[(ndvi >= 0.2) & (ndvi < 0.4)] = 3    # moderate vegetation
    veg_class[ndvi >= 0.4] = 4                      # dense vegetation

    unique, counts = np.unique(veg_class, return_counts=True)
    class_names = {1: "built-up/barren", 2: "sparse veg", 3: "moderate veg", 4: "dense veg"}
    for u, c in zip(unique, counts):
        pct = 100 * c / veg_class.size
        print(f"  Class {u} ({class_names.get(u, 'unknown')}): {c} pixels ({pct:.1f}%)")

    # --- Save outputs ---
    profile.update(
        height=red.shape[0],
        width=red.shape[1],
        transform=red_transform,
        count=1,
        dtype="float32",
        driver="GTiff",
    )

    ndvi_path = PROCESSED_DIR / "ndvi.tif"
    with rasterio.open(ndvi_path, "w", **profile) as dst:
        dst.write(ndvi, 1)
    print(f"\nSaved NDVI raster: {ndvi_path}")

    profile.update(dtype="uint8")
    veg_class_path = PROCESSED_DIR / "veg_class.tif"
    with rasterio.open(veg_class_path, "w", **profile) as dst:
        dst.write(veg_class, 1)
    print(f"Saved vegetation class raster: {veg_class_path}")


if __name__ == "__main__":
    main()
