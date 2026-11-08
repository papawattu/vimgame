from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from src.player.state import PlayerState
from src.player.exp import PlayerExperience

from src.core.progression import ProgressionLogic
from src.core.config import load_config
from src.core.exceptions import GameOver, GameWon


class BaseGameConfig:
    def __init__(self) -> None:
        pass


class GameConfig(BaseGameConfig):
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__()
        config = config or {}
        # Difficulty keys must exist in ProgressionLogic.DIFFICULTY_LEVELS.
        self.base_difficulty = config.get("base_difficulty", "1")
        self.max_difficulty = config.get("max_difficulty", "5")
        self.points_correct = config.get("points_correct", 10)
        self.points_wrong = config.get("points_wrong", -5)
        self.points_invalid = config.get("points_invalid", -10)
        self.xp_correct = config.get("xp_correct", 5)
        self.xp_invalid = config.get("xp_invalid", -2)


@dataclass
class GameState:
    sequence: List[Any] = field(default_factory=list)
    current_level: int = 0


class BaseGameEngine:
    def __init__(self) -> None:
        pass


class GameEngine(BaseGameEngine):
    def __init__(
        self,
        player_state: PlayerState,
        player_exp: PlayerExperience,
        config: Optional[GameConfig] = None,
        sequence_factory: Optional[Callable[[int], List[Any]]] = None,
    ) -> None:
        super().__init__()
        self.player_state = player_state
        self.player_exp = player_exp
        self.config = config if isinstance(config, GameConfig) else GameConfig()
        # Supplies the items for each level: called with the number of items wanted.
        self.sequence_factory = sequence_factory
        self.progression = ProgressionLogic(
            self.config.base_difficulty, self.config.max_difficulty
        )
        self.state = GameState()

    @property
    def current(self) -> Any:
        """The item the player has to clear next, or None."""
        return self.state.sequence[0] if self.state.sequence else None

    @property
    def difficulty(self) -> Dict[str, int]:
        return self.progression.get_current_difficulty_params()

    def start(self) -> None:
        self.state.current_level = 1
        self.state.sequence = self.generate_sequence(self.state.current_level)

    def generate_sequence(self, progress: float) -> List[Any]:
        if self.sequence_factory is None:
            sequence_length = 3 + int(progress * 2)
            return [f"motion_{i}" for i in range(sequence_length)]
        return list(self.sequence_factory(self.difficulty["moves"]))

    def handle_input(self, input: str) -> bool:
        if not self.state.sequence:
            return False
        expected = self.state.sequence[0]
        if input == expected or input == str(expected):
            self.state.sequence.pop(0)
            self.player_state.update_score(self.config.points_correct)
            self.player_exp.add_experience(self.config.xp_correct)
            self.player_exp.update_player_level()
            return True
        else:
            self.player_state.update_score(self.config.points_wrong)
            return False

    def update_game_state(self, input: str) -> str:
        """Apply one input. Returns "correct", "wrong", "invalid" or "level_complete".

        Raises GameOver / GameWon when the score crosses a limit.
        """
        if input == "invalid":
            self.player_state.update_score(self.config.points_invalid)
            self.player_exp.add_experience(self.config.xp_invalid)
            status = "invalid"
        elif self.handle_input(input):
            status = "correct"
            if not self.state.sequence:
                self.state.current_level += 1
                self.state.sequence = self.generate_sequence(self.state.current_level)
                status = "level_complete"
        else:
            status = "wrong"
        self._check_game_over()
        return status

    def _check_game_over(self) -> None:
        if self.player_state.score <= 0:
            raise GameOver("Game over: Your score has dropped to zero.")
        elif self.player_state.level >= 10:
            raise GameWon("Congratulations! You've reached level 10 and won the game!")

    def track_performance(self, time: float, accuracy: float) -> float:
        performance = (1.0 - time / 10.0) * accuracy
        self.player_state.update_accuracy(performance)

        self.progression.update_progress(
            {"time": time, "accuracy": accuracy, "performance": performance}
        )

        return performance
