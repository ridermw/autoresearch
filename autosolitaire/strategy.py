"""
Klondike Solitaire strategy — the agent modifies this file.
Usage: python strategy.py

The goal: maximize win_rate over 10,000 fixed deals of 3-card-draw Klondike.
Higher is better.

The agent can change anything in this file: the heuristics, the move
ordering, add lookahead/backtracking, maintain state across calls, etc.
The only contract is that choose_move(game_state, legal_moves) must return
a Move from the legal_moves list (or an integer index into it).
"""

import random

from prepare import (
    GameState,
    Move,
    MoveType,
    apply_move,
    evaluate_strategy,
    get_legal_moves,
)

ROLLOUTS = 6
ROLLOUT_DEPTH = 24
CANDIDATES = 3


def _is_safe_to_foundation(gs: GameState, card) -> bool:
    """
    A card is 'safe' to move to foundation if both cards of the opposite
    color with rank one less are already on their foundations.
    """
    if card.rank <= 1:
        return True
    needed_rank = card.rank - 1
    if card.color == 1:
        opposite_suits = (0, 3)
    else:
        opposite_suits = (1, 2)
    return all(gs.foundation_top_rank(suit) >= needed_rank for suit in opposite_suits)


def _reveals_facedown(gs: GameState, move: Move) -> bool:
    """Does this move reveal a face-down card underneath?"""
    if move.type == MoveType.TABLEAU_TO_TABLEAU:
        pile = gs.tableau[move.from_col]
        return move.count == len(pile.face_up) and bool(pile.face_down)
    if move.type == MoveType.TABLEAU_TO_FOUNDATION:
        pile = gs.tableau[move.from_col]
        return len(pile.face_up) == 1 and bool(pile.face_down)
    return False


def _get_card_for_move(gs: GameState, move: Move):
    """Get the card being played for foundation moves."""
    if move.type == MoveType.WASTE_TO_FOUNDATION:
        return gs.waste[-1] if gs.waste else None
    if move.type == MoveType.TABLEAU_TO_FOUNDATION:
        return gs.tableau[move.from_col].top_card()
    return None


def _move_priority(gs: GameState, move: Move) -> tuple:
    """Lower tuple = higher priority."""
    t = move.type

    if t == MoveType.FLIP_TABLEAU:
        return (0,)

    if t in (MoveType.WASTE_TO_FOUNDATION, MoveType.TABLEAU_TO_FOUNDATION):
        card = _get_card_for_move(gs, move)
        reveals = (
            _reveals_facedown(gs, move)
            if t == MoveType.TABLEAU_TO_FOUNDATION
            else False
        )

        if card.rank <= 1:
            return (1, 0 if reveals else 1)
        if reveals:
            return (2, -card.rank)
        if _is_safe_to_foundation(gs, card):
            return (3, -card.rank)
        if card.rank <= 5:
            return (6, -card.rank)
        return (9, -card.rank)

    if t == MoveType.TABLEAU_TO_TABLEAU and _reveals_facedown(gs, move):
        return (4, -len(gs.tableau[move.from_col].face_down))

    if t == MoveType.WASTE_TO_TABLEAU:
        pile = gs.tableau[move.to_col]
        return (5, -len(pile.face_down), -len(pile.face_up))

    if t == MoveType.DRAW:
        return (7,)

    if t == MoveType.TABLEAU_TO_TABLEAU:
        src = gs.tableau[move.from_col]
        dst = gs.tableau[move.to_col]
        bottom_card = src.face_up[-move.count]
        if dst.is_empty() and bottom_card.rank == 12 and src.face_down:
            return (8, -len(src.face_down))
        if dst.is_empty():
            return (10, 5)
        return (10, -len(dst.face_down), -len(dst.face_up), -move.count)

    if t == MoveType.RESET_STOCK:
        return (11,)

    return (99,)


def _baseline_move(gs: GameState, legal_moves: list[Move]) -> Move:
    return min(legal_moves, key=lambda move: _move_priority(gs, move))


def _state_score(gs: GameState) -> float:
    foundation = gs.total_foundation_cards()
    facedown = sum(len(pile.face_down) for pile in gs.tableau)
    empty_cols = sum(1 for pile in gs.tableau if pile.is_empty())
    score = foundation * 22.0 - facedown * 9.0 - gs.stock_passes * 7.0
    if empty_cols:
        king_ready = bool(gs.waste and gs.waste[-1].rank == 12) or any(
            pile.face_up and pile.face_up[0].rank == 12 for pile in gs.tableau
        )
        score += empty_cols * (4.0 if king_ready else -6.0)
    return score


def _rollout_move(gs: GameState, legal_moves: list[Move], rng: random.Random) -> Move:
    ordered = sorted(legal_moves, key=lambda move: _move_priority(gs, move))
    best_bucket = _move_priority(gs, ordered[0])[0]
    shortlist = [move for move in ordered if _move_priority(gs, move)[0] <= best_bucket + 1]
    shortlist = shortlist[: min(3, len(shortlist))]
    return shortlist[0] if len(shortlist) == 1 else shortlist[rng.randrange(len(shortlist))]


def _rollout_score(gs: GameState, seed: int) -> float:
    trial = gs.clone()
    rng = random.Random(seed)
    for _ in range(ROLLOUT_DEPTH):
        if trial.is_won():
            return 1_000_000.0 + _state_score(trial)
        legal = get_legal_moves(trial)
        if not legal:
            break
        move = _rollout_move(trial, legal, rng)
        apply_move(trial, move)
    return _state_score(trial)


def choose_move(gs: GameState, legal_moves: list[Move]) -> Move:
    """
    Keep the baseline on obviously good moves. When the choice is ambiguous,
    compare a few candidate moves with short stochastic rollouts.
    """
    ordered = sorted(legal_moves, key=lambda move: _move_priority(gs, move))
    best = ordered[0]
    if _move_priority(gs, best)[0] <= 5:
        return best

    state_seed = hash(gs.state_key())
    best_move = best
    best_score = float("-inf")
    for idx, move in enumerate(ordered[:CANDIDATES]):
        total = 0.0
        for rollout in range(ROLLOUTS):
            child = gs.clone()
            apply_move(child, move)
            total += _rollout_score(child, state_seed + idx * 101 + rollout)
        average = total / ROLLOUTS
        if average > best_score:
            best_score = average
            best_move = move
    return best_move


if __name__ == "__main__":
    import sys
    import time

    t0 = time.time()
    print("Klondike 3-Card Draw — Strategy Evaluation")
    print("=" * 50)
    print()

    evaluate_strategy(choose_move)

    print()
    print(f"Strategy file: {__file__}")
    print(f"Wall clock:    {time.time() - t0:.1f}s")

    sys.exit(0)
