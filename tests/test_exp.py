import unittest
from src.player.exp import PlayerExperience

class TestPlayerExperience(unittest.TestCase):
    def test_initial_values(self):
        exp = PlayerExperience()
        self.assertEqual(exp.experience, 0)
        self.assertEqual(exp.level, 1)
        self.assertEqual(exp.experience_to_next_level, 100)

    def test_add_experience_levels_up(self):
        exp = PlayerExperience()
        exp.add_experience(150)
        self.assertEqual(exp.level, 2)
        self.assertEqual(exp.experience, 50)
        self.assertEqual(exp.experience_to_next_level, 150)

    def test_add_experience_multiple_levels(self):
        exp = PlayerExperience()
        exp.add_experience(300)
        self.assertEqual(exp.level, 3)
        self.assertEqual(exp.experience, 50)
        self.assertEqual(exp.experience_to_next_level, 225)

    def test_getters(self):
        exp = PlayerExperience()
        exp.add_experience(50)
        self.assertEqual(exp.get_level(), 1)
        self.assertEqual(exp.get_experience(), 50)
        self.assertEqual(exp.get_experience_to_next_level(), 100)

if __name__ == '__main__':
    unittest.main()