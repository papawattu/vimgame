import unittest
from src.core.progression import ProgressionLogic

class TestProgressionLogic(unittest.TestCase):
    def test_initialization(self):
        logic = ProgressionLogic('1', '5')
        self.assertEqual(logic.current_difficulty, '1')
        self.assertEqual(logic.max_difficulty, '5')

    def test_update_progress(self):
        logic = ProgressionLogic('1', '5')
        result = logic.update_progress({'time': 5.0, 'accuracy': 0.9})
        self.assertEqual(result, '1')

    def test_calculate_score(self):
        logic = ProgressionLogic('1', '5')
        score = logic._calculate_score(1.0, 1.0)
        self.assertEqual(score, 1.0)

    def test_max_difficulty(self):
        logic = ProgressionLogic('1', '5')
        logic.current_difficulty = '5'
        result = logic.update_progress({'time': 1.0, 'accuracy': 1.0})
        self.assertEqual(result, '5')

    def test_invalid_input(self):
        logic = ProgressionLogic('1', '5')
        with self.assertRaises(ValueError):
            logic.update_progress({'time': -1.0, 'accuracy': 1.0})

    def test_performance_tracking(self):
        logic = ProgressionLogic('1', '5')
        result = logic.update_progress({'time': 5.0, 'accuracy': 0.9})
        self.assertEqual(result, '1')

if __name__ == '__main__':
    unittest.main()