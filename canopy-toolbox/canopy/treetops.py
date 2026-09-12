"""Stage 3-4: smoothing, banded local maxima, plateau collapse."""

from __future__ import annotations

import os

import arcpy

from .bands import Band, radius_in_cells


def detect(
    chm_path: str,
    out_workspace: str,
    bands,
    cell_size: float = 0.5,
    smooth_cells: int = 1,
    prefix: str = "",
) -> str:
    """Return a point feature class of treetops with TREE_ID and HEIGHT_M.

    One point per tree, not one per maximum cell: flat crown tops produce
    clusters of tied maxima and collapsing them is worth 15-30% of the count.
    """
    from arcpy.sa import (
        Con,
        ExtractMultiValuesToPoints,
        FocalStatistics,
        IsNull,
        NbrCircle,
        Raster,
        RegionGroup,
        SetNull,
    )

    chm = Raster(chm_path)
    min_height = bands[0].low

    # Light smoothing only. Over-smoothing merges a row of street trees into one.
    surface = (
        FocalStatistics(chm, NbrCircle(smooth_cells, "CELL"), "MEAN", "DATA")
        if smooth_cells > 0
        else chm
    )
    canopy = SetNull(surface < min_height, surface)

    maxima = None
    for band in bands:
        neighbourhood = NbrCircle(radius_in_cells(band.radius, cell_size), "CELL")
        focal_max = FocalStatistics(canopy, neighbourhood, "MAXIMUM", "DATA")
        in_band = (
            canopy >= band.low
            if band.high is None
            else ((canopy >= band.low) & (canopy < band.high))
        )
        # >= rather than == : focal maximum is never below the cell itself, so
        # this is equality without depending on float equality across rasters.
        hit = Con(in_band & (canopy >= focal_max), 1)
        maxima = hit if maxima is None else Con(IsNull(maxima), hit, maxima)

    plateaus = RegionGroup(maxima, "EIGHT", "WITHIN", "NO_LINK")
    plateau_raster = os.path.join(out_workspace, f"{prefix}plateaus.tif")
    plateaus.save(plateau_raster)

    plateau_polys = os.path.join(out_workspace, f"{prefix}plateau_polys")
    arcpy.conversion.RasterToPolygon(
        plateau_raster, plateau_polys, "NO_SIMPLIFY", "VALUE"
    )

    tops = os.path.join(out_workspace, f"{prefix}treetops")
    arcpy.management.FeatureToPoint(plateau_polys, tops, "INSIDE")

    arcpy.management.AddField(tops, "TREE_ID", "LONG")
    arcpy.management.CalculateField(tops, "TREE_ID", "!OBJECTID!", "PYTHON3")
    ExtractMultiValuesToPoints(tops, [[chm_path, "HEIGHT_M"]], "NONE")

    # Smoothing can pull a peak below the threshold; drop those rather than
    # carrying a tree with no measurable height.
    with arcpy.da.UpdateCursor(tops, ["HEIGHT_M"]) as cursor:
        for (height,) in cursor:
            if height is None or height < min_height:
                cursor.deleteRow()

    return tops
