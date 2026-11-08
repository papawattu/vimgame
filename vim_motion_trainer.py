"""Vim Motion Trainer - a live, keystroke-driven terminal game for learning Vim motions.

Every key you press moves the cursor immediately, just like in Vim. Reach the
target in as few keystrokes as possible: a solver works out the optimal ("par")
keystroke count for each target, and you earn stars for matching it.
"""

from __future__ import annotations

import curses
import heapq
import itertools
import json
import locale
import os
import random
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


PROGRESS_PATH = Path.home() / ".vim_motion_trainer_progress.json"
CHALLENGES_PER_ROUND = 8
SPRINT_SECONDS = 60
QUICK_LEARN_SECONDS = 120
UNLOCK_ATTEMPTS = 5
UNLOCK_EFFICIENCY = 0.7
MIN_HEIGHT, MIN_WIDTH = 20, 60

MOTIONS = ("h", "j", "k", "l", "w", "b", "e", "0", "$", "gg", "G")
WANT_EOL = 10**9  # "desired column" after $: stick to end of line on j/k


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Position:
    line: int
    col: int


@dataclass(frozen=True)
class Cursor:
    """A cursor position plus Vim's remembered column (curswant) for j/k."""

    pos: Position
    want: int

    @classmethod
    def at(cls, pos: Position) -> "Cursor":
        return cls(pos, pos.col)


@dataclass(frozen=True)
class Challenge:
    lines: list[str]
    start: Position
    target: Position
    prompt: str
    hint: str
    solution: str  # the motion the lesson is teaching; the solver finds the true optimum


@dataclass(frozen=True)
class Lesson:
    lesson_id: str
    title: str
    description: str
    commands: tuple[str, ...]
    generator: Callable[[], Challenge]


REFERENCE = {
    "h": "left one character",
    "j": "down one line (remembers your column)",
    "k": "up one line (remembers your column)",
    "l": "right one character",
    "w": "start of next word",
    "b": "start of previous word",
    "e": "end of word (always moves forward)",
    "0": "start of line",
    "$": "end of line (2$ = end of next line)",
    "gg": "first line, or line N with Ngg",
    "G": "last line, or line N with NG",
}


SINGLE_LINES = [
    "calm motions build confidence",
    "small steps become muscle memory",
    "vim rewards precise movement",
    "steady practice beats guessing",
    "focus on one motion at a time",
    "think in words not characters",
    "every keystroke has a cost",
    "fingers rest on the home row",
]

STACKED_LINES = [
    ["alpha lane", "bravo lane", "charlie run", "delta path"],
    ["north gate", "south gate", "east ridge", "west ridge"],
    ["amber note", "bronze note", "copper note", "silver note"],
    ["red planet", "blue comet", "green moon", "white star", "black hole"],
]

SPRINT_SNIPPETS = [
    [
        "def load(path):",
        "    with open(path) as fh:",
        "        data = json.load(fh)",
        '    return data.get("items", [])',
        'items = load("config.json")',
        'print(len(items), "items loaded")',
    ],
    [
        "for row in table.rows:",
        '    if row.status == "done":',
        "        total += row.score",
        "    else:",
        "        pending.append(row.id)",
        'print(f"total={total} left={len(pending)}")',
    ],
    [
        "the quick brown fox jumps over the lazy dog",
        "pack my box with five dozen liquor jugs",
        "how vexingly quick daft zebras jump",
        "sphinx of black quartz, judge my vow",
        "calm motions build lasting muscle memory",
    ],
    [
        "const user = await api.fetch(id);",
        "if (!user.active) {",
        '  log.warn("inactive user", user.id);',
        "  return null;",
        "}",
        "return { name: user.name, role: user.role };",
    ],
    [
        "server:",
        "  host: 0.0.0.0",
        "  port: 8080",
        "  workers: 4",
        "logging:",
        "  level: info",
        "  file: /var/log/app.log",
    ],
]


# --------------------------------------------------------------------------
# Motion engine (aims to match Vim's behaviour)
# --------------------------------------------------------------------------


def char_class(char: str) -> int:
    """Vim's word classes: 0 = blank, 1 = punctuation, 2 = keyword character."""
    if char.isspace():
        return 0
    if char.isalnum() or char == "_":
        return 2
    return 1


def last_col(lines: list[str], line: int) -> int:
    return max(0, len(lines[line]) - 1)


def first_non_blank(lines: list[str], line: int) -> int:
    text = lines[line]
    stripped = len(text) - len(text.lstrip())
    return min(stripped, last_col(lines, line))


def to_flat_index(lines: list[str], pos: Position) -> int:
    index = 0
    for line_no, line in enumerate(lines):
        if line_no == pos.line:
            return index + min(pos.col, max(0, len(line) - 1))
        index += len(line) + 1
    raise ValueError("Position is out of range")


def from_flat_index(lines: list[str], flat_index: int) -> Position:
    index = 0
    for line_no, line in enumerate(lines):
        next_index = index + len(line)
        if flat_index <= next_index:
            return Position(line_no, max(0, min(flat_index - index, len(line) - 1)))
        index = next_index + 1
    return Position(len(lines) - 1, last_col(lines, len(lines) - 1))


def move_w(text: str, index: int) -> int:
    size = len(text)
    cls = char_class(text[index])
    cursor = index
    if cls:
        while cursor < size and char_class(text[cursor]) == cls:
            cursor += 1
    while cursor < size and char_class(text[cursor]) == 0:
        cursor += 1
    if cursor >= size:
        # Vim stops on the last character of the buffer.
        cursor = size - 1
        while cursor > index and char_class(text[cursor]) == 0:
            cursor -= 1
    return cursor


def move_b(text: str, index: int) -> int:
    cursor = index - 1
    while cursor >= 0 and char_class(text[cursor]) == 0:
        cursor -= 1
    if cursor < 0:
        return 0
    cls = char_class(text[cursor])
    while cursor > 0 and char_class(text[cursor - 1]) == cls:
        cursor -= 1
    return cursor


def move_e(text: str, index: int) -> int:
    size = len(text)
    cursor = index + 1
    while cursor < size and char_class(text[cursor]) == 0:
        cursor += 1
    if cursor >= size:
        return index
    cls = char_class(text[cursor])
    while cursor + 1 < size and char_class(text[cursor + 1]) == cls:
        cursor += 1
    return cursor


def apply_motion(lines: list[str], text: str, cur: Cursor, count: int | None, motion: str) -> Cursor:
    """Apply one (count, motion) pair. `text` is "\\n".join(lines), passed in for speed."""
    repeats = count or 1
    line, col = cur.pos.line, cur.pos.col
    final_line = len(lines) - 1

    if motion == "h":
        col = max(0, col - repeats)
        return Cursor(Position(line, col), col)
    if motion == "l":
        col = min(last_col(lines, line), col + repeats)
        return Cursor(Position(line, col), col)
    if motion in ("j", "k"):
        step = repeats if motion == "j" else -repeats
        line = max(0, min(final_line, line + step))
        return Cursor(Position(line, min(cur.want, last_col(lines, line))), cur.want)
    if motion == "0":
        return Cursor(Position(line, 0), 0)
    if motion == "$":
        line = min(final_line, line + repeats - 1)
        return Cursor(Position(line, last_col(lines, line)), WANT_EOL)
    if motion in ("gg", "G"):
        if count is None:
            line = 0 if motion == "gg" else final_line
        else:
            line = max(0, min(final_line, count - 1))
        col = first_non_blank(lines, line)
        return Cursor(Position(line, col), col)
    if motion in ("w", "b", "e"):
        mover = {"w": move_w, "b": move_b, "e": move_e}[motion]
        flat = to_flat_index(lines, cur.pos)
        for _ in range(repeats):
            flat = mover(text, flat)
        pos = from_flat_index(lines, flat)
        return Cursor(pos, pos.col)
    raise ValueError(f"Unsupported motion: {motion}")


def parse_command(command: str) -> list[tuple[int | None, str]]:
    buffer = KeyBuffer()
    tokens: list[tuple[int | None, str]] = []
    for char in command.replace(" ", ""):
        token = buffer.feed(char)
        if token:
            tokens.append(token)
    if buffer.pending:
        raise ValueError(f"Incomplete motion: {buffer.pending}")
    if not tokens:
        raise ValueError("Enter a motion like l, 2w, $, gg, or G.")
    return tokens


def execute_motion(lines: list[str], start: Position, command: str) -> Position:
    text = "\n".join(lines)
    cur = Cursor.at(start)
    for count, motion in parse_command(command):
        cur = apply_motion(lines, text, cur, count, motion)
    return cur.pos


class KeyBuffer:
    """Turns individual keypresses into (count, motion) commands, like Vim's normal mode."""

    MAX_COUNT_DIGITS = 3

    def __init__(self) -> None:
        self.count = ""
        self.g_pending = False

    @property
    def pending(self) -> str:
        return self.count + ("g" if self.g_pending else "")

    def clear(self) -> None:
        self.count = ""
        self.g_pending = False

    def _take_count(self) -> int | None:
        count = int(self.count) if self.count else None
        self.count = ""
        return count

    def feed(self, char: str) -> tuple[int | None, str] | None:
        if self.g_pending:
            self.g_pending = False
            if char == "g":
                return self._take_count(), "gg"
            self.clear()
            raise ValueError(f"g{char} isn't a motion here - did you mean gg?")
        if char.isdigit() and (char != "0" or self.count):
            if len(self.count) < self.MAX_COUNT_DIGITS:
                self.count += char
            return None
        if char == "g":
            self.g_pending = True
            return None
        if char in MOTIONS:
            return self._take_count(), char
        self.clear()
        raise ValueError(f"{char!r} isn't a supported motion")


def command_label(count: int | None, motion: str) -> str:
    return f"{count}{motion}" if count is not None else motion


# --------------------------------------------------------------------------
# Solver: fewest keystrokes to every reachable position
# --------------------------------------------------------------------------


def motion_options(allowed: tuple[str, ...] | set[str], line_count: int) -> list[tuple[int | None, str, str]]:
    options: list[tuple[int | None, str, str]] = []
    for motion in MOTIONS:
        if motion not in allowed:
            continue
        options.append((None, motion, motion))
        if motion == "0":
            continue
        counts = range(1, line_count + 1) if motion in ("gg", "G") else range(2, 10)
        options.extend((count, motion, f"{count}{motion}") for count in counts)
    return options


def solve(lines: list[str], start: Cursor, allowed) -> dict[Position, tuple[int, str]]:
    """Dijkstra over cursor states. Returns {position: (keystrokes, optimal command string)}."""
    text = "\n".join(lines)
    options = motion_options(allowed, len(lines))
    best: dict[Cursor, int] = {start: 0}
    found: dict[Position, tuple[int, str]] = {}
    tie = itertools.count()
    heap: list[tuple[int, int, str, Cursor]] = [(0, next(tie), "", start)]
    while heap:
        cost, _, keys, cur = heapq.heappop(heap)
        if best.get(cur, cost) < cost:
            continue
        found.setdefault(cur.pos, (cost, keys))
        for count, motion, label in options:
            nxt = apply_motion(lines, text, cur, count, motion)
            new_cost = cost + len(label)
            if new_cost < best.get(nxt, new_cost + 1):
                best[nxt] = new_cost
                heapq.heappush(heap, (new_cost, next(tie), f"{keys} {label}".strip(), nxt))
    return found


def rate(keys: int, par: int) -> int:
    if keys <= par:
        return 3
    if keys <= par + 2:
        return 2
    return 1


def stars_text(stars: int) -> str:
    return "★" * stars + "☆" * (3 - stars)


# --------------------------------------------------------------------------
# Lesson challenge generators
# --------------------------------------------------------------------------


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
    target_col = start_col
    while target_col == start_col:
        target_col = max(0, min(len(line) - 1, start_col + random.choice([-4, -3, -2, -1, 1, 2, 3, 4])))
    steps = abs(target_col - start_col)
    motion = "l" if target_col > start_col else "h"
    return Challenge(
        lines=[line],
        start=Position(0, start_col),
        target=Position(0, target_col),
        prompt="Move to the target on the same line using h and l.",
        hint="h goes left, l goes right. A count repeats the move: 3l is two keys instead of three.",
        solution=f"{steps}{motion}" if steps > 1 else motion,
    )


def challenge_up_down() -> Challenge:
    lines = random.choice(STACKED_LINES)
    width = min(len(line) for line in lines)
    col = random.randint(1, width - 3)
    start_line = random.randint(0, len(lines) - 1)
    target_line = start_line
    while target_line == start_line:
        target_line = max(0, min(len(lines) - 1, start_line + random.choice([-3, -2, -1, 1, 2, 3])))
    steps = abs(target_line - start_line)
    motion = "j" if target_line > start_line else "k"
    return Challenge(
        lines=lines,
        start=Position(start_line, col),
        target=Position(target_line, col),
        prompt="Move vertically to the target using j and k.",
        hint="j moves down, k moves up. Counts work here too, like 2j.",
        solution=f"{steps}{motion}" if steps > 1 else motion,
    )


def challenge_word_forward() -> Challenge:
    line = random.choice(SINGLE_LINES)
    starts, _ = motion_word_positions(line)
    step = random.randint(1, min(3, len(starts) - 1))
    start_index = random.randint(0, len(starts) - step - 1)
    return Challenge(
        lines=[line],
        start=Position(0, starts[start_index]),
        target=Position(0, starts[start_index + step]),
        prompt="Jump forward to the start of a word with w.",
        hint="w lands on the first character of the next word. 2w skips two.",
        solution=f"{step}w" if step > 1 else "w",
    )


def challenge_word_back() -> Challenge:
    line = random.choice(SINGLE_LINES)
    starts, _ = motion_word_positions(line)
    step = random.randint(1, min(3, len(starts) - 1))
    start_index = random.randint(step, len(starts) - 1)
    return Challenge(
        lines=[line],
        start=Position(0, starts[start_index]),
        target=Position(0, starts[start_index - step]),
        prompt="Jump back to the start of a word with b.",
        hint="b moves to the beginning of the word to your left. 2b goes two words back.",
        solution=f"{step}b" if step > 1 else "b",
    )


def challenge_word_end() -> Challenge:
    line = random.choice(SINGLE_LINES)
    starts, ends = motion_word_positions(line)
    # Start mid-word or on a word start, and aim for the end of this or a later word.
    start_index = random.randint(0, len(starts) - 2)
    step = random.randint(0, min(2, len(starts) - start_index - 1))
    start_col = starts[start_index]
    if ends[start_index] - starts[start_index] >= 2 and random.random() < 0.4:
        start_col += 1
    target_col = ends[start_index + step]
    if target_col == start_col:
        target_col = ends[start_index + step + 1]
    return Challenge(
        lines=[line],
        start=Position(0, start_col),
        target=Position(0, target_col),
        prompt="Land on the end of a word with e.",
        hint="e lands on the last character of a word. If you're already there, it goes to the next word's end.",
        solution="e" if step == 0 else f"{step + 1}e",
    )


def challenge_line_edges() -> Challenge:
    line = random.choice(SINGLE_LINES)
    start_col = random.randint(4, len(line) - 5)
    if random.choice([True, False]):
        return Challenge([line], Position(0, start_col), Position(0, 0),
                         "Snap to the start of the line.", "0 jumps straight to column 1.", "0")
    return Challenge([line], Position(0, start_col), Position(0, len(line) - 1),
                     "Snap to the end of the line.", "$ lands on the last character of the line.", "$")


def challenge_counts() -> Challenge:
    choice = random.choice(["horizontal", "vertical", "word"])
    if choice == "horizontal":
        line = random.choice(SINGLE_LINES)
        count = random.randint(2, 7)
        start_col = random.randint(0, len(line) - count - 2)
        return Challenge(
            lines=[line],
            start=Position(0, start_col),
            target=Position(0, start_col + count),
            prompt="Reach the target in as few keystrokes as you can.",
            hint="Counts come before the motion, like 4l - but sometimes a word motion is shorter.",
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
    count = random.randint(2, min(4, len(starts) - 1))
    start_index = random.randint(0, len(starts) - count - 1)
    return Challenge(
        lines=[line],
        start=Position(0, starts[start_index]),
        target=Position(0, starts[start_index + count]),
        prompt="Use a counted word motion to reach the target.",
        hint="Counts also work with words, like 3w.",
        solution=f"{count}w",
    )


def challenge_file_jumps() -> Challenge:
    lines = [
        "first checkpoint",
        "second checkpoint",
        "third checkpoint",
        "fourth checkpoint",
        "fifth checkpoint",
        "sixth checkpoint",
        "final checkpoint",
    ]
    start_line = random.randint(1, len(lines) - 2)
    target_line = start_line
    while abs(target_line - start_line) < 2:
        target_line = random.choice([0, len(lines) - 1, random.randint(0, len(lines) - 1)])
    if target_line == 0:
        solution, hint = "gg", "gg jumps to the first line. Add a count for a line number, like 3gg."
    elif target_line == len(lines) - 1:
        solution, hint = "G", "G jumps to the last line. A count turns it into a line number, like 4G."
    else:
        solution, hint = f"{target_line + 1}G", "A count before G or gg goes to that line number."
    return Challenge(
        lines=lines,
        start=Position(start_line, 0),
        target=Position(target_line, 0),
        prompt="Jump to the target line - the line numbers are there to help.",
        hint=hint,
        solution=solution,
    )


LESSONS = [
    Lesson("left_right", "Step 1: Left and Right",
           "Start with h and l so horizontal movement feels automatic.", ("h", "l"), challenge_left_right),
    Lesson("up_down", "Step 2: Up and Down",
           "Add j and k to move between lines while keeping your column.", ("h", "j", "k", "l"), challenge_up_down),
    Lesson("word_forward", "Step 3: Next Word",
           "Use w to stop crawling and start thinking in words.", ("h", "j", "k", "l", "w"), challenge_word_forward),
    Lesson("word_back", "Step 4: Previous Word",
           "Learn b so you can reposition without falling back to arrows.",
           ("h", "j", "k", "l", "w", "b"), challenge_word_back),
    Lesson("word_end", "Step 5: Word Ends",
           "Add e to land exactly where edits often begin.",
           ("h", "j", "k", "l", "w", "b", "e"), challenge_word_end),
    Lesson("line_edges", "Step 6: Line Edges",
           "Use 0 and $ to snap to the start or end of a line.",
           ("h", "j", "k", "l", "w", "b", "e", "0", "$"), challenge_line_edges),
    Lesson("counts", "Step 7: Counts",
           "Bundle repeated motions into one command for speed.",
           ("h", "j", "k", "l", "w", "b", "e", "0", "$"), challenge_counts),
    Lesson("file_jumps", "Step 8: Big Jumps",
           "Finish with gg and G so you can navigate whole files.", MOTIONS, challenge_file_jumps),
]

LESSON_INDEX = {lesson.lesson_id: index for index, lesson in enumerate(LESSONS)}


def lesson_by_id(lesson_id: str) -> Lesson:
    return LESSONS[LESSON_INDEX.get(lesson_id, 0)]


def make_challenge(lesson: Lesson) -> tuple[Challenge, int, str]:
    """Generate a challenge and compute its par with the lesson's allowed motions."""
    for _ in range(100):
        challenge = lesson.generator()
        if challenge.start == challenge.target:
            continue
        result = solve(challenge.lines, Cursor.at(challenge.start), lesson.commands).get(challenge.target)
        if result:
            return challenge, result[0], result[1]
    raise RuntimeError(f"Could not generate a solvable challenge for {lesson.lesson_id}")


def pick_quick_lesson(progress: dict, rng: random.Random | None = None) -> Lesson:
    """Pick an unlocked lesson for Quick Learn, favouring the ones with the lowest par rate."""
    rng = rng or random
    unlocked = [lesson for lesson in LESSONS if lesson.lesson_id in progress["unlocked_lessons"]]
    weights = []
    for lesson in unlocked:
        stats = progress["lessons"][lesson.lesson_id]
        # Untried lessons count as weak; well-practised ones still turn up occasionally.
        rate_ = accuracy(stats) if int(stats["attempts"]) else 0.0
        weights.append(0.15 + (1.0 - rate_))
    return rng.choices(unlocked, weights=weights, k=1)[0]


# --------------------------------------------------------------------------
# Real-world coding scenarios and the coach
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Step:
    task: str  # what you're trying to do, in editing terms
    line: int  # 0-based line of the target
    find: str  # text on that line to land on
    at: str = "start"  # "start" or "end" of `find`
    why: str = ""  # what you'd do next in a real edit


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    title: str
    language: str
    lines: list[str]
    steps: tuple[Step, ...]


LANGUAGES = ("HTML", "JavaScript", "CSS", "Python", "Java", "Go", "C/C++", "Shell", "YAML", "JSON")

SCENARIOS = [
    Scenario("html_page", "Tidy up a landing page", "HTML", [
        "<!doctype html>",
        '<html lang="en">',
        "  <head>",
        "    <title>My Page</title>",
        "  </head>",
        "  <body>",
        '    <a href="/about" class="nav">About us</a>',
        "  </body>",
        "</html>",
    ], (
        Step("Fix the page title: land on `My`.", 3, "My",
             why="Then `cit` changes everything inside the tag."),
        Step("Change the link target: land on `about` in the href.", 6, "about",
             why='Then `ci"` swaps the whole URL.'),
        Step("Rename the link's class: land on `nav`.", 6, "nav",
             why="Then `ciw` and the new class name."),
        Step("Change the document language: land on `en`.", 1, "en",
             why="Then `ciw` fr."),
        Step("Jump to `html` in the closing tag.", 8, "html",
             why="Then `gg=G` would re-indent the whole page."),
    )),
    Scenario("js_config", "Change the dev server config", "JavaScript", [
        "const config = {",
        '  host: "localhost",',
        "  port: 3000,",
        "  debug: false,",
        "};",
        "export default config;",
    ], (
        Step("The port is wrong. Jump to 3000.", 2, "3000",
             why="Then `ciw` 8080 - or 5080 Ctrl-A to add to it."),
        Step("Turn debugging on: land on `false`.", 3, "false",
             why="Then `ciw` true."),
        Step("Change the host: land on `localhost`.", 1, "localhost",
             why='Then `ci"` replaces everything inside the quotes.'),
        Step("Rename the export: land on `config` on the last line.", 5, "config",
             why="Then `ciw` - press * first to find every use."),
    )),
    Scenario("js_fetch", "Harden an async fetch", "JavaScript", [
        "async function loadUser(id) {",
        "  const res = await fetch(`/api/users/${id}`);",
        '  if (!res.ok) throw new Error("load failed");',
        "  return res.json();",
        "}",
    ], (
        Step("Point it at another endpoint: land on `users`.", 1, "users",
             why="Then `ciw` and the new resource name."),
        Step("Improve the error: land on `load` in the message.", 2, "load",
             why='Then `ci"` rewrites the whole string.'),
        Step("Land on the function name `loadUser`.", 0, "loadUser",
             why="Then `*` jumps to its next use."),
        Step("Land on `json` in the return line.", 3, "json",
             why="Then `ciw` text if the API returns plain text."),
    )),
    Scenario("css_card", "Restyle a card component", "CSS", [
        ".card {",
        "  display: flex;",
        "  padding: 16px 24px;",
        "  border-radius: 8px;",
        "  color: #333;",
        "}",
        ".card:hover {",
        "  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2);",
        "}",
    ], (
        Step("Tighten the padding: land on 24px.", 2, "24px",
             why="Then `ciw` - 24px is one word, digits and unit together."),
        Step("Change the colour: land on the # of #333.", 4, "#",
             why="Then `cW` replaces the whole value, # included."),
        Step("Switch the layout: land on `flex`.", 1, "flex",
             why="Then `ciw` grid."),
        Step("Soften the shadow: land on 0.2.", 7, "0.2",
             why="Then `cW` replaces 0.2 in one go."),
    )),
    Scenario("py_typo", "Fix a typo in average()", "Python", [
        "def average(values):",
        "    total = 0",
        "    for v in values:",
        "        total += v",
        "    return total / len(value)",
    ], (
        Step("A NameError points at the last line - jump there.", 4, "return",
             why="G lands on the first non-blank, ready to read the line."),
        Step("Land on the misspelt `value` inside len().", 4, "value",
             why="Then `ea` would append the missing s."),
        Step("Check the closing paren at the end of the line.", 4, ")",
             why="Then `i` lets you type just before the paren."),
        Step("Back to the top: land on the function name.", 0, "average",
             why="Then `ciw` would rename it."),
        Step("Now the loop variable `v` on line 3.", 2, "v",
             why="Then `*` would highlight every use of v."),
    )),
    Scenario("py_fetch", "Tune an HTTP helper", "Python", [
        "import requests",
        "def fetch(url, timeout=5):",
        "    resp = requests.get(url, timeout=timeout)",
        "    resp.raise_for_status()",
        "    return resp.json()",
    ], (
        Step("Raise the default timeout: land on the 5.", 1, "5",
             why="Then `r9` replaces that one character."),
        Step("Land on `raise_for_status`.", 3, "raise_for_status",
             why="Underscores are word characters, so w treats it as one word."),
        Step("Land on `get` in requests.get.", 2, "get",
             why="The . is its own word - count it when you use w."),
        Step("Go to the import on the first line.", 0, "import",
             why="Then `o` opens a new line below for another import."),
    )),
    Scenario("java_greeter", "Refactor a small class", "Java", [
        "public class Greeter {",
        "    private final String name;",
        "    public Greeter(String name) {",
        "        this.name = name;",
        "    }",
        "    public String greet() {",
        '        return "Hello, " + name + "!";',
        "    }",
        "}",
    ], (
        Step("Make the greeting friendlier: land on `Hello`.", 6, "Hello",
             why='Then `ci"` rewrites the string.'),
        Step("This field should be mutable: land on `final`.", 1, "final",
             why="Then `dw` deletes the word and the space after it."),
        Step("Rename the method: land on `greet`.", 5, "greet",
             why="Then `ciw` - and remember to update its callers."),
        Step("Go to the class name on line 1.", 0, "Greeter",
             why="Then `ciw` renames the class - and the file name must match!"),
    )),
    Scenario("go_handler", "Tidy an HTTP handler", "Go", [
        "func handle(w http.ResponseWriter, r *http.Request) {",
        '    id := r.URL.Query().Get("id")',
        '    if id == "" {',
        '        http.Error(w, "missing id", 400)',
        "        return",
        "    }",
        '    fmt.Fprintf(w, "hello %s", id)',
        "}",
    ], (
        Step("Replace the magic number: land on 400.", 3, "400",
             why="Then `ciw` http.StatusBadRequest."),
        Step("Improve the error text: land on `missing`.", 3, "missing",
             why='Then `ci"` rewrites the whole message.'),
        Step("Rename the handler: land on `handle`.", 0, "handle",
             why="Then `ciw` - punctuation like ( is its own word for w."),
        Step("Check the greeting: land on `hello`.", 6, "hello",
             why='Then `ci"` changes the greeting text.'),
        Step("Go to the closing brace at the very end.", 7, "}",
             why="Then `o` opens a new line below for the next function."),
    )),
    Scenario("c_loop", "Fix an off-by-one in C", "C/C++", [
        "#include <stdio.h>",
        "int main(void) {",
        "    int total = 0;",
        "    for (int i = 0; i < 10; i++) {",
        "        total += i;",
        "    }",
        '    printf("total: %d\\n", total);',
        "    return 0;",
        "}",
    ], (
        Step("Off by one? Land on the loop bound 10.", 3, "10",
             why="Then `ciw` 11 - or Ctrl-A to increment it."),
        Step("Land on `stdio` in the include.", 0, "stdio",
             why="< is punctuation, so it counts as its own word for w."),
        Step("Change the format: land on `total` inside the quotes.", 6, "total",
             why='Then `ci"` rewrites the whole format string.'),
        Step("Land on the 0 in `return 0`.", 7, "0",
             why="Then `r1` makes it return an error code."),
    )),
    Scenario("cpp_split", "Finish a C++ helper", "C/C++", [
        "#include <vector>",
        "#include <string>",
        "std::vector<std::string> split(std::string s) {",
        "  std::vector<std::string> out;",
        "  // TODO: handle empty input",
        "  return out;",
        "}",
    ], (
        Step("Find the TODO and land on it.", 4, "TODO",
             why="Then `cc` replaces the whole comment line."),
        Step("Land on `split`, the function name.", 2, "split",
             why="Then `ciw` to rename it."),
        Step("Land on `out` in the return line.", 5, "out",
             why="Then `*` highlights every use."),
        Step("Back to the first include: land on `vector`.", 0, "vector",
             why="# and < are punctuation, so each run of them is a word for w."),
    )),
    Scenario("sh_script", "Edit a shell script", "Shell", [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "NAME=${1:-world}",
        "for i in 1 2 3; do",
        '  echo "hello $NAME ($i)"',
        "done",
    ], (
        Step("Change the default name: land on `world`.", 2, "world",
             why="Then `ciw` and the new default."),
        Step("Loop more times: land on the 3.", 3, "3",
             why="Then `a 4 5` appends more values after it."),
        Step("Land on `echo` to swap it for printf.", 4, "echo",
             why="Then `cw` printf."),
        Step("Check the shell options: land on the end of `pipefail`.", 1, "pipefail", at="end",
             why="Then `a` appends another option after pipefail."),
    )),
    Scenario("k8s_deploy", "Scale up a Deployment", "YAML", [
        "apiVersion: apps/v1",
        "kind: Deployment",
        "metadata:",
        "  name: web",
        "spec:",
        "  replicas: 2",
        "  template:",
        "    spec:",
        "      containers: [{image: nginx:1.25}]",
    ], (
        Step("Scale up: land on the replica count.", 5, "2",
             why="Then `4` Ctrl-A bumps it from 2 to 6."),
        Step("Bump the image tag: land on 1.25.", 8, "1.25",
             why="Then `cW` swaps the whole tag in one go."),
        Step("Rename the app: land on `web`.", 3, "web",
             why="Then `ciw` and the new name."),
        Step("Check the kind: land on the end of `Deployment`.", 1, "Deployment", at="end",
             why="Then `ciw` StatefulSet if it needs stable storage."),
    )),
    Scenario("json_package", "Update a package manifest", "JSON", [
        "{",
        '  "name": "vimgame",',
        '  "version": "1.2.0",',
        '  "scripts": {',
        '    "test": "pytest -q",',
        '    "start": "python3 main.py"',
        "  },",
        '  "private": true',
        "}",
    ], (
        Step("Bump the minor version: land on the 2 in 1.2.0.", 2, "2",
             why="Then `r3` makes it 1.3.0."),
        Step("Make the tests verbose: land on the q in -q.", 4, "q",
             why="Then `rv` turns -q into -v."),
        Step("Publish it: land on `true`.", 7, "true",
             why="Then `ciw` false."),
        Step("Rename the package: land on `vimgame`.", 1, "vimgame",
             why='Then `ci"` replaces the whole name.'),
        Step("Change the entry point: land on `main`.", 5, "main",
             why="Then `ciw` app - the .py stays put."),
    )),
]

SCENARIO_INDEX = {scenario.scenario_id: scenario for scenario in SCENARIOS}


def step_target(lines: list[str], step: Step) -> Position:
    col = lines[step.line].index(step.find)
    if step.at == "end":
        col += len(step.find) - 1
    return Position(step.line, col)


def scenario_start(lines: list[str]) -> Position:
    return Position(0, first_non_blank(lines, 0))


def coach_plan(lines: list[str], cursor: Cursor, target: Position, allowed) -> list[str]:
    """The optimal commands from wherever the cursor is right now."""
    found = solve(lines, cursor, allowed).get(target)
    return found[1].split() if found else []


def explain_command(label: str) -> str:
    """Describe a single command like `3w` or `2G` in plain English."""
    ((count, motion),) = parse_command(label)
    n = count or 1
    plural = "" if n == 1 else "s"
    phrases = {
        "h": f"left {n} character{plural}",
        "l": f"right {n} character{plural}",
        "j": f"down {n} line{plural}",
        "k": f"up {n} line{plural}",
        "w": f"forward {n} word{plural}",
        "b": f"back {n} word{plural}",
        "e": "to the end of the word" if n == 1 else f"to the end of the word {n - 1} ahead",
        "0": "to the start of the line",
        "$": "to the end of the line" if n == 1 else f"to the end of the line {n - 1} down",
        "gg": "to the first line" if count is None else f"to line {count}",
        "G": "to the last line" if count is None else f"to line {count}",
    }
    return phrases[motion]


def sprint_motions(progress: dict) -> tuple[str, ...]:
    unlocked = [lesson for lesson in LESSONS if lesson.lesson_id in progress["unlocked_lessons"]]
    return unlocked[-1].commands if unlocked else LESSONS[0].commands


def pick_sprint_target(lines: list[str], cursor: Cursor, allowed) -> tuple[Position, int, str]:
    reachable = solve(lines, cursor, allowed)
    candidates = [
        (pos, cost, keys)
        for pos, (cost, keys) in reachable.items()
        if pos != cursor.pos and lines[pos.line][pos.col] != " "
    ]
    interesting = [c for c in candidates if 2 <= c[1] <= 6] or candidates
    return random.choice(interesting)


# --------------------------------------------------------------------------
# Progress persistence and stats
# --------------------------------------------------------------------------


def empty_lesson_stats() -> dict[str, float | int]:
    return {
        "attempts": 0,
        "successes": 0,
        "current_streak": 0,
        "best_streak": 0,
        "total_time": 0.0,
        "stars": 0,
    }


def default_progress() -> dict:
    return {
        "current_lesson": LESSONS[0].lesson_id,
        "unlocked_lessons": [LESSONS[0].lesson_id],
        "overall": empty_lesson_stats(),
        "lessons": {lesson.lesson_id: empty_lesson_stats() for lesson in LESSONS},
        "sprint_best": 0,
        "scenarios": {},  # scenario_id -> best stars
    }


def load_progress() -> dict:
    progress = default_progress()
    if not PROGRESS_PATH.exists():
        return progress
    try:
        data = json.loads(PROGRESS_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return progress

    if data.get("current_lesson") in LESSON_INDEX:
        progress["current_lesson"] = data["current_lesson"]
    unlocked = [lid for lid in data.get("unlocked_lessons", []) if lid in LESSON_INDEX]
    progress["unlocked_lessons"] = list(dict.fromkeys([LESSONS[0].lesson_id, *unlocked]))
    progress["sprint_best"] = int(data.get("sprint_best", 0))
    progress["scenarios"] = {
        sid: int(best) for sid, best in data.get("scenarios", {}).items() if sid in SCENARIO_INDEX
    }

    overall = data.get("overall", {})
    for key in progress["overall"]:
        progress["overall"][key] = overall.get(key, progress["overall"][key])

    saved_lessons = data.get("lessons", {})
    for lesson in LESSONS:
        stats = saved_lessons.get(lesson.lesson_id, {})
        for key in progress["lessons"][lesson.lesson_id]:
            progress["lessons"][lesson.lesson_id][key] = stats.get(key, progress["lessons"][lesson.lesson_id][key])
    return progress


def save_progress(progress: dict) -> None:
    try:
        PROGRESS_PATH.write_text(json.dumps(progress, indent=2))
    except OSError:
        pass  # Progress is a nicety; never crash the game over it.


def accuracy(stats: dict[str, float | int]) -> float:
    attempts = int(stats["attempts"])
    return float(stats["successes"]) / attempts if attempts else 0.0


def average_time(stats: dict[str, float | int]) -> float:
    attempts = int(stats["attempts"])
    return float(stats["total_time"]) / attempts if attempts else 0.0


def progress_bar(ratio: float, width: int = 18) -> str:
    filled = int(width * max(0.0, min(1.0, ratio)))
    return "█" * filled + "░" * (width - filled)


def update_stats(stats: dict[str, float | int], success: bool, elapsed: float, stars: int = 0) -> None:
    stats["attempts"] = int(stats["attempts"]) + 1
    stats["total_time"] = float(stats["total_time"]) + elapsed
    stats["stars"] = int(stats.get("stars", 0)) + stars
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
    if int(stats["attempts"]) < UNLOCK_ATTEMPTS or accuracy(stats) < UNLOCK_EFFICIENCY:
        return None
    next_lesson = LESSONS[lesson_number + 1]
    if next_lesson.lesson_id not in progress["unlocked_lessons"]:
        progress["unlocked_lessons"].append(next_lesson.lesson_id)
        return next_lesson.title
    return None


def unlock_all_lessons(progress: dict) -> None:
    for lesson in LESSONS:
        if lesson.lesson_id not in progress["unlocked_lessons"]:
            progress["unlocked_lessons"].append(lesson.lesson_id)
    save_progress(progress)


# --------------------------------------------------------------------------
# Curses UI
# --------------------------------------------------------------------------

ENTER_KEYS = {"\n", "\r", curses.KEY_ENTER}
ESC = "\x1b"
ARROW_KEYS = {curses.KEY_LEFT, curses.KEY_RIGHT, curses.KEY_UP, curses.KEY_DOWN}


@dataclass
class PlayResult:
    status: str  # "hit", "quit" or "timeout"
    cursor: Cursor
    keys: int = 0
    elapsed: float = 0.0
    commands: list[str] = field(default_factory=list)
    coached: bool = False  # the coach was showing when a motion was made
    coach_on: bool = False  # coach state when the target was reached (carried to the next one)


class Screen:
    def __init__(self, scr) -> None:
        self.scr = scr
        scr.keypad(True)
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        self.attr = {
            "target": curses.A_BOLD | curses.A_UNDERLINE,
            "cursor": curses.A_REVERSE | curses.A_BOLD,
            "accent": curses.A_BOLD,
            "good": curses.A_BOLD,
            "warn": curses.A_BOLD,
            "bad": curses.A_BOLD,
            "dim": curses.A_DIM,
            "sel": curses.A_REVERSE,
        }
        if curses.has_colors():
            curses.start_color()
            try:
                curses.use_default_colors()
                bg = -1
            except curses.error:
                bg = curses.COLOR_BLACK
            pairs = {
                "target": (curses.COLOR_BLACK, curses.COLOR_GREEN, curses.A_BOLD),
                "cursor": (curses.COLOR_BLACK, curses.COLOR_YELLOW, curses.A_BOLD),
                "accent": (curses.COLOR_CYAN, bg, curses.A_BOLD),
                "good": (curses.COLOR_GREEN, bg, curses.A_BOLD),
                "warn": (curses.COLOR_YELLOW, bg, curses.A_BOLD),
                "bad": (curses.COLOR_RED, bg, curses.A_BOLD),
            }
            for number, (name, (fg, pair_bg, extra)) in enumerate(pairs.items(), start=1):
                curses.init_pair(number, fg, pair_bg)
                self.attr[name] = curses.color_pair(number) | extra

    @property
    def size(self) -> tuple[int, int]:
        return self.scr.getmaxyx()

    def put(self, y: int, x: int, text: str, style: str | int = 0) -> None:
        height, width = self.size
        if not 0 <= y < height or x >= width:
            return
        room = width - x - (1 if y == height - 1 else 0)
        attr = self.attr[style] if isinstance(style, str) else style
        try:
            self.scr.addstr(y, x, text[: max(0, room)], attr)
        except curses.error:
            pass

    def rule(self, y: int) -> None:
        self.put(y, 0, "─" * self.size[1], "dim")

    def begin(self) -> bool:
        """Clear the screen; return False (after drawing a warning) if it's too small."""
        self.scr.erase()
        height, width = self.size
        if height < MIN_HEIGHT or width < MIN_WIDTH:
            self.put(0, 0, f"Terminal too small: need {MIN_WIDTH}x{MIN_HEIGHT}, have {width}x{height}.", "warn")
            self.put(1, 0, "Resize the window, or press q to go back.")
            self.scr.refresh()
            return False
        return True

    def header(self, title: str, right: str = "") -> None:
        self.put(0, 1, "VIM MOTION TRAINER", "accent")
        self.put(0, 21, f"· {title}")
        if right:
            self.put(0, max(0, self.size[1] - len(right) - 2), right, "warn")
        self.rule(1)

    def footer(self, text: str) -> None:
        self.put(self.size[0] - 1, 1, text, "dim")

    def key(self, timeout_ms: int = -1) -> str | int | None:
        self.scr.timeout(timeout_ms)
        try:
            return self.scr.get_wch()
        except curses.error:
            return None

    def draw_buffer(self, top: int, lines: list[str], cursor: Position | None, target: Position | None) -> int:
        for line_no, line in enumerate(lines):
            y = top + line_no
            self.put(y, 1, f"{line_no + 1:>3} ", "dim")
            self.put(y, 6, line)
            if target and target.line == line_no:
                self.put(y, 6 + target.col, line[target.col] if target.col < len(line) else " ", "target")
            if cursor and cursor.line == line_no:
                self.put(y, 6 + cursor.col, line[cursor.col] if cursor.col < len(line) else " ", "cursor")
        return top + len(lines)


class App:
    def __init__(self, scr) -> None:
        self.ui = Screen(scr)
        self.progress = load_progress()

    # ---- generic screens -------------------------------------------------

    def header_right(self) -> str:
        return f"★ {self.progress['overall'].get('stars', 0)}   sprint best {self.progress['sprint_best']}"

    def menu(self, title: str, intro: list[str], items: list[tuple[str, str]], back_key: str | None = None) -> str | None:
        index = 0
        hotkeys = {key for key, _ in items}
        while True:
            if self.ui.begin():
                self.ui.header(title, self.header_right())
                y = 3
                for line in intro:
                    self.ui.put(y, 2, line, "dim")
                    y += 1
                y += 1 if intro else 0
                width = self.ui.size[1]
                for row, (key, label) in enumerate(items):
                    selected = row == index
                    text = f" {key}  {label}"
                    self.ui.put(y + row, 2, text.ljust(min(width - 4, 64)), "sel" if selected else 0)
                    self.ui.put(y + row, 3, key, "sel" if selected else "accent")
                self.ui.footer("j/k move · enter or l select · hotkey jumps · q back")
                self.ui.scr.refresh()
            key = self.ui.key()
            if key in ("j", curses.KEY_DOWN):
                index = (index + 1) % len(items)
            elif key in ("k", curses.KEY_UP):
                index = (index - 1) % len(items)
            elif key == "g":
                index = 0
            elif key == "G":
                index = len(items) - 1
            elif key in ENTER_KEYS or key in ("l", curses.KEY_RIGHT):
                return items[index][0]
            elif isinstance(key, str) and key in hotkeys:
                return key
            elif key in ("q", ESC, "h", curses.KEY_LEFT):
                return back_key

    def notice(self, title: str, lines: list[tuple[str, str | int]], footer: str = "press any key") -> str | int | None:
        while True:
            if self.ui.begin():
                self.ui.header(title, self.header_right())
                for row, (text, style) in enumerate(lines):
                    self.ui.put(3 + row, 2, text, style)
                self.ui.footer(footer)
                self.ui.scr.refresh()
            key = self.ui.key()
            if key != curses.KEY_RESIZE:
                return key

    def confirm(self, title: str, question: str) -> bool:
        return self.notice(title, [(question, "warn")], "y to confirm · any other key to cancel") in ("y", "Y")

    # ---- main flow ------------------------------------------------------

    def run(self) -> None:
        while True:
            current = lesson_by_id(self.progress["current_lesson"])
            choice = self.menu(
                "Main menu",
                [
                    "Move the cursor with real Vim keys. Reach the green target",
                    "in as few keystrokes as you can - par earns three stars.",
                ],
                [
                    ("c", f"Continue      {current.title}"),
                    ("o", "Choose lesson"),
                    ("t", f"Quick learn   {QUICK_LEARN_SECONDS // 60} minutes on your weak spots"),
                    ("w", "Real-world    edit real code with a coach"),
                    ("s", f"Sprint        {SPRINT_SECONDS}s time attack"),
                    ("p", "Progress"),
                    ("r", "Motion reference"),
                    ("x", "Reset progress"),
                    ("q", "Quit"),
                ],
                back_key="q",
            )
            if choice == "c":
                self.play_lesson(current.lesson_id)
            elif choice == "o":
                self.choose_lesson()
            elif choice == "t":
                self.quick_learn()
            elif choice == "w":
                self.real_world()
            elif choice == "s":
                self.sprint()
            elif choice == "p":
                self.show_progress()
            elif choice == "r":
                self.show_reference()
            elif choice == "x":
                if self.confirm("Reset", "Reset all saved progress, stars and sprint best? [y/N]"):
                    self.progress = default_progress()
                    save_progress(self.progress)
            elif choice == "q":
                return

    def choose_lesson(self) -> None:
        while True:
            items = []
            for number, lesson in enumerate(LESSONS, start=1):
                stats = self.progress["lessons"][lesson.lesson_id]
                if lesson.lesson_id in self.progress["unlocked_lessons"]:
                    status = f"★ {stats['stars']:<4} {accuracy(stats) * 100:3.0f}% par" if stats["attempts"] else "new"
                else:
                    status = "locked"
                items.append((str(number), f"{lesson.title:<24} {status}"))
            items.append(("u", "Unlock everything (expert mode)"))
            choice = self.menu(
                "Choose lesson",
                [f"Hit par on {UNLOCK_EFFICIENCY:.0%} of targets (min {UNLOCK_ATTEMPTS}) to unlock the next lesson."],
                items,
            )
            if choice is None:
                return
            if choice == "u":
                unlock_all_lessons(self.progress)
                continue
            lesson = LESSONS[int(choice) - 1]
            if lesson.lesson_id not in self.progress["unlocked_lessons"]:
                self.notice("Locked", [(f"{lesson.title} is still locked.", "warn"),
                                       ("Hit par more often in the previous lesson to open it.", 0)])
                continue
            self.play_lesson(lesson.lesson_id)
            return

    # ---- gameplay -------------------------------------------------------

    def play_target(
        self,
        title: str,
        info: Callable[[], str],
        lines: list[str],
        cursor: Cursor,
        target: Position,
        allowed: tuple[str, ...],
        par: int,
        prompt: str,
        hint: str | None = None,
        message: tuple[str, str] = ("", 0),
        deadline: float | None = None,
        tip: str | None = None,
        coach: bool | None = None,
    ) -> PlayResult:
        """Play one target. `coach`: None = no coach; False/True = available, starting off/on (toggle with c)."""
        buffer = KeyBuffer()
        coach_on = bool(coach)
        plan_for: Cursor | None = None
        plan: list[str] = []
        result = PlayResult("hit", cursor)
        started = time.monotonic()
        text = "\n".join(lines)
        msg_text, msg_style = message
        allowed_set = set(allowed)

        while True:
            if deadline is not None and time.monotonic() >= deadline:
                result.status = "timeout"
                break
            if self.ui.begin():
                self.ui.header(title, info())
                bottom = self.ui.draw_buffer(3, lines, result.cursor.pos, target)
                self.ui.rule(bottom + 1)
                self.ui.put(bottom + 2, 2, prompt)
                self.ui.put(bottom + 3, 2, "motions: " + " ".join(m for m in MOTIONS if m in allowed_set), "dim")
                keys_text = f"keys {result.keys}  par {par}"
                self.ui.put(bottom + 3, self.ui.size[1] - len(keys_text) - 2, keys_text,
                            "good" if result.keys <= par else "warn")
                if buffer.pending:
                    self.ui.put(bottom + 4, 2, f"pending: {buffer.pending}", "warn")
                self.ui.put(bottom + 5, 2, msg_text, msg_style)
                if coach_on:
                    if plan_for != result.cursor:
                        plan, plan_for = coach_plan(lines, result.cursor, target, allowed), result.cursor
                    self.draw_coach(bottom + 6, plan)
                elif tip:
                    self.ui.put(bottom + 6, 2, f"tip: {tip}", "accent")
                footer = ("? hint · " if hint else "") + ("c coach · " if coach is not None else "")
                self.ui.footer(footer + "esc clear pending · q quit to menu")
                self.ui.scr.refresh()

            key = self.ui.key(100 if deadline is not None else -1)
            if key is None or key == curses.KEY_RESIZE:
                continue
            if key in ARROW_KEYS:
                buffer.clear()
                msg_text, msg_style = "Arrow keys don't count here - use h j k l!", "bad"
                continue
            if not isinstance(key, str):
                continue
            if key == ESC:
                buffer.clear()
                msg_text = ""
                continue
            if key == "q" and not buffer.pending:
                result.status = "quit"
                break
            if key == "?" and hint:
                msg_text, msg_style = hint, "accent"
                continue
            if key == "c" and coach is not None and not buffer.pending:
                coach_on = not coach_on
                msg_text, msg_style = ("Coach on - follow the highlighted keys.", "accent") if coach_on \
                    else ("Coach off - you're on your own!", "accent")
                continue
            try:
                token = buffer.feed(key)
            except ValueError as error:
                msg_text, msg_style = str(error), "bad"
                continue
            if token is None:
                continue
            count, motion = token
            label = command_label(count, motion)
            if motion not in allowed_set:
                msg_text, msg_style = f"{motion} isn't unlocked in this lesson yet.", "bad"
                continue
            result.coached |= coach_on
            result.cursor = apply_motion(lines, text, result.cursor, count, motion)
            result.keys += len(label)
            result.commands.append(label)
            msg_text = ""
            if result.cursor.pos == target:
                break

        result.elapsed = time.monotonic() - started
        result.coach_on = coach_on
        return result

    def draw_coach(self, y: int, plan: list[str]) -> None:
        if not plan:
            return
        first = plan[0]
        self.ui.put(y, 2, "coach: press", "accent")
        self.ui.put(y, 15, f" {first} ", "cursor")
        note = f"  {explain_command(first)}"
        if len(plan) > 1:
            note += "   then " + " ".join(plan[1:])
        self.ui.put(y, 17 + len(first), note, "dim")

    def play_lesson(self, lesson_id: str) -> None:
        lesson = lesson_by_id(lesson_id)
        self.progress["current_lesson"] = lesson.lesson_id
        save_progress(self.progress)
        stats = self.progress["lessons"][lesson.lesson_id]
        round_stars, played, perfect = 0, 0, 0
        unlocked: list[str] = []

        for number in range(1, CHALLENGES_PER_ROUND + 1):
            challenge, par, optimal = make_challenge(lesson)
            info = lambda: f"{number}/{CHALLENGES_PER_ROUND}   ★ {round_stars}"  # noqa: E731
            result = self.play_target(
                lesson.title, info, challenge.lines, Cursor.at(challenge.start), challenge.target,
                lesson.commands, par, challenge.prompt, f"{challenge.hint}  (try: {challenge.solution})",
                coach=False,
            )
            if result.status != "hit":
                break

            stars = rate(result.keys, par)
            hit_par = result.keys <= par
            update_stats(stats, hit_par, result.elapsed, stars)
            update_stats(self.progress["overall"], hit_par, result.elapsed, stars)
            newly = maybe_unlock_next(self.progress, lesson.lesson_id)
            if newly:
                unlocked.append(newly)
            save_progress(self.progress)
            round_stars += stars
            played += 1
            perfect += hit_par

            if not self.show_feedback(lesson.title, info, challenge, result, par, optimal, stars, newly):
                break

        if played:
            lines: list[tuple[str, str | int]] = [
                (f"{lesson.title} - round complete" if played == CHALLENGES_PER_ROUND else f"{lesson.title} - round ended", "accent"),
                ("", 0),
                (f"Stars       {round_stars} / {played * 3}", "warn"),
                (f"Par hits    {perfect} / {played}", "good" if perfect == played else 0),
                (f"Lesson par rate  {accuracy(stats) * 100:.0f}%   best streak {stats['best_streak']}", 0),
            ]
            for title in unlocked:
                lines += [("", 0), (f"Unlocked: {title}", "good")]
            self.notice("Round summary", lines)

    def show_feedback(self, title, info, challenge, result, par, optimal, stars, unlocked) -> bool:
        """Show how the attempt went. Returns False if the player wants to stop."""
        if result.keys <= par:
            headline, style = f"{stars_text(stars)}  Par! {result.keys} key{'s' * (result.keys != 1)} in {result.elapsed:.1f}s", "good"
        else:
            headline, style = f"{stars_text(stars)}  Reached in {result.keys} keys - par is {par}", "warn"
        detail = [f"you:     {' '.join(result.commands)}", f"optimal: {optimal}"]
        if unlocked:
            detail.append(f"Unlocked: {unlocked}!")
        auto = result.keys <= par and not unlocked

        while True:
            if self.ui.begin():
                self.ui.header(title, info())
                bottom = self.ui.draw_buffer(3, challenge.lines, result.cursor.pos, None)
                self.ui.rule(bottom + 1)
                self.ui.put(bottom + 2, 2, headline, style)
                for row, line in enumerate(detail):
                    self.ui.put(bottom + 3 + row, 2, line, "good" if line.startswith("Unlocked") else "dim")
                self.ui.footer("any key: next target · q: menu")
                self.ui.scr.refresh()
            key = self.ui.key(900 if auto else -1)
            if key == curses.KEY_RESIZE:
                continue
            return key != "q"

    def real_world(self) -> None:
        while True:
            items = []
            for number, language in enumerate(LANGUAGES, start=1):
                scenarios = [sc for sc in SCENARIOS if sc.language == language]
                done = sum(sc.scenario_id in self.progress["scenarios"] for sc in scenarios)
                items.append((str(number), f"{language:<11} {done}/{len(scenarios)} scenarios done"))
            choice = self.menu("Real-world code", [
                "Short editing tasks on real code: the kind of jumps you make",
                "before a ciw or ci\". The coach shows the best next key from",
                "wherever you are - press c to hide it and go solo.",
            ], items)
            if choice is None:
                return
            self.choose_scenario(LANGUAGES[int(choice) - 1])

    def choose_scenario(self, language: str) -> None:
        scenarios = [sc for sc in SCENARIOS if sc.language == language]
        while True:
            if len(scenarios) == 1:
                choice = "1"
            else:
                items = []
                for number, sc in enumerate(scenarios, start=1):
                    best = self.progress["scenarios"].get(sc.scenario_id)
                    status = f"best ★ {best}/{len(sc.steps) * 3}" if best is not None else "new"
                    items.append((str(number), f"{sc.title:<30} {status}"))
                choice = self.menu(f"Real-world · {language}", [], items)
                if choice is None:
                    return
            if not self.play_scenario(scenarios[int(choice) - 1]) or len(scenarios) == 1:
                return

    def play_scenario(self, scenario: Scenario) -> bool:
        """Play every step of a scenario. Returns False if the player quit part-way."""
        lines = scenario.lines
        cursor = Cursor.at(scenario_start(lines))
        coach_on = True
        total, solo, pars = 0, 0, 0
        message: tuple[str, str] = ("", 0)
        steps = len(scenario.steps)
        title = f"{scenario.language} · {scenario.title}"

        for number, step in enumerate(scenario.steps, start=1):
            target = step_target(lines, step)
            par, optimal = solve(lines, cursor, MOTIONS)[target]
            info = lambda: f"step {number}/{steps}   ★ {total}"  # noqa: E731
            result = self.play_target(
                title, info, lines, cursor, target, MOTIONS, par, step.task,
                message=message, coach=coach_on,
            )
            if result.status != "hit":
                return False
            cursor, coach_on = result.cursor, result.coach_on
            stars = rate(result.keys, par)
            total += stars
            solo += not result.coached
            pars += result.keys <= par
            verdict = "par!" if result.keys <= par else f"{result.keys} keys, par {par} ({optimal})."
            message = (f"{stars_text(stars)} {verdict}  {step.why}", "good" if stars == 3 else "warn")

        best = self.progress["scenarios"].get(scenario.scenario_id)
        record = best is None or total > best
        if record:
            self.progress["scenarios"][scenario.scenario_id] = total
            save_progress(self.progress)
        lines_out: list[tuple[str, str | int]] = [
            (f"{title} - done!", "accent"),
            ("", 0),
            (message[0], message[1]),
            ("", 0),
            (f"Stars       {total} / {steps * 3}" + ("   new best!" if record and best is not None else ""), "warn"),
            (f"Par hits    {pars} / {steps}", 0),
            (f"Solo steps  {solo} / {steps}" + ("" if solo == steps else "   (try it again with the coach off: c)"),
             "good" if solo == steps else 0),
        ]
        self.notice("Scenario complete", lines_out)
        return True

    def quick_learn(self) -> None:
        """A 2-minute time box: tips always on, targets drawn from your weakest unlocked lessons."""
        intro = self.notice("Quick learn", [
            (f"{QUICK_LEARN_SECONDS // 60} minutes. Short drills from the lessons you find hardest.", "accent"),
            ("", 0),
            ("A tip is shown for every target. Aim for par, but don't rush.", 0),
            ("Results count toward lesson progress and unlocks.", 0),
        ], "any key to start · q back")
        if intro == "q":
            return

        deadline = time.monotonic() + QUICK_LEARN_SECONDS
        tally: dict[str, list[int]] = {}  # lesson_id -> [targets, par hits]
        message: tuple[str, str] = ("Go!", "good")
        unlocked: list[str] = []

        def info() -> str:
            left = max(0, int(deadline - time.monotonic()))
            return f"{left // 60}:{left % 60:02d} left   {sum(t[0] for t in tally.values())} done"

        while True:
            lesson = pick_quick_lesson(self.progress)
            challenge, par, optimal = make_challenge(lesson)
            result = self.play_target(
                f"Quick learn · {lesson.title}", info, challenge.lines, Cursor.at(challenge.start),
                challenge.target, lesson.commands, par, challenge.prompt,
                message=message, deadline=deadline, tip=f"{challenge.hint}  (try: {challenge.solution})",
                coach=False,
            )
            if result.status != "hit":
                break
            stars = rate(result.keys, par)
            hit_par = result.keys <= par
            for stats in (self.progress["lessons"][lesson.lesson_id], self.progress["overall"]):
                update_stats(stats, hit_par, result.elapsed, stars)
            newly = maybe_unlock_next(self.progress, lesson.lesson_id)
            if newly:
                unlocked.append(newly)
            save_progress(self.progress)
            counts = tally.setdefault(lesson.lesson_id, [0, 0])
            counts[0] += 1
            counts[1] += hit_par
            if newly:
                message = (f"{stars_text(stars)}  Unlocked {newly}!", "good")
            elif hit_par:
                message = (f"{stars_text(stars)}  par!", "good")
            else:
                message = (f"{stars_text(stars)}  {result.keys} keys, par {par} - optimal: {optimal}", "warn")

        if not tally:
            return
        lines: list[tuple[str, str | int]] = [("Time's up - nice session.", "accent"), ("", 0)]
        for lesson_id, (done, hits) in tally.items():
            lines.append((f"{lesson_by_id(lesson_id).title:<24} {hits}/{done} at par", "good" if hits == done else 0))
        weakest = min(tally.items(), key=lambda item: item[1][1] / item[1][0])
        if weakest[1][1] < weakest[1][0]:
            lines += [("", 0), (f"Practise next: {lesson_by_id(weakest[0]).title}", "warn")]
        for title in unlocked:
            lines.append((f"Unlocked: {title}", "good"))
        time.sleep(0.3)
        curses.flushinp()
        self.notice("Quick learn complete", lines)

    def sprint(self) -> None:
        allowed = sprint_motions(self.progress)
        intro = self.notice("Sprint", [
            (f"{SPRINT_SECONDS} seconds. Hit as many targets as you can.", "accent"),
            ("", 0),
            ("Motions: " + " ".join(allowed), 0),
            ("Par = 100 pts, near par = 50, otherwise 20.", 0),
            ("Consecutive par hits build a combo multiplier (up to x5).", 0),
            ("Your cursor stays where it lands - plan the next jump.", 0),
            ("", 0),
            (f"Best so far: {self.progress['sprint_best']}", "warn"),
        ], "any key to start · q back")
        if intro == "q":
            return

        score, combo, hits, pars, on_buffer = 0, 1, 0, 0, 0
        snippets = itertools.cycle(random.sample(SPRINT_SNIPPETS, len(SPRINT_SNIPPETS)))
        lines = next(snippets)
        cursor = Cursor.at(Position(0, 0))
        message: tuple[str, str] = ("Go!", "good")
        deadline = time.monotonic() + SPRINT_SECONDS

        def info() -> str:
            left = max(0.0, deadline - time.monotonic())
            return f"{left:4.1f}s   {score} pts   x{combo}"

        while True:
            if on_buffer == 5:
                lines, on_buffer = next(snippets), 0
                cursor = Cursor.at(Position(0, first_non_blank(lines, 0)))
                message = ("New buffer!", "accent")
            target, par, optimal = pick_sprint_target(lines, cursor, allowed)
            result = self.play_target("Sprint", info, lines, cursor, target, allowed, par,
                                      "Reach the target!", message=message, deadline=deadline)
            if result.status == "quit":
                return
            if result.status == "timeout":
                break
            cursor = result.cursor
            hits += 1
            on_buffer += 1
            stars = rate(result.keys, par)
            points = {3: 100, 2: 50, 1: 20}[stars] * combo
            score += points
            if stars == 3:
                pars += 1
                combo = min(5, combo + 1)
                message = (f"{stars_text(stars)} +{points}  par!", "good")
            else:
                combo = 1
                message = (f"{stars_text(stars)} +{points}  optimal was: {optimal}", "warn")

        record = score > self.progress["sprint_best"]
        if record:
            self.progress["sprint_best"] = score
            save_progress(self.progress)
        lines_out: list[tuple[str, str | int]] = [
            ("Time!", "accent"),
            ("", 0),
            (f"Score     {score}", "warn"),
            (f"Targets   {hits}   ({pars} at par)", 0),
            (f"Best      {self.progress['sprint_best']}", 0),
        ]
        if record:
            lines_out += [("", 0), ("New personal best!", "good")]
        time.sleep(0.3)  # swallow keys mashed as the clock ran out
        curses.flushinp()
        self.notice("Sprint over", lines_out)

    # ---- info screens ---------------------------------------------------

    def show_progress(self) -> None:
        overall = self.progress["overall"]
        lines: list[tuple[str, str | int]] = [
            (f"Overall par rate {accuracy(overall) * 100:5.1f}%   targets {overall['attempts']}   "
             f"avg {average_time(overall):.1f}s   ★ {overall.get('stars', 0)}", "accent"),
            (f"Best streak {overall['best_streak']}   sprint best {self.progress['sprint_best']}", 0),
            ("", 0),
        ]
        for lesson in LESSONS:
            stats = self.progress["lessons"][lesson.lesson_id]
            if lesson.lesson_id not in self.progress["unlocked_lessons"]:
                lines.append((f"{lesson.title:<24} locked", "dim"))
                continue
            ratio = accuracy(stats)
            lines.append((f"{lesson.title:<24} {progress_bar(ratio, 14)} {ratio * 100:4.0f}%  "
                          f"n={stats['attempts']:<3} ★ {stats['stars']}", "good" if ratio >= UNLOCK_EFFICIENCY else 0))
        lines += [("", 0), (f"Saved to {PROGRESS_PATH}", "dim")]
        self.notice("Progress", lines)

    def show_reference(self) -> None:
        lines: list[tuple[str, str | int]] = [(f"{key:<4} {desc}", 0) for key, desc in REFERENCE.items()]
        lines += [
            ("", 0),
            ("Counts go first: 3l, 2w, 4j. A count before gg/G is a line number.", "dim"),
            ("w/b/e treat punctuation as its own word: foo.bar is three words.", "dim"),
            ("Esc cancels a half-typed count or g. c toggles the coach where it's offered.", "dim"),
        ]
        self.notice("Motion reference", lines)


# --------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------


def run_self_test() -> None:
    lines = ["alpha beta gamma", "delta epsilon zeta", "eta theta iota"]
    assert execute_motion(lines, Position(0, 0), "w") == Position(0, 6)
    assert execute_motion(lines, Position(0, 6), "b") == Position(0, 0)
    assert execute_motion(lines, Position(0, 6), "e") == Position(0, 9)
    assert execute_motion(lines, Position(0, 9), "e") == Position(0, 15)
    assert execute_motion(lines, Position(0, 0), "2w") == Position(0, 11)
    assert execute_motion(lines, Position(0, 0), "j") == Position(1, 0)
    assert execute_motion(lines, Position(1, 5), "k") == Position(0, 5)
    assert execute_motion(lines, Position(1, 5), "0") == Position(1, 0)
    assert execute_motion(lines, Position(1, 5), "$") == Position(1, len(lines[1]) - 1)
    assert execute_motion(lines, Position(1, 5), "gg") == Position(0, 0)
    assert execute_motion(lines, Position(0, 5), "G") == Position(2, 0)
    assert execute_motion(lines, Position(2, 0), "2gg") == Position(1, 0)
    assert execute_motion(lines, Position(0, 0), "3G") == Position(2, 0)
    assert execute_motion(["foo.bar baz"], Position(0, 0), "w") == Position(0, 3)
    for lesson in LESSONS:
        make_challenge(lesson)
    print("Self-test passed.")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        run_self_test()
        return
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("Vim Motion Trainer needs an interactive terminal.", file=sys.stderr)
        sys.exit(1)
    locale.setlocale(locale.LC_ALL, "")
    os.environ.setdefault("ESCDELAY", "25")  # make Esc responsive
    try:
        curses.wrapper(lambda scr: App(scr).run())
    except KeyboardInterrupt:
        pass
    print("See you next session. Keep your fingers on the home row.")


if __name__ == "__main__":
    main()
