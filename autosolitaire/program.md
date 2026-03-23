# autosolitaire

This is an experiment to have an LLM autonomously improve a Klondike Solitaire (3-card draw) playing algorithm.

## Setup

To set up a new experiment, work with the user to:

1. **Agree on a run tag**: propose a tag based on today's date (e.g. `jun15`). The branch `autosolitaire/<tag>` must not already exist — this is a fresh run.
2. **Create the branch**: `git checkout -b autosolitaire/<tag>` from current master.
3. **Read the in-scope files**: The project is small. Read these files for full context:
   - `prepare.py` — game engine, move generation, evaluation harness. Do not modify.
   - `strategy.py` — the file you modify. Contains `choose_move(gs, legal_moves) -> Move`.
4. **Verify the engine works**: Run `python prepare.py --num-games 100` to confirm it runs without errors.
5. **Initialize results.tsv**: Create `results.tsv` with just the header row. The baseline will be recorded after the first run.
6. **Confirm and go**: Confirm setup looks good.

Once you get confirmation, kick off the experimentation.

## Experimentation

Each experiment runs on CPU. You launch it simply as: `python strategy.py`

The evaluation plays **10,000 fixed deals** (seeds 1,000,000 through 1,009,999) and reports the win rate.

**What you CAN do:**
- Modify `strategy.py` — this is the only file you edit. Everything is fair game: move priority heuristics, lookahead search, backtracking, Monte Carlo rollouts, state tracking across moves, precomputation, entirely new algorithms.

**What you CANNOT do:**
- Modify `prepare.py`. It is read-only. It contains the game engine, move generation, deal logic, and the fixed evaluation harness.
- Install new packages or add dependencies. You can only use the Python standard library plus what `prepare.py` already imports.
- Modify the evaluation. `evaluate_strategy()` in `prepare.py` is the ground truth metric.

**The goal is simple: get the highest win_rate.** Everything is fair game: change the heuristics, add search, add backtracking, add Monte Carlo sampling, maintain persistent state, precompute — whatever works. The only constraint is that the code runs without crashing and finishes within a reasonable time.

**Time** is a soft constraint. The baseline strategy evaluates in a few seconds. More complex strategies (lookahead, backtracking) will be slower. Anything under 2 minutes total is fine. If a run exceeds 5 minutes, kill it and treat it as a failure.

**Simplicity criterion**: All else being equal, simpler is better. A small win_rate improvement that adds ugly complexity is questionable. Conversely, removing something and getting equal or better results is a great outcome — that's a simplification win. When evaluating whether to keep a change, weigh the complexity cost against the improvement magnitude. A 0.001 win_rate improvement that adds 50 lines of hacky code? Probably not worth it. A 0.01 win_rate improvement from a clean 10-line change? Definitely keep. An improvement of ~0 but much simpler code? Keep.

**The first run**: Your very first run should always be to establish the baseline — run the current `strategy.py` as-is. Note that `strategy.py` may already contain an evolved strategy from a previous experiment run. Record whatever it achieves as the starting point for this run.

## Output format

Once the evaluation finishes it prints a summary like this:

```
---
win_rate:         0.082300
wins:             823
total_games:      10000
avg_foundation:   18.4
avg_moves:        231.7
total_seconds:    3.2
```

You can extract the key metrics from the log file:

```
grep "^win_rate:\|^avg_foundation:" run.log
```

**Important**: 3-card draw Klondike is extremely hard for greedy heuristics. A naive greedy heuristic wins ~0.14% of games (14/10,000) with avg_foundation ~4.1. The current `strategy.py` already includes a beam-preview search that achieves ~11% win rate. Use `avg_foundation` as a progress signal when win_rate differences are small (it's more granular). To push beyond the current level, consider deeper search, Monte Carlo rollouts, or hybrid approaches — see the strategy ideas section below.

## Logging results

When an experiment is done, log it to `results.tsv` (tab-separated, NOT comma-separated — commas break in descriptions).

The TSV has a header row and 5 columns:

```
commit	win_rate	avg_foundation	status	description
```

1. git commit hash (short, 7 chars)
2. win_rate achieved (e.g. 0.082300) — use 0.000000 for crashes
3. avg_foundation cards (e.g. 18.4) — use 0.0 for crashes
4. status: `keep`, `discard`, or `crash`
5. short text description of what this experiment tried

**Deciding what to keep**: A change is an improvement if avg_foundation increases meaningfully (even if win_rate stays at 0). Once you start getting wins, win_rate becomes the primary metric. When both metrics are available, prefer changes that improve win_rate; use avg_foundation as a tiebreaker.

Example:

```
commit	win_rate	avg_foundation	status	description
a1b2c3d	0.001400	4.1	keep	baseline (greedy heuristic)
b2c3d4e	0.002100	5.8	keep	prefer revealing moves over waste-to-tableau
c3d4e5f	0.000800	3.3	discard	aggressive foundation play (worse on both metrics)
d4e5f6g	0.000000	0.0	crash	backtracking solver (recursion limit)
e5f6g7h	0.012000	12.1	keep	DFS with depth limit + heuristic fallback
f6g7h8i	0.035000	16.7	keep	Monte Carlo rollouts for move selection
```

## The experiment loop

The experiment runs on a dedicated branch (e.g. `autosolitaire/jun15`).

LOOP FOREVER:

1. Look at the git state: the current branch/commit we're on
2. Edit `strategy.py` with an experimental idea by directly hacking the code.
3. git commit
4. Run the experiment: `python strategy.py > run.log 2>&1` (redirect everything — do NOT use tee or let output flood your context)
5. Read out the results: `grep "^win_rate:\|^avg_foundation:" run.log`
6. If the grep output is empty, the run crashed. Run `tail -n 50 run.log` to read the Python stack trace and attempt a fix. If you can't get things to work after more than a few attempts, give up.
7. Record the results in the tsv
8. If the result improved (higher win_rate, or same win_rate but higher avg_foundation), you "advance" the branch, keeping the git commit
9. If the result is equal or worse on both metrics, you git reset back to where you started

The idea is that you are a completely autonomous researcher trying things out. If they work, keep. If they don't, discard. And you're advancing the branch so that you can iterate. If you feel like you're getting stuck in some way, you can rewind but you should probably do this very very sparingly (if ever).

**Timeout**: Each experiment should take under 2 minutes. If a run exceeds 5 minutes, kill it and treat it as a failure (discard and revert).

**Crashes**: If a run crashes (recursion error, bug, etc.), use your judgment: If it's something dumb and easy to fix (e.g. a typo, a missing import), fix it and re-run. If the idea itself is fundamentally broken, just skip it, log "crash" as the status in the tsv, and move on.

**NEVER STOP**: Once the experiment loop has begun (after the initial setup), do NOT pause to ask the human if you should continue. Do NOT ask "should I keep going?" or "is this a good stopping point?". The human might be asleep, or gone from a computer and expects you to continue working *indefinitely* until you are manually stopped. You are autonomous. If you run out of ideas, think harder — study the game engine code, think about known solitaire strategies, try combining previous near-misses, try more radical approaches. The loop runs until the human interrupts you, period.

## Strategy ideas to explore

Here are some directions worth trying (rough order of expected impact):

**Understanding the challenge**: 3-card draw Klondike is fundamentally different from 1-card draw. You can only access every 3rd card in the waste pile. This means most cards are inaccessible to a greedy heuristic — you need to strategically play waste cards to *shift the alignment* and access different cards on subsequent passes. This is why the baseline wins 0% — it's not a bug, it's the core challenge.

**Phase 1 — Heuristic improvements (fast, may reach avg_foundation ~5-10):**
- Tune the move priority ordering (which moves to prefer over others)
- Be smarter about when to play to foundation vs. keep on tableau
- Prefer moves that reveal face-down cards (more information = more options)
- Track waste alignment: know which cards become accessible if you play the current waste card
- Value waste-to-tableau moves highly — each one shifts the draw alignment for ALL subsequent cards
- Avoid moving cards to empty columns unless a King is available to fill them

**Phase 2 — Search-based approaches (slower, this is where wins start):**
- One-ply lookahead: try each move, evaluate resulting state, pick best
- Multi-ply lookahead with pruning
- Backtracking/DFS: try a move, recurse, undo if stuck, try alternatives (use game_state.clone() for branching)
- Beam search: track top-N candidate game states in parallel
- IMPORTANT: use game_state.state_key() for visited-state detection to avoid infinite loops in search

**Phase 3 — Monte Carlo methods (powerful, can reach 10%+ wins):**
- For each legal move, play out N random continuations, pick the move with best average outcome
- Use foundation card count as a rollout evaluation (faster than playing to completion)
- Combine with heuristic: use fast heuristic for "obvious" moves, Monte Carlo only for ambiguous decisions

**State evaluation heuristics (for use in search):**
- Number of face-down cards remaining (fewer = better)
- Number of empty tableau columns (more = better, up to a point)
- Cards on foundation (more = better)
- Waste alignment: how many useful cards are accessible at current draw positions
- "Trapped" cards: important cards buried under many others
- Runs built on tableau (longer sequential runs = better)

**Hybrid approaches (best results):**
- Fast heuristic for obvious moves (safe foundation plays, mandatory flips)
- Search/backtracking only when the heuristic is uncertain
- Time-limited search: spend more computation on harder positions
- Iterative deepening: try shallow search first, go deeper if time permits

**Rough performance targets for 3-card draw:**
- Baseline greedy heuristic: ~0.14% wins, avg_foundation ~4.1
- Improved heuristic with waste awareness: ~0.5-1% wins, avg_foundation ~6-10
- Basic search/backtracking: 2-8% wins
- Monte Carlo + heuristic: 5-15% wins
- Sophisticated solver: 15-30%+ wins
- State of the art: ~35% wins
- There is a LOT of headroom.