-- scripts/04_accessibility.sql
-- Urban Green Space Accessibility & Equity Analyzer
--
-- Steps:
-- 1. 500m x 500m grid banate hain buildings ke extent par
-- 2. Har building centroid se sabse nazdeek park ki distance nikalte hain (LATERAL)
-- 3. Aggregate karte hain: har grid cell mein kitne % buildings 400m ke andar hain

-- ============================================================
-- STEP 1: Grid generate karna (ST_SquareGrid, correct SRID ke saath)
-- ============================================================
DROP TABLE IF EXISTS grid_cells;

CREATE TABLE grid_cells AS
SELECT
    (ST_SquareGrid(500, geom)).i AS cell_x,
    (ST_SquareGrid(500, geom)).j AS cell_y,
    ST_SetSRID((ST_SquareGrid(500, geom)).geom, 32643) AS geom
FROM (
    SELECT ST_SetSRID(ST_Extent(geometry), 32643) AS geom
    FROM buildings
) AS extent;

-- Har cell ko unique ID dena
ALTER TABLE grid_cells ADD COLUMN cell_id SERIAL PRIMARY KEY;

-- Spatial index (fast joins ke liye)
CREATE INDEX idx_grid_cells_geom ON grid_cells USING GIST (geom);

-- Sanity check: kitne cells bane, aur SRID sahi hai ya nahi
SELECT COUNT(*) AS total_cells, ST_SRID(geom) AS srid
FROM grid_cells
GROUP BY ST_SRID(geom);


-- ============================================================
-- STEP 2: building_centroids mein ek proper ID column add karna
-- (OSM tags mein koi usable ID nahi tha, isliye SERIAL use kiya)
-- ============================================================
ALTER TABLE building_centroids ADD COLUMN building_id SERIAL PRIMARY KEY;


-- ============================================================
-- STEP 3: Har building se sabse nazdeek park ki distance (LATERAL join)
-- ============================================================
DROP TABLE IF EXISTS building_park_distance;

CREATE TABLE building_park_distance AS
SELECT
    b.building_id,
    b.geometry AS building_geom,
    nearest.park_id,
    nearest.distance_m
FROM building_centroids b
CROSS JOIN LATERAL (
    SELECT
        p."@id" AS park_id,
        ST_Distance(b.geometry, p.geometry) AS distance_m
    FROM parks p
    ORDER BY b.geometry <-> p.geometry   -- KNN index se fast nearest-neighbor search
    LIMIT 1
) AS nearest;

CREATE INDEX idx_bpd_geom ON building_park_distance USING GIST (building_geom);

-- Sanity check
SELECT COUNT(*) AS total_buildings_scored,
       ROUND(AVG(distance_m)::numeric, 1) AS avg_distance_m,
       ROUND(MIN(distance_m)::numeric, 1) AS min_distance_m,
       ROUND(MAX(distance_m)::numeric, 1) AS max_distance_m
FROM building_park_distance;


-- ============================================================
-- STEP 4: Grid cells par aggregate karna — accessibility score
-- ============================================================
DROP MATERIALIZED VIEW IF EXISTS grid_accessibility_score;

CREATE MATERIALIZED VIEW grid_accessibility_score AS
SELECT
    g.cell_id,
    g.geom,
    COUNT(bpd.building_id) AS total_buildings,
    COUNT(bpd.building_id) FILTER (WHERE bpd.distance_m <= 400) AS buildings_within_400m,
    ROUND(
        100.0 * COUNT(bpd.building_id) FILTER (WHERE bpd.distance_m <= 400)
        / NULLIF(COUNT(bpd.building_id), 0), 1
    ) AS accessibility_pct,
    ROUND(AVG(bpd.distance_m)::numeric, 1) AS avg_distance_m
FROM grid_cells g
LEFT JOIN building_park_distance bpd
    ON ST_Contains(g.geom, bpd.building_geom)
GROUP BY g.cell_id, g.geom
HAVING COUNT(bpd.building_id) > 0;   -- khali cells (bina buildings ke) hata do

CREATE INDEX idx_grid_score_geom ON grid_accessibility_score USING GIST (geom);

-- Final result — sabse kam accessibility wale 10 cells
SELECT cell_id, total_buildings, buildings_within_400m, accessibility_pct, avg_distance_m
FROM grid_accessibility_score
ORDER BY accessibility_pct ASC
LIMIT 10;
