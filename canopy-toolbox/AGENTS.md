# canopy-toolbox — Agent Routing

ArcGIS Pro Python toolbox: classified lidar → canopy cover + individual trees.
Full rationale and caveats live in `README.md`. Keep this file under 60 lines.

## Working on X → read Y

| Working on | Read first |
|---|---|
| Band / window logic | `canopy/bands.py`, `tests/test_bands.py` |
| Tiling, seams | `canopy/tiling.py`, `tests/test_tiling.py` |
| CHM construction | `canopy/rasters.py`, README "Design decisions" |
| Detection | `canopy/treetops.py` |
| Crowns | `canopy/crowns.py` |
| Tool UI / parameters | `CanopyTools.pyt` |

## Non-negotiables

- `canopy/bands.py` and `canopy/tiling.py` **must not import arcpy.** They are
  the only testable surface outside ArcGIS Pro; keep new pure logic there.
- Never run `Fill` before `Flow Direction` in `crowns.py`. The sinks are the
  trees.
- Never drop the plateau collapse in `treetops.py`. Without it the count
  inflates 15–30%.
- Never reuse a delivered highest-hit DSM in place of the vegetation-only DSM.
- Tool 5 (canopy cover) must stay independent of tools 3 and 4. It is the
  defensible deliverable and cannot depend on detection.
- Detection output carries an estimate warning. Do not remove it.

## Verify

```bash
cd canopy-toolbox && python3 -m unittest discover -s tests -t .   # 31 tests
python3 -m py_compile canopy/*.py
```

`arcpy` paths cannot be verified off a Pro machine — see the README warning.
Changes to them need a real run on a single tile before they are trusted.
