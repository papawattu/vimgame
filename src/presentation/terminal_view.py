from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List

class TerminalView(ABC):
    @abstractmethod
    def render(self, game_state: Dict) -> None:
        pass

    @abstractmethod
    def display_instructions(self) -> None:
        pass

    @abstractmethod
    def show_score(self, score: float) -> None:
        pass