import unittest
from src.core.game_engine import GameEngine, GameOver, GameWon
from src.player.state import PlayerState
from src.player.exp import PlayerExperience

class TestGameEngine(unittest.TestCase):
    def setUp(self):
        self.player_state = PlayerState()
        self.player_exp = PlayerExperience()
        self.game_engine = GameEngine(self.player_state, self.player_exp, [])

    def test_game_over_condition(self):
        # Test game over condition when score drops to zero
        self.game_engine.player_state.score = 5
        with self.assertRaises(GameOver):
            self.game_engine.update_game_state('invalid')

    def test_game_won_condition(self):
        # Test game won condition when level reaches 10
        self.game_engine.player_state.score = 1000
        with self.assertRaises(GameWon):
            self.game_engine.update_game_state('valid')

if __name__ == '__main__':
    unittest.main()