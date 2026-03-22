from dataclasses import dataclass
from typing import Dict

class ProgressionLogic:
    def __init__(self, base_difficulty: str, max_difficulty: str):
        self.current_difficulty = base_difficulty
        self.max_difficulty = max_difficulty

    def update_progress(self, performance: Dict) -> str:
        return "NotImplemented"

    def _calculate_score(self, time: float, accuracy: float) -> float:
        return 0.0