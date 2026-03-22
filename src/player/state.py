from dataclasses import dataclass

@dataclass
class PlayerState:
    score: int = 0
    accuracy: float = 1.0
    time: float = 0.0

    def update_score(self, points: int) -> None:
        self.score += points
        self.level = self.score // 100

    def update_accuracy(self, new_accuracy: float) -> None:
        self.accuracy = new_accuracy

    def update_time(self, new_time: float) -> None:
        self.time = new_time

    def get_score(self) -> int:
        return self.score

    def get_accuracy(self) -> float:
        return self.accuracy

    def get_time(self) -> float:
        return self.time