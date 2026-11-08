// Vim Motion Trainer - browser engine.
//
// A direct port of the motion engine, solver and game rules in vim_motion_trainer.py.
// Both are checked against tests/shared/cases.json, so they behave identically.

export const MOTIONS = ["h", "j", "k", "l", "w", "b", "e", "0", "$", "gg", "G"];
export const WANT_EOL = 1e9; // desired column after $: stick to end of line on j/k

// ---------------------------------------------------------------------------
// Motions (aims to match Vim)
// ---------------------------------------------------------------------------

const BLANK = /\s/u;
const KEYWORD = /[\p{L}\p{N}_]/u;

/** Vim's word classes: 0 = blank, 1 = punctuation, 2 = keyword character. */
export function charClass(ch) {
  if (BLANK.test(ch)) return 0;
  if (KEYWORD.test(ch)) return 2;
  return 1;
}

export const pos = (line, col) => ({ line, col });
export const samePos = (a, b) => a.line === b.line && a.col === b.col;
export const cursorAt = (p) => ({ line: p.line, col: p.col, want: p.col });
const posKey = (p) => `${p.line},${p.col}`;
const cursorKey = (c) => `${c.line},${c.col},${c.want}`;

export const lastCol = (lines, line) => Math.max(0, lines[line].length - 1);

export function firstNonBlank(lines, line) {
  const text = lines[line];
  const stripped = text.length - text.trimStart().length;
  return Math.min(stripped, lastCol(lines, line));
}

function toFlatIndex(lines, p) {
  let index = 0;
  for (let n = 0; n < lines.length; n++) {
    if (n === p.line) return index + Math.min(p.col, Math.max(0, lines[n].length - 1));
    index += lines[n].length + 1;
  }
  throw new Error("Position is out of range");
}

function fromFlatIndex(lines, flat) {
  let index = 0;
  for (let n = 0; n < lines.length; n++) {
    const next = index + lines[n].length;
    if (flat <= next) return pos(n, Math.max(0, Math.min(flat - index, lines[n].length - 1)));
    index = next + 1;
  }
  return pos(lines.length - 1, lastCol(lines, lines.length - 1));
}

function moveW(text, i) {
  const size = text.length;
  const cls = charClass(text[i]);
  let c = i;
  if (cls) while (c < size && charClass(text[c]) === cls) c++;
  while (c < size && charClass(text[c]) === 0) c++;
  if (c >= size) {
    c = size - 1; // Vim stops on the last character of the buffer
    while (c > i && charClass(text[c]) === 0) c--;
  }
  return c;
}

function moveB(text, i) {
  let c = i - 1;
  while (c >= 0 && charClass(text[c]) === 0) c--;
  if (c < 0) return 0;
  const cls = charClass(text[c]);
  while (c > 0 && charClass(text[c - 1]) === cls) c--;
  return c;
}

function moveE(text, i) {
  const size = text.length;
  let c = i + 1;
  while (c < size && charClass(text[c]) === 0) c++;
  if (c >= size) return i;
  const cls = charClass(text[c]);
  while (c + 1 < size && charClass(text[c + 1]) === cls) c++;
  return c;
}

/** Apply one (count, motion) pair to a cursor {line, col, want}. `text` is lines.join("\n"). */
export function applyMotion(lines, text, cur, count, motion) {
  const n = count ?? 1;
  let { line, col } = cur;
  const finalLine = lines.length - 1;
  switch (motion) {
    case "h":
      col = Math.max(0, col - n);
      return { line, col, want: col };
    case "l":
      col = Math.min(lastCol(lines, line), col + n);
      return { line, col, want: col };
    case "j":
    case "k":
      line = Math.max(0, Math.min(finalLine, line + (motion === "j" ? n : -n)));
      return { line, col: Math.min(cur.want, lastCol(lines, line)), want: cur.want };
    case "0":
      return { line, col: 0, want: 0 };
    case "$":
      line = Math.min(finalLine, line + n - 1);
      return { line, col: lastCol(lines, line), want: WANT_EOL };
    case "gg":
    case "G":
      if (count == null) line = motion === "gg" ? 0 : finalLine;
      else line = Math.max(0, Math.min(finalLine, count - 1));
      col = firstNonBlank(lines, line);
      return { line, col, want: col };
    case "w":
    case "b":
    case "e": {
      const mover = { w: moveW, b: moveB, e: moveE }[motion];
      let flat = toFlatIndex(lines, cur);
      for (let r = 0; r < n; r++) flat = mover(text, flat);
      const p = fromFlatIndex(lines, flat);
      return { line: p.line, col: p.col, want: p.col };
    }
    default:
      throw new Error(`Unsupported motion: ${motion}`);
  }
}

/** Turns individual keypresses into [count, motion] commands, like Vim's normal mode. */
export class KeyBuffer {
  constructor() {
    this.count = "";
    this.gPending = false;
  }
  get pending() {
    return this.count + (this.gPending ? "g" : "");
  }
  clear() {
    this.count = "";
    this.gPending = false;
  }
  takeCount() {
    const c = this.count ? parseInt(this.count, 10) : null;
    this.count = "";
    return c;
  }
  /** Returns [count, motion], null while a command is incomplete, or throws on a bad key. */
  feed(ch) {
    if (this.gPending) {
      this.gPending = false;
      if (ch === "g") return [this.takeCount(), "gg"];
      this.clear();
      throw new Error(`g${ch} isn't a motion here - did you mean gg?`);
    }
    if (/^[0-9]$/.test(ch) && (ch !== "0" || this.count)) {
      if (this.count.length < 3) this.count += ch;
      return null;
    }
    if (ch === "g") {
      this.gPending = true;
      return null;
    }
    if (MOTIONS.includes(ch)) return [this.takeCount(), ch];
    this.clear();
    throw new Error(`'${ch}' isn't a supported motion`);
  }
}

export const commandLabel = (count, motion) => (count != null ? `${count}${motion}` : motion);

export function parseCommand(command) {
  const buffer = new KeyBuffer();
  const tokens = [];
  for (const ch of command.replace(/ /g, "")) {
    const token = buffer.feed(ch);
    if (token) tokens.push(token);
  }
  if (buffer.pending) throw new Error(`Incomplete motion: ${buffer.pending}`);
  if (!tokens.length) throw new Error("Enter a motion like l, 2w, $, gg, or G.");
  return tokens;
}

export function executeMotion(lines, start, command) {
  const text = lines.join("\n");
  let cur = cursorAt(start);
  for (const [count, motion] of parseCommand(command)) cur = applyMotion(lines, text, cur, count, motion);
  return pos(cur.line, cur.col);
}

// ---------------------------------------------------------------------------
// Solver: fewest keystrokes to every reachable position (Dijkstra)
// ---------------------------------------------------------------------------

export function motionOptions(allowed, lineCount) {
  const options = [];
  for (const motion of MOTIONS) {
    if (!allowed.includes(motion)) continue;
    options.push([null, motion, motion]);
    if (motion === "0") continue;
    const counts = [];
    if (motion === "gg" || motion === "G") for (let c = 1; c <= lineCount; c++) counts.push(c);
    else for (let c = 2; c <= 9; c++) counts.push(c);
    for (const c of counts) options.push([c, motion, `${c}${motion}`]);
  }
  return options;
}

class MinHeap {
  constructor() {
    this.items = [];
  }
  get size() {
    return this.items.length;
  }
  static less(a, b) {
    return a.cost < b.cost || (a.cost === b.cost && a.tie < b.tie);
  }
  push(item) {
    const h = this.items;
    h.push(item);
    let i = h.length - 1;
    while (i > 0) {
      const parent = (i - 1) >> 1;
      if (!MinHeap.less(h[i], h[parent])) break;
      [h[i], h[parent]] = [h[parent], h[i]];
      i = parent;
    }
  }
  pop() {
    const h = this.items;
    const top = h[0];
    const last = h.pop();
    if (h.length) {
      h[0] = last;
      let i = 0;
      for (;;) {
        const l = 2 * i + 1;
        const r = l + 1;
        let m = i;
        if (l < h.length && MinHeap.less(h[l], h[m])) m = l;
        if (r < h.length && MinHeap.less(h[r], h[m])) m = r;
        if (m === i) break;
        [h[i], h[m]] = [h[m], h[i]];
        i = m;
      }
    }
    return top;
  }
}

/** Returns Map "line,col" -> {cost, keys} for every position reachable from `start` (a cursor). */
export function solve(lines, start, allowed) {
  const text = lines.join("\n");
  const options = motionOptions(allowed, lines.length);
  const best = new Map([[cursorKey(start), 0]]);
  const found = new Map();
  const heap = new MinHeap();
  let tie = 0;
  heap.push({ cost: 0, tie: tie++, keys: "", cur: start });
  while (heap.size) {
    const { cost, keys, cur } = heap.pop();
    if ((best.get(cursorKey(cur)) ?? cost) < cost) continue;
    const pk = posKey(cur);
    if (!found.has(pk)) found.set(pk, { cost, keys });
    for (const [count, motion, label] of options) {
      const next = applyMotion(lines, text, cur, count, motion);
      const nextCost = cost + label.length;
      const nk = cursorKey(next);
      if (nextCost < (best.get(nk) ?? nextCost + 1)) {
        best.set(nk, nextCost);
        heap.push({ cost: nextCost, tie: tie++, keys: keys ? `${keys} ${label}` : label, cur: next });
      }
    }
  }
  return found;
}

export const solveTo = (lines, start, target, allowed) => solve(lines, start, allowed).get(posKey(target));

/** The optimal commands from the cursor to the target, e.g. ["2w", "$"]. */
export function coachPlan(lines, cursor, target, allowed) {
  const found = solveTo(lines, cursor, target, allowed);
  return found && found.keys ? found.keys.split(" ") : [];
}

export const rate = (keys, par) => (keys <= par ? 3 : keys <= par + 2 ? 2 : 1);
export const starsText = (stars) => "★".repeat(stars) + "☆".repeat(3 - stars);

export function explainCommand(label) {
  const [[count, motion]] = parseCommand(label);
  const n = count ?? 1;
  const s = n === 1 ? "" : "s";
  return {
    h: `left ${n} character${s}`,
    l: `right ${n} character${s}`,
    j: `down ${n} line${s}`,
    k: `up ${n} line${s}`,
    w: `forward ${n} word${s}`,
    b: `back ${n} word${s}`,
    e: n === 1 ? "to the end of the word" : `to the end of the word ${n - 1} ahead`,
    0: "to the start of the line",
    $: n === 1 ? "to the end of the line" : `to the end of the line ${n - 1} down`,
    gg: count == null ? "to the first line" : `to line ${count}`,
    G: count == null ? "to the last line" : `to line ${count}`,
  }[motion];
}

// ---------------------------------------------------------------------------
// Randomness (seedable for tests)
// ---------------------------------------------------------------------------

export function makeRng(seed = Date.now()) {
  let a = seed >>> 0;
  const next = () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  return {
    random: next,
    int: (lo, hi) => lo + Math.floor(next() * (hi - lo + 1)), // inclusive, like random.randint
    choice: (items) => items[Math.floor(next() * items.length)],
  };
}

// ---------------------------------------------------------------------------
// Lesson challenge generators
// ---------------------------------------------------------------------------

function wordPositions(line) {
  const starts = [];
  const ends = [];
  for (const m of line.matchAll(/[\p{L}\p{N}_]+/gu)) {
    starts.push(m.index);
    ends.push(m.index + m[0].length - 1);
  }
  return [starts, ends];
}

const challenge = (lines, start, target, prompt, hint, solution) => ({ lines, start, target, prompt, hint, solution });

export const GENERATORS = {
  left_right(content, rng) {
    const line = rng.choice(content.single_lines);
    const startCol = rng.int(2, line.length - 4);
    let targetCol = startCol;
    while (targetCol === startCol) {
      targetCol = Math.max(0, Math.min(line.length - 1, startCol + rng.choice([-4, -3, -2, -1, 1, 2, 3, 4])));
    }
    const steps = Math.abs(targetCol - startCol);
    const motion = targetCol > startCol ? "l" : "h";
    return challenge([line], pos(0, startCol), pos(0, targetCol),
      "Move to the target on the same line using h and l.",
      "h goes left, l goes right. A count repeats the move: 3l is two keys instead of three.",
      steps > 1 ? `${steps}${motion}` : motion);
  },
  up_down(content, rng) {
    const lines = rng.choice(content.stacked_lines);
    const width = Math.min(...lines.map((l) => l.length));
    const col = rng.int(1, width - 3);
    const startLine = rng.int(0, lines.length - 1);
    let targetLine = startLine;
    while (targetLine === startLine) {
      targetLine = Math.max(0, Math.min(lines.length - 1, startLine + rng.choice([-3, -2, -1, 1, 2, 3])));
    }
    const steps = Math.abs(targetLine - startLine);
    const motion = targetLine > startLine ? "j" : "k";
    return challenge(lines, pos(startLine, col), pos(targetLine, col),
      "Move vertically to the target using j and k.",
      "j moves down, k moves up. Counts work here too, like 2j.",
      steps > 1 ? `${steps}${motion}` : motion);
  },
  word_forward(content, rng) {
    const line = rng.choice(content.single_lines);
    const [starts] = wordPositions(line);
    const step = rng.int(1, Math.min(3, starts.length - 1));
    const i = rng.int(0, starts.length - step - 1);
    return challenge([line], pos(0, starts[i]), pos(0, starts[i + step]),
      "Jump forward to the start of a word with w.",
      "w lands on the first character of the next word. 2w skips two.",
      step > 1 ? `${step}w` : "w");
  },
  word_back(content, rng) {
    const line = rng.choice(content.single_lines);
    const [starts] = wordPositions(line);
    const step = rng.int(1, Math.min(3, starts.length - 1));
    const i = rng.int(step, starts.length - 1);
    return challenge([line], pos(0, starts[i]), pos(0, starts[i - step]),
      "Jump back to the start of a word with b.",
      "b moves to the beginning of the word to your left. 2b goes two words back.",
      step > 1 ? `${step}b` : "b");
  },
  word_end(content, rng) {
    const line = rng.choice(content.single_lines);
    const [starts, ends] = wordPositions(line);
    const i = rng.int(0, starts.length - 2);
    const step = rng.int(0, Math.min(2, starts.length - i - 1));
    let startCol = starts[i];
    if (ends[i] - starts[i] >= 2 && rng.random() < 0.4) startCol += 1;
    let targetCol = ends[i + step];
    if (targetCol === startCol) targetCol = ends[i + step + 1];
    return challenge([line], pos(0, startCol), pos(0, targetCol),
      "Land on the end of a word with e.",
      "e lands on the last character of a word. If you're already there, it goes to the next word's end.",
      step === 0 ? "e" : `${step + 1}e`);
  },
  line_edges(content, rng) {
    const line = rng.choice(content.single_lines);
    const startCol = rng.int(4, line.length - 5);
    if (rng.random() < 0.5) {
      return challenge([line], pos(0, startCol), pos(0, 0),
        "Snap to the start of the line.", "0 jumps straight to column 1.", "0");
    }
    return challenge([line], pos(0, startCol), pos(0, line.length - 1),
      "Snap to the end of the line.", "$ lands on the last character of the line.", "$");
  },
  counts(content, rng) {
    const kind = rng.choice(["horizontal", "vertical", "word"]);
    if (kind === "horizontal") {
      const line = rng.choice(content.single_lines);
      const count = rng.int(2, 7);
      const startCol = rng.int(0, line.length - count - 2);
      return challenge([line], pos(0, startCol), pos(0, startCol + count),
        "Reach the target in as few keystrokes as you can.",
        "Counts come before the motion, like 4l - but sometimes a word motion is shorter.", `${count}l`);
    }
    if (kind === "vertical") {
      const lines = rng.choice(content.stacked_lines);
      const count = rng.int(2, lines.length - 1);
      const col = rng.int(0, Math.min(...lines.map((l) => l.length)) - 2);
      return challenge(lines, pos(0, col), pos(count, col),
        "Use a counted vertical motion to land on the target.", "Try a command like 2j or 3k.", `${count}j`);
    }
    const line = rng.choice(content.single_lines);
    const [starts] = wordPositions(line);
    const count = rng.int(2, Math.min(4, starts.length - 1));
    const i = rng.int(0, starts.length - count - 1);
    return challenge([line], pos(0, starts[i]), pos(0, starts[i + count]),
      "Use a counted word motion to reach the target.", "Counts also work with words, like 3w.", `${count}w`);
  },
  file_jumps(content, rng) {
    const lines = ["first checkpoint", "second checkpoint", "third checkpoint", "fourth checkpoint",
      "fifth checkpoint", "sixth checkpoint", "final checkpoint"];
    const startLine = rng.int(1, lines.length - 2);
    let targetLine = startLine;
    while (Math.abs(targetLine - startLine) < 2) {
      targetLine = rng.choice([0, lines.length - 1, rng.int(0, lines.length - 1)]);
    }
    let solution;
    let hint;
    if (targetLine === 0) {
      solution = "gg";
      hint = "gg jumps to the first line. Add a count for a line number, like 3gg.";
    } else if (targetLine === lines.length - 1) {
      solution = "G";
      hint = "G jumps to the last line. A count turns it into a line number, like 4G.";
    } else {
      solution = `${targetLine + 1}G`;
      hint = "A count before G or gg goes to that line number.";
    }
    return challenge(lines, pos(startLine, 0), pos(targetLine, 0),
      "Jump to the target line - the line numbers are there to help.", hint, solution);
  },
};

/** Generate a solvable challenge for a lesson; returns {challenge, par, optimal}. */
export function makeChallenge(content, lesson, rng) {
  for (let attempt = 0; attempt < 100; attempt++) {
    const c = GENERATORS[lesson.id](content, rng);
    if (samePos(c.start, c.target)) continue;
    const found = solveTo(c.lines, cursorAt(c.start), c.target, lesson.commands);
    if (found) return { challenge: c, par: found.cost, optimal: found.keys };
  }
  throw new Error(`Could not generate a solvable challenge for ${lesson.id}`);
}

// ---------------------------------------------------------------------------
// Real-world scenarios
// ---------------------------------------------------------------------------

export function stepTarget(lines, step) {
  let col = lines[step.line].indexOf(step.find);
  if (col < 0) throw new Error(`"${step.find}" not found on line ${step.line}`);
  if (step.at === "end") col += step.find.length - 1;
  return pos(step.line, col);
}

export const scenarioStart = (lines) => pos(0, firstNonBlank(lines, 0));

// ---------------------------------------------------------------------------
// Sprint and Survival
// ---------------------------------------------------------------------------

export function pickSprintTarget(lines, cursor, allowed, rng) {
  const candidates = [];
  for (const [key, { cost, keys }] of solve(lines, cursor, allowed)) {
    const [line, col] = key.split(",").map(Number);
    if ((line !== cursor.line || col !== cursor.col) && lines[line][col] !== " ") {
      candidates.push({ target: pos(line, col), par: cost, optimal: keys });
    }
  }
  const interesting = candidates.filter((c) => c.par >= 2 && c.par <= 6);
  return rng.choice(interesting.length ? interesting : candidates);
}

/** One Survival level: `count` reachable non-blank cells in one buffer, never repeating back to back. */
export function survivalSequence(content, count, allowed, rng) {
  const buffers = [...content.sprint_snippets, ...content.scenarios.map((s) => s.lines)];
  let lines;
  let cells;
  let previous;
  for (;;) {
    lines = rng.choice(buffers);
    previous = scenarioStart(lines);
    cells = [...solve(lines, cursorAt(previous), allowed).keys()]
      .map((k) => k.split(",").map(Number))
      .filter(([l, c]) => !BLANK.test(lines[l][c]))
      .sort((a, b) => a[0] - b[0] || a[1] - b[1])
      .map(([l, c]) => pos(l, c));
    if (cells.length >= 5) break;
  }
  const targets = [];
  while (targets.length < count) {
    const p = rng.choice(cells);
    if (!samePos(p, previous)) {
      targets.push({ lines, pos: p });
      previous = p;
    }
  }
  return targets;
}

/** Survival rules: the same as the src/ GameEngine + ProgressionLogic setup used by the terminal game. */
export const DIFFICULTY_LEVELS = {
  1: { moves: 3, timeLimit: 10 },
  2: { moves: 5, timeLimit: 8 },
  3: { moves: 7, timeLimit: 6 },
  4: { moves: 10, timeLimit: 5 },
  5: { moves: 15, timeLimit: 4 },
};
export const SURVIVAL = { startScore: 50, pointsCorrect: 25, pointsWrong: -15, xpCorrect: 10, winScore: 1000 };

export class SurvivalGame {
  constructor(factory) {
    this.factory = factory; // count -> targets
    this.score = SURVIVAL.startScore;
    this.difficulty = 1;
    this.level = 1;
    this.sequence = factory(this.params.moves);
  }
  get params() {
    return DIFFICULTY_LEVELS[this.difficulty];
  }
  get current() {
    return this.sequence[0];
  }
  /** Adapt difficulty from speed (seconds) and accuracy (0..1), like ProgressionLogic.update_progress. */
  trackPerformance(time, accuracy) {
    const score = time > 0 ? accuracy * 0.7 + (1 / time) * 0.3 : 0;
    if (score > 0.85 && this.difficulty < 5) this.difficulty += 1;
    else if (score < 0.65 && this.difficulty > 1) this.difficulty -= 1;
  }
  /** Returns "correct", "level_complete", "wrong", "over" or "won". */
  record(hit) {
    let status;
    if (hit) {
      this.sequence.shift();
      this.score += SURVIVAL.pointsCorrect;
      status = "correct";
      if (!this.sequence.length) {
        this.level += 1;
        this.sequence = this.factory(this.params.moves);
        status = "level_complete";
      }
    } else {
      this.score += SURVIVAL.pointsWrong;
      status = "wrong";
    }
    if (this.score <= 0) return "over";
    if (this.score >= SURVIVAL.winScore) return "won";
    return status;
  }
}

// ---------------------------------------------------------------------------
// Progress (mirrors the terminal game's progress file)
// ---------------------------------------------------------------------------

export const UNLOCK_ATTEMPTS = 5;
export const UNLOCK_EFFICIENCY = 0.7;
export const XP_PER_STAR = 5;

export const emptyStats = () => ({ attempts: 0, successes: 0, current_streak: 0, best_streak: 0, total_time: 0, stars: 0 });

export function defaultProgress(content) {
  return {
    current_lesson: content.lessons[0].id,
    unlocked_lessons: [content.lessons[0].id],
    overall: emptyStats(),
    lessons: Object.fromEntries(content.lessons.map((l) => [l.id, emptyStats()])),
    sprint_best: 0,
    scenarios: {},
    xp: { experience: 0, level: 1, experience_to_next_level: 100 },
    survival_best: { score: 0, level: 0 },
  };
}

/** Merge saved data over defaults, ignoring anything unknown or malformed. */
export function mergeProgress(content, saved) {
  const progress = defaultProgress(content);
  if (!saved || typeof saved !== "object") return progress;
  const lessonIds = new Set(content.lessons.map((l) => l.id));
  if (lessonIds.has(saved.current_lesson)) progress.current_lesson = saved.current_lesson;
  if (Array.isArray(saved.unlocked_lessons)) {
    progress.unlocked_lessons = [...new Set([content.lessons[0].id, ...saved.unlocked_lessons.filter((id) => lessonIds.has(id))])];
  }
  const num = (v, d) => (typeof v === "number" && Number.isFinite(v) ? v : d);
  for (const key of Object.keys(progress.overall)) progress.overall[key] = num(saved.overall?.[key], 0);
  for (const id of lessonIds) {
    for (const key of Object.keys(progress.lessons[id])) progress.lessons[id][key] = num(saved.lessons?.[id]?.[key], 0);
  }
  progress.sprint_best = num(saved.sprint_best, 0);
  const scenarioIds = new Set(content.scenarios.map((s) => s.id));
  for (const [id, best] of Object.entries(saved.scenarios ?? {})) {
    if (scenarioIds.has(id) && typeof best === "number") progress.scenarios[id] = best;
  }
  for (const section of ["xp", "survival_best"]) {
    for (const key of Object.keys(progress[section])) progress[section][key] = num(saved[section]?.[key], progress[section][key]);
  }
  return progress;
}

export const accuracy = (s) => (s.attempts ? s.successes / s.attempts : 0);
export const averageTime = (s) => (s.attempts ? s.total_time / s.attempts : 0);

export function updateStats(stats, success, elapsed, stars = 0) {
  stats.attempts += 1;
  stats.total_time += elapsed;
  stats.stars += stars;
  if (success) {
    stats.successes += 1;
    stats.current_streak += 1;
    stats.best_streak = Math.max(stats.best_streak, stats.current_streak);
  } else {
    stats.current_streak = 0;
  }
}

/** Returns the newly unlocked lesson's title, or null. */
export function maybeUnlockNext(content, progress, lessonId) {
  const index = content.lessons.findIndex((l) => l.id === lessonId);
  if (index >= content.lessons.length - 1) return null;
  const stats = progress.lessons[lessonId];
  if (stats.attempts < UNLOCK_ATTEMPTS || accuracy(stats) < UNLOCK_EFFICIENCY) return null;
  const next = content.lessons[index + 1];
  if (progress.unlocked_lessons.includes(next.id)) return null;
  progress.unlocked_lessons.push(next.id);
  return next.title;
}

/** Add XP like PlayerExperience.add_experience. Returns true on level-up. */
export function addXp(xp, amount) {
  const before = xp.level;
  xp.experience += amount;
  while (xp.experience >= xp.experience_to_next_level) {
    xp.experience -= xp.experience_to_next_level;
    xp.level += 1;
    xp.experience_to_next_level = Math.floor(xp.experience_to_next_level * 1.5);
  }
  return xp.level > before;
}

/** Motions available outside lessons: those of the furthest unlocked lesson. */
export function unlockedMotions(content, progress) {
  const unlocked = content.lessons.filter((l) => progress.unlocked_lessons.includes(l.id));
  return (unlocked.at(-1) ?? content.lessons[0]).commands;
}

/** Pick a lesson for Quick Learn, weighted towards a low par rate. */
export function pickQuickLesson(content, progress, rng) {
  const unlocked = content.lessons.filter((l) => progress.unlocked_lessons.includes(l.id));
  const weights = unlocked.map((l) => {
    const s = progress.lessons[l.id];
    return 0.15 + (1 - (s.attempts ? accuracy(s) : 0));
  });
  let roll = rng.random() * weights.reduce((a, b) => a + b, 0);
  for (let i = 0; i < unlocked.length; i++) {
    roll -= weights[i];
    if (roll <= 0) return unlocked[i];
  }
  return unlocked.at(-1);
}
