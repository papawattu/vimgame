from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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
        self.base_difficulty = (
            config.get("base_difficulty", "beginner") if config else "beginner"
        )
        self.max_difficulty = (
            config.get("max_difficulty", "expert") if config else "expert"
        )


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
    ) -> None:
        super().__init__()
        self.player_state = player_state
        self.player_exp = player_exp
        if config:
            self.config = config
        else:
            self.config = GameConfig({'base_difficulty': '1', 'max_difficulty': '5'})
        self.progression = ProgressionLogic(
            self.config.base_difficulty, self.config.max_difficulty
        )
        self.state = GameState()

    def generate_sequence(self, progress: float) -> List[Any]:
        sequence_length = 3 + int(progress * 2)
        return [f"motion_{i}" for i in range(sequence_length)]

    def handle_input(self, input: str) -> bool:
        if not self.state.sequence:
            return False
        if input == str(self.state.sequence[0]):
            self.state.sequence.pop(0)
            self.player_state.update_score(10)
            self.player_exp.add_experience(5)
            self.player_exp.update_player_level()
            return True
        else:
            self.player_state.update_score(-5)
            return False

    def update_game_state(self, input: str) -> None:
        if input == "invalid":
            self.player_state.update_score(-10)
            self.player_exp.add_experience(-2)
        else:
            if self.handle_input(input):
                self.state.current_level += 1
                self.state.sequence = self.generate_sequence(self.state.current_level)
        self._check_game_over()

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
