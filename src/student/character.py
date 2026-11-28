"""Character stores the explorer's read-only public identity."""
from src.api import CharacterDefinition


class Character:
    """Character(agent_id); expose a read-only str agent_id property."""

    def __init__(self, agent_id: str) -> None:
        validated = CharacterDefinition(agent_id)
        self._agent_id = validated.agent_id

    @property
    def agent_id(self) -> str:
        return self._agent_id
