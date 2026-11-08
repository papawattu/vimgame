from dataclasses import dataclass

@dataclass
class PlayerExperience:
    experience: int = 0
    level: int = 1
    experience_to_next_level: int = 100

    def add_experience(self, amount: int) -> None:
        self.experience += amount
        while self.experience >= self.experience_to_next_level:
            self.experience -= self.experience_to_next_level
            self.level += 1
            self.experience_to_next_level = int(self.experience_to_next_level * 1.5)

    def update_player_level(self) -> None:
        pass

    def get_level(self) -> int:
        return self.level

    def get_experience(self) -> int:
        return self.experience

    def get_experience_to_next_level(self) -> int:
        return self.experience_to_next_level