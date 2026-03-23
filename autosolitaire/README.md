# autosolitaire

Autonomous Klondike Solitaire (3-card draw) strategy research, built on the [autoresearch](https://github.com/karpathy/autoresearch) pattern.

An AI agent iteratively modifies a solitaire-playing algorithm, evaluates it over 10,000 fixed deals, and keeps changes that improve the win rate. You wake up to a log of experiments and (hopefully) a stronger solver.

## How it works

Three files:

- **`prepare.py`** — the game engine, move generation, dealing, and evaluation harness. **Do not modify.**
- **`strategy.py`** — the playing algorithm. Contains `choose_move(game_state, legal_moves) -> Move`. **This is the only file the agent edits.**
- **`program.md`** — instructions for the autonomous agent loop.

The metric is **win_rate** over 10,000 deterministic deals (higher is better), with **avg_foundation** (average cards moved to foundation) as a secondary signal.

## Quick start

No GPU needed — everything runs on CPU.

```bash
# Verify the engine works (plays 1,000 games, ~1 second)
python prepare.py --num-games 1000

# Run full baseline evaluation (10,000 games, ~10 seconds)
python strategy.py

# Debug a single game interactively
python prepare.py --seed 42
```

### Baseline results (3-card draw)

```
win_rate:         0.001400
wins:             14
total_games:      10000
avg_foundation:   4.1
avg_moves:        35.6
total_seconds:    10.3
```

## Running the agent

Spin up Claude, Codex, or your preferred coding agent in this directory, then prompt:

```
Hi, have a look at program.md and let's kick off a new experiment! Let's do the setup first.
```

The agent will read the files, establish a baseline, then loop: modify `strategy.py` → evaluate → keep or revert → repeat.

## Why 3-card draw?

3-card draw Klondike is dramatically harder than 1-card draw. You can only access every 3rd card in the waste pile, so most cards are inaccessible to a simple greedy heuristic. This makes it an ideal optimization target:

| Approach | Expected win rate |
|---|---|
| Baseline greedy heuristic | ~0.14% |
| Improved heuristic with waste awareness | ~0.5–1% |
| Basic search/backtracking | 2–8% |
| Monte Carlo + heuristic | 5–15% |
| Sophisticated solver | 15–30%+ |
| State of the art | ~35% |

The jump from 0.14% to 35% is enormous — the agent has to discover search, backtracking, Monte Carlo methods, and positional evaluation, all autonomously.

## Game rules

Standard Klondike Solitaire:

- 7 tableau piles (pile *i* has *i* face-down cards + 1 face-up)
- 24 cards in the stock, drawn **3 at a time**
- Only the top waste card is playable; playing it shifts which cards are accessible on subsequent draws
- 4 foundation piles (Ace → King, by suit)
- Tableau builds descending rank, alternating color
- Only Kings may fill empty tableau columns
- Unlimited passes through the stock
- Win = all 52 cards on foundations

## Design choices

- **Fixed evaluation set.** The same 10,000 seeds every time, so strategies are directly comparable.
- **CPU only.** No GPU, no dependencies beyond the Python standard library.
- **Cycle detection.** The engine detects repeated game states and stops (the strategy is stuck). Better strategies avoid this by finding productive moves.
- **Fast iteration.** The baseline evaluates in ~10 seconds. Even sophisticated strategies should finish under 2 minutes. This means ~30+ experiments per hour.
- **Single file to modify.** The agent only touches `strategy.py`, keeping diffs small and reviewable.

## Project structure

```
prepare.py      — game engine + evaluation harness (do not modify)
strategy.py     — playing algorithm (agent modifies this)
program.md      — agent instructions
README.md       — this file
```

## License

MIT