"""Stage 5-6: watershed crown delineation and per-tree attributes."""

from __future__ import annotations

import math
import os

import arcpy


def delineate(
    chm_path: str,
    treetops: str,
    out_workspace: str,
    min_height: float = 2.0,
    min_crown_area: float = 3.0,
    cell_size: float = 0.5,
    prefix: str = "",
) -> str:
    """Return a crown polygon feature class joined to its treetop.

    The CHM is inverted so treetops become basins. Fill is deliberately NOT
    run: the sinks are the trees, and filling erases them.
    """
    from arcpy.sa import Con, FlowDirection, IsNull, Raster, SetNull, Watershed

    chm = Raster(chm_path)
    canopy = SetNull(chm < min_height, chm)

    flow_direction = FlowDirection(canopy * -1, "NORMAL")
    basins = Watershed(flow_direction, treetops, "TREE_ID")

    # Watershed floods outward across lawn and pavement to the raster edge.
    # Clipping back to the canopy mask is what keeps crowns the size of crowns.
    clipped = os.path.join(out_workspace, f"{prefix}crowns.tif")
    Con(~IsNull(canopy), basins).save(clipped)

    raw = os.path.join(out_workspace, f"{prefix}crowns_raw")
    arcpy.conversion.RasterToPolygon(clipped, raw, "NO_SIMPLIFY", "VALUE")

    crowns = os.path.join(out_workspace, f"{prefix}crowns")
    arcpy.management.Dissolve(raw, crowns, "gridcode")
    arcpy.management.AlterField(crowns, "gridcode", "TREE_ID", "TREE_ID")

    arcpy.management.MakeFeatureLayer(crowns, "crown_lyr")
    arcpy.management.SelectLayerByAttribute(
        "crown_lyr", "NEW_SELECTION", f"Shape_Area < {min_crown_area}"
    )
    arcpy.management.DeleteFeatures("crown_lyr")
    arcpy.management.Delete("crown_lyr")

    _attribute(crowns, chm_path, treetops, out_workspace, cell_size, prefix)
    return crowns


def _attribute(crowns, chm_path, treetops, workspace, cell_size, prefix) -> None:
    from arcpy.sa import ZonalStatisticsAsTable

    stats = os.path.join(workspace, f"{prefix}crown_stats")
    ZonalStatisticsAsTable(crowns, "TREE_ID", chm_path, stats, "DATA", "ALL")

    for name, dtype in (
        ("HEIGHT_M", "DOUBLE"),
        ("CROWN_AREA_M2", "DOUBLE"),
        ("CROWN_DIAM_M", "DOUBLE"),
    ):
        arcpy.management.AddField(crowns, name, dtype)

    arcpy.management.JoinField(crowns, "TREE_ID", stats, "TREE_ID", ["MAX", "AREA"])
    with arcpy.da.UpdateCursor(
        crowns, ["MAX", "AREA", "HEIGHT_M", "CROWN_AREA_M2", "CROWN_DIAM_M"]
    ) as cursor:
        for row in cursor:
            peak, area = row[0], row[1]
            if area is None:
                continue
            row[2] = peak
            row[3] = area
            row[4] = 2.0 * math.sqrt(area / math.pi)
            cursor.updateRow(row)

    arcpy.management.DeleteField(crowns, ["MAX", "AREA"])
    arcpy.management.JoinField(treetops, "TREE_ID", crowns, "TREE_ID",
                               ["CROWN_AREA_M2", "CROWN_DIAM_M"])
