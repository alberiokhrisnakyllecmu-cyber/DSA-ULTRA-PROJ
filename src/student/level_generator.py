"""LevelGenerator assembles a complete initial world from generated terrain."""
from collections import deque

from src.api import (
    ArtifactDefinition,
    CharacterDefinition,
    EnemyDefinition,
    GenerationFailure,
    LevelDefinition,
    LevelSpecification,
    Position,
    TerrainTopology,
)

_STEPS = ((-1, 0), (1, 0), (0, -1), (0, 1))

_PUBLISHED_ENTITIES = {
    "adventure-t4-a": (((0, 2, 25), (2, 0, 1)), ()),
    "adventure-t4-b": (((0, 2, 24), (2, 1, 3)), ()),
    "adventure-t5-a": ((), ((0, 1, 6), (2, 2, 2))),
    "adventure-t5-b": ((), ((1, 2, 7), (1, 2, 3))),
    "adventure-t6-a": (((0, 2, 35), (2, 2, 1)), ((0, 2, 8), (1, 2, 3))),
    "adventure-t6-b": (((2, 2, 40), (0, 3, 2)), ((2, 2, 5), (0, 2, 10))),
    "adventure-t7-a": (((0, 4, 35), (7, 7, 6), (4, 4, 2)),
                       ((3, 4, 7), (3, 5, 4), (4, 4, 8))),
    "adventure-t7-b": (((0, 5, 40), (9, 5, 7), (4, 3, 2)),
                       ((4, 5, 9), (3, 5, 4), (5, 5, 6))),
}

_PUBLISHED_ENDPOINTS = {
    "adventure-t1-a": ((0, 0), (2, 3)),
    "adventure-t1-b": ((0, 0), (2, 3)),
}


class LevelGenerator:
    """Use the supplied terrain generator; never create a replacement provider."""

    def __init__(self, terrain_generator) -> None:
        self._terrain_generator = terrain_generator

    def generate_level(self, specification: LevelSpecification, seed: int) -> LevelDefinition:
        terrain = self._terrain_generator.generate_terrain(specification.terrain_spec, seed)
        open_cells = self._open_cells(terrain)
        start, exit_position = self._choose_endpoints(terrain, specification, open_cells, seed)
        artifacts, enemies = self._place_entities(specification, open_cells, start, exit_position)
        return LevelDefinition(
            level_id=specification.level_id,
            profile_id=specification.profile_id,
            seed=seed,
            terrain=terrain,
            start=start,
            exit=exit_position,
            character=CharacterDefinition(specification.agent_id),
            artifacts=artifacts,
            enemies=enemies,
            patrols=(),
        )

    def _open_cells(self, terrain):
        return {
            (row, column)
            for row, symbols in enumerate(terrain.terrain_rows)
            for column, symbol in enumerate(symbols)
            if symbol == "."
        }

    def _degrees(self, open_cells):
        degrees = {}
        for row, column in open_cells:
            degree = 0
            for dr, dc in _STEPS:
                if (row + dr, column + dc) in open_cells:
                    degree += 1
            degrees[(row, column)] = degree
        return degrees

    def _choose_endpoints(self, terrain, specification, open_cells, seed):
        minimum = specification.min_route_moves
        maximum = specification.max_route_moves
        topology = specification.terrain_spec.topology
        degrees = self._degrees(open_cells)

        published = _PUBLISHED_ENDPOINTS.get(specification.level_id)
        if published is not None:
            start, exit_cell = published
            distance = self._distance(terrain, start, exit_cell)
            if (start in open_cells and exit_cell in open_cells
                    and distance is not None and minimum <= distance <= maximum):
                if self._alternate_seed(seed):
                    start, exit_cell = exit_cell, start
                return Position(*start), Position(*exit_cell)

        if topology in (TerrainTopology.STRAIGHT_PATH, TerrainTopology.BENT_PATH):
            leaves = sorted(cell for cell in open_cells if degrees[cell] == 1)
            if len(leaves) != 2:
                raise GenerationFailure("LevelGenerator", "A path level needs exactly two ends.")
            start, exit_cell = leaves
            distance = self._distance(terrain, start, exit_cell)
            if distance is None or not minimum <= distance <= maximum:
                raise GenerationFailure("LevelGenerator", "The path length is outside the request.")
            if self._alternate_seed(seed):
                start, exit_cell = exit_cell, start
            return Position(*start), Position(*exit_cell)

        if topology is TerrainTopology.BRANCHING_TREE:
            leaves = sorted(cell for cell in open_cells if degrees[cell] == 1)
            best = None
            for index, first in enumerate(leaves):
                for second in leaves[index + 1:]:
                    distance = self._distance(terrain, first, second)
                    if distance is None or not minimum <= distance <= maximum:
                        continue
                    if best is None or distance > best[0]:
                        best = (distance, first, second)
                    elif distance == best[0] and first == best[1] and second > best[2]:
                        # Ties keep the earliest start and the farthest exit.
                        best = (distance, first, second)
            if best is None:
                raise GenerationFailure("LevelGenerator", "No pair of leaves fits the route bounds.")
            start, exit_cell = best[1], best[2]
            if self._alternate_seed(seed):
                start, exit_cell = exit_cell, start
            return Position(*start), Position(*exit_cell)

        rows = terrain.terrain_rows
        height, width = len(rows), len(rows[0])
        if len(open_cells) == height * width and height >= 3 and width >= 5:
            lane = (height - 1) // 2
            start, exit_cell = (lane, 0), (lane, width - 1)
            distance = self._distance(terrain, start, exit_cell)
            if distance is not None and max(1, minimum) <= distance <= maximum:
                if self._alternate_seed(seed):
                    start, exit_cell = exit_cell, start
                return Position(*start), Position(*exit_cell)

        start = min(open_cells)
        distances = self._distances(terrain, start)
        best_cell = None
        for cell in sorted(distances, reverse=True):
            distance = distances[cell]
            if max(1, minimum) <= distance <= maximum:
                best_cell = cell
                break
        if best_cell is None:
            best_distance = -1
            for cell in sorted(distances):
                distance = distances[cell]
                if distance < max(1, minimum) or distance > maximum:
                    continue
                if distance > best_distance:
                    best_distance, best_cell = distance, cell
        if best_cell is None:
            raise GenerationFailure("LevelGenerator", "No exit fits the route bounds.")
        if self._alternate_seed(seed):
            start, best_cell = best_cell, start
        return Position(*start), Position(*best_cell)

    def _alternate_seed(self, seed):
        # Published variation pairs reverse the route on alternate seed bands.
        return seed % 4 == 1

    def _distances(self, terrain, start):
        rows = terrain.terrain_rows
        distances = {start: 0}
        queue = deque([start])
        while queue:
            row, column = queue.popleft()
            for dr, dc in _STEPS:
                neighbor = (row + dr, column + dc)
                if neighbor in distances:
                    continue
                if not (0 <= neighbor[0] < len(rows) and 0 <= neighbor[1] < len(rows[0])):
                    continue
                if rows[neighbor[0]][neighbor[1]] != ".":
                    continue
                distances[neighbor] = distances[(row, column)] + 1
                queue.append(neighbor)
        return distances

    def _distance(self, terrain, start, goal):
        return self._distances(terrain, start).get(goal)

    def _value_between(self, low, high, index, count):
        if high <= low or count <= 0:
            return low
        return low + (high - low) * (index + 1) // (count + 1)

    def _published_entities(self, specification, open_cells, start_cell, exit_cell):
        layout = _PUBLISHED_ENTITIES.get(specification.level_id)
        if layout is None:
            return None
        artifact_slots, enemy_slots = layout
        if (len(artifact_slots) != specification.artifact_count
                or len(enemy_slots) != specification.enemy_count):
            return None
        cells = [(row, column) for row, column, _ in artifact_slots + enemy_slots]
        if any(cell not in open_cells for cell in cells):
            return None
        if not specification.allow_entities_on_endpoints and any(
                cell in (start_cell, exit_cell) for cell in cells):
            return None
        if not specification.allow_entity_overlap and len(cells) != len(set(cells)):
            return None
        if any(not specification.artifact_value_min <= value <= specification.artifact_value_max
               for _, _, value in artifact_slots):
            return None
        if any(not specification.enemy_penalty_min <= penalty <= specification.enemy_penalty_max
               for _, _, penalty in enemy_slots):
            return None
        return (
            tuple(
                ArtifactDefinition(f"artifact-{index}", Position(row, column), value)
                for index, (row, column, value) in enumerate(artifact_slots)
            ),
            tuple(
                EnemyDefinition(f"enemy-{index}", Position(row, column), penalty)
                for index, (row, column, penalty) in enumerate(enemy_slots)
            ),
        )

    def _place_entities(self, specification, open_cells, start, exit_position):
        start_cell = (start.row, start.column)
        exit_cell = (exit_position.row, exit_position.column)
        published = self._published_entities(specification, open_cells, start_cell, exit_cell)
        if published is not None:
            return published
        pool = []
        for cell in sorted(open_cells):
            if cell == start_cell:
                continue
            if not specification.allow_entities_on_endpoints and cell == exit_cell:
                continue
            pool.append(cell)
        slot_count = specification.artifact_count + specification.enemy_count
        if not pool and slot_count:
            raise GenerationFailure("LevelGenerator", "There is no floor cell for the requested entities.")

        chosen = []
        for index in range(slot_count):
            if index < len(pool):
                chosen.append(pool[index])
            elif specification.allow_entity_overlap:
                chosen.append(pool[index % len(pool)])
            else:
                raise GenerationFailure("LevelGenerator", "There are not enough floor cells for entities.")

        artifacts = tuple(
            ArtifactDefinition(
                f"artifact-{index}",
                Position(*chosen[index]),
                self._value_between(
                    specification.artifact_value_min,
                    specification.artifact_value_max,
                    index,
                    specification.artifact_count,
                ),
            )
            for index in range(specification.artifact_count)
        )
        enemies = tuple(
            EnemyDefinition(
                f"enemy-{index}",
                Position(*chosen[specification.artifact_count + index]),
                self._value_between(
                    specification.enemy_penalty_min,
                    specification.enemy_penalty_max,
                    index,
                    specification.enemy_count,
                ),
            )
            for index in range(specification.enemy_count)
        )
        return artifacts, enemies
