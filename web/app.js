// Vim Motion Trainer - browser UI. Game rules and motions live in engine.js.
import * as E from "./engine.js";

const STORAGE_KEY = "vim-motion-trainer.progress.v1";
const CHALLENGES_PER_ROUND = 8;
const SPRINT_SECONDS = 60;
const QUICK_LEARN_SECONDS = 120;

const app = document.getElementById("app");
const rng = E.makeRng();
let content;
let progress;

// ---------------------------------------------------------------------------
// Storage (per browser; the game still works if storage is blocked)
// ---------------------------------------------------------------------------

function loadProgress() {
  try {
    return E.mergeProgress(content, JSON.parse(localStorage.getItem(STORAGE_KEY) || "null"));
  } catch {
    return E.defaultProgress(content);
  }
}

function save() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(progress));
  } catch {
    /* progress is a nicety; never break the game over it */
  }
}

function awardXp(amount) {
  const levelled = E.addXp(progress.xp, amount);
  save();
  return levelled ? `Level up! You're now level ${progress.xp.level}.` : null;
}

// ---------------------------------------------------------------------------
// Keyboard routing: one active handler at a time
// ---------------------------------------------------------------------------

let keyHandler = null;

document.addEventListener("keydown", (event) => {
  if (event.ctrlKey || event.metaKey || event.altKey || !keyHandler) return;
  if (event.key === "Tab" || event.key === "Shift" || event.key.startsWith("F") && event.key.length > 1) return;
  if (keyHandler(event.key) !== false) event.preventDefault();
});

// ---------------------------------------------------------------------------
// Rendering helpers
// ---------------------------------------------------------------------------

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const span = (cls, text) => `<span class="${cls}">${esc(text)}</span>`;
const kbd = (k) => `<kbd>${esc(k)}</kbd>`;

function headerRight() {
  const { level, experience, experience_to_next_level: next } = progress.xp;
  return `Lv ${level}  ${experience}/${next} xp   ★ ${progress.overall.stars}`;
}

function keepInView() {
  for (const sel of [".buffer .tgt", ".buffer .cur"]) {
    app.querySelector(sel)?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }
}

function frame(title, right, body, footer) {
  app.innerHTML = `
    <header class="bar">
      <span class="brand">VIM MOTION TRAINER</span>
      <span class="title">· ${esc(title)}</span>
      <span class="right">${esc(right)}</span>
    </header>
    <section class="body">${body}</section>
    <footer class="keys">${footer}</footer>`;
  keepInView();
}

function bufferHtml(lines, cursor, target) {
  const width = String(lines.length).length;
  return `<pre class="buffer">${lines
    .map((line, n) => {
      const chars = [...(line.length ? line : " ")];
      const cells = chars.map((ch, col) => {
        const isCursor = cursor && cursor.line === n && cursor.col === col;
        const isTarget = target && target.line === n && target.col === col;
        if (isCursor) return span("cur", ch);
        if (isTarget) return span("tgt", ch);
        return esc(ch);
      });
      return `${span("ln", String(n + 1).padStart(width + 1) + "  ")}${cells.join("")}`;
    })
    .join("\n")}</pre>`;
}

const linesHtml = (lines) => `<div class="lines">${lines.map(([text, style]) => `<p class="${style || ""}">${esc(text)}</p>`).join("")}</div>`;

// ---------------------------------------------------------------------------
// Generic screens
// ---------------------------------------------------------------------------

/** A keyboard (and mouse) driven menu. Resolves to the chosen key, or `backKey` on back. */
function menu(title, intro, items, backKey = null, { canGoBack = true } = {}) {
  return new Promise((resolve) => {
    let index = 0;
    const done = (value) => {
      keyHandler = null;
      resolve(value);
    };
    const render = () => {
      frame(title, headerRight(),
        `${intro.length ? `<p class="intro">${intro.map(esc).join("<br>")}</p>` : ""}
         <ul class="menu" role="listbox">${items
           .map(({ key, label, detail }, i) => `
             <li role="option" data-key="${esc(key)}" aria-selected="${i === index}">
               <span class="hot">${esc(key)}</span><span>${esc(label)}</span>
               ${detail ? `<span class="detail">${esc(detail)}</span>` : ""}
             </li>`)
           .join("")}</ul>`,
        `${kbd("j")}/${kbd("k")} move · ${kbd("Enter")} or ${kbd("l")} select · hotkey jumps${canGoBack ? ` · ${kbd("q")} back` : ""}`);
      app.querySelectorAll(".menu li").forEach((li) => li.addEventListener("click", () => done(li.dataset.key)));
    };
    keyHandler = (key) => {
      const hotkeys = items.map((i) => i.key);
      if (key === "j" || key === "ArrowDown") index = (index + 1) % items.length;
      else if (key === "k" || key === "ArrowUp") index = (index - 1 + items.length) % items.length;
      else if (key === "g") index = 0;
      else if (key === "G") index = items.length - 1;
      else if (key === "Enter" || key === "l" || key === "ArrowRight") return done(items[index].key);
      else if (hotkeys.includes(key)) return done(key);
      else if (["q", "Escape", "h", "ArrowLeft"].includes(key)) return done(backKey);
      else return false;
      render();
    };
    render();
  });
}

/** Show some lines; resolves with the next key pressed (or "click"). */
function notice(title, lines, footer = "press any key") {
  return new Promise((resolve) => {
    frame(title, headerRight(),
      `${linesHtml(lines)}<div class="notice-actions"><button type="button">Continue</button></div>`,
      esc(footer));
    const done = (value) => {
      keyHandler = null;
      resolve(value);
    };
    app.querySelector("button").addEventListener("click", () => done("click"));
    keyHandler = (key) => done(key);
  });
}

const confirm = async (title, question) => (await notice(title, [[question, "warn"]], "y to confirm · any other key to cancel")) === "y";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---------------------------------------------------------------------------
// Playing one target
// ---------------------------------------------------------------------------

/**
 * Resolves with {status: "hit"|"quit"|"timeout", cursor, keys, elapsed, commands, coached, coachOn}.
 * `coach`: undefined = not offered; false/true = offered, starting off/on (toggle with c).
 */
function playTarget({ title, info, lines, cursor, target, allowed, par, prompt, hint, message = ["", ""], deadline, tip, coach }) {
  return new Promise((resolve) => {
    const buffer = new E.KeyBuffer();
    const text = lines.join("\n");
    const result = { status: "hit", cursor, keys: 0, elapsed: 0, commands: [], coached: false, coachOn: !!coach };
    const started = performance.now();
    let [msg, msgStyle] = message;
    let plan = [];
    let planFor = null;
    let timer = null;

    const finish = (status) => {
      clearInterval(timer);
      keyHandler = null;
      result.status = status;
      result.elapsed = (performance.now() - started) / 1000;
      resolve(result);
    };

    const render = () => {
      let coachLine = "";
      if (result.coachOn) {
        const key = `${result.cursor.line},${result.cursor.col},${result.cursor.want}`;
        if (planFor !== key) {
          plan = E.coachPlan(lines, result.cursor, target, allowed);
          planFor = key;
        }
        if (plan.length) {
          coachLine = `<div class="coach">${span("accent", "coach: press")}<span class="press">${esc(plan[0])}</span>`
            + span("dim", `${E.explainCommand(plan[0])}${plan.length > 1 ? `   then ${plan.slice(1).join(" ")}` : ""}`) + "</div>";
        }
      } else if (tip) {
        coachLine = `<div>${span("accent", `tip: ${tip}`)}</div>`;
      }
      frame(title, info(),
        `${bufferHtml(lines, result.cursor, target)}
         <div class="status">
           <div class="row"><span>${esc(prompt)}</span>
             ${span(result.keys <= par ? "good" : "warn", `keys ${result.keys}  par ${par}`)}</div>
           <div class="dim">motions: ${esc(E.MOTIONS.filter((m) => allowed.includes(m)).join(" "))}</div>
           <div class="warn">${buffer.pending ? esc(`pending: ${buffer.pending}`) : "&nbsp;"}</div>
           <div class="msg ${msgStyle}" role="status">${esc(msg) || "&nbsp;"}</div>
           ${coachLine}
         </div>`,
        [hint ? `${kbd("?")} hint` : "", coach !== undefined ? `${kbd("c")} coach` : "",
          `${kbd("Esc")} clear pending`, `${kbd("q")} quit to menu`].filter(Boolean).join(" · "));
    };

    keyHandler = (key) => {
      if (key.startsWith("Arrow")) {
        buffer.clear();
        [msg, msgStyle] = ["Arrow keys don't count here - use h j k l!", "bad"];
      } else if (key === "Escape") {
        buffer.clear();
        msg = "";
      } else if (key === "q" && !buffer.pending) {
        return finish("quit");
      } else if (key === "?" && hint) {
        [msg, msgStyle] = [hint, "accent"];
      } else if (key === "c" && coach !== undefined && !buffer.pending) {
        result.coachOn = !result.coachOn;
        [msg, msgStyle] = result.coachOn ? ["Coach on - follow the highlighted keys.", "accent"] : ["Coach off - you're on your own!", "accent"];
      } else if (key.length === 1) {
        let token;
        try {
          token = buffer.feed(key);
        } catch (error) {
          [msg, msgStyle] = [error.message, "bad"];
          render();
          return;
        }
        if (token) {
          const [count, motion] = token;
          const label = E.commandLabel(count, motion);
          if (!allowed.includes(motion)) {
            [msg, msgStyle] = [`${motion} isn't unlocked in this lesson yet.`, "bad"];
          } else {
            result.coached ||= result.coachOn;
            result.cursor = E.applyMotion(lines, text, result.cursor, count, motion);
            result.keys += label.length;
            result.commands.push(label);
            msg = "";
            if (E.samePos(result.cursor, target)) return finish("hit");
          }
        }
      } else {
        return false;
      }
      render();
    };

    if (deadline) {
      timer = setInterval(() => (performance.now() >= deadline ? finish("timeout") : render()), 100);
    }
    render();
  });
}

// ---------------------------------------------------------------------------
// Lessons
// ---------------------------------------------------------------------------

const lessonById = (id) => content.lessons.find((l) => l.id === id) ?? content.lessons[0];

async function playLesson(lessonId) {
  const lesson = lessonById(lessonId);
  progress.current_lesson = lesson.id;
  save();
  const stats = progress.lessons[lesson.id];
  let roundStars = 0;
  let played = 0;
  let perfect = 0;
  const unlocked = [];

  for (let number = 1; number <= CHALLENGES_PER_ROUND; number++) {
    const { challenge, par, optimal } = E.makeChallenge(content, lesson, rng);
    const info = () => `${number}/${CHALLENGES_PER_ROUND}   ★ ${roundStars}`;
    const result = await playTarget({
      title: lesson.title, info, lines: challenge.lines, cursor: E.cursorAt(challenge.start), target: challenge.target,
      allowed: lesson.commands, par, prompt: challenge.prompt, hint: `${challenge.hint}  (try: ${challenge.solution})`, coach: false,
    });
    if (result.status !== "hit") break;

    const stars = E.rate(result.keys, par);
    const hitPar = result.keys <= par;
    E.updateStats(stats, hitPar, result.elapsed, stars);
    E.updateStats(progress.overall, hitPar, result.elapsed, stars);
    const newly = E.maybeUnlockNext(content, progress, lesson.id);
    if (newly) unlocked.push(newly);
    save();
    const levelUp = awardXp(stars * E.XP_PER_STAR);
    roundStars += stars;
    played += 1;
    perfect += hitPar;

    const news = [newly && `Unlocked: ${newly}!`, levelUp].filter(Boolean);
    if (!(await showFeedback(lesson.title, info, challenge, result, par, optimal, stars, news))) break;
  }

  if (played) {
    const lines = [
      [`${lesson.title} - ${played === CHALLENGES_PER_ROUND ? "round complete" : "round ended"}`, "accent"],
      [""],
      [`Stars       ${roundStars} / ${played * 3}`, "warn"],
      [`Par hits    ${perfect} / ${played}`, perfect === played ? "good" : ""],
      [`Lesson par rate  ${Math.round(E.accuracy(stats) * 100)}%   best streak ${stats.best_streak}`],
      ...unlocked.flatMap((t) => [[""], [`Unlocked: ${t}`, "good"]]),
    ];
    await notice("Round summary", lines);
  }
}

/** Resolves false if the player wants to stop. */
function showFeedback(title, info, challenge, result, par, optimal, stars, news) {
  return new Promise((resolve) => {
    const atPar = result.keys <= par;
    const headline = atPar
      ? [`${E.starsText(stars)}  Par! ${result.keys} key${result.keys === 1 ? "" : "s"} in ${result.elapsed.toFixed(1)}s`, "good"]
      : [`${E.starsText(stars)}  Reached in ${result.keys} keys - par is ${par}`, "warn"];
    frame(title, info(),
      `${bufferHtml(challenge.lines, result.cursor, null)}
       <div class="status">${linesHtml([headline, [`you:     ${result.commands.join(" ")}`, "dim"],
        [`optimal: ${optimal}`, "dim"], ...news.map((n) => [n, "good"])])}</div>`,
      `any key: next target · ${kbd("q")} menu`);
    let timer = null;
    const done = (value) => {
      clearTimeout(timer);
      keyHandler = null;
      resolve(value);
    };
    if (atPar && !news.length) timer = setTimeout(() => done(true), 900);
    keyHandler = (key) => done(key !== "q");
  });
}

async function chooseLesson() {
  for (;;) {
    const items = content.lessons.map((lesson, i) => {
      const stats = progress.lessons[lesson.id];
      const open = progress.unlocked_lessons.includes(lesson.id);
      const detail = !open ? "locked" : stats.attempts ? `★ ${stats.stars}  ${Math.round(E.accuracy(stats) * 100)}% par` : "new";
      return { key: String(i + 1), label: lesson.title, detail };
    });
    items.push({ key: "u", label: "Unlock everything (expert mode)" });
    const choice = await menu("Choose lesson",
      [`Hit par on ${E.UNLOCK_EFFICIENCY * 100}% of targets (min ${E.UNLOCK_ATTEMPTS}) to unlock the next lesson.`], items);
    if (choice === null) return;
    if (choice === "u") {
      for (const l of content.lessons) if (!progress.unlocked_lessons.includes(l.id)) progress.unlocked_lessons.push(l.id);
      save();
      continue;
    }
    const lesson = content.lessons[Number(choice) - 1];
    if (!progress.unlocked_lessons.includes(lesson.id)) {
      await notice("Locked", [[`${lesson.title} is still locked.`, "warn"], ["Hit par more often in the previous lesson to open it."]]);
      continue;
    }
    await playLesson(lesson.id);
    return;
  }
}

// ---------------------------------------------------------------------------
// Quick learn
// ---------------------------------------------------------------------------

async function quickLearn() {
  const intro = await notice("Quick learn", [
    [`${QUICK_LEARN_SECONDS / 60} minutes. Short drills from the lessons you find hardest.`, "accent"],
    [""],
    ["A tip is shown for every target. Aim for par, but don't rush."],
    ["Results count toward lesson progress and unlocks."],
  ], "any key to start · q back");
  if (intro === "q") return;

  const deadline = performance.now() + QUICK_LEARN_SECONDS * 1000;
  const tally = new Map();
  const unlocked = [];
  let message = ["Go!", "good"];
  const info = () => {
    const left = Math.max(0, Math.floor((deadline - performance.now()) / 1000));
    const done = [...tally.values()].reduce((a, [n]) => a + n, 0);
    return `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")} left   ${done} done`;
  };

  for (;;) {
    const lesson = E.pickQuickLesson(content, progress, rng);
    const { challenge, par, optimal } = E.makeChallenge(content, lesson, rng);
    const result = await playTarget({
      title: `Quick learn · ${lesson.title}`, info, lines: challenge.lines, cursor: E.cursorAt(challenge.start),
      target: challenge.target, allowed: lesson.commands, par, prompt: challenge.prompt, message, deadline,
      tip: `${challenge.hint}  (try: ${challenge.solution})`, coach: false,
    });
    if (result.status !== "hit") break;
    const stars = E.rate(result.keys, par);
    const hitPar = result.keys <= par;
    E.updateStats(progress.lessons[lesson.id], hitPar, result.elapsed, stars);
    E.updateStats(progress.overall, hitPar, result.elapsed, stars);
    const newly = E.maybeUnlockNext(content, progress, lesson.id);
    if (newly) unlocked.push(newly);
    save();
    const counts = tally.get(lesson.id) ?? [0, 0];
    tally.set(lesson.id, [counts[0] + 1, counts[1] + hitPar]);
    if (newly) message = [`${E.starsText(stars)}  Unlocked ${newly}!`, "good"];
    else if (hitPar) message = [`${E.starsText(stars)}  par!`, "good"];
    else message = [`${E.starsText(stars)}  ${result.keys} keys, par ${par} - optimal: ${optimal}`, "warn"];
    const levelUp = awardXp(stars * E.XP_PER_STAR);
    if (levelUp) message = [`${levelUp}  ${message[0]}`, "good"];
  }

  if (!tally.size) return;
  const lines = [["Time's up - nice session.", "accent"], [""]];
  for (const [id, [done, hits]] of tally) lines.push([`${lessonById(id).title.padEnd(24)} ${hits}/${done} at par`, hits === done ? "good" : ""]);
  const [weakId, [wDone, wHits]] = [...tally].sort((a, b) => a[1][1] / a[1][0] - b[1][1] / b[1][0])[0];
  if (wHits < wDone) lines.push([""], [`Practise next: ${lessonById(weakId).title}`, "warn"]);
  for (const t of unlocked) lines.push([`Unlocked: ${t}`, "good"]);
  await sleep(300);
  await notice("Quick learn complete", lines);
}

// ---------------------------------------------------------------------------
// Real-world code with a coach
// ---------------------------------------------------------------------------

async function realWorld() {
  for (;;) {
    const items = content.languages.map((language, i) => {
      const scenarios = content.scenarios.filter((s) => s.language === language);
      const done = scenarios.filter((s) => s.id in progress.scenarios).length;
      return { key: String((i + 1) % 10), label: language, detail: `${done}/${scenarios.length} done` };
    });
    const choice = await menu("Real-world code", [
      "Short editing tasks on real code: the kind of jumps you make before a ciw or ci\".",
      "The coach shows the best next key from wherever you are - press c to hide it and go solo.",
    ], items);
    if (choice === null) return;
    await chooseScenario(content.languages[(Number(choice) + 9) % 10]);
  }
}

async function chooseScenario(language) {
  const scenarios = content.scenarios.filter((s) => s.language === language);
  for (;;) {
    let choice = "1";
    if (scenarios.length > 1) {
      choice = await menu(`Real-world · ${language}`, [], scenarios.map((s, i) => {
        const best = progress.scenarios[s.id];
        return { key: String(i + 1), label: s.title, detail: best === undefined ? "new" : `best ★ ${best}/${s.steps.length * 3}` };
      }));
      if (choice === null) return;
    }
    const finished = await playScenario(scenarios[Number(choice) - 1]);
    if (!finished || scenarios.length === 1) return;
  }
}

async function playScenario(scenario) {
  const { lines } = scenario;
  let cursor = E.cursorAt(E.scenarioStart(lines));
  let coachOn = true;
  let total = 0;
  let solo = 0;
  let pars = 0;
  let message = ["", ""];
  const steps = scenario.steps.length;
  const title = `${scenario.language} · ${scenario.title}`;

  for (let number = 1; number <= steps; number++) {
    const step = scenario.steps[number - 1];
    const target = E.stepTarget(lines, step);
    const { cost: par, keys: optimal } = E.solveTo(lines, cursor, target, E.MOTIONS);
    const result = await playTarget({
      title, info: () => `step ${number}/${steps}   ★ ${total}`, lines, cursor, target, allowed: E.MOTIONS, par,
      prompt: step.task, message, coach: coachOn,
    });
    if (result.status !== "hit") return false;
    cursor = result.cursor;
    coachOn = result.coachOn;
    const stars = E.rate(result.keys, par);
    total += stars;
    solo += !result.coached;
    pars += result.keys <= par;
    const verdict = result.keys <= par ? "par!" : `${result.keys} keys, par ${par} (${optimal}).`;
    message = [`${E.starsText(stars)} ${verdict}  ${step.why}`, stars === 3 ? "good" : "warn"];
    const levelUp = awardXp(stars * E.XP_PER_STAR);
    if (levelUp) message = [`${levelUp}  ${message[0]}`, "good"];
  }

  const best = progress.scenarios[scenario.id];
  const record = best === undefined || total > best;
  if (record) {
    progress.scenarios[scenario.id] = total;
    save();
  }
  await notice("Scenario complete", [
    [`${title} - done!`, "accent"],
    [""],
    message,
    [""],
    [`Stars       ${total} / ${steps * 3}${record && best !== undefined ? "   new best!" : ""}`, "warn"],
    [`Par hits    ${pars} / ${steps}`],
    [`Solo steps  ${solo} / ${steps}${solo === steps ? "" : "   (try it again with the coach off: c)"}`, solo === steps ? "good" : ""],
  ]);
  return true;
}

// ---------------------------------------------------------------------------
// Sprint
// ---------------------------------------------------------------------------

async function sprint() {
  const allowed = E.unlockedMotions(content, progress);
  const intro = await notice("Sprint", [
    [`${SPRINT_SECONDS} seconds. Hit as many targets as you can.`, "accent"],
    [""],
    [`Motions: ${allowed.join(" ")}`],
    ["Par = 100 pts, near par = 50, otherwise 20."],
    ["Consecutive par hits build a combo multiplier (up to x5)."],
    ["Your cursor stays where it lands - plan the next jump."],
    [""],
    [`Best so far: ${progress.sprint_best}`, "warn"],
  ], "any key to start · q back");
  if (intro === "q") return;

  let score = 0;
  let combo = 1;
  let hits = 0;
  let pars = 0;
  let onBuffer = 0;
  const order = [...content.sprint_snippets].sort(() => rng.random() - 0.5);
  let snippet = 0;
  let lines = order[0];
  let cursor = E.cursorAt(E.pos(0, 0));
  let message = ["Go!", "good"];
  const deadline = performance.now() + SPRINT_SECONDS * 1000;
  const info = () => `${Math.max(0, (deadline - performance.now()) / 1000).toFixed(1)}s   ${score} pts   x${combo}`;

  for (;;) {
    if (onBuffer === 5) {
      snippet = (snippet + 1) % order.length;
      lines = order[snippet];
      onBuffer = 0;
      cursor = E.cursorAt(E.pos(0, E.firstNonBlank(lines, 0)));
      message = ["New buffer!", "accent"];
    }
    const { target, par, optimal } = E.pickSprintTarget(lines, cursor, allowed, rng);
    const result = await playTarget({ title: "Sprint", info, lines, cursor, target, allowed, par, prompt: "Reach the target!", message, deadline });
    if (result.status === "quit") return;
    if (result.status === "timeout") break;
    cursor = result.cursor;
    hits += 1;
    onBuffer += 1;
    const stars = E.rate(result.keys, par);
    const points = { 3: 100, 2: 50, 1: 20 }[stars] * combo;
    score += points;
    if (stars === 3) {
      pars += 1;
      combo = Math.min(5, combo + 1);
      message = [`${E.starsText(stars)} +${points}  par!`, "good"];
    } else {
      combo = 1;
      message = [`${E.starsText(stars)} +${points}  optimal was: ${optimal}`, "warn"];
    }
    const levelUp = awardXp(stars * E.XP_PER_STAR);
    if (levelUp) message = [`${levelUp}  ${message[0]}`, "good"];
  }

  const record = score > progress.sprint_best;
  if (record) {
    progress.sprint_best = score;
    save();
  }
  await sleep(300);
  await notice("Sprint over", [
    ["Time!", "accent"],
    [""],
    [`Score     ${score}`, "warn"],
    [`Targets   ${hits}   (${pars} at par)`],
    [`Best      ${progress.sprint_best}`],
    ...(record ? [[""], ["New personal best!", "good"]] : []),
  ]);
}

// ---------------------------------------------------------------------------
// Survival
// ---------------------------------------------------------------------------

async function survival() {
  const best = progress.survival_best;
  const allowed = E.unlockedMotions(content, progress);
  const S = E.SURVIVAL;
  const intro = await notice("Survival", [
    ["Clear each level's targets before the clock runs out.", "accent"],
    [""],
    [`Start with ${S.startScore} points. Each target +${S.pointsCorrect}, each timeout ${S.pointsWrong}.`],
    [`Hit 0 and it's game over. Reach ${S.winScore} to win.`],
    ["Fast, efficient moves raise the difficulty: more targets"],
    ["per level and less time per target. Slow ones ease it off."],
    [`Motions: ${allowed.join(" ")}`],
    [""],
    [`Best: ${best.score} points, level ${best.level}`, "warn"],
  ], "any key to start · q back");
  if (intro === "q") return;

  const game = new E.SurvivalGame((count) => E.survivalSequence(content, count, allowed, rng));
  const levelBefore = progress.xp.level;
  let lines = null;
  let cursor = null;
  let message = ["Go!", "good"];
  let cleared = 0;
  let ending = "quit";

  outer: for (;;) {
    const target = game.current;
    if (target.lines !== lines) {
      lines = target.lines;
      cursor = E.cursorAt(E.scenarioStart(lines));
    }
    const limit = game.params.timeLimit;
    const deadline = performance.now() + limit * 1000;
    const { cost: par, keys: optimal } = E.solveTo(lines, cursor, target.pos, allowed);
    const level = game.level;
    const left = game.sequence.length;
    const info = () => `level ${level} · ${left} left · diff ${game.difficulty}   ${game.score} pts   `
      + `${Math.max(0, (deadline - performance.now()) / 1000).toFixed(1)}s`;
    const result = await playTarget({ title: "Survival", info, lines, cursor, target: target.pos, allowed, par,
      prompt: `Reach the target within ${limit}s!`, message, deadline });
    if (result.status === "quit") break;
    cursor = result.cursor;

    let status;
    if (result.status === "timeout") {
      game.trackPerformance(limit, 0);
      status = game.record(false);
      message = [`Too slow! ${S.pointsWrong}  optimal was: ${optimal}`, "bad"];
    } else {
      game.trackPerformance(Math.max(result.elapsed, 0.01), Math.min(1, par / result.keys));
      status = game.record(true);
      cleared += 1;
      E.addXp(progress.xp, S.xpCorrect);
      const stars = E.rate(result.keys, par);
      message = status === "level_complete"
        ? [`Level ${level} cleared! Next: ${game.sequence.length} targets, ${game.params.timeLimit}s each`, "accent"]
        : [`${E.starsText(stars)} +${S.pointsCorrect}${result.keys <= par ? "  par!" : `  optimal was: ${optimal}`}`, stars === 3 ? "good" : "warn"];
    }
    switch (status) {
      case "over":
        ending = "over";
        break outer;
      case "won":
        ending = "won";
        break outer;
      default:
    }
  }

  const score = Math.max(0, game.score);
  const record = score > best.score;
  if (record) progress.survival_best = { score, level: game.level };
  save();
  const headline = { over: ["Game over - your score hit zero.", "bad"], won: [`You won! ${S.winScore} points - a true motion master.`, "good"], quit: ["Run ended.", "accent"] }[ending];
  await sleep(300);
  await notice("Survival", [
    headline,
    [""],
    [`Score       ${score}`, "warn"],
    [`Level       ${game.level}   (difficulty ${game.difficulty})`],
    [`Targets     ${cleared}`],
    [`Best        ${progress.survival_best.score} points, level ${progress.survival_best.level}`],
    ...(record && score > 0 ? [[""], ["New personal best!", "good"]] : []),
    ...(progress.xp.level > levelBefore ? [[`Level up! You're now level ${progress.xp.level}.`, "good"]] : []),
  ]);
}

// ---------------------------------------------------------------------------
// Info screens and main menu
// ---------------------------------------------------------------------------

async function showProgress() {
  const o = progress.overall;
  const lines = [
    [`Overall par rate ${(E.accuracy(o) * 100).toFixed(1)}%   targets ${o.attempts}   avg ${E.averageTime(o).toFixed(1)}s   ★ ${o.stars}`, "accent"],
    [`Best streak ${o.best_streak}   sprint best ${progress.sprint_best}   survival best ${progress.survival_best.score} (level ${progress.survival_best.level})`],
    [`Player level ${progress.xp.level}   ${progress.xp.experience}/${progress.xp.experience_to_next_level} xp to next`, "warn"],
    [""],
  ];
  for (const lesson of content.lessons) {
    const s = progress.lessons[lesson.id];
    if (!progress.unlocked_lessons.includes(lesson.id)) {
      lines.push([`${lesson.title.padEnd(24)} locked`, "dim"]);
      continue;
    }
    const ratio = E.accuracy(s);
    const bar = "█".repeat(Math.floor(14 * ratio)) + "░".repeat(14 - Math.floor(14 * ratio));
    lines.push([`${lesson.title.padEnd(24)} ${bar} ${String(Math.round(ratio * 100)).padStart(3)}%  n=${String(s.attempts).padEnd(3)} ★ ${s.stars}`,
      ratio >= E.UNLOCK_EFFICIENCY ? "good" : ""]);
  }
  lines.push([""], ["Progress is saved in this browser.", "dim"]);
  await notice("Progress", lines);
}

async function showReference() {
  await notice("Motion reference", [
    ...Object.entries(content.reference).map(([key, desc]) => [`${key.padEnd(4)} ${desc}`]),
    [""],
    ["Counts go first: 3l, 2w, 4j. A count before gg/G is a line number.", "dim"],
    ["w/b/e treat punctuation as its own word: foo.bar is three words.", "dim"],
    ["Esc cancels a half-typed count or g. c toggles the coach where it's offered.", "dim"],
  ]);
}

async function mainMenu() {
  for (;;) {
    const current = lessonById(progress.current_lesson);
    const choice = await menu("Main menu", [
      "Move the cursor with real Vim keys. Reach the green target",
      "in as few keystrokes as you can - par earns three stars.",
    ], [
      { key: "c", label: "Continue", detail: current.title },
      { key: "o", label: "Choose lesson" },
      { key: "t", label: "Quick learn", detail: `${QUICK_LEARN_SECONDS / 60} minutes on your weak spots` },
      { key: "w", label: "Real-world", detail: "edit real code with a coach" },
      { key: "v", label: "Survival", detail: "timed levels that speed up" },
      { key: "s", label: "Sprint", detail: `${SPRINT_SECONDS}s time attack` },
      { key: "p", label: "Progress" },
      { key: "r", label: "Motion reference" },
      { key: "x", label: "Reset progress" },
    ], null, { canGoBack: false });
    if (choice === "c") await playLesson(current.id);
    else if (choice === "o") await chooseLesson();
    else if (choice === "t") await quickLearn();
    else if (choice === "w") await realWorld();
    else if (choice === "v") await survival();
    else if (choice === "s") await sprint();
    else if (choice === "p") await showProgress();
    else if (choice === "r") await showReference();
    else if (choice === "x" && (await confirm("Reset", "Reset all saved progress, stars, XP and best scores? [y/N]"))) {
      progress = E.defaultProgress(content);
      save();
    }
  }
}

async function start() {
  try {
    const response = await fetch("content.json");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    content = await response.json();
  } catch (error) {
    app.innerHTML = `<p class="bad">Couldn't load content.json (${esc(error.message)}).</p>
      <p class="dim">If you opened index.html straight from disk, serve it instead: <code>scripts/build-web.sh --serve</code></p>`;
    return;
  }
  progress = loadProgress();
  if (window.matchMedia("(pointer: coarse)").matches && !window.matchMedia("(any-pointer: fine)").matches) {
    await notice("Heads up", [
      ["This trainer is played with a physical keyboard.", "warn"],
      ["On a phone or tablet, connect a Bluetooth keyboard for the full experience."],
    ], "any key or tap Continue");
  }
  await mainMenu();
}

start();
