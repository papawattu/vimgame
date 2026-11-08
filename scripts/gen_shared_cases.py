"""Regenerate tests/shared/cases.json from the Python engine, the reference implementation.

Both test suites (pytest and node --test web/engine.test.mjs) check their engine against these cases,
so the terminal and web versions can't drift apart on how a motion behaves.

    python3 scripts/gen_shared_cases.py
"""

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import vim_motion_trainer as v  # noqa: E402

# Hand-picked cases that pin down Vim behaviour (punctuation words, curswant, $ stickiness, gg/G...).
HANDWRITTEN = [
    (["alpha beta gamma", "delta epsilon zeta", "eta theta iota"], (0, 0), "w"),
    (["alpha beta gamma", "delta epsilon zeta", "eta theta iota"], (0, 9), "e"),
    (["alpha beta gamma", "delta epsilon zeta", "eta theta iota"], (0, 0), "2w"),
    (["alpha beta gamma", "delta epsilon zeta", "eta theta iota"], (2, 0), "2gg"),
    (["alpha beta gamma", "delta epsilon zeta", "eta theta iota"], (0, 0), "3G"),
    (["foo.bar baz"], (0, 0), "w"),
    (["foo.bar baz"], (0, 0), "3w"),
    (["foo.bar baz"], (0, 8), "2b"),
    (["foo.bar baz"], (0, 2), "e"),
    (["one two", "three"], (0, 4), "w"),
    (["one two", "three"], (1, 0), "w"),
    (["a long line here", "ab", "another long line"], (0, 10), "jj"),
    (["short", "a much longer line", "mid line"], (0, 0), "$j"),
    (["short", "a much longer line", "mid line"], (0, 0), "2$"),
    (["top", "    indented", "  end"], (0, 0), "G"),
    (["top", "    indented", "  end"], (0, 0), "2G"),
    (["abc"], (0, 1), "9l"),
    (["abc"], (0, 1), "9h"),
    (["a", "b"], (0, 0), "9j"),
]


def motion_case(lines, start, keys):
    end = v.execute_motion(lines, v.Position(*start), keys)
    return {"lines": lines, "start": list(start), "keys": keys, "expect": [end.line, end.col]}


def main() -> None:
    rng = random.Random(20261108)
    buffers = v.SPRINT_SNIPPETS + [s.lines for s in v.SCENARIOS] + [[line] for line in v.SINGLE_LINES]
    commands = [m for m in v.MOTIONS] + [f"{n}{m}" for n in (2, 3, 5) for m in v.MOTIONS if m != "0"]

    motions = [motion_case(lines, start, keys) for lines, start, keys in HANDWRITTEN]
    for _ in range(400):
        lines = rng.choice(buffers)
        row = rng.randrange(len(lines))
        start = (row, rng.randrange(max(1, len(lines[row]))))
        keys = "".join(rng.choice(commands) for _ in range(rng.randint(1, 3)))
        motions.append(motion_case(lines, start, keys))

    par = []
    for _ in range(40):
        lines = rng.choice(buffers)
        allowed = rng.choice([("h", "l"), ("h", "j", "k", "l", "w"), v.MOTIONS])
        start = v.Cursor.at(v.scenario_start(lines))
        reachable = v.solve(lines, start, allowed)
        target = rng.choice(sorted(reachable, key=lambda p: (p.line, p.col)))
        par.append({"lines": lines, "start": [start.pos.line, start.pos.col], "allowed": list(allowed),
                    "target": [target.line, target.col], "cost": reachable[target][0]})

    explain = {label: v.explain_command(label) for label in ["l", "3h", "j", "4k", "w", "3w", "b", "e", "3e",
                                                             "0", "$", "4$", "gg", "5gg", "G", "12G"]}
    keybuffer = []
    for keys in ["12w0", "10l", "3gg", "gG", "x", "g5"]:
        buffer, tokens, error = v.KeyBuffer(), [], False
        try:
            for key in keys:
                token = buffer.feed(key)
                if token:
                    tokens.append([token[0], token[1]])
        except ValueError:
            error = True
        keybuffer.append({"keys": keys, "tokens": tokens, "error": error, "pending": buffer.pending})

    out = {"motions": motions, "par": par, "explain": explain, "keybuffer": keybuffer,
           "rate": [[keys, p, v.rate(keys, p)] for keys in range(1, 8) for p in range(1, 5)]}
    path = ROOT / "tests" / "shared" / "cases.json"
    path.write_text(json.dumps(out, indent=1) + "\n")
    print(f"wrote {path.relative_to(ROOT)}: {len(motions)} motions, {len(par)} par, "
          f"{len(explain)} explain, {len(keybuffer)} keybuffer")


if __name__ == "__main__":
    main()
