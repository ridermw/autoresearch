"""
Klondike Solitaire strategy - the agent modifies this file.
Usage: python strategy.py

The goal: maximize win_rate over 10,000 fixed deals of 3-card-draw Klondike.
Higher is better.

The agent can change anything in this file: the heuristics, the move
ordering, add lookahead/backtracking, maintain state across calls, etc.
The only contract is that choose_move(game_state, legal_moves) must return
a Move from the legal_moves list (or an integer index into it).
"""

from prepare import (
    GameState,
    Move,
    MoveType,
    apply_move,
    evaluate_strategy,
    foundation_accepts,
    get_legal_moves,
)

PREVIEW_DEPTH = 7
PREVIEW_CANDIDATES = 10
BEAM_WIDTH = 1
BEAM_EXPANSION = 3
WASTE_LOOKAHEAD = 2


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
        return (5, -len(pile.face_down), len(pile.face_up))

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


def _king_ready(gs: GameState) -> bool:
    return bool(gs.waste and gs.waste[-1].rank == 12) or any(
        pile.face_up and pile.face_up[0].rank == 12 for pile in gs.tableau
    )


def _tableau_target_count(gs: GameState, card) -> int:
    count = 0
    for pile in gs.tableau:
        if pile.is_empty():
            if card.rank == 12:
                count += 1
            continue
        top = pile.top_card()
        if top and top.color != card.color and top.rank == card.rank + 1:
            count += 1
    return count


def _waste_future_score(gs: GameState) -> float:
    trial = gs.clone()
    score = 0.0
    for step in range(WASTE_LOOKAHEAD):
        if not trial.waste:
            if trial.stock:
                apply_move(trial, Move(MoveType.DRAW))
            elif trial.waste:
                apply_move(trial, Move(MoveType.RESET_STOCK))
            else:
                break
        if not trial.waste:
            break
        card = trial.waste[-1]
        weight = 1.0 / (step + 1)
        if foundation_accepts(trial, card):
            score += 10.0 * weight
        tableau_targets = _tableau_target_count(trial, card)
        if tableau_targets:
            score += (6.0 + 2.0 * tableau_targets) * weight
        if trial.stock:
            apply_move(trial, Move(MoveType.DRAW))
        elif trial.waste:
            apply_move(trial, Move(MoveType.RESET_STOCK))
        else:
            break
    return score


def _state_score(gs: GameState) -> float:
    foundation = gs.total_foundation_cards()
    facedown = sum(len(pile.face_down) for pile in gs.tableau)
    empty_cols = sum(1 for pile in gs.tableau if pile.is_empty())
    score = foundation * 22.0 - facedown * 14.0 - gs.stock_passes * 6.0
    if gs.waste:
        waste_card = gs.waste[-1]
        if foundation_accepts(gs, waste_card):
            score += 10.0
        tableau_targets = _tableau_target_count(gs, waste_card)
        score += 5.0 * tableau_targets
    score += _waste_future_score(gs)
    if empty_cols:
        score += empty_cols * (5.0 if _king_ready(gs) else 6.0)
    # Penalize uneven foundation distribution
    f_lens = [len(f) for f in gs.foundations]
    score -= (max(f_lens) - min(f_lens)) * 2.0
    return score


GREEDY_DEPTH = 55


def _preview_score(gs: GameState) -> float:
    """Pure greedy rollout: play forward 20 steps using heuristic, track best score."""
    state = gs.clone()
    seen = {state.state_key()}
    best_score = _state_score(state)

    for step in range(GREEDY_DEPTH):
        if state.is_won():
            return 1_000_000.0 + _state_score(state)
        legal = get_legal_moves(state)
        if not legal:
            break
        move = _baseline_move(state, legal)
        apply_move(state, move)
        key = state.state_key()
        if key in seen:
            break
        seen.add(key)
        score = _state_score(state) - step * 0.05
        if score > best_score:
            best_score = score

    return best_score


def choose_move(gs: GameState, legal_moves: list[Move]) -> Move:
    """
    Keep the baseline on obviously good moves. When the choice is ambiguous,
    compare a few candidate moves by previewing the greedy continuation.
    """
    priorities = [(move, _move_priority(gs, move)) for move in legal_moves]
    priorities.sort(key=lambda x: x[1])
    best, best_pri = priorities[0]
    if best_pri[0] <= 5:
        return best

    best_bucket = best_pri[0]
    shortlist = [
        move for move, pri in priorities if pri[0] <= best_bucket + 2
    ][:PREVIEW_CANDIDATES]
    for move_type in (MoveType.DRAW, MoveType.RESET_STOCK):
        special = next((move for move, _ in priorities if move.type == move_type), None)
        if not special or special in shortlist:
            continue
        if len(shortlist) < PREVIEW_CANDIDATES:
            shortlist.append(special)
        else:
            shortlist[-1] = special
    if len(shortlist) == 1:
        return shortlist[0]

    best_move = best
    best_score = float("-inf")
    for move in shortlist:
        child = gs.clone()
        apply_move(child, move)
        score = _preview_score(child)
        if score > best_score:
            best_score = score
            best_move = move
    return best_move


if __name__ == "__main__":
    import sys
    import time

    t0 = time.time()
    print("Klondike 3-Card Draw - Strategy Evaluation")
    print("=" * 50)
    print()

    evaluate_strategy(choose_move)

    print()
    print(f"Strategy file: {__file__}")
    print(f"Wall clock:    {time.time() - t0:.1f}s")

    sys.exit(0)
