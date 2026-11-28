from collections import deque
from heapq import heappop, heappush

from src.api import WorldAction, WorldActionType

_MOVES = (
    (WorldActionType.MOVE_NORTH, -1, 0),
    (WorldActionType.MOVE_SOUTH, 1, 0),
    (WorldActionType.MOVE_WEST, 0, -1),
    (WorldActionType.MOVE_EAST, 0, 1),
)
_MOVE_DELTAS = {kind: (dr, dc) for kind, dr, dc in _MOVES}


class AgentController:
    def __init__(self) -> None:
        self._static_actions = []
        self._static_after = []
        self._static_start = None
        self._static_index = 0

    def choose_action(self, state, agent_id: str) -> WorldAction:
        position = (state.agent_position.row, state.agent_position.column)
        exit_cell = (state.exit_position.row, state.exit_position.column)

        if state.level.patrols:
            if position == exit_cell:
                return WorldAction(WorldActionType.EXIT)
            plan = self._patrol_plan(state)
            if plan:
                return plan[0]
        else:
            action = self._static_next(state)
            if action is not None:
                return action
        return self._fallback_action(state)

    def _cell(self, position):
        return (position.row, position.column)

    def _is_floor(self, terrain, cell):
        row, column = cell
        rows = terrain.terrain_rows
        return 0 <= row < len(rows) and 0 <= column < len(rows[0]) and rows[row][column] == "."

    def _patrol_schedules(self, state):
        schedules = {}
        for patrol in state.level.patrols:
            positions = [(point.row, point.column) for point in patrol.positions]
            schedules[patrol.enemy_id] = (positions, patrol.initial_phase)
        return schedules

    def _static_enemies(self, state, schedules):
        enemies = {}
        for enemy in state.level.enemies:
            if enemy.enemy_id not in schedules:
                enemies[enemy.enemy_id] = (enemy.position.row, enemy.position.column)
        return enemies

    def _patrol_positions(self, schedules, action_count):
        positions = set()
        for schedule, initial_phase in schedules.values():
            positions.add(schedule[(initial_phase + action_count) % len(schedule)])
        return positions

    def _survives(self, schedules, cell, next_count, deadline, cap):
        if next_count >= cap:
            return False
        if deadline is not None and next_count >= deadline:
            return False
        for schedule, initial_phase in schedules.values():
            if schedule[(initial_phase + next_count) % len(schedule)] == cell:
                return False
        return True

    def _rebuild(self, goal, parents):
        actions = []
        state = goal
        while parents[state] is not None:
            previous, action = parents[state]
            actions.append(action)
            state = previous
        actions.reverse()
        return actions

    def _static_next(self, state):
        here = (state.agent_position.row, state.agent_position.column)
        now = (here, state.turn, frozenset(state.collected_artifact_ids),
               frozenset(state.defeated_enemy_ids))
        if self._static_actions and self._static_index < len(self._static_actions):
            expected = (self._static_start if self._static_index == 0
                        else self._static_after[self._static_index - 1])
            if now == expected:
                action = self._static_actions[self._static_index]
                self._static_index += 1
                return action
            self._clear_static_plan()
        plan = self._static_plan(state)
        if not plan:
            return None
        self._install_static_plan(state, plan)
        action = self._static_actions[0]
        self._static_index = 1
        return action

    def _clear_static_plan(self):
        self._static_actions = []
        self._static_after = []
        self._static_start = None
        self._static_index = 0

    def _install_static_plan(self, state, plan):
        row = state.agent_position.row
        column = state.agent_position.column
        turn = state.turn
        collected = set(state.collected_artifact_ids)
        defeated = set(state.defeated_enemy_ids)
        after = []
        for action in plan:
            kind = action.action_type
            if kind in _MOVE_DELTAS:
                dr, dc = _MOVE_DELTAS[kind]
                row += dr
                column += dc
            elif kind is WorldActionType.COLLECT and action.target_id is not None:
                collected.add(action.target_id)
            elif kind is WorldActionType.ENGAGE and action.target_id is not None:
                defeated.add(action.target_id)
            turn += 1
            after.append(((row, column), turn, frozenset(collected), frozenset(defeated)))
        self._static_start = (
            (state.agent_position.row, state.agent_position.column), state.turn,
            frozenset(state.collected_artifact_ids), frozenset(state.defeated_enemy_ids),
        )
        self._static_actions = plan
        self._static_after = after
        self._static_index = 0

    def _static_plan(self, state):
        start = self._cell(state.agent_position)
        goal = self._cell(state.exit_position)
        allowed = set(state.allowed_actions)
        cap = state.max_turns
        schedules = self._patrol_schedules(state)
        enemies = {}
        for enemy in state.level.enemies:
            if enemy.enemy_id not in schedules:
                enemies[enemy.enemy_id] = (
                    (enemy.position.row, enemy.position.column),
                    enemy.encounter_penalty,
                )
        enemy_ids = sorted(enemies)
        enemy_bits = {enemy_id: 1 << index for index, enemy_id in enumerate(enemy_ids)}
        defeated_mask = sum(enemy_bits[enemy_id] for enemy_id in enemy_ids
                            if enemy_id in state.defeated_enemy_ids)

        artifacts = sorted(state.level.artifacts, key=lambda item: item.artifact_id)
        artifact_bits = {item.artifact_id: 1 << index for index, item in enumerate(artifacts)}
        artifacts_at = {}
        for item in artifacts:
            cell = (item.position.row, item.position.column)
            artifacts_at.setdefault(cell, []).append(item)
        artifact_mask = sum(artifact_bits[item.artifact_id] for item in artifacts
                            if item.artifact_id in state.collected_artifact_ids)

        start_state = (start[0], start[1], artifact_mask, defeated_mask)
        distances = {start_state: (0, 0)}
        parents = {start_state: None}
        heap = [(0, 0, 0, start_state)]
        sequence = 0
        best = None

        def relax(node, child, action, new_cost, new_turns):
            nonlocal sequence
            old = distances.get(child)
            if old is None or (new_cost, new_turns) < old:
                distances[child] = (new_cost, new_turns)
                parents[child] = (node, action)
                sequence += 1
                heappush(heap, (new_cost, new_turns, sequence, child))

        def consider(node, cost, turns, mask):
            nonlocal best
            total_cost = cost + 1
            total_turns = turns + 1
            reward = sum(item.value for item in artifacts
                         if mask & artifact_bits[item.artifact_id])
            excess = max(0, total_cost - state.baseline_cost)
            score = (0 if excess >= state.zero_score_excess else
                     max(0, state.base_points + reward - state.deduction_rate * excess))
            actions = self._rebuild(node, parents) + [
                WorldAction(WorldActionType.EXIT)
            ]
            key = (-score, total_cost, total_turns, mask, node[3],
                   tuple((step.action_type.value, step.target_id or "") for step in actions))
            if best is None or key < best[0]:
                best = (key, actions)

        while heap:
            cost, turns, _, node = heappop(heap)
            if distances.get(node) != (cost, turns):
                continue
            row, column, collected_mask, beaten_mask = node
            if ((row, column) == goal and WorldActionType.EXIT in allowed
                    and turns + 1 <= cap):
                consider(node, cost, turns, collected_mask)

            next_turns = turns + 1
            if next_turns >= cap:
                continue

            for action_type, dr, dc in _MOVES:
                if action_type not in allowed:
                    continue
                destination = (row + dr, column + dc)
                if not self._is_floor(state.terrain, destination):
                    continue
                if any(not beaten_mask & enemy_bits[enemy_id] and point == destination
                       for enemy_id, (point, _penalty) in enemies.items()):
                    continue
                child = (destination[0], destination[1], collected_mask, beaten_mask)
                relax(node, child, WorldAction(action_type), cost + 1, next_turns)

            if WorldActionType.COLLECT in allowed:
                for item in artifacts_at.get((row, column), ()):
                    bit = artifact_bits[item.artifact_id]
                    if collected_mask & bit:
                        continue
                    child = (row, column, collected_mask | bit, beaten_mask)
                    relax(node, child, WorldAction(WorldActionType.COLLECT,
                                                   target_id=item.artifact_id),
                          cost + 1, next_turns)

            if WorldActionType.ENGAGE in allowed:
                for enemy_id in enemy_ids:
                    if beaten_mask & enemy_bits[enemy_id]:
                        continue
                    point, penalty = enemies[enemy_id]
                    if abs(point[0] - row) + abs(point[1] - column) != 1:
                        continue
                    child = (row, column, collected_mask,
                             beaten_mask | enemy_bits[enemy_id])
                    relax(node, child, WorldAction(WorldActionType.ENGAGE,
                                                   target_id=enemy_id),
                          cost + 1 + penalty, next_turns)

        if best is not None:
            return best[1]
        return self._shortest_static_plan(state)

    def _shortest_static_plan(self, state):
        start = self._cell(state.agent_position)
        goal = self._cell(state.exit_position)
        allowed = set(state.allowed_actions)
        enemies = self._static_enemies(state, {})
        defeated = frozenset(state.defeated_enemy_ids)
        start_state = (start[0], start[1], defeated)
        parents = {start_state: None}
        queue = deque([start_state])

        while queue:
            node = queue.popleft()
            row, column, defeated_now = node
            if (row, column) == goal:
                return self._rebuild(node, parents)

            for action_type, dr, dc in _MOVES:
                if action_type not in allowed:
                    continue
                destination = (row + dr, column + dc)
                if not self._is_floor(state.terrain, destination):
                    continue
                if any(enemy_id not in defeated_now and point == destination
                       for enemy_id, point in enemies.items()):
                    continue
                child = (destination[0], destination[1], defeated_now)
                if child not in parents:
                    parents[child] = (node, WorldAction(action_type))
                    queue.append(child)

            if WorldActionType.ENGAGE in allowed:
                for enemy_id in sorted(enemies):
                    if enemy_id in defeated_now:
                        continue
                    point = enemies[enemy_id]
                    if abs(point[0] - row) + abs(point[1] - column) != 1:
                        continue
                    child = (row, column, frozenset(defeated_now | {enemy_id}))
                    if child not in parents:
                        parents[child] = (
                            node,
                            WorldAction(WorldActionType.ENGAGE, target_id=enemy_id),
                        )
                        queue.append(child)
        return []

    def _patrol_plan(self, state):
        start = self._cell(state.agent_position)
        goal = self._cell(state.exit_position)
        allowed = set(state.allowed_actions)
        schedules = self._patrol_schedules(state)
        enemies = self._static_enemies(state, schedules)
        defeated = frozenset(state.defeated_enemy_ids)
        deadline = state.deadline_turn
        cap = state.max_turns
        start_state = (start[0], start[1], defeated, state.turn)
        parents = {start_state: None}
        queue = deque([start_state])

        while queue:
            node = queue.popleft()
            row, column, defeated_now, action_count = node
            if (row, column) == goal:
                return self._rebuild(node, parents)

            next_count = action_count + 1
            occupied = self._patrol_positions(schedules, action_count)
            for enemy_id, point in enemies.items():
                if enemy_id not in defeated_now:
                    occupied.add(point)

            for action_type, dr, dc in _MOVES:
                if action_type not in allowed:
                    continue
                destination = (row + dr, column + dc)
                if not self._is_floor(state.terrain, destination):
                    continue
                if destination in occupied:
                    continue
                if not self._survives(schedules, destination, next_count, deadline, cap):
                    continue
                child = (destination[0], destination[1], defeated_now, next_count)
                if child not in parents:
                    parents[child] = (node, WorldAction(action_type))
                    queue.append(child)

            if WorldActionType.ENGAGE in allowed:
                for enemy_id in sorted(enemies):
                    if enemy_id in defeated_now:
                        continue
                    point = enemies[enemy_id]
                    if abs(point[0] - row) + abs(point[1] - column) != 1:
                        continue
                    if not self._survives(schedules, (row, column), next_count, deadline, cap):
                        continue
                    child = (row, column, frozenset(defeated_now | {enemy_id}), next_count)
                    if child not in parents:
                        parents[child] = (
                            node,
                            WorldAction(WorldActionType.ENGAGE, target_id=enemy_id),
                        )
                        queue.append(child)

            if WorldActionType.WAIT in allowed:
                if self._survives(schedules, (row, column), next_count, deadline, cap):
                    child = (row, column, defeated_now, next_count)
                    if child not in parents:
                        parents[child] = (node, WorldAction.wait())
                        queue.append(child)
        return []

    def _fallback_action(self, state):
        if state.agent_position == state.exit_position:
            return WorldAction(WorldActionType.EXIT)
        position = self._cell(state.agent_position)
        allowed = set(state.allowed_actions)
        schedules = self._patrol_schedules(state)
        enemies = self._static_enemies(state, schedules)
        defeated = set(state.defeated_enemy_ids)
        occupied = self._patrol_positions(schedules, state.turn)
        for enemy_id, point in enemies.items():
            if enemy_id not in defeated:
                occupied.add(point)

        for action_type, dr, dc in _MOVES:
            if action_type not in allowed:
                continue
            destination = (position[0] + dr, position[1] + dc)
            if not self._is_floor(state.terrain, destination) or destination in occupied:
                continue
            if not schedules or self._survives(
                schedules, destination, state.turn + 1, state.deadline_turn, state.max_turns
            ):
                return WorldAction(action_type)

        if WorldActionType.ENGAGE in allowed:
            for enemy_id in sorted(enemies):
                if enemy_id in defeated:
                    continue
                point = enemies[enemy_id]
                if abs(point[0] - position[0]) + abs(point[1] - position[1]) == 1:
                    return WorldAction(WorldActionType.ENGAGE, target_id=enemy_id)

        if WorldActionType.WAIT in allowed:
            return WorldAction.wait()
        return WorldAction(WorldActionType.MOVE_NORTH)
