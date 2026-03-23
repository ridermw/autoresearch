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

from prepare import (
    GameState,
    Move,
    MoveType,
    evaluate_strategy,
    foundation_accepts,
)

# ---------------------------------------------------------------------------
# Strategy: choose_move(game_state, legal_moves) -> Move
# ---------------------------------------------------------------------------
#
# Simple priority baseline:
#
#   0. Flip face-down tableau cards (mandatory)
#   1. Play Aces/Twos to foundation (always correct)
#   2. Any foundation move that reveals a face-down card
#   3. Safe foundation moves (opposite-color predecessors already placed)
#   4. Tableau-to-tableau that reveals face-down cards
#   5. Waste to tableau (shifts waste access pattern — vital for 3-draw)
#   6. Foundation moves for low cards (rank 3-5)
#   7. Draw from stock
#   8. Tableau reorg: King to empty column if it reveals cards
#   9. Foundation moves for high cards
#  10. Tableau reorg that doesn't reveal
#  11. Reset stock
#
# Design notes:
# - Foundation play is very aggressive. In 3-card draw, removing cards from
#   the game almost always helps because it thins the stock/waste cycle.
# - Waste-to-tableau is ranked high because every card removed from waste
#   shifts which cards are accessible in subsequent draw cycles.
# - Non-revealing tableau reorg is ranked BELOW draw, to avoid cycles where
#   the strategy just shuffles visible cards instead of drawing new ones.
# ---------------------------------------------------------------------------


def _is_safe_to_foundation(gs: GameState, card) -> bool:
    """
    A card is 'safe' to move to foundation if both cards of the opposite
    color with rank one less are already on their foundations.
    """
    if card.rank <= 1:
        return True
    needed_rank = card.rank - 1
    if card.color == 1:  # red — need black suits
        opposite_suits = [0, 3]
    else:  # black — need red suits
        opposite_suits = [1, 2]
    for suit in opposite_suits:
        if gs.foundation_top_rank(suit) < needed_rank:
            return False
    return True


def _reveals_facedown(gs: GameState, move: Move) -> bool:
    """Does this move reveal a face-down card underneath?"""
    if move.type == MoveType.TABLEAU_TO_TABLEAU:
        pile = gs.tableau[move.from_col]
        return move.count == len(pile.face_up) and len(pile.face_down) > 0
    if move.type == MoveType.TABLEAU_TO_FOUNDATION:
        pile = gs.tableau[move.from_col]
        return len(pile.face_up) == 1 and len(pile.face_down) > 0
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

    # 0: Flip face-down cards (mandatory)
    if t == MoveType.FLIP_TABLEAU:
        return (0,)

    # Foundation moves — classify by safety and card rank
    if t in (MoveType.WASTE_TO_FOUNDATION, MoveType.TABLEAU_TO_FOUNDATION):
        card = _get_card_for_move(gs, move)
        reveals = (
            _reveals_facedown(gs, move)
            if t == MoveType.TABLEAU_TO_FOUNDATION
            else False
        )

        # 1: Aces and Twos — always play immediately
        if card.rank <= 1:
            return (1, 0 if reveals else 1)

        # 2: Foundation move that reveals a face-down card — almost always worth it
        if reveals:
            return (2, -card.rank)

        # 3: Safe foundation (opposite predecessors already placed)
        if _is_safe_to_foundation(gs, card):
            return (3, -card.rank)

        # 6: Low cards (rank 3-5) even if not safe — unlikely to be needed
        if card.rank <= 5:
            return (6, -card.rank)

        # 9: High cards — risky, might strand tableau sequences
        return (9, -card.rank)

    # 4: Tableau-to-tableau that reveals face-down cards
    if t == MoveType.TABLEAU_TO_TABLEAU and _reveals_facedown(gs, move):
        facedown_count = len(gs.tableau[move.from_col].face_down)
        return (4, -facedown_count)

    # 5: Waste to tableau — every card pulled from waste changes draw alignment
    if t == MoveType.WASTE_TO_TABLEAU:
        pile = gs.tableau[move.to_col]
        facedown = len(pile.face_down)
        pile_size = len(pile.face_up)
        return (5, -facedown, -pile_size)

    # 7: Draw from stock
    if t == MoveType.DRAW:
        return (7,)

    # 8-10: Tableau reorg that doesn't reveal
    if t == MoveType.TABLEAU_TO_TABLEAU:
        src = gs.tableau[move.from_col]
        dst = gs.tableau[move.to_col]
        bottom_card = src.face_up[-move.count]

        # 8: King to empty column with face-down cards underneath — good
        if dst.is_empty() and bottom_card.rank == 12 and src.face_down:
            return (8, -len(src.face_down))

        # Moving to empty column without a King, or King with nothing to reveal
        if dst.is_empty():
            return (10, 5)

        # Regular reorg — prefer building longer runs on piles with face-down
        dst_facedown = len(dst.face_down)
        dst_size = len(dst.face_up)
        return (10, -dst_facedown, -dst_size, -move.count)

    # 11: Reset stock
    if t == MoveType.RESET_STOCK:
        return (11,)

    return (99,)


def choose_move(gs: GameState, legal_moves: list[Move]) -> Move:
    """
    Choose the best move from the list of legal moves.

    Args:
        gs: current game state (treat as read-only)
        legal_moves: list of legal Move objects (non-empty)

    Returns:
        A Move from legal_moves
    """
    return min(legal_moves, key=lambda m: _move_priority(gs, m))


# ---------------------------------------------------------------------------
# Main — run evaluation
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import time

    t0 = time.time()
    print("Klondike 3-Card Draw — Strategy Evaluation")
    print("=" * 50)
    print()

    stats = evaluate_strategy(choose_move)

    print()
    print(f"Strategy file: {__file__}")
    print(f"Wall clock:    {time.time() - t0:.1f}s")

    sys.exit(0)
