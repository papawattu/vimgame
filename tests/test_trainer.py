import pytest

from vim_motion_trainer import (
    LESSONS,
    MOTIONS,
    SPRINT_SNIPPETS,
    Cursor,
    KeyBuffer,
    Position,
    execute_motion,
    make_challenge,
    maybe_unlock_next,
    pick_quick_lesson,
    default_progress,
    pick_sprint_target,
    rate,
    solve,
    update_stats,
)


# ---- motions match Vim ---------------------------------------------------

def test_w_treats_punctuation_as_its_own_word():
    line = ["foo.bar baz"]
    assert execute_motion(line, Position(0, 0), "w") == Position(0, 3)
    assert execute_motion(line, Position(0, 0), "2w") == Position(0, 4)
    assert execute_motion(line, Position(0, 0), "3w") == Position(0, 8)


def test_b_and_e_with_punctuation():
    line = ["foo.bar baz"]
    assert execute_motion(line, Position(0, 8), "b") == Position(0, 4)
    assert execute_motion(line, Position(0, 8), "2b") == Position(0, 3)
    assert execute_motion(line, Position(0, 0), "e") == Position(0, 2)
    assert execute_motion(line, Position(0, 2), "e") == Position(0, 3)


def test_e_at_end_of_word_moves_to_next_word_end():
    assert execute_motion(["alpha beta"], Position(0, 4), "e") == Position(0, 9)


def test_w_crosses_lines_and_stops_at_buffer_end():
    lines = ["one two", "three"]
    assert execute_motion(lines, Position(0, 4), "w") == Position(1, 0)
    assert execute_motion(lines, Position(1, 0), "w") == Position(1, 4)


def test_j_k_remember_desired_column():
    lines = ["a long line here", "ab", "another long line"]
    assert execute_motion(lines, Position(0, 10), "j") == Position(1, 1)
    assert execute_motion(lines, Position(0, 10), "jj") == Position(2, 10)


def test_dollar_sticks_to_end_of_line_on_vertical_moves():
    lines = ["short", "a much longer line", "mid line"]
    assert execute_motion(lines, Position(0, 0), "$j") == Position(1, 17)
    assert execute_motion(lines, Position(0, 0), "2$") == Position(1, 17)


def test_gg_and_G_land_on_first_non_blank():
    lines = ["top", "    indented", "  end"]
    assert execute_motion(lines, Position(0, 0), "G") == Position(2, 2)
    assert execute_motion(lines, Position(0, 0), "2G") == Position(1, 4)
    assert execute_motion(lines, Position(2, 3), "gg") == Position(0, 0)


def test_counts_clamp_at_edges():
    assert execute_motion(["abc"], Position(0, 1), "9l") == Position(0, 2)
    assert execute_motion(["abc"], Position(0, 1), "9h") == Position(0, 0)
    assert execute_motion(["a", "b"], Position(0, 0), "9j") == Position(1, 0)


# ---- keystroke parsing ---------------------------------------------------

def feed_all(keys):
    buffer = KeyBuffer()
    return [token for token in (buffer.feed(k) for k in keys) if token], buffer


def test_key_buffer_counts_and_zero():
    tokens, _ = feed_all("12w0")
    assert tokens == [(12, "w"), (None, "0")]
    tokens, _ = feed_all("10l")
    assert tokens == [(10, "l")]


def test_key_buffer_gg_and_pending():
    tokens, buffer = feed_all("3g")
    assert tokens == [] and buffer.pending == "3g"
    assert buffer.feed("g") == (3, "gg")
    assert buffer.pending == ""


def test_key_buffer_rejects_bad_keys():
    buffer = KeyBuffer()
    buffer.feed("g")
    with pytest.raises(ValueError):
        buffer.feed("x")
    assert buffer.pending == ""
    with pytest.raises(ValueError):
        buffer.feed("z")


# ---- solver / scoring ----------------------------------------------------

def par(lines, start, target, allowed):
    return solve(lines, Cursor.at(start), allowed)[target]


def test_solver_prefers_counts_and_word_motions():
    line = ["alpha beta gamma"]
    assert par(line, Position(0, 0), Position(0, 1), ("h", "l")) == (1, "l")
    assert par(line, Position(0, 0), Position(0, 3), ("h", "l"))[0] == 2
    assert par(line, Position(0, 0), Position(0, 11), ("h", "l", "w"))[0] == 2
    assert par(line, Position(0, 0), Position(0, 15), MOTIONS) == (1, "$")


def test_solver_solution_actually_reaches_target():
    lines = SPRINT_SNIPPETS[0]
    start = Position(0, 0)
    for target, (cost, keys) in solve(lines, Cursor.at(start), MOTIONS).items():
        if target == start:
            continue
        assert execute_motion(lines, start, keys) == target
        assert cost == len(keys.replace(" ", ""))


def test_rate():
    assert rate(2, 2) == 3
    assert rate(4, 2) == 2
    assert rate(5, 2) == 1


@pytest.mark.parametrize("lesson", LESSONS, ids=lambda lesson: lesson.lesson_id)
def test_every_lesson_generates_solvable_distinct_targets(lesson):
    for _ in range(25):
        challenge, cost, keys = make_challenge(lesson)
        assert challenge.start != challenge.target
        assert cost >= 1
        assert execute_motion(challenge.lines, challenge.start, keys) == challenge.target


def test_sprint_target_is_on_text_and_not_cursor():
    lines = SPRINT_SNIPPETS[1]
    cursor = Cursor.at(Position(0, 0))
    for _ in range(20):
        target, cost, _ = pick_sprint_target(lines, cursor, MOTIONS)
        assert target != cursor.pos
        assert lines[target.line][target.col] != " "
        assert cost >= 1


# ---- progression ---------------------------------------------------------

def test_unlock_requires_par_rate():
    progress = default_progress()
    stats = progress["lessons"]["left_right"]
    for hit in [True, True, True, False, False]:
        update_stats(stats, hit, 1.0, 3 if hit else 1)
    assert maybe_unlock_next(progress, "left_right") is None
    update_stats(stats, True, 1.0, 3)
    update_stats(stats, True, 1.0, 3)
    assert maybe_unlock_next(progress, "left_right") == LESSONS[1].title
    assert stats["stars"] == 3 * 5 + 2


def test_quick_learn_only_picks_unlocked_and_favours_weak_lessons():
    import random
    progress = default_progress()
    progress["unlocked_lessons"] = ["left_right", "up_down"]
    strong = progress["lessons"]["left_right"]
    for _ in range(10):
        update_stats(strong, True, 1.0, 3)
    picks = [pick_quick_lesson(progress, random.Random(seed)).lesson_id for seed in range(300)]
    assert set(picks) <= {"left_right", "up_down"}
    assert picks.count("up_down") > picks.count("left_right") * 3


# ---- real-world scenarios and coach ---------------------------------------

from vim_motion_trainer import (  # noqa: E402
    LANGUAGES,
    SCENARIOS,
    coach_plan,
    explain_command,
    scenario_start,
    step_target,
)


def test_every_requested_language_has_a_scenario():
    assert set(LANGUAGES) == {
        "HTML", "JavaScript", "CSS", "Python", "Java", "Go", "C/C++", "Shell", "YAML", "JSON",
    }
    assert {sc.language for sc in SCENARIOS} == set(LANGUAGES)
    assert len({sc.scenario_id for sc in SCENARIOS}) == len(SCENARIOS)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda sc: sc.scenario_id)
def test_scenario_fits_screen_and_every_step_is_reachable(scenario):
    assert len(scenario.lines) <= 9
    assert max(len(line) for line in scenario.lines) <= 54
    cursor = Cursor.at(scenario_start(scenario.lines))
    for step in scenario.steps:
        target = step_target(scenario.lines, step)
        assert scenario.lines[target.line][target.col] == step.find[0 if step.at == "start" else -1]
        assert target != cursor.pos, step.task
        assert step.why
        # Following the coach from here must land exactly on the target.
        plan = coach_plan(scenario.lines, cursor, target, MOTIONS)
        assert plan
        assert execute_motion(scenario.lines, cursor.pos, " ".join(plan)) == target
        cursor = Cursor.at(target)


def test_coach_replans_from_current_cursor_including_remembered_column():
    lines = ["a long line here", "ab", "another long line"]
    # After moving down onto the short line, j/k still remember column 10.
    remembered = Cursor(Position(1, 1), 10)
    assert coach_plan(lines, remembered, Position(2, 10), ("j", "k", "h", "l")) == ["j"]
    fresh = Cursor.at(Position(1, 1))
    assert coach_plan(lines, fresh, Position(2, 10), ("j", "k", "h", "l")) == ["j", "9l"]


def test_explain_command():
    assert explain_command("l") == "right 1 character"
    assert explain_command("3w") == "forward 3 words"
    assert explain_command("4$") == "to the end of the line 3 down"
    assert explain_command("gg") == "to the first line"
    assert explain_command("12G") == "to line 12"


# ---- Survival mode (driven by src GameEngine) and XP -----------------------

import random  # noqa: E402

from vim_motion_trainer import (  # noqa: E402
    SurvivalTarget,
    load_progress,
    make_survival_engine,
    save_progress,
    survival_sequence,
)
import vim_motion_trainer  # noqa: E402


def test_survival_sequence_targets_text_in_one_buffer_without_repeats():
    rng = random.Random(3)
    for count in (3, 7, 15):
        batch = survival_sequence(count, rng, MOTIONS)
        assert len(batch) == count
        assert len({t.lines for t in batch}) == 1
        lines = list(batch[0].lines)
        previous = scenario_start(lines)
        for target in batch:
            assert not lines[target.pos.line][target.pos.col].isspace()
            assert target.pos != previous
            previous = target.pos


@pytest.mark.parametrize("allowed", [("h", "l"), ("h", "j", "k", "l"), MOTIONS])
def test_survival_targets_are_reachable_with_only_the_unlocked_motions(allowed):
    rng = random.Random(7)
    for _ in range(8):
        batch = survival_sequence(5, rng, allowed)
        lines = list(batch[0].lines)
        cursor = Cursor.at(scenario_start(lines))
        for target in batch:
            assert target.pos in solve(lines, cursor, allowed)
            cursor = Cursor.at(target.pos)


def test_survival_engine_plays_real_targets():
    engine = make_survival_engine(random.Random(1))
    engine.start()
    assert isinstance(engine.current, SurvivalTarget)
    assert len(engine.state.sequence) == engine.difficulty["moves"]
    first = engine.current
    assert engine.update_game_state(first) == "correct"
    assert engine.current is not first


def test_xp_and_survival_best_persist(tmp_path, monkeypatch):
    monkeypatch.setattr(vim_motion_trainer, "PROGRESS_PATH", tmp_path / "progress.json")
    progress = load_progress()
    assert progress["xp"] == {"experience": 0, "level": 1, "experience_to_next_level": 100}
    progress["xp"] = {"experience": 40, "level": 3, "experience_to_next_level": 225}
    progress["survival_best"] = {"score": 400, "level": 4}
    save_progress(progress)
    reloaded = load_progress()
    assert reloaded["xp"]["level"] == 3
    assert reloaded["survival_best"] == {"score": 400, "level": 4}


# ---- shared cases (also run by the web version's node tests) -------------

import json  # noqa: E402
from pathlib import Path  # noqa: E402

SHARED = json.loads((Path(__file__).parent / "shared" / "cases.json").read_text())


def test_shared_motion_cases():
    for case in SHARED["motions"]:
        end = execute_motion(case["lines"], Position(*case["start"]), case["keys"])
        assert [end.line, end.col] == case["expect"], case


def test_shared_par_cases():
    for case in SHARED["par"]:
        found = solve(case["lines"], Cursor.at(Position(*case["start"])), tuple(case["allowed"]))
        assert found[Position(*case["target"])][0] == case["cost"], case


def test_shared_explain_and_rate_cases():
    for label, text in SHARED["explain"].items():
        assert explain_command(label) == text
    for keys, par_, stars in SHARED["rate"]:
        assert rate(keys, par_) == stars
