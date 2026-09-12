# canopy-toolbox

A Python toolbox (`CanopyTools.pyt`) that turns a classified lidar point cloud
into canopy cover and an individual-tree layer using only ArcGIS Pro, 3D
Analyst, and Spatial Analyst. No R, no `lidR`, no external dependencies.

Built against Salt Lake County QL1 lidar (8 pulses/m², 0.5 m products), but
nothing here is Utah-specific.

## What it produces, and how much to trust it

| Deliverable | Tool | Defensibility |
|---|---|---|
| Canopy cover — acres and % by parcel, district, block group | 5 | **High.** Deterministic, auditable, no tuning. |
| Individual tree points and crown polygons | 3 + 4 | **Medium.** An estimate with known bias, never a census. |
| Per-tree height and crown geometry | 4 | Fine as a screening layer, not as a record of a tree. |

If the question is "how much canopy does the city have," run tool 5 and stop.
If the question is "how many trees," you are producing an interval estimate and
the metadata needs to say so.

**Known detection rates:** ~85–95% for open-grown trees (street ROW, parks,
yards); ~50–75% in closed canopy. Understory is invisible. Multi-stem oak and
maple clumps are one crown from above regardless of how many stems are on the
ground. The count is biased **low**, worst in the areas people ask about most.

## Order of operations

| # | Tool | Notes |
|---|---|---|
| 0 | *Classify LAS Noise* (stock 3D Analyst) | **Do this first.** Isolated high points become phantom 40 m treetops — the largest single source of commission error. |
| 0 | *Classify LAS Ground / Building / By Height* (stock) | Only if the delivery lacks classes 2/6 and 3/4/5. Set the high-vegetation break to match your tree threshold. |
| 1 | **Audit LAS Dataset** | Class codes, spatial reference, point count. Warns about each missing class above. |
| 2 | **Build Canopy Height Model** | DTM + vegetation-only DSM, differenced on one snapped grid. |
| 3 | **Detect Treetops** | Height-banded local maxima with plateau collapse. |
| 4 | **Delineate Crowns** | Inverted-CHM watershed, clipped to the canopy mask. |
| 5 | **Summarize Canopy Cover** | Zonal rollup. Independent of 3 and 4 — run it first. |

## Design decisions worth knowing

**The DSM is rebuilt, not reused.** A delivered first-return DSM is a
highest-hit surface with buildings in it. Tool 2 builds the DSM from vegetation
returns only (classes 1/3/4/5, first-of-many and single returns), which removes
the rooftop false-positive problem at the source instead of masking it later.

**The DTM is pinned as the snap raster** before the DSM is generated. A
half-cell misregistration at 0.5 m puts a rim of false height around every
crown edge, and those rims become treetops.

**The search window varies with height.** ArcGIS has no variable-window filter,
so `canopy/bands.py` runs Focal Statistics once per height band and combines
the results:

```
2-6:1.0, 6-12:1.5, 12-20:2.0, 20-:2.5
```

These are open-grown urban defaults. **Re-fit them against a local
crown-radius sample before publishing a count** — this is the single biggest
accuracy lever in the whole workflow. The spec is validated on entry: gaps,
overlaps, and a closed top band (which would silently drop every tall tree) are
rejected before anything runs.

**Local maxima use `>=` against the focal maximum, not `==`.** The focal maximum
is never below the cell itself, so this is equality without depending on
float equality holding across two rasters.

**Plateaus are collapsed.** Flat crown tops produce clusters of tied maxima.
Region-grouping them and taking one interior point per region is worth 15–30%
of the count. (This is why tool 3 needs an Advanced license — `Feature To
Point`.)

**`Fill` is deliberately never run before `Flow Direction`.** The CHM is
inverted so treetops become basins; filling would erase exactly the features
being detected. This is the classic way this recipe fails.

**Crowns are clipped back to the canopy mask.** Watershed floods outward across
lawn and pavement to the raster edge. Without the clip, every tree gets a 30 m
crown.

**Seams are resolved by ownership, not proximity.** `canopy/tiling.py` gives
each tile a non-overlapping *core* and a buffered *halo*; a treetop is kept by
the one tile whose core contains it (half-open on the upper edges). That is
exact and has no distance threshold to tune, unlike a `Near`-and-delete pass.
Tiling matters: a city of ~33 km² is ~132 million cells at 0.5 m, and
`Watershed` on a single raster that size is not practical.

## Validating before you publish

The toolbox will not do this for you and the numbers are not publishable
without it.

1. Stratify the study area — street ROW, park, single-family, foothill.
2. Draw 60–100 random plots and count trees manually from imagery (field-check
   a subset).
3. Report **detection rate, commission, and omission per stratum**, not a
   single overall accuracy.
4. Use [i-Tree Canopy](https://canopy.itreetools.org/) as the independent check
   on percent cover. It is photo-interpreted point sampling with a real
   confidence interval and it is the accepted municipal standard.
5. Publish the count as an interval.

⚠️ **Check your flight date.** Leaf-off and shoulder-season acquisitions
under-detect and under-measure deciduous crowns badly. The Salt Lake County
2023 collection was flown 7 Oct – 5 Nov, which is partial leaf-off on the
Wasatch Front. It is not comparable to a summer flight, and change detection
against another acquisition is only valid if both are in the same phenological
state.

## Requirements

- ArcGIS Pro with an **Advanced** licence (tool 3 uses `Feature To Point`)
- **3D Analyst** — LAS dataset tools
- **Spatial Analyst** — Focal Statistics, Region Group, Flow Direction,
  Watershed, Zonal Statistics
- A classified LAS dataset (`.lasd`)

## Install

Copy this `canopy-toolbox/` folder anywhere, then add the toolbox in the
Catalog pane in ArcGIS Pro:

```
Catalog → Toolboxes → Add Toolbox → CanopyTools.pyt
```

`canopy/` must stay beside the `.pyt`; the toolbox adds its own folder to
`sys.path` and reloads the package on every run so edits take effect without
restarting Pro.

## Tests

The geometry and band logic are pure Python with no `arcpy` import, so they run
anywhere:

```bash
cd canopy-toolbox
python3 -m unittest discover -s tests -t .
```

31 tests, no dependencies.

⚠️ **The `arcpy` code paths have not been executed.** They were written on
macOS, where ArcGIS Pro does not run. Tool signatures and keyword arguments
follow the documented API, but the interpolation strings in
`canopy/rasters.py` are exposed as constants precisely because valid keyword
combinations drift between Pro releases — adjust them there rather than
assuming a failure is a logic bug. First run should be on a single small tile.

## Licence

Inherits the parent repository's licence.
