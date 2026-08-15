# scripts/main.py
"""
Orchestrates the full pipeline: cleaning -> PostGIS load -> accessibility
scoring -> NDVI -> zonal stats -> correlation.

Runs scripts/02 through scripts/07 in order. Stops immediately if any
step fails, so you never run a later step on broken/missing data.

Note: scripts 03, 06, and 07 connect to PostGIS and will each prompt
for your database password separately (that's expected).
"""

import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent

PIPELINE = [
    "02_clean_vectors.py",
    "03_load_postgis.py",
    "04_accessibility.sql",   # handled specially — see note below
    "05_raster_ndvi.py",
    "06_zonal_stats.py",
    "07_correlate.py",
]

PYTHON_EXE = sys.executable  # uses whichever python is running this script


def run_python_script(script_name):
    script_path = SCRIPTS_DIR / script_name
    print(f"\n{'='*60}")
    print(f"Running: {script_name}")
    print('='*60)
    result = subprocess.run([PYTHON_EXE, str(script_path)])
    if result.returncode != 0:
        print(f"\n[FAILED] {script_name} exited with code {result.returncode}")
        sys.exit(1)
    print(f"[OK] {script_name} completed")


def main():
    print("Starting full pipeline run...\n")

    run_python_script("02_clean_vectors.py")
    run_python_script("03_load_postgis.py")

    print(f"\n{'='*60}")
    print("Step: 04_accessibility.sql")
    print('='*60)
    print("This step must be run manually in pgAdmin's Query Tool —")
    print("it's a .sql file, not a Python script. Run scripts/04_accessibility.sql")
    print("now, then press Enter here to continue the pipeline.")
    input("Press Enter once 04_accessibility.sql has been run successfully...")

    run_python_script("05_raster_ndvi.py")
    run_python_script("06_zonal_stats.py")
    run_python_script("07_correlate.py")

    print(f"\n{'='*60}")
    print("PIPELINE COMPLETE")
    print('='*60)
    print("Outputs saved in: outputs/grid_final_scores.geojson, summary.csv, priority_zones.csv")


if __name__ == "__main__":
    main()
