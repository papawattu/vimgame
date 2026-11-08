// Run with: node --test web/engine.test.mjs
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  KeyBuffer, MOTIONS, SurvivalGame, addXp, coachPlan, cursorAt, defaultProgress, executeMotion, explainCommand,
  makeChallenge, makeRng, maybeUnlockNext, mergeProgress, pickQuickLesson, pos, rate, samePos, scenarioStart, solve,
  solveTo, stepTarget, survivalSequence, updateStats,
} from "./engine.js";

const read = (path) => JSON.parse(readFileSync(new URL(path, import.meta.url), "utf8"));
const SHARED = read("../tests/shared/cases.json");
const CONTENT = read("../src/content/content.json");

// ---- shared cases: identical behaviour to the Python engine ----------------

test("shared motion cases match the Python engine", () => {
  for (const c of SHARED.motions) {
    const end = executeMotion(c.lines, pos(...c.start), c.keys);
    assert.deepEqual([end.line, end.col], c.expect, JSON.stringify(c));
  }
});

test("shared par cases match the Python solver", () => {
  for (const c of SHARED.par) {
    const found = solveTo(c.lines, cursorAt(pos(...c.start)), pos(...c.target), c.allowed);
    assert.equal(found.cost, c.cost, JSON.stringify(c));
  }
});

test("shared explain, rate and key-buffer cases", () => {
  for (const [label, text] of Object.entries(SHARED.explain)) assert.equal(explainCommand(label), text);
  for (const [keys, par, stars] of SHARED.rate) assert.equal(rate(keys, par), stars);
  for (const c of SHARED.keybuffer) {
    const buffer = new KeyBuffer();
    const tokens = [];
    let error = false;
    try {
      for (const key of c.keys) {
        const token = buffer.feed(key);
        if (token) tokens.push(token);
      }
    } catch {
      error = true;
    }
    assert.deepEqual({ tokens, error, pending: buffer.pending },
      { tokens: c.tokens, error: c.error, pending: c.pending }, c.keys);
  }
});

// ---- content -----------------------------------------------------------------

test("every lesson generates solvable, distinct targets", () => {
  const rng = makeRng(1);
  for (const lesson of CONTENT.lessons) {
    for (let i = 0; i < 25; i++) {
      const { challenge, par, optimal } = makeChallenge(CONTENT, lesson, rng);
      assert.ok(!samePos(challenge.start, challenge.target));
      assert.ok(par >= 1);
      assert.ok(samePos(executeMotion(challenge.lines, challenge.start, optimal), challenge.target));
    }
  }
});

test("every scenario step is reachable by following the coach", () => {
  for (const scenario of CONTENT.scenarios) {
    let cursor = cursorAt(scenarioStart(scenario.lines));
    for (const step of scenario.steps) {
      const target = stepTarget(scenario.lines, step);
      const plan = coachPlan(scenario.lines, cursor, target, MOTIONS);
      assert.ok(plan.length, `${scenario.id}: ${step.task}`);
      assert.ok(samePos(executeMotion(scenario.lines, cursor, plan.join(" ")), target));
      cursor = cursorAt(target);
    }
  }
});

test("coach replans using the remembered column", () => {
  const lines = ["a long line here", "ab", "another long line"];
  assert.deepEqual(coachPlan(lines, { line: 1, col: 1, want: 10 }, pos(2, 10), ["h", "j", "k", "l"]), ["j"]);
  assert.deepEqual(coachPlan(lines, cursorAt(pos(1, 1)), pos(2, 10), ["h", "j", "k", "l"]), ["j", "9l"]);
});

// ---- survival / progress -------------------------------------------------------

test("survival targets are reachable with only the unlocked motions", () => {
  const rng = makeRng(7);
  for (const allowed of [["h", "l"], ["h", "j", "k", "l"], MOTIONS]) {
    for (let i = 0; i < 6; i++) {
      const batch = survivalSequence(CONTENT, 5, allowed, rng);
      let cursor = cursorAt(scenarioStart(batch[0].lines));
      for (const t of batch) {
        assert.ok(solve(batch[0].lines, cursor, allowed).has(`${t.pos.line},${t.pos.col}`));
        cursor = cursorAt(t.pos);
      }
    }
  }
});

test("survival game: levels, scoring, game over and win", () => {
  let made = 0;
  const game = new SurvivalGame((count) => Array.from({ length: count }, () => made++));
  assert.equal(game.sequence.length, 3);
  assert.equal(game.record(true), "correct");
  assert.equal(game.score, 75);
  game.record(true);
  assert.equal(game.record(true), "level_complete");
  assert.equal(game.level, 2);
  game.trackPerformance(1.0, 1.0);
  assert.equal(game.difficulty, 2);
  game.trackPerformance(10, 0);
  assert.equal(game.difficulty, 1);
  game.score = 10;
  assert.equal(game.record(false), "over");
  game.score = 990;
  assert.equal(game.record(true), "won");
});

test("xp levels up like PlayerExperience", () => {
  const xp = { experience: 0, level: 1, experience_to_next_level: 100 };
  assert.equal(addXp(xp, 300), true);
  assert.deepEqual(xp, { experience: 50, level: 3, experience_to_next_level: 225 });
});

test("unlocks need a 70% par rate over 5 targets", () => {
  const progress = defaultProgress(CONTENT);
  const stats = progress.lessons.left_right;
  for (const hit of [true, true, true, false, false]) updateStats(stats, hit, 1, hit ? 3 : 1);
  assert.equal(maybeUnlockNext(CONTENT, progress, "left_right"), null);
  updateStats(stats, true, 1, 3);
  updateStats(stats, true, 1, 3);
  assert.equal(maybeUnlockNext(CONTENT, progress, "left_right"), CONTENT.lessons[1].title);
});

test("saved progress is merged safely", () => {
  const merged = mergeProgress(CONTENT, { unlocked_lessons: ["up_down", "bogus"], sprint_best: "x", scenarios: { py_typo: 9, nope: 3 } });
  assert.deepEqual(merged.unlocked_lessons, ["left_right", "up_down"]);
  assert.equal(merged.sprint_best, 0);
  assert.deepEqual(merged.scenarios, { py_typo: 9 });
  assert.deepEqual(mergeProgress(CONTENT, null), defaultProgress(CONTENT));
});

test("quick learn favours weak lessons", () => {
  const progress = defaultProgress(CONTENT);
  progress.unlocked_lessons = ["left_right", "up_down"];
  for (let i = 0; i < 10; i++) updateStats(progress.lessons.left_right, true, 1, 3);
  const rng = makeRng(3);
  const picks = Array.from({ length: 300 }, () => pickQuickLesson(CONTENT, progress, rng).id);
  assert.ok(picks.filter((p) => p === "up_down").length > picks.filter((p) => p === "left_right").length * 3);
});
