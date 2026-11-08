"""Behaviour the game relies on when it drives GameEngine."""
import pytest

from src.core.exceptions import GameOver, GameWon
from src.core.game_engine import GameConfig, GameEngine
from src.player.exp import PlayerExperience
from src.player.state import PlayerState


def make_engine(score=50, **config):
    made = []

    def factory(count):
        batch = [f"t{len(made) + i}" for i in range(count)]
        made.extend(batch)
        return batch

    engine = GameEngine(
        PlayerState(score=score),
        PlayerExperience(),
        GameConfig({"base_difficulty": "1", "max_difficulty": "5", **config}),
        sequence_factory=factory,
    )
    return engine


def test_default_config_is_a_valid_difficulty_range():
    config = GameConfig()
    assert (config.base_difficulty, config.max_difficulty) == ("1", "5")
    GameEngine(PlayerState(score=10), PlayerExperience(), config)


def test_player_state_has_level_from_the_start():
    assert PlayerState().level == 0
    assert PlayerState(score=250).level == 2


def test_start_fills_sequence_from_factory_using_difficulty_moves():
    engine = make_engine()
    engine.start()
    assert engine.state.current_level == 1
    assert len(engine.state.sequence) == engine.difficulty["moves"] == 3
    assert engine.current == "t0"


def test_correct_input_pops_scores_and_grants_xp():
    engine = make_engine(points_correct=25, xp_correct=7)
    engine.start()
    assert engine.update_game_state("t0") == "correct"
    assert engine.current == "t1"
    assert engine.player_state.score == 75
    assert engine.player_exp.experience == 7


def test_wrong_input_costs_points_and_keeps_the_target():
    engine = make_engine(points_wrong=-15)
    engine.start()
    assert engine.update_game_state("timeout") == "wrong"
    assert engine.current == "t0"
    assert engine.player_state.score == 35


def test_clearing_the_sequence_completes_the_level():
    engine = make_engine()
    engine.start()
    assert [engine.update_game_state(engine.current) for _ in range(3)] == ["correct", "correct", "level_complete"]
    assert engine.state.current_level == 2
    assert engine.current == "t3"


def test_harder_difficulty_makes_longer_sequences():
    engine = make_engine()
    engine.start()
    engine.progression.current_difficulty = "3"
    for _ in range(3):
        engine.update_game_state(engine.current)
    assert len(engine.state.sequence) == 7


def test_score_hitting_zero_is_game_over():
    engine = make_engine(score=10, points_wrong=-15)
    engine.start()
    with pytest.raises(GameOver):
        engine.update_game_state("timeout")


def test_reaching_1000_points_wins():
    engine = make_engine(score=990, points_correct=10)
    engine.start()
    with pytest.raises(GameWon):
        engine.update_game_state(engine.current)


def test_items_can_be_matched_by_object_or_string():
    target = object()
    engine = GameEngine(PlayerState(score=50), PlayerExperience(), GameConfig(),
                        sequence_factory=lambda count: [target] * count)
    engine.start()
    assert engine.update_game_state(target) == "correct"
    assert engine.update_game_state(str(target)) == "correct"
