# -*- coding: utf-8 -*-
"""Canopy Tools -- lidar tree detection and canopy cover for ArcGIS Pro.

Pro caches .pyt modules between runs, so the package is reloaded on every
import to make edits take effect without restarting Pro.
"""

import importlib
import os
import sys

import arcpy

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import canopy
from canopy import bands as _bands

for _name in ("bands", "tiling", "rasters", "treetops", "crowns", "cover", "licensing"):
    _module = getattr(canopy, _name, None)
    if _module is not None:
        importlib.reload(_module)
importlib.reload(_bands)


def _param(name, label, datatype, direction="Input", ptype="Required", default=None):
    parameter = arcpy.Parameter(
        displayName=label,
        name=name,
        datatype=datatype,
        parameterType=ptype,
        direction=direction,
    )
    if default is not None:
        parameter.value = default
    return parameter


class Toolbox(object):
    def __init__(self):
        self.label = "Canopy Tools"
        self.alias = "canopy"
        self.tools = [
            AuditLasDataset,
            BuildCanopyHeightModel,
            DetectTreetops,
            DelineateCrowns,
            SummarizeCanopyCover,
        ]


class AuditLasDataset(object):
    def __init__(self):
        self.label = "1. Audit LAS Dataset"
        self.description = (
            "Report class codes, spatial reference, and point count before "
            "trusting a delivery. Run this first."
        )

    def getParameterInfo(self):
        return [
            _param("lasd", "LAS Dataset", "DELasDataset"),
            _param("report", "Report", "GPString", "Output", "Derived"),
        ]

    def execute(self, parameters, messages):
        from canopy import rasters

        report = rasters.audit(parameters[0].valueAsText)
        for key, value in report.items():
            arcpy.AddMessage(f"{key}: {value}")
        if not report["has_ground"]:
            arcpy.AddWarning("No ground class (2). Run Classify LAS Ground first.")
        if not report["has_vegetation"]:
            arcpy.AddWarning(
                "No vegetation classes (3/4/5). Run Classify LAS By Height with "
                "the high-vegetation break at the tree threshold."
            )
        if not report["has_noise"]:
            arcpy.AddWarning(
                "No noise class (7/18). Run Classify LAS Noise first -- isolated "
                "high points become phantom 40 m treetops and are the largest "
                "single source of commission error."
            )
        parameters[1].value = str(report)


class BuildCanopyHeightModel(object):
    def __init__(self):
        self.label = "2. Build Canopy Height Model"
        self.description = (
            "Bare-earth DTM plus a vegetation-only DSM (buildings and noise "
            "excluded at the source), differenced into a CHM on one snapped grid."
        )

    def getParameterInfo(self):
        return [
            _param("lasd", "LAS Dataset", "DELasDataset"),
            _param("workspace", "Output Folder", "DEFolder"),
            _param("cell_size", "Cell Size (m)", "GPDouble", default=0.5),
            _param("extent", "Processing Extent", "GPExtent", ptype="Optional"),
            _param("prefix", "Output Prefix", "GPString", ptype="Optional", default=""),
            _param("chm", "CHM", "DERasterDataset", "Output", "Derived"),
        ]

    def execute(self, parameters, messages):
        from canopy import licensing, rasters

        with licensing.extensions("3D", "Spatial"):
            result = rasters.build_chm(
                lasd=parameters[0].valueAsText,
                out_workspace=parameters[1].valueAsText,
                cell_size=parameters[2].value,
                extent=parameters[3].valueAsText,
                prefix=parameters[4].valueAsText or "",
            )
        for key, path in result.items():
            arcpy.AddMessage(f"{key}: {path}")
        parameters[5].value = result["chm"]


class DetectTreetops(object):
    def __init__(self):
        self.label = "3. Detect Treetops"
        self.description = (
            "Height-banded local maxima with plateau collapse. The bands "
            "approximate a variable-radius window and are the single biggest "
            "accuracy lever -- re-fit them locally before publishing a count."
        )

    def getParameterInfo(self):
        return [
            _param("chm", "Canopy Height Model", "DERasterDataset"),
            _param("workspace", "Output Workspace", "DEWorkspace"),
            _param("band_spec", "Height Bands (low-high:radius_m)", "GPString",
                   default=_bands.DEFAULT_SPEC),
            _param("cell_size", "Cell Size (m)", "GPDouble", default=0.5),
            _param("smooth", "Smoothing Radius (cells)", "GPLong", default=1),
            _param("prefix", "Output Prefix", "GPString", ptype="Optional", default=""),
            _param("tops", "Treetops", "DEFeatureClass", "Output", "Derived"),
        ]

    def updateMessages(self, parameters):
        if parameters[2].value:
            try:
                _bands.parse_bands(parameters[2].valueAsText)
            except ValueError as exc:
                parameters[2].setErrorMessage(str(exc))
        if parameters[4].value is not None and parameters[4].value > 2:
            parameters[4].setWarningMessage(
                "Smoothing beyond 2 cells merges adjacent crowns."
            )
        return

    def execute(self, parameters, messages):
        from canopy import licensing, treetops

        licensing.require_advanced()
        parsed = _bands.parse_bands(parameters[2].valueAsText)
        with licensing.extensions("Spatial"):
            tops = treetops.detect(
                chm_path=parameters[0].valueAsText,
                out_workspace=parameters[1].valueAsText,
                bands=parsed,
                cell_size=parameters[3].value,
                smooth_cells=parameters[4].value,
                prefix=parameters[5].valueAsText or "",
            )
        count = int(arcpy.management.GetCount(tops)[0])
        arcpy.AddMessage(f"{count} treetops: {tops}")
        arcpy.AddWarning(
            "This is an estimate, not a census. Detection runs ~85-95% for "
            "open-grown trees and ~50-75% in closed canopy; multi-stem oak "
            "clumps are one crown from above. Validate before publishing."
        )
        parameters[6].value = tops


class DelineateCrowns(object):
    def __init__(self):
        self.label = "4. Delineate Crowns"
        self.description = (
            "Inverted-CHM watershed seeded by treetops, clipped to the canopy "
            "mask, with height and crown geometry attached."
        )

    def getParameterInfo(self):
        return [
            _param("chm", "Canopy Height Model", "DERasterDataset"),
            _param("tops", "Treetops", "GPFeatureLayer"),
            _param("workspace", "Output Workspace", "DEWorkspace"),
            _param("min_height", "Minimum Tree Height (m)", "GPDouble", default=2.0),
            _param("min_area", "Minimum Crown Area (m2)", "GPDouble", default=3.0),
            _param("cell_size", "Cell Size (m)", "GPDouble", default=0.5),
            _param("prefix", "Output Prefix", "GPString", ptype="Optional", default=""),
            _param("crowns", "Crowns", "DEFeatureClass", "Output", "Derived"),
        ]

    def execute(self, parameters, messages):
        from canopy import crowns, licensing

        with licensing.extensions("Spatial"):
            result = crowns.delineate(
                chm_path=parameters[0].valueAsText,
                treetops=parameters[1].valueAsText,
                out_workspace=parameters[2].valueAsText,
                min_height=parameters[3].value,
                min_crown_area=parameters[4].value,
                cell_size=parameters[5].value,
                prefix=parameters[6].valueAsText or "",
            )
        arcpy.AddMessage(f"crowns: {result}")
        parameters[7].value = result


class SummarizeCanopyCover(object):
    def __init__(self):
        self.label = "5. Summarize Canopy Cover"
        self.description = (
            "Canopy area and percent by zone straight from the CHM. No "
            "detection, no tuning -- the defensible number."
        )

    def getParameterInfo(self):
        return [
            _param("chm", "Canopy Height Model", "DERasterDataset"),
            _param("zones", "Zone Features", "GPFeatureLayer"),
            _param("zone_field", "Zone Field", "Field"),
            _param("out_table", "Output Table", "DETable", "Output"),
            _param("min_height", "Minimum Tree Height (m)", "GPDouble", default=2.0),
            _param("cell_size", "Cell Size (m)", "GPDouble", default=0.5),
        ]

    def updateParameters(self, parameters):
        parameters[2].parameterDependencies = [parameters[1].name]
        return

    def execute(self, parameters, messages):
        from canopy import cover, licensing

        with licensing.extensions("Spatial"):
            table = cover.summarize(
                chm_path=parameters[0].valueAsText,
                zones=parameters[1].valueAsText,
                zone_field=parameters[2].valueAsText,
                out_table=parameters[3].valueAsText,
                min_height=parameters[4].value,
                cell_size=parameters[5].value,
            )
        arcpy.AddMessage(f"canopy cover: {table}")
