from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from src.player.state import PlayerState
from src.player.exp import PlayerExperience


from src.core.progression import ProgressionLogic

from src.core.config import load_config
from src.core.exceptions import GameOver, GameWon


class BaseGameConfig:
    def __init__(self):
        pass

class GameConfig(BaseGameConfig):
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.base_difficulty = config.get('base_difficulty', 'beginner') if config else 'beginner'
        self.max_difficulty = config.get('max_difficulty', 'expert') if config else 'expert'


from dataclasses import field

@dataclass
class GameState:
    sequence: List[Any] = field(default_factory=list)
    current_level: int = 0


class BaseGameEngine:
    def __init__(self):
        pass

class GameEngine(BaseGameEngine):
    def initialize(self, player_state: PlayerState, player_exp: PlayerExperience, config: GameConfig = GameConfig()) -> None:
        super().__init__()
        self.player_state = player_state
        self.player_exp = player_exp
        self.config = config
        self.progression = ProgressionLogic(config.base_difficulty, config.max_difficulty)
        self.state = GameState()
    def __init__(self, player_state: PlayerState, player_exp: PlayerExperience, motions: List[Any]):
        self.player_state = player_state
        self.player_exp = player_exp
        self.motions = motions
        self.current_level = 0
        self.sequence: List[Any] = []

    def generate_sequence(self, progress: float) -> List[Any]:
        # Generate sequence based on current difficulty level
        sequence_length = 3 + int(progress * 2)
        return [f"motion_{i}" for i in range(sequence_length)]

    def handle_input(self, input: str) -> bool:
        # Check if the input matches the current sequence
        if not self.sequence:
            return False
        if input == str(self.sequence[0]):
            self.sequence.pop(0)
            self.player_state.update_score(10)
            self.player_exp.add_experience(5)
            return True
        else:
            self.player_state.update_score(-5)
            return False

    def update_game_state(self, input: str) -> None:
        if input == 'invalid':
            self.player_state.update_score(-10)
            self.player_exp.add_experience(-2)
        else:
            if self.handle_input(input):
                self.current_level += 1
                self.sequence = self.generate_sequence(self.current_level)
            else:
                self._check_game_over()

    def _check_game_over(self) -> None:
        if self.player_state.score <= 0:
            raise GameOver("Game over: Your score has dropped to zero.")
        elif self.player_state.level >= 10:
            raise GameWon("Congratulations! You've reached level 10 and won the game!")

    def track_performance(self, time: float, accuracy: float) -> float:
        # Calculate performance based on time and accuracy
        performance = (1.0 - time / 10.0) * accuracy
        self.player_state.update_accuracy(performance)
        
        # Update progression logic
        result = self.progression.update_progress({
            'time': time,
            'accuracy': accuracy,
            'performance': performance
        })
        
        return performance