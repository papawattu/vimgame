# Vim Motion Trainer

A terminal game for learning Vim motions. Every key you press moves the cursor
immediately, just like in Vim. Reach the green target in as few keystrokes as
you can: a solver works out the optimal ("par") keystroke count for every target,
and matching it earns three stars.

## Run it

```bash
python3 vim_motion_trainer.py
```

Needs an interactive terminal of at least 60x20.

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
- **Sprint** – a 60-second time attack on code-like buffers using every motion
  you've unlocked. Par hits build a combo multiplier, and your best score is saved.

After each target you see your keys alongside the optimal solution, so you learn
shortcuts such as `$` instead of `9l`.

## What it teaches

- `h` `l`, `j` `k` (with Vim's remembered column)
- `w` `b` `e` (punctuation counts as its own word, as in Vim)
- `0` `$`
- counts like `3l`, `2w`, `2$`
- `gg` `G`, and `Ngg` / `NG` for line numbers

Progress is stored in `~/.vim_motion_trainer_progress.json`.

## Tests

```bash
python3 vim_motion_trainer.py --self-test
python3 -m pytest
```
