
"""Artifact stores the initial data of one collectible reward."""

from src.api import ArtifactDefinition, Position


class Artifact:
    """Expose read-only canonical identity, position, and nonnegative value."""

    def __init__(self, artifact_id: str, position: Position, value: int) -> None:
        validated = ArtifactDefinition(artifact_id, position, value)

        self._artifact_id = validated.artifact_id
        self._position = Position(
            validated.position.row,
            validated.position.column
        )
        self._value = validated.value

    @property
    def artifact_id(self) -> str:
        return self._artifact_id

    @property
    def position(self) -> Position:
        return Position(self._position.row, self._position.column)

    @property
    def value(self) -> int:
        return self._value
