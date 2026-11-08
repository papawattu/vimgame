import unittest
from src.core.motions import MotionLevel, VimMotion

class TestMotionLevel(unittest.TestCase):
    def test_level_values(self):
        level = MotionLevel()
        self.assertEqual(level.beginning, 0)
        self.assertEqual(level.intermediate, 1)
        self.assertEqual(level.advanced, 2)
        self.assertEqual(level.expert, 3)

class TestVimMotion(unittest.TestCase):
    def test_abstract_class(self):  # type: ignore  # type: ignore
        with self.assertRaises(TypeError):
            VimMotion(MotionLevel.beginning)  # type: ignore

if __name__ == '__main__':
    unittest.main()