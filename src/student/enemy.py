"""TODO: implement initial enemy data; introductory gameplay has no enemies."""
from src.api import EnemyDefinition, Position


class Enemy:
    """Expose read-only identity, position, and nonnegative encounter penalty."""

    def __init__(self, enemy_id, position, encounter_penalty) -> None:
        validated = EnemyDefinition(enemy_id, position, encounter_penalty)
        self._enemy_id = validated.enemy_id
        self._position = Position(validated.position.row, validated.position.column)
        self._encounter_penalty = validated.encounter_penalty
        raise NotImplementedError("TODO Enemy: implement constructor and properties")

    @property
    def enemy_id(self) -> str:
        return self._enemy_id
    #raise NotImplementedError("TODO Enemy.enemy_id")

    @property
    def position(self) -> Position:
        return self._position
    #raise NotImplementedError("TODO Enemy.position")

    @property
    def encounter_penalty(self) -> int:
        return self._encounter_penalty
    #raise NotImplementedError("TODO Enemy.encounter_penalty")
