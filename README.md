# agol-python-scripts

Small, standalone Python utilities for ArcGIS Online and ArcGIS Pro. Each
script is self-contained; there is no package to install.

| Script | What it does | Runs with |
|---|---|---|
| `assign_polygon_colors.py` | Assigns a `colorID` to polygons so no two adjacent polygons share a value (greedy graph coloring over a Polygon Neighbors table) — for cartography where touching parcels or zones need distinct fills. Set the two path variables at the top before running. | ArcGIS Pro's Python (`arcpy`) |
| `add_badelf_fields_to_agol.py` | Adds the Bad Elf Flex (2025) GNSS metadata fields and coded-value domains to a hosted feature layer, so surveyed points keep correction type, geoid model, antenna height, and final heights. Idempotent — existing fields are skipped. | ArcGIS API for Python (`arcgis`) |

## Environment

For `add_badelf_fields_to_agol.py`, any Python ≥ 3.10 with `arcgis` — for
example the `arcgis-online` pixi environment (`pixi shell` in its folder), or
`pip install arcgis`.

## Usage

```bash
python add_badelf_fields_to_agol.py --url https://myorg.maps.arcgis.com --item <item-id> --username <user>
```

The password is prompted for. Use `--layer N` when the item has more than one
sublayer. `--password` exists for automation only — prefer the prompt so the
password never lands in shell history.

## History

Started as `colorID.py` (the polygon coloring script alone); renamed
2026-09-07 when the Bad Elf script joined it.
