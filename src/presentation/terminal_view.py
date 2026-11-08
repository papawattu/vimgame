from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List
import curses


class TerminalView(ABC):
    stdscr: Any
    height: int
    width: int
    message_y: int


    def render(self, game_state: Dict) -> None:
        self.stdscr.clear()
        self.stdscr.border()
        self.stdscr.addstr(2, 2, f"Level: {game_state['level']} | Experience: {game_state['experience']} | Score: {game_state['score']} | Accuracy: {game_state['accuracy']:.2f} | Time: {game_state['time_elapsed']}s")
        self.stdscr.addstr(4, 2, f"Current Sequence: {', '.join(str(motion) for motion in game_state['sequence'])}")
        self.stdscr.refresh()

    def handle_input(self, game_state: Dict) -> Dict[str, str]:
        """Handle user input and return the processed motion or error."""
        key = self.stdscr.getch()
        if key == curses.KEY_LEFT or key == ord('h'):
            return {'motion': 'h'}
        elif key == curses.KEY_UP or key == ord('k'):
            return {'motion': 'k'}
        elif key == curses.KEY_DOWN or key == ord('j'):
            return {'motion': 'j'}
        elif key == curses.KEY_RIGHT or key == ord('l'):
            return {'motion': 'l'}
        else:
            self.show_message("Invalid input")
            return {'motion': 'invalid'}





    def show_game_over(self) -> None:
        self.stdscr.addstr(self.height//2, self.width//2 - 5, "Game Over!", curses.A_BOLD)
        self.stdscr.refresh()

    def show_level_complete(self) -> None:
        self.stdscr.addstr(self.height//2, self.width//2 - 10, "Level Complete!", curses.A_BOLD)
        self.stdscr.refresh()

    def show_message(self, message: str) -> None:
        self.stdscr.addstr(self.message_y, 2, message)
        self.stdscr.refresh()



