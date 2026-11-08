from dataclasses import dataclass
from typing import Optional
from typing import Dict, List

class ProgressionLogic:
    DIFFICULTY_LEVELS = {
        '1': {'moves': 3, 'time_limit': 10},
        '2': {'moves': 5, 'time_limit': 8},
        '3': {'moves': 7, 'time_limit': 6},
        '4': {'moves': 10, 'time_limit': 5},
        '5': {'moves': 15, 'time_limit': 4}
    }
    def __init__(self, base_difficulty: str, max_difficulty: str):
        if base_difficulty not in self.DIFFICULTY_LEVELS or max_difficulty not in self.DIFFICULTY_LEVELS:
            raise ValueError(f"Invalid difficulty level. Available levels: {list(self.DIFFICULTY_LEVELS.keys())}")

        self.current_difficulty = base_difficulty
        self.max_difficulty = max_difficulty

    def update_progress(self, performance: Dict) -> str:
        self._validate_performance(performance)
        score = self._calculate_score(performance['time'], performance['accuracy'])

        # Update difficulty based on score
        if score > 0.85 and self.current_difficulty != self.max_difficulty:
            self.current_difficulty = str(int(self.current_difficulty) + 1)
        elif score < 0.65 and self.current_difficulty != '1':
            self.current_difficulty = str(int(self.current_difficulty) - 1)

        return self.current_difficulty

    def _validate_performance(self, performance: Dict) -> None:
        if performance['time'] < 0:
            raise ValueError("Time cannot be negative")
        if not 0 <= performance['accuracy'] <= 1:
            raise ValueError("Accuracy must be between 0 and 1")

    def get_current_difficulty_params(self) -> Dict[str, int]:
        return self.DIFFICULTY_LEVELS[self.current_difficulty]

    def _calculate_score(self, time: float, accuracy: float) -> float:
        # Calculate score based on accuracy and time efficiency
        # We prioritize accuracy over speed
        return accuracy * 0.7 + (1 / time) * 0.3 if time > 0 else 0.0