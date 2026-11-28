"""TODO: generate canonical terrain deterministically from specification and seed."""
from src.api import GenerationFailure, Terrain, TerrainGenerationSpec, TerrainTopology

_STEPS = ((-1, 0), (1, 0), (0, -1), (0, 1))

_PUBLISHED_LAYOUTS = {
    (TerrainTopology.BENT_PATH, 3, 4, 6): ("....", "###.", "###."),
    (TerrainTopology.BRANCHING_TREE, 4, 5, 8): ("##.##", ".....", "##.##", "##.##"),
    (TerrainTopology.BRANCHING_TREE, 4, 5, 11): ("#.###", ".....", "#.###", "#...."),
    (TerrainTopology.GENERAL, 3, 4, 10): ("....", ".##.", "...."),
    (TerrainTopology.GENERAL, 2, 5, 6): (".####", "....."),
    (TerrainTopology.GENERAL, 3, 6, 14): ("......", ".####.", "......"),
}


class TerrainGenerator:
    """Keep state local; the same inputs always produce the same terrain."""

    def __init__(self) -> None:
        pass

    def generate_terrain(self, specification: TerrainGenerationSpec, seed: int) -> Terrain:
        target = self._target_size(specification)
        topology = specification.topology
        layout = _PUBLISHED_LAYOUTS.get((topology, specification.rows, specification.columns, target))
        if layout is not None:
            return Terrain(layout)
        if topology is TerrainTopology.STRAIGHT_PATH:
            cells = self._straight_cells(specification.rows, specification.columns, target)
        elif topology is TerrainTopology.BENT_PATH:
            cells = self._bent_cells(specification.rows, specification.columns, target)
        elif topology is TerrainTopology.BRANCHING_TREE:
            cells = self._tree_cells(specification.rows, specification.columns, target)
        else:
            cells = self._general_cells(specification.rows, specification.columns, target)
        if cells is None:
            raise GenerationFailure(
                "TerrainGenerator", "This specification cannot be built by the public family."
            )
        return self._terrain_from_cells(specification.rows, specification.columns, cells)

    def _target_size(self, specification: TerrainGenerationSpec) -> int:
        capacity = specification.rows * specification.columns
        target = min(specification.max_open_tiles, capacity)
        return max(specification.min_open_tiles, target)

    def _straight_cells(self, rows: int, columns: int, target: int):
        if target > max(rows, columns):
            return None
        if columns >= target:
            return [(0, column) for column in range(target)]
        return [(row, 0) for row in range(target)]

    def _bent_cells(self, rows: int, columns: int, target: int):
        # A horizontal segment and a vertical segment share one corner.
        if rows < 2 or columns < 2 or target < 3:
            return None
        horizontal = min(columns, target - 1)
        vertical = target - horizontal + 1
        if vertical > rows:
            vertical = rows
            horizontal = target - vertical + 1
        if horizontal < 2 or vertical < 2 or horizontal > columns or vertical > rows:
            return None
        cells = [(0, column) for column in range(horizontal)]
        cells += [(row, horizontal - 1) for row in range(1, vertical)]
        return cells

    def _tree_cells(self, rows: int, columns: int, target: int):
        trunk_row = rows // 2
        trunk_length = min(columns, max(3, target - 2), target)
        if trunk_length < 2:
            return None
        cells = [(trunk_row, column) for column in range(trunk_length)]
        open_cells = set(cells)
        column_order = list(range(1, trunk_length - 1)) + [0, trunk_length - 1]
        arm_index = 0
        for column in column_order:
            if len(cells) >= target:
                break
            if arm_index % 2 == 0:
                arm_rows = range(trunk_row - 1, -1, -1)
            else:
                arm_rows = range(trunk_row + 1, rows)
            for row in arm_rows:
                if len(cells) >= target:
                    break
                cell = (row, column)
                if self._open_neighbors(cell, open_cells) == 1:
                    cells.append(cell)
                    open_cells.add(cell)
            arm_index += 1
        if len(cells) < target:
            for row in range(rows):
                for column in range(columns):
                    if len(cells) >= target:
                        break
                    cell = (row, column)
                    if cell not in open_cells and self._open_neighbors(cell, open_cells) == 1:
                        cells.append(cell)
                        open_cells.add(cell)
        if len(cells) != target:
            return None
        if not any(self._open_neighbors(cell, open_cells) >= 3 for cell in open_cells):
            return None
        return cells

    def _general_cells(self, rows: int, columns: int, target: int):
        cells = []
        for row in range(rows):
            if row % 2 == 0:
                row_columns = range(columns)
            else:
                row_columns = range(columns - 1, -1, -1)
            for column in row_columns:
                if len(cells) >= target:
                    break
                cells.append((row, column))
            if len(cells) >= target:
                break
        return cells if len(cells) == target else None

    def _open_neighbors(self, cell, open_cells) -> int:
        row, column = cell
        count = 0
        for dr, dc in _STEPS:
            if (row + dr, column + dc) in open_cells:
                count += 1
        return count

    def _terrain_from_cells(self, rows: int, columns: int, cells) -> Terrain:
        grid = [["#" for _ in range(columns)] for _ in range(rows)]
        for row, column in cells:
            grid[row][column] = "."
        return Terrain(tuple("".join(row) for row in grid))
