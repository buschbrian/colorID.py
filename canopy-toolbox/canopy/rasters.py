"""Stage 1-2: canopy height model from a LAS dataset.

The delivered UGRC first-return DSM is a highest-hit surface with buildings in
it. Rebuilding the DSM from vegetation returns only removes the rooftop
false-positive problem at the source rather than masking it downstream.
"""

from __future__ import annotations

import os

import arcpy

GROUND_CLASSES = "2"
VEG_CLASSES = "1;3;4;5"           # unassigned + low/medium/high vegetation
VEG_RETURNS = "FIRST_OF_MANY;SINGLE"

# Interpolation strings are exposed as parameters because valid keyword
# combinations vary between Pro releases; adjust rather than editing code.
DTM_INTERPOLATION = "TRIANGULATION NATURAL_NEIGHBOR WINDOW_SIZE MINIMUM 1"
DSM_INTERPOLATION = "BINNING MAXIMUM NATURAL_NEIGHBOR"


def audit(lasd: str) -> dict:
    """Stage 0. Report what is actually in the .lasd before trusting it."""
    describe = arcpy.Describe(lasd)
    spatial_ref = describe.spatialReference
    report = {
        "path": lasd,
        "spatial_reference": spatial_ref.name,
        "vertical_reference": getattr(spatial_ref, "VCS", None)
        and spatial_ref.VCS.name,
        "linear_unit": spatial_ref.linearUnitName,
        "point_count": getattr(describe, "pointCount", None),
        "class_codes": sorted(
            {int(code) for code in getattr(describe, "classCodes", "").split(";") if code}
        ),
    }
    report["has_ground"] = 2 in report["class_codes"]
    report["has_vegetation"] = bool({3, 4, 5} & set(report["class_codes"]))
    report["has_building"] = 6 in report["class_codes"]
    report["has_noise"] = bool({7, 18} & set(report["class_codes"]))
    return report


def _las_layer(lasd: str, name: str, class_codes: str, returns: str | None):
    arcpy.management.MakeLasDatasetLayer(
        in_las_dataset=lasd,
        out_layer=name,
        class_code=class_codes,
        return_values=returns,
    )
    return name


def _to_raster(layer: str, out_raster: str, interpolation: str, cell_size: float) -> str:
    arcpy.conversion.LasDatasetToRaster(
        in_las_dataset=layer,
        out_raster=out_raster,
        value_field="ELEVATION",
        interpolation_type=interpolation,
        data_type="FLOAT",
        sampling_type="CELLSIZE",
        sampling_value=cell_size,
        z_factor=1,
    )
    return out_raster


def build_chm(
    lasd: str,
    out_workspace: str,
    cell_size: float = 0.5,
    extent: str | None = None,
    prefix: str = "",
    dtm_interpolation: str = DTM_INTERPOLATION,
    dsm_interpolation: str = DSM_INTERPOLATION,
) -> dict:
    """Return paths to the DTM, vegetation DSM, and CHM.

    The DTM is built first and then pinned as the snap raster, so the DSM lands
    on exactly the same grid. Subtracting misregistered surfaces is the most
    common way this workflow produces phantom trees.
    """
    from arcpy.sa import Con, Raster

    dtm = os.path.join(out_workspace, f"{prefix}dtm.tif")
    dsm = os.path.join(out_workspace, f"{prefix}dsm_veg.tif")
    chm = os.path.join(out_workspace, f"{prefix}chm.tif")

    with arcpy.EnvManager(extent=extent, cellSize=cell_size, snapRaster=None):
        ground = _las_layer(lasd, f"{prefix}ground_lyr", GROUND_CLASSES, None)
        _to_raster(ground, dtm, dtm_interpolation, cell_size)

    with arcpy.EnvManager(extent=extent, cellSize=cell_size, snapRaster=dtm):
        veg = _las_layer(lasd, f"{prefix}veg_lyr", VEG_CLASSES, VEG_RETURNS)
        _to_raster(veg, dsm, dsm_interpolation, cell_size)

        difference = Raster(dsm) - Raster(dtm)
        Con(difference < 0, 0, difference).save(chm)

    return {"dtm": dtm, "dsm": dsm, "chm": chm}
