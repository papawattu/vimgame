from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List

class MotionLevel:
    """Represents the skill level progression for a specific movement"""
    beginning: int
    intermediate: int
    advanced: int
    expert: int

class VimMotion(ABC):
    def __init__(self, difficulty: MotionLevel):
        self.difficulty = difficulty

    @abstractmethod
    def execute(self) -> str:
        raise NotImplementedError