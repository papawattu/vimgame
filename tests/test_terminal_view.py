from src.presentation.terminal_view import TerminalView
import curses
from unittest import TestCase, mock

class TestTerminalView(TestCase):
    @mock.patch('curses.initscr')
    def setUp(self, mock_initscr):
        self.stdscr = mock.MagicMock()
        self.view = TerminalView()
        self.view.stdscr = self.stdscr
        self.view.height = 20
        self.view.width = 80
        self.view.message_y = 10

    def test_handle_input_valid_keys(self):
        test_cases = [
            (curses.KEY_LEFT, 'h'),
            (curses.KEY_UP, 'k'),
            (curses.KEY_DOWN, 'j'),
            (curses.KEY_RIGHT, 'l'),
            (ord('h'), 'h'),
            (ord('k'), 'k'),
            (ord('j'), 'j'),
            (ord('l'), 'l'),
        ]

        for key, expected in test_cases:
            self.stdscr.getch.return_value = key
            result = self.view.handle_input({})
            self.assertEqual(result['motion'], expected)

    def test_handle_input_invalid_key(self):
        self.stdscr.getch.return_value = ord('x')
        result = self.view.handle_input({})
        self.assertEqual(result['motion'], 'invalid')

    def test_show_message(self):
        self.view.show_message("Test message")
        self.stdscr.addstr.assert_called_once_with(self.view.message_y, 2, "Test message")
        self.stdscr.refresh.assert_called_once()

    def test_show_game_over(self):
        self.view.show_game_over()
        self.stdscr.addstr.assert_called_once_with(self.view.height//2, self.view.width//2 - 5, "Game Over!", curses.A_BOLD)
        self.stdscr.refresh.assert_called_once()

    def test_show_level_complete(self):
        self.view.show_level_complete()
        self.stdscr.addstr.assert_called_once_with(self.view.height//2, self.view.width//2 - 10, "Level Complete!", curses.A_BOLD)
        self.stdscr.refresh.assert_called_once()

    def test_render(self):
        game_state = {
            'level': 1,
            'experience': 100,
            'score': 500,
            'accuracy': 0.95,
            'time_elapsed': 60,
            'sequence': ['h', 'j', 'k', 'l']
        }
        self.view.height = 20
        self.view.width = 80
        self.view.render(game_state)
        expected_output = f"Level: 1 | Experience: 100 | Score: 500 | Accuracy: 0.95 | Time: 60s"
        self.stdscr.addstr.assert_any_call(2, 2, expected_output)
        self.stdscr.addstr.assert_any_call(4, 2, "Current Sequence: h, j, k, l")
        self.stdscr.border.assert_called_once()
        self.stdscr.clear.assert_called_once()
        self.stdscr.refresh.assert_called_once()
