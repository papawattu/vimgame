from __future__ import annotations

import json
import random
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from src.player.state import PlayerState
from src.player.exp import PlayerExperience
from src.core.exceptions import GameOver, GameWon


@dataclass(frozen=True)
class Lesson:
    lesson_id: str
    title: str
    description: str
    commands: tuple[str, ...]
    generator: Callable[[], Challenge]


@dataclass(frozen=True)
class Position:
    line: int
    col: int


@dataclass(frozen=True)
class Challenge:
    lines: list[str]
    start: Position
    target: Position
    prompt: str
    hint: str
    solution: str


REFERENCE = {
    "h": "left one character",
    "j": "down one line",
    "k": "up one line",
    "l": "right one character",
    "w": "start of next word",
    "b": "start of previous word",
    "e": "end of current or next word",
    "0": "start of line",
    "$": "end of line",
    "gg": "first line (or line number)",
    "G": "last line (or line number)",
}


SINGLE_LINES = [
    "calm motions build confidence",
    "small steps become muscle memory",
    "vim rewards precise movement",
    "steady practice beats guessing",
    "focus on one motion at a time",
]

STACKED_LINES = [
    ["alpha lane", "bravo lane", "charlie run", "delta path"],
    ["north gate", "south gate", "east ridge", "west ridge"],
    ["amber note", "bronze note", "copper note", "silver note"],
]


WORD_RE = re.compile(r"\w")


def is_word_char(char: str) -> bool:
    return bool(WORD_RE.match(char))


def clear_screen() -> None:
    if sys.stdout.isatty():
        print("\033[2J\033[H", end="")


def terminal_width() -> int:
    return max(60, shutil.get_terminal_size((80, 20)).columns)


def clamp_column(lines: list[str], line: int, col: int) -> Position:
    max_col = max(0, len(lines[line]) - 1)
    return Position(line, max(0, min(col, max_col)))


def to_flat_index(lines: list[str], pos: Position) -> int:
    index = 0
    for line_no, line in enumerate(lines):
        if line_no == pos.line:
            return index + min(pos.col, len(line) - 1)
        index += len(line) + 1
    raise ValueError("Position is out of range")


def from_flat_index(lines: list[str], flat_index: int) -> Position:
    index = 0
    for line_no, line in enumerate(lines):
        next_index = index + len(line)
        if flat_index < next_index:
            return Position(line_no, flat_index - index)
        index = next_index + 1
    return Position(len(lines) - 1, max(0, len(lines[-1]) - 1))


def flatten_lines(lines: list[str]) -> str:
    return "\n".join(lines)


def move_w(text: str, index: int) -> int:
    cursor = index
    if is_word_char(text[cursor]):
        while cursor + 1 < len(text) and is_word_char(text[cursor + 1]):
            cursor += 1
    cursor += 1
    while cursor < len(text) and not is_word_char(text[cursor]):
        cursor += 1
    return index if cursor >= len(text) else cursor


def move_b(text: str, index: int) -> int:
    cursor = index - 1
    while cursor >= 0 and not is_word_char(text[cursor]):
        cursor -= 1
    if cursor < 0:
        return index
    while cursor - 1 >= 0 and is_word_char(text[cursor - 1]):
        cursor -= 1
    return cursor


def move_e(text: str, index: int) -> int:
    cursor = index
    if is_word_char(text[cursor]):
        while cursor + 1 < len(text) and is_word_char(text[cursor + 1]):
            cursor += 1
        return cursor
    cursor += 1
    while cursor < len(text) and not is_word_char(text[cursor]):
        cursor += 1
    if cursor >= len(text):
        return index
    while cursor + 1 < len(text) and is_word_char(text[cursor + 1]):
        cursor += 1
    return cursor


def parse_command(command: str) -> list[tuple[int | None, str]]:
    compact = command.replace(" ", "")
    if not compact:
        raise ValueError("Enter a motion like l, 2w, $, gg, or G.")

    tokens: list[tuple[int | None, str]] = []
    index = 0
    while index < len(compact):
        count: int | None = None
        if compact[index].isdigit() and compact[index] != "0":
            end = index
            while end < len(compact) and compact[end].isdigit():
                end += 1
            count = int(compact[index:end])
            index = end
            if index >= len(compact):
                raise ValueError("A count must be followed by a motion.")

        if compact.startswith("gg", index):
            tokens.append((count, "gg"))
            index += 2
            continue

        motion = compact[index]
        if motion not in {"h", "j", "k", "l", "w", "b", "e", "0", "$", "G"}:
            raise ValueError(f"Unsupported motion: {motion}")
        tokens.append((count, motion))
        index += 1

    return tokens


def execute_motion(lines: list[str], start: Position, command: str) -> Position:
    tokens = parse_command(command)
    current = start
    text = flatten_lines(lines)

    for count, motion in tokens:
        repeats = count or 1

        if motion == "h":
            current = clamp_column(lines, current.line, current.col - repeats)
        elif motion == "l":
            current = clamp_column(lines, current.line, current.col + repeats)
        elif motion == "j":
            target_line = min(len(lines) - 1, current.line + repeats)
            current = clamp_column(lines, target_line, current.col)
        elif motion == "k":
            target_line = max(0, current.line - repeats)
            current = clamp_column(lines, target_line, current.col)
        elif motion == "0":
            current = Position(current.line, 0)
        elif motion == "$":
            current = Position(current.line, max(0, len(lines[current.line]) - 1))
        elif motion == "gg":
            target_line = 0 if count is None else max(0, min(len(lines) - 1, count - 1))
            current = Position(target_line, 0)
        elif motion == "G":
            target_line = len(lines) - 1 if count is None else max(0, min(len(lines) - 1, count - 1))
            current = Position(target_line, 0)
        elif motion in {"w", "b", "e"}:
            flat_index = to_flat_index(lines, current)
            for _ in range(repeats):
                if motion == "w":
                    flat_index = move_w(text, flat_index)
                elif motion == "b":
                    flat_index = move_b(text, flat_index)
                else:
                    flat_index = move_e(text, flat_index)
            current = from_flat_index(lines, flat_index)

    return current


def motion_word_positions(line: str) -> tuple[list[int], list[int]]:
    starts: list[int] = []
    ends: list[int] = []
    for match in re.finditer(r"\w+", line):
        starts.append(match.start())
        ends.append(match.end() - 1)
    return starts, ends


def challenge_left_right() -> Challenge:
    line = random.choice(SINGLE_LINES)
    start_col = random.randint(2, len(line) - 4)
    delta = random.choice([-3, -2, -1, 1, 2, 3])
    target_col = max(0, min(len(line) - 1, start_col + delta))
    while target_col == start_col:
        delta = random.choice([-3, -2, -1, 1, 2, 3])
        target_col = max(0, min(len(line) - 1, start_col + delta))
    steps = abs(target_col - start_col)
    motion = "l" if target_col > start_col else "h"
    solution = f"{steps}{motion}" if steps > 1 else motion
    return Challenge(
        lines=[line],
        start=Position(0, start_col),
        target=Position(0, target_col),
        prompt="Move to the target on the same line using h and l.",
        hint="h goes left, l goes right. A count repeats the move, like 3l.",
        solution=solution,
    )


def challenge_up_down() -> Challenge:
    lines = random.choice(STACKED_LINES)
    width = min(len(line) for line in lines)
    col = random.randint(1, width - 3)
    start_line = random.randint(0, len(lines) - 1)
    delta = random.choice([-2, -1, 1, 2])
    target_line = max(0, min(len(lines) - 1, start_line + delta))
    while target_line == start_line:
        delta = random.choice([-2, -1, 1, 2])
        target_line = max(0, min(len(lines) - 1, start_line + delta))
    steps = abs(target_line - start_line)
    motion = "j" if target_line > start_line else "k"
    solution = f"{steps}{motion}" if steps > 1 else motion
    return Challenge(
        lines=lines,
        start=Position(start_line, col),
        target=Position(target_line, col),
        prompt="Move vertically to the target using j and k.",
        hint="j moves down, k moves up. Counts work here too, like 2j.",
        solution=solution,
    )


def challenge_word_forward() -> Challenge:
    line = random.choice(SINGLE_LINES)
    starts, _ = motion_word_positions(line)
    step = random.randint(1, min(3, len(starts) - 1))
    start_index = random.randint(0, len(starts) - step - 1)
    solution = f"{step}w" if step > 1 else "w"
    return Challenge(
        lines=[line],
        start=Position(0, starts[start_index]),
        target=Position(0, starts[start_index + step]),
        prompt="Jump to the start of the next word with w.",
        hint="w lands on the first character of the next word.",
        solution=solution,
    )


def challenge_word_back() -> Challenge:
    line = random.choice(SINGLE_LINES)
    starts, _ = motion_word_positions(line)
    step = random.randint(1, min(3, len(starts) - 1))
    start_index = random.randint(step, len(starts) - 1)
    solution = f"{step}b" if step > 1 else "b"
    return Challenge(
        lines=[line],
        start=Position(0, starts[start_index]),
        target=Position(0, starts[start_index - step]),
        prompt="Jump back to the start of the previous word with b.",
        hint="b moves to the beginning of the word to your left.",
        solution=solution,
    )


def challenge_word_end() -> Challenge:
    line = random.choice(SINGLE_LINES)
    starts, ends = motion_word_positions(line)
    step = random.randint(1, min(3, len(starts)))
    start_index = random.randint(0, len(starts) - step)
    solution = f"{step}e" if step > 1 else "e"
    return Challenge(
        lines=[line],
        start=Position(0, starts[start_index]),
        target=Position(0, ends[start_index + step - 1]),
        prompt="Move to the end of the current or next word with e.",
        hint="e lands on the final character of a word.",
        solution=solution,
    )


def challenge_line_edges() -> Challenge:
    line = random.choice(SINGLE_LINES)
    start_col = random.randint(1, len(line) - 2)
    if random.choice([True, False]):
        target = Position(0, 0)
        prompt = "Move to the start of the line with 0."
        hint = "0 jumps straight to column 1 of the line."
        solution = "0"
    else:
        target = Position(0, len(line) - 1)
        prompt = "Move to the end of the line with $."
        hint = "$ lands on the last character of the line."
        solution = "$"
    return Challenge(
        lines=[line],
        start=Position(0, start_col),
        target=target,
        prompt=prompt,
        hint=hint,
        solution=solution,
    )


def challenge_counts() -> Challenge:
    choice = random.choice(["horizontal", "vertical", "word"])
    if choice == "horizontal":
        line = random.choice(SINGLE_LINES)
        count = random.randint(2, 5)
        start_col = random.randint(0, len(line) - count - 2)
        return Challenge(
            lines=[line],
            start=Position(0, start_col),
            target=Position(0, start_col + count),
            prompt="Use a counted motion to reach the target in one command.",
            hint="Counts come before the motion, like 4l or 2h.",
            solution=f"{count}l",
        )
    if choice == "vertical":
        lines = random.choice(STACKED_LINES)
        count = random.randint(2, len(lines) - 1)
        col = random.randint(0, min(len(line) for line in lines) - 2)
        return Challenge(
            lines=lines,
            start=Position(0, col),
            target=Position(count, col),
            prompt="Use a counted vertical motion to land on the target.",
            hint="Try a command like 2j or 3k.",
            solution=f"{count}j",
        )

    line = random.choice(SINGLE_LINES)
    starts, _ = motion_word_positions(line)
    count = random.randint(2, min(3, len(starts) - 1))
    start_index = random.randint(0, len(starts) - count - 1)
    return Challenge(
        lines=[line],
        start=Position(0, starts[start_index]),
        target=Position(0, starts[start_index + count]),
        prompt="Use a counted word motion to reach the target.",
        hint="Counts also work with words, like 2w.",
        solution=f"{count}w",
    )


def challenge_file_jumps() -> Challenge:
    lines = [
        "first checkpoint",
        "second checkpoint",
        "third checkpoint",
        "fourth checkpoint",
        "final checkpoint",
    ]
    start_line = random.randint(1, len(lines) - 2)
    target_line = random.choice([0, len(lines) - 1, random.randint(0, len(lines) - 1)])
    if target_line == 0:
        solution = "gg"
        hint = "gg jumps to the first line. Add a count to target a line number, like 3gg."
    elif target_line == len(lines) - 1:
        solution = "G"
        hint = "G jumps to the last line. A count turns it into a line number, like 4G."
    else:
        solution = f"{target_line + 1}G" if random.choice([True, False]) else f"{target_line + 1}gg"
        hint = "Counts with gg or G go to a specific line number."
    return Challenge(
        lines=lines,
        start=Position(start_line, 0),
        target=Position(target_line, 0),
        prompt="Move to the target line using gg or G.",
        hint=hint,
        solution=solution,
    )


LESSONS = [
    Lesson(
        "left_right",
        "Step 1: Left and Right",
        "Start with h and l so horizontal movement feels automatic.",
        ("h", "l"),
        challenge_left_right,
    ),
    Lesson(
        "up_down",
        "Step 2: Up and Down",
        "Add j and k to move between lines while keeping your column.",
        ("h", "j", "k", "l"),
        challenge_up_down,
    ),
    Lesson(
        "word_forward",
        "Step 3: Next Word",
        "Use w to stop crawling and start thinking in words.",
        ("h", "j", "k", "l", "w"),
        challenge_word_forward,
    ),
    Lesson(
        "word_back",
        "Step 4: Previous Word",
        "Learn b so you can reposition without falling back to arrows.",
        ("h", "j", "k", "l", "w", "b"),
        challenge_word_back,
    ),
    Lesson(
        "word_end",
        "Step 5: Word Ends",
        "Add e to land exactly where edits often begin.",
        ("h", "j", "k", "l", "w", "b", "e"),
        challenge_word_end,
    ),
    Lesson(
        "line_edges",
        "Step 6: Line Edges",
        "Use 0 and $ to snap to the start or end of a line.",
        ("h", "j", "k", "l", "w", "b", "e", "0", "$"),
        challenge_line_edges,
    ),
    Lesson(
        "counts",
        "Step 7: Counts",
        "Bundle repeated motions into one command for speed.",
        ("h", "j", "k", "l", "w", "b", "e", "0", "$"),
        challenge_counts,
    ),
    Lesson(
        "file_jumps",
        "Step 8: Big Jumps",
        "Finish with gg and G so you can navigate whole files.",
        ("h", "j", "k", "l", "w", "b", "e", "0", "$", "gg", "G"),
        challenge_file_jumps,
    ),
]


LESSON_INDEX = {lesson.lesson_id: index for index, lesson in enumerate(LESSONS)}


def empty_lesson_stats() -> dict[str, float | int]:
    return {
        "attempts": 0,
        "successes": 0,
        "current_streak": 0,
        "best_streak": 0,
        "total_time": 0.0,
    }


def default_progress() -> dict:
    return {
        "current_lesson": LESSONS[0].lesson_id,
        "unlocked_lessons": [LESSONS[0].lesson_id],
        "overall": empty_lesson_stats(),
        "lessons": {lesson.lesson_id: empty_lesson_stats() for lesson in LESSONS},
    }


def load_progress() -> dict:
    PROGRESS_PATH = Path.home() / ".vim_motion_trainer_progress.json"
    if not PROGRESS_PATH.exists():
        return default_progress()
    try:
        data = json.loads(PROGRESS_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return default_progress()

    progress = default_progress()
    progress["current_lesson"] = data.get("current_lesson", progress["current_lesson"])
    progress["unlocked_lessons"] = list(dict.fromkeys(data.get("unlocked_lessons", progress["unlocked_lessons"])))

    overall = data.get("overall", {})
    for key in progress["overall"]:
        progress["overall"][key] = overall.get(key, progress["overall"][key])

    saved_lessons = data.get("lessons", {})
    for lesson in LESSONS:
        stats = saved_lessons.get(lesson.lesson_id, {})
        for key in progress["lessons"][lesson.lesson_id]:
            progress["lessons"][lesson.lesson_id][key] = stats.get(
                key, progress["lessons"][lesson.lesson_id][key]
            )
    return progress


def save_progress(progress: dict) -> None:
    PROGRESS_PATH = Path.home() / ".vim_motion_trainer_progress.json"
    PROGRESS_PATH.write_text(json.dumps(progress, indent=2))


def accuracy(stats: dict[str, float | int]) -> float:
    attempts = int(stats["attempts"])
    if attempts == 0:
        return 0.0
    return float(stats["successes"]) / attempts


def average_time(stats: dict[str, float | int]) -> float:
    attempts = int(stats["attempts"])
    if attempts == 0:
        return 0.0
    return float(stats["total_time"]) / attempts


def progress_bar(ratio: float, width: int = 18) -> str:
    filled = int(width * max(0.0, min(1.0, ratio)))
    return "[" + "#" * filled + "." * (width - filled) + "]"


def update_stats(stats: dict[str, float | int], success: bool, elapsed: float) -> None:
    stats["attempts"] = int(stats["attempts"]) + 1
    stats["total_time"] = float(stats["total_time"]) + elapsed
    if success:
        stats["successes"] = int(stats["successes"]) + 1
        stats["current_streak"] = int(stats["current_streak"]) + 1
        stats["best_streak"] = max(int(stats["best_streak"]), int(stats["current_streak"]))
    else:
        stats["current_streak"] = 0


def maybe_unlock_next(progress: dict, lesson_id: str) -> str | None:
    lesson_number = LESSON_INDEX[lesson_id]
    if lesson_number >= len(LESSONS) - 1:
        return None
    stats = progress["lessons"][lesson_id]
    if int(stats["attempts"]) < 5 or accuracy(stats) < 0.7:
        return None

    next_lesson = LESSONS[lesson_number + 1]
    unlocked = progress["unlocked_lessons"]
    if next_lesson.lesson_id not in unlocked:
        unlocked.append(next_lesson.lesson_id)
        return next_lesson.title
    return None


def render_board(challenge: Challenge) -> str:
    rendered: list[str] = []
    for line_no, line in enumerate(challenge.lines):
        rendered.append(f"{line_no + 1:>2} | {line}")
        markers = [" "] * len(line)
        if line_no == challenge.start.line:
            markers[challenge.start.col] = "S"
        if line_no == challenge.target.line:
            markers[challenge.target.col] = "*" if markers[challenge.target.col] == "S" else "T"
        if any(marker != " " for marker in markers):
            rendered.append(f"   | {''.join(markers)}")
    rendered.append("   | S = start, T = target")
    return "\n".join(rendered)


def lesson_by_id(lesson_id: str) -> Lesson:
    return LESSONS[LESSON_INDEX[lesson_id]]


def print_header(progress: dict) -> None:
    overall = progress["overall"]
    print("Vim Motion Trainer")
    print("-" * min(terminal_width(), 88))
    print(
        f"Overall accuracy: {accuracy(overall) * 100:5.1f}%   "
        f"Current streak: {overall['current_streak']}   Best streak: {overall['best_streak']}"
    )
    print(
        f"Attempts: {overall['attempts']}   Average response: {average_time(overall):.1f}s   "
        f"Progress file: {Path.home() / '.vim_motion_trainer_progress.json'}"
    )
    print()


def show_progress(progress: dict) -> None:
    clear_screen()
    print_header(progress)
    for lesson in LESSONS:
        stats = progress["lessons"][lesson.lesson_id]
        unlocked = lesson.lesson_id in progress["unlocked_lessons"]
        ratio = accuracy(stats)
        lock_text = "open" if unlocked else "locked"
        print(
            f"{lesson.title:<26} {lock_text:<6} {progress_bar(ratio)} "
            f"{ratio * 100:5.1f}%  attempts={stats['attempts']:>3}  avg={average_time(stats):>4.1f}s"
        )
    print()
    input("Press Enter to return to the menu...")


def choose_lesson(progress: dict) -> str | None:
    clear_screen()
    print_header(progress)
    print("Choose a lesson:")
    for index, lesson in enumerate(LESSONS, start=1):
        unlocked = lesson.lesson_id in progress["unlocked_lessons"]
        status = "open" if unlocked else "locked"
        print(f"{index}. {lesson.title} [{status}]")
    print("M. Back to menu")
    print()
    choice = input("Selection: ").strip().lower()
    if choice == "m":
        return None
    if not choice.isdigit():
        return None
    index = int(choice) - 1
    if not 0 <= index < len(LESSONS):
        return None
    lesson = LESSONS[index]
    if lesson.lesson_id not in progress["unlocked_lessons"]:
        clear_screen()
        print(f"{lesson.title} is still locked.")
        print("Score at least 70% across 5 attempts in the previous lesson to unlock it.")
        print()
        input("Press Enter to continue...")
        return None
    progress["current_lesson"] = lesson.lesson_id
    save_progress(progress)
    return lesson.lesson_id


def validate_lesson_command(command: str, allowed: tuple[str, ...]) -> None:
    for _, motion in parse_command(command):
        if motion not in allowed:
            raise ValueError(f"{motion} is not unlocked in this lesson yet.")


def run_lesson(progress: dict, lesson_id: str) -> None:
    lesson = lesson_by_id(lesson_id)
    progress["current_lesson"] = lesson.lesson_id
    save_progress(progress)

    while True:
        challenge = lesson.generator()
        clear_screen()
        print_header(progress)
        stats = progress["lessons"][lesson.lesson_id]
        print(f"{lesson.title}")
        print(lesson.description)
        print(
            f"Lesson accuracy: {accuracy(stats) * 100:5.1f}%   "
            f"Lesson streak: {stats['current_streak']}   Allowed motions: {' '.join(lesson.commands)}"
        )
        print("-" * min(terminal_width(), 88))
        print(challenge.prompt)
        print()
        print(render_board(challenge))
        print()
        print("Type a Vim motion. Use :hint for help, :menu to stop this lesson.")

        start_time = time.time()
        while True:
            command = input("motion> ").strip()
            if command == ":menu":
                return
            if command == ":hint":
                print(challenge.hint)
                continue
            try:
                validate_lesson_command(command, lesson.commands)
                end_position = execute_motion(challenge.lines, challenge.start, command)
                break
            except ValueError as error:
                print(f"Try again: {error}")

        elapsed = time.time() - start_time
        success = end_position == challenge.target
        update_stats(progress["lessons"][lesson.lesson_id], success, elapsed)
        update_stats(progress["overall"], success, elapsed)
        unlocked = maybe_unlock_next(progress, lesson.lesson_id)
        save_progress(progress)

        print()
        if success:
            print(f"Correct. {command} landed on the target in {elapsed:.1f}s.")
        else:
            print(f"Not quite. {command} landed on line {end_position.line + 1}, col {end_position.col + 1}.")
            print(f"Target was line {challenge.target.line + 1}, col {challenge.target.col + 1}.")
            print(f"One clean answer was: {challenge.solution}")
        if unlocked:
            print()
            print(f"Unlocked: {unlocked}")
        print()
        next_step = input("Press Enter for another challenge, or type menu to leave: ").strip().lower()
        if next_step == "menu":
            return


def reset_progress() -> dict:
    progress = default_progress()
    save_progress(progress)
    return progress


def main_menu() -> None:
    progress = load_progress()
    while True:
        clear_screen()
        print_header(progress)
        current = lesson_by_id(progress["current_lesson"])
        print(f"Current lesson: {current.title}")
        print()
        print("1. Continue current lesson")
        print("2. Choose lesson")
        print("3. View progress")
        print("4. Reset progress")
        print("5. Quit")
        print()
        choice = input("Select an option: ").strip().lower()

        if choice == "1":
            run_lesson(progress, progress["current_lesson"])
            progress = load_progress()
        elif choice == "2":
            selected = choose_lesson(progress)
            if selected:
                run_lesson(progress, selected)
                progress = load_progress()
        elif choice == "3":
            show_progress(progress)
            progress = load_progress()
        elif choice == "4":
            confirm = input("Reset all saved progress? [y/N] ").strip().lower()
            if confirm == "y":
                progress = reset_progress()
        elif choice == "5":
            clear_screen()
            print("See you next session.")
            return


def run_self_test() -> None:
    lines = ["alpha beta gamma", "delta epsilon zeta", "eta theta iota"]
    assert execute_motion(lines, Position(0, 0), "w") == Position(0, 6)
    assert execute_motion(lines, Position(0, 6), "b") == Position(0, 0)
    assert execute_motion(lines, Position(0, 6), "e") == Position(0, 9)
    assert execute_motion(lines, Position(0, 0), "2w") == Position(0, 11)
    assert execute_motion(lines, Position(0, 0), "j") == Position(1, 0)
    assert execute_motion(lines, Position(1, 5), "k") == Position(0, 5)
    assert execute_motion(lines, Position(1, 5), "0") == Position(1, 0)
    assert execute_motion(lines, Position(1, 5), "$") == Position(1, len(lines[1]) - 1)
    assert execute_motion(lines, Position(1, 5), "gg") == Position(0, 0)
    assert execute_motion(lines, Position(0, 5), "G") == Position(2, 0)
    assert execute_motion(lines, Position(2, 0), "2gg") == Position(1, 0)
    assert execute_motion(lines, Position(0, 0), "3G") == Position(2, 0)
    print("Self-test passed.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        run_self_test()
    else:
        try:
            main_menu()
        except KeyboardInterrupt:
            clear_screen()
            print("Session ended.")
