"""Tile grid and seam reconciliation.

Watershed on a 130-million-cell raster is not practical, so the study area is
processed in buffered tiles. Every tile owns a *core* extent and is processed
over a larger *buffered* extent, so trees near a seam are delineated with full
neighbourhood context.

Duplicates are then resolved by ownership, not by proximity: a treetop is kept
by exactly one tile -- the one whose core extent contains it. That is exact and
has no distance threshold to tune, unlike a Near-and-delete pass.

Pure Python: no arcpy, so it is unit-testable outside ArcGIS Pro.
"""

from __future__ import annotations

import math
from typing import Iterable, Iterator, NamedTuple


class Extent(NamedTuple):
    xmin: float
    ymin: float
    xmax: float
    ymax: float

    @property
    def width(self) -> float:
        return self.xmax - self.xmin

    @property
    def height(self) -> float:
        return self.ymax - self.ymin

    def buffered(self, distance: float) -> "Extent":
        return Extent(
            self.xmin - distance,
            self.ymin - distance,
            self.xmax + distance,
            self.ymax + distance,
        )

    def clipped_to(self, other: "Extent") -> "Extent":
        return Extent(
            max(self.xmin, other.xmin),
            max(self.ymin, other.ymin),
            min(self.xmax, other.xmax),
            min(self.ymax, other.ymax),
        )

    def as_arcpy_string(self) -> str:
        return f"{self.xmin} {self.ymin} {self.xmax} {self.ymax}"


class Tile(NamedTuple):
    row: int
    col: int
    core: Extent
    buffered: Extent

    @property
    def name(self) -> str:
        return f"r{self.row:03d}c{self.col:03d}"

    def owns(self, x: float, y: float) -> bool:
        """Half-open on the upper edges so adjacent cores never both claim a point."""
        return (
            self.core.xmin <= x < self.core.xmax
            and self.core.ymin <= y < self.core.ymax
        )


def snap_extent(extent: Extent, cell_size: float, origin: tuple[float, float] | None = None) -> Extent:
    """Grow an extent outward to whole cells on a shared grid origin.

    Every tile must land on the same grid as the CHM. A half-cell offset between
    the DSM and DTM puts a rim of false height around every crown edge, and those
    rims become treetops.
    """
    if cell_size <= 0:
        raise ValueError("cell size must be positive")
    ox, oy = origin or (0.0, 0.0)
    return Extent(
        ox + math.floor((extent.xmin - ox) / cell_size) * cell_size,
        oy + math.floor((extent.ymin - oy) / cell_size) * cell_size,
        ox + math.ceil((extent.xmax - ox) / cell_size) * cell_size,
        oy + math.ceil((extent.ymax - oy) / cell_size) * cell_size,
    )


def tile_grid(
    extent: Extent,
    tile_size: float,
    overlap: float,
    cell_size: float = 0.5,
) -> list[Tile]:
    """Cover `extent` with snapped, non-overlapping cores plus buffered halos."""
    if tile_size <= 0:
        raise ValueError("tile size must be positive")
    if overlap < 0:
        raise ValueError("overlap cannot be negative")
    if overlap >= tile_size / 2:
        raise ValueError("overlap must be smaller than half the tile size")

    grid = snap_extent(extent, cell_size)
    n_cols = max(1, math.ceil(grid.width / tile_size))
    n_rows = max(1, math.ceil(grid.height / tile_size))

    tiles: list[Tile] = []
    for row in range(n_rows):
        for col in range(n_cols):
            core = Extent(
                grid.xmin + col * tile_size,
                grid.ymin + row * tile_size,
                min(grid.xmin + (col + 1) * tile_size, grid.xmax),
                min(grid.ymin + (row + 1) * tile_size, grid.ymax),
            )
            if core.width <= 0 or core.height <= 0:
                continue
            tiles.append(Tile(row, col, core, core.buffered(overlap)))
    return tiles


def owning_tile(tiles: Iterable[Tile], x: float, y: float) -> Tile | None:
    for tile in tiles:
        if tile.owns(x, y):
            return tile
    return None


def dedupe_by_core(
    detections: Iterable[tuple[float, float, object]],
    tile: Tile,
) -> Iterator[tuple[float, float, object]]:
    """Keep only the detections this tile owns. Run per tile before merging."""
    for x, y, payload in detections:
        if tile.owns(x, y):
            yield x, y, payload


def recommended_overlap(bands: Iterable[object], minimum: float = 15.0) -> float:
    """Halo wide enough that the largest search window fits inside it.

    Defaults to 15 m, which comfortably exceeds any urban crown radius; the
    cost of a too-large halo is compute, the cost of a too-small one is split
    crowns at every seam.
    """
    radii = [getattr(band, "radius", 0.0) for band in bands]
    return max(minimum, (max(radii) if radii else 0.0) * 6.0)
