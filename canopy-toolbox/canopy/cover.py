"""Canopy cover by zone -- the deliverable that does not depend on detection.

No local maxima, no watershed, no tuning. This is the number that survives a
council meeting; build it before spending a week on tree counts.
"""

from __future__ import annotations

import os

import arcpy


def summarize(
    chm_path: str,
    zones: str,
    zone_field: str,
    out_table: str,
    min_height: float = 2.0,
    cell_size: float = 0.5,
) -> str:
    from arcpy.sa import Con, Raster, ZonalStatisticsAsTable

    workspace = os.path.dirname(out_table) or arcpy.env.scratchGDB
    binary = os.path.join(workspace, "canopy_binary")
    Con(Raster(chm_path) >= min_height, 1, 0).save(binary)

    ZonalStatisticsAsTable(zones, zone_field, binary, out_table, "DATA", "SUM")

    cell_area = cell_size * cell_size
    for name in ("CANOPY_M2", "CANOPY_ACRES", "ZONE_M2", "CANOPY_PCT"):
        arcpy.management.AddField(out_table, name, "DOUBLE")

    with arcpy.da.UpdateCursor(
        out_table, ["SUM", "COUNT", "CANOPY_M2", "CANOPY_ACRES", "ZONE_M2", "CANOPY_PCT"]
    ) as cursor:
        for row in cursor:
            canopy_cells, zone_cells = row[0], row[1]
            if canopy_cells is None or not zone_cells:
                continue
            canopy_m2 = canopy_cells * cell_area
            zone_m2 = zone_cells * cell_area
            row[2] = canopy_m2
            row[3] = canopy_m2 / 4046.8564224
            row[4] = zone_m2
            row[5] = 100.0 * canopy_m2 / zone_m2
            cursor.updateRow(row)

    return out_table
