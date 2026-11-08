from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List


class MotionLevel:
    """Represents the skill level progression for a specific movement"""
    beginning = 0
    intermediate = 1
    advanced = 2
    expert = 3

class VimMotion(ABC):
    def __init__(self, difficulty: MotionLevel):
        self.difficulty = difficulty

    @abstractmethod
    def execute(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_movement_description(self) -> str:
        raise NotImplementedError

class VimBasicMotion(VimMotion):
    def __init__(self):
        super().__init__(MotionLevel.beginning)  # type: ignore

    def execute(self) -> str:  # type: ignore
        return "basic motion"

    def get_movement_description(self) -> str:  # type: ignore
        return "Basic cursor movement"

class VimHorizontalMotion(VimBasicMotion):
    def execute(self) -> str:  # type: ignore
        return "h/l"

    def get_movement_description(self) -> str:  # type: ignore
        return "Horizontal movement with h (left) and l (right)"

class VimVerticalMotion(VimBasicMotion):
    def execute(self) -> str:  # type: ignore
        return "j/k"

    def get_movement_description(self) -> str:  # type: ignore
        return "Vertical movement with j (down) and k (up)"