"""Assign non-adjacent colors to polygons from a neighbor table.

This script is designed for ArcGIS Pro / ArcPy workflows, but the core coloring
logic also works as a pure-Python utility for local development and testing.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from typing import Dict, Iterable, List, Mapping, MutableMapping, Sequence, Set, Tuple

try:
    import arcpy  # type: ignore
except ImportError:  # pragma: no cover - optional dependency in non-ArcGIS environments
    arcpy = None

COLOR_SCHEMES: Dict[str, Sequence[str]] = {
    "default": ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"],
    "pastel": ["#a6cee3", "#b2df8a", "#fb9a99", "#fdbf6f", "#cab2d6", "#ffff99", "#1f78b4", "#33a02c"],
    "high-contrast": ["#000000", "#ffffff", "#ff0000", "#00ff00", "#0000ff", "#ff00ff", "#00ffff", "#ffff00"],
    "mono": ["#111111", "#444444", "#777777", "#aaaaaa", "#dddddd"],
}


def build_adjacency(neighbor_rows: Iterable[Tuple[int, int]]) -> Dict[int, Set[int]]:
    """Create an adjacency map from a neighbor-table-style row iterator."""
    adjacency: MutableMapping[int, Set[int]] = defaultdict(set)
    for src, nbr in neighbor_rows:
        adjacency[src].add(nbr)
        adjacency[nbr].add(src)
    return {polygon: set(neighbors) for polygon, neighbors in adjacency.items()}


def assign_polygon_colors(
    adjacency: Mapping[int, Iterable[int]],
    color_scheme: str = "default",
    max_colors: int | None = None,
) -> Dict[int, str]:
    """Apply a greedy graph-coloring pass and return a mapping of polygon IDs to colors."""
    normalized_adjacency = {polygon: set(neighbors) for polygon, neighbors in adjacency.items()}
    palette = list(COLOR_SCHEMES.get(color_scheme, COLOR_SCHEMES["default"]))
    if max_colors is not None:
        palette = palette[:max_colors]
    if not palette:
        raise ValueError("At least one color is required for coloring.")

    ordered_polygons = sorted(normalized_adjacency, key=lambda polygon: len(normalized_adjacency[polygon]), reverse=True)
    colors: Dict[int, str] = {}

    for polygon in ordered_polygons:
        used_colors = {colors[nbr] for nbr in normalized_adjacency[polygon] if nbr in colors}
        for color in palette:
            if color not in used_colors:
                colors[polygon] = color
                break
        else:
            raise ValueError(
                f"Unable to assign a color with scheme '{color_scheme}'. "
                "Try a larger palette or a different scheme."
            )

    return colors


def read_neighbor_rows(neighbor_table: str) -> List[Tuple[int, int]]:
    """Read neighbor rows from an ArcGIS table when ArcPy is available."""
    if arcpy is None:
        raise RuntimeError("ArcPy is required to read from a neighbor table.")

    with arcpy.da.SearchCursor(neighbor_table, ["src_OBJECTID", "nbr_OBJECTID"]) as cursor:
        return [(int(src), int(nbr)) for src, nbr in cursor]


def write_colors_to_layer(
    polygon_layer: str,
    polygon_ids: Iterable[int],
    colors: Mapping[int, str],
    color_field: str,
    id_field: str = "OBJECTID",
) -> None:
    """Write the assigned color values to an ArcGIS feature class or table."""
    if arcpy is None:
        raise RuntimeError("ArcPy is required to write colors to the polygon layer.")

    existing_fields = [field.name for field in arcpy.ListFields(polygon_layer)]
    if color_field in existing_fields:
        field_type = "TEXT"
    else:
        field_type = "TEXT" if any(isinstance(value, str) for value in colors.values()) else "SHORT"
        arcpy.AddField_management(polygon_layer, color_field, field_type, field_length=32)

    with arcpy.da.UpdateCursor(polygon_layer, [id_field, color_field]) as cursor:
        for oid, _ in cursor:
            cursor.updateRow([oid, colors.get(int(oid), next(iter(colors.values()), "#1f77b4"))])

    if color_field not in existing_fields:
        return

    with arcpy.da.UpdateCursor(polygon_layer, [id_field, color_field]) as cursor:
        for oid, _ in cursor:
            cursor.updateRow([oid, colors.get(int(oid), next(iter(colors.values()), "#1f77b4"))])


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the script."""
    parser = argparse.ArgumentParser(description="Assign colors to polygon neighbors with built-in palettes")
    parser.add_argument("polygon_layer", help="Path to the polygon feature class or layer")
    parser.add_argument("neighbor_table", help="Path to the polygon neighbor table")
    parser.add_argument("--color-field", default="Color_ID", help="Field name to store the color values")
    parser.add_argument("--id-field", default="OBJECTID", help="Object ID field name in the polygon layer")
    parser.add_argument("--color-scheme", default="default", choices=sorted(COLOR_SCHEMES), help="Color palette to use")
    parser.add_argument("--max-colors", type=int, default=None, help="Optional limit for the number of palette colors to use")
    parser.add_argument("--dry-run", action="store_true", help="Build the color map without writing to the layer")
    return parser.parse_args()


def main() -> None:
    """Run the CLI workflow."""
    args = parse_args()

    if arcpy is None:
        raise RuntimeError("ArcPy is required to run this workflow. Install ArcGIS Pro or use the core functions directly.")

    neighbor_rows = read_neighbor_rows(args.neighbor_table)
    adjacency = build_adjacency(neighbor_rows)
    colors = assign_polygon_colors(adjacency, color_scheme=args.color_scheme, max_colors=args.max_colors)

    if args.dry_run:
        print("Dry run complete. Color assignments:")
        for polygon_id, color in sorted(colors.items()):
            print(f"{polygon_id}: {color}")
        return

    polygon_ids = [row[0] for row in arcpy.da.SearchCursor(args.polygon_layer, [args.id_field])]
    for polygon_id in polygon_ids:
        if int(polygon_id) not in colors:
            colors[int(polygon_id)] = next(iter(colors.values()), "#1f77b4")

    write_colors_to_layer(args.polygon_layer, polygon_ids, colors, args.color_field, args.id_field)
    print(f"Color assignment complete using scheme '{args.color_scheme}'.")


if __name__ == "__main__":
    main()
