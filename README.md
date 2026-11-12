# Vim Motion Trainer

A terminal game for learning Vim motions. Every key you press moves the cursor
immediately, just like in Vim. Reach the green target in as few keystrokes as
you can: a solver works out the optimal ("par") keystroke count for every target,
and matching it earns three stars.

**Play it in your browser: https://papawattu.github.io/vimgame/**

## Run it

```bash
python3 vim_motion_trainer.py
```

Needs an interactive terminal of at least 60x20.

## Play in the browser

The same game runs as a static web page, deployed to GitHub Pages from `main`:
**https://papawattu.github.io/vimgame/**. Progress is saved in your browser.

To run it locally:

```bash
scripts/build-web.sh --serve   # then open http://localhost:8000
```

## Modes

- **Lessons** – eight steps, eight targets per round. Hit par on 70% of targets
  (minimum 5) to unlock the next lesson.
- **Quick learn** – a 2-minute time box. Targets come from your weakest unlocked
  lessons, a tip is shown for each one, and results count toward lesson progress.
- **Real-world code** – short editing tasks on real snippets in HTML, JavaScript,
  CSS, Python, Java, Go, C/C++, Shell, YAML and JSON ("the port is wrong, jump
  to `3000`").
  Your cursor carries over between steps, and each step ends with the edit you'd
  make next (`ciw`, `ci"`, `r9`...). A **coach** shows the best next key from
  wherever your cursor is and explains it ("`4$` → to the end of the line 3
  down"). It recalculates after every move. Press `c` to hide it and go solo;
  it's also available, off by default, in lessons and Quick learn.
- **Survival** – timed levels run by the `src/` game engine. Each level is a
  sequence of targets; clear one in time for +25, time out for −15. Score 0 is
  game over and 1000 wins. Fast, efficient moves raise the difficulty (more
  targets per level, less time per target) and slow ones ease it off.
- **Sprint** – a 60-second time attack on code-like buffers using every motion
  you've unlocked. Par hits build a combo multiplier, and your best score is saved.

After each target you see your keys alongside the optimal solution, so you learn
shortcuts such as `$` instead of `9l`.

Every target you clear earns XP towards a player level that persists across
sessions and is shown in the menus.

## What it teaches

- `h` `l`, `j` `k` (with Vim's remembered column)
- `w` `b` `e` (punctuation counts as its own word, as in Vim)
- `0` `$`
- counts like `3l`, `2w`, `2$`
- `gg` `G`, and `Ngg` / `NG` for line numbers

Progress is stored in `~/.vim_motion_trainer_progress.json`.

## Code layout

- `vim_motion_trainer.py` – the game: motion engine, solver, curses UI, all modes.
- `src/core/game_engine.py` – `GameEngine` runs Survival: the target sequence,
  score, XP and the game-over and win conditions. The game supplies targets
  through a `sequence_factory`.
- `src/core/progression.py` – `ProgressionLogic` adapts Survival's difficulty
  (targets per level, time limit) from your speed and efficiency.
- `src/player/` – `PlayerState` (score) and `PlayerExperience` (the persistent
  XP and level shared by every mode).

- `src/content/content.json` – lessons, snippets, real-world scenarios and the
  reference card, shared by the terminal and web versions.
- `web/` – the browser version: `engine.js` (a port of the motion engine,
  solver and rules), `app.js` (UI), `index.html`, `style.css`.

## Tests

The Python and JavaScript engines are both checked against
`tests/shared/cases.json` (hundreds of motion, solver and parsing cases
generated from the Python engine), so the two versions behave identically.
After changing motion behaviour, regenerate it with
`python3 scripts/gen_shared_cases.py`; CI fails if it's stale.

```bash
python3 vim_motion_trainer.py --self-test
python3 -m pytest
node --test web/engine.test.mjs
```
