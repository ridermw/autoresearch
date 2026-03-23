"""
Klondike Solitaire (3-card draw) — game engine and evaluation harness.
This file is FIXED. The agent modifies strategy.py only.

Usage:
    python prepare.py              # verify engine works, run baseline
    python prepare.py --seed 42    # play one game with debug output
"""

import argparse
import random
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

# ---------------------------------------------------------------------------
# Constants (fixed, do not modify)
# ---------------------------------------------------------------------------

NUM_EVAL_GAMES = 10_000  # number of games per evaluation
MAX_MOVES_PER_GAME = 1_000  # prevent infinite loops
EVAL_SEED_START = 1_000_000  # deterministic seed range for eval games
TIME_BUDGET = 120  # soft time budget in seconds for strategy.py runs
DRAW_COUNT = 3  # cards drawn per draw action (3 = standard 3-card draw)

# ---------------------------------------------------------------------------
# Card representation
# ---------------------------------------------------------------------------

SUITS = ["C", "D", "H", "S"]
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]


class Suit(int, Enum):
    CLUBS = 0
    DIAMONDS = 1
    HEARTS = 2
    SPADES = 3


@dataclass(frozen=True, slots=True)
class Card:
    rank: int  # 0=Ace, 1=2, ..., 12=King
    suit: int  # 0=Clubs, 1=Diamonds, 2=Hearts, 3=Spades

    @property
    def color(self) -> int:
        """0=black (clubs, spades), 1=red (diamonds, hearts)"""
        return 1 if self.suit in (Suit.DIAMONDS, Suit.HEARTS) else 0

    def __repr__(self):
        return f"{RANKS[self.rank]}{SUITS[self.suit]}"


def make_deck() -> list[Card]:
    """Standard 52-card deck."""
    return [Card(r, s) for s in range(4) for r in range(13)]


# ---------------------------------------------------------------------------
# Move types
# ---------------------------------------------------------------------------


class MoveType(Enum):
    DRAW = auto()  # draw up to 3 from stock to waste
    RESET_STOCK = auto()  # flip waste back to stock (stock empty)
    WASTE_TO_FOUNDATION = auto()  # waste top -> foundation
    WASTE_TO_TABLEAU = auto()  # waste top -> tableau column
    TABLEAU_TO_FOUNDATION = auto()  # tableau top -> foundation
    TABLEAU_TO_TABLEAU = auto()  # move face-up cards between columns
    FLIP_TABLEAU = auto()  # flip top face-down card in tableau


@dataclass(frozen=True, slots=True)
class Move:
    type: MoveType
    from_col: int = -1  # source tableau column (0-6)
    to_col: int = -1  # dest tableau column (0-6)
    count: int = 1  # number of cards to move (tableau-to-tableau)
    foundation: int = -1  # which foundation pile (0-3, by suit)

    def __repr__(self):
        t = self.type.name
        if self.type == MoveType.WASTE_TO_TABLEAU:
            return f"{t}(col={self.to_col})"
        if self.type == MoveType.WASTE_TO_FOUNDATION:
            return f"{t}(f={self.foundation})"
        if self.type == MoveType.TABLEAU_TO_FOUNDATION:
            return f"{t}(col={self.from_col}, f={self.foundation})"
        if self.type == MoveType.TABLEAU_TO_TABLEAU:
            return f"{t}({self.from_col}->{self.to_col}, n={self.count})"
        if self.type == MoveType.FLIP_TABLEAU:
            return f"{t}(col={self.from_col})"
        return t


# ---------------------------------------------------------------------------
# Game state
# ---------------------------------------------------------------------------


@dataclass
class TableauPile:
    """A single tableau column: face-down cards on bottom, face-up on top."""

    face_down: list[Card] = field(default_factory=list)
    face_up: list[Card] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.face_down and not self.face_up

    def top_card(self) -> Optional[Card]:
        return self.face_up[-1] if self.face_up else None

    def needs_flip(self) -> bool:
        """True if there are face-down cards but no face-up cards."""
        return bool(self.face_down) and not self.face_up


@dataclass
class GameState:
    stock: list[Card] = field(default_factory=list)
    waste: list[Card] = field(default_factory=list)
    foundations: list[list[Card]] = field(
        default_factory=lambda: [[] for _ in range(4)]
    )
    tableau: list[TableauPile] = field(
        default_factory=lambda: [TableauPile() for _ in range(7)]
    )
    stock_passes: int = 0  # how many times we've recycled the stock
    moves_made: int = 0

    def is_won(self) -> bool:
        return all(len(f) == 13 for f in self.foundations)

    def foundation_top_rank(self, suit: int) -> int:
        """Returns the rank of the top card on a foundation, or -1 if empty."""
        pile = self.foundations[suit]
        return pile[-1].rank if pile else -1

    def total_foundation_cards(self) -> int:
        return sum(len(f) for f in self.foundations)

    def state_key(self) -> tuple:
        """Hash-friendly snapshot of the full game state for cycle detection."""
        stock = tuple(self.stock)
        waste = tuple(self.waste)
        foundations = tuple(tuple(f) for f in self.foundations)
        tableau = tuple((tuple(t.face_down), tuple(t.face_up)) for t in self.tableau)
        return (stock, waste, foundations, tableau)

    def clone(self) -> "GameState":
        """Deep copy of game state."""
        gs = GameState()
        gs.stock = list(self.stock)
        gs.waste = list(self.waste)
        gs.foundations = [list(f) for f in self.foundations]
        gs.tableau = [
            TableauPile(list(t.face_down), list(t.face_up)) for t in self.tableau
        ]
        gs.stock_passes = self.stock_passes
        gs.moves_made = self.moves_made
        return gs


# ---------------------------------------------------------------------------
# Dealing
# ---------------------------------------------------------------------------


def deal_game(seed: int) -> GameState:
    """Deal a standard Klondike game with a given seed."""
    rng = random.Random(seed)
    deck = make_deck()
    rng.shuffle(deck)

    gs = GameState()
    idx = 0
    # Deal 7 tableau piles: pile i gets i face-down + 1 face-up
    for col in range(7):
        for _ in range(col):
            gs.tableau[col].face_down.append(deck[idx])
            idx += 1
        gs.tableau[col].face_up.append(deck[idx])
        idx += 1

    # Remaining 24 cards go to stock
    gs.stock = list(reversed(deck[idx:]))  # top of stock = end of list
    return gs


# ---------------------------------------------------------------------------
# Legal move generation
# ---------------------------------------------------------------------------


def _can_place_on_tableau(card: Card, pile: TableauPile) -> bool:
    """Can this card be placed on top of a tableau pile?"""
    if pile.is_empty():
        return card.rank == 12  # only Kings on empty piles
    top = pile.top_card()
    return card.color != top.color and card.rank == top.rank - 1


def _can_place_on_foundation(card: Card, foundations: list[list[Card]]) -> bool:
    """Can this card go to its foundation pile?"""
    pile = foundations[card.suit]
    if not pile:
        return card.rank == 0  # Ace
    return card.rank == pile[-1].rank + 1


def get_legal_moves(gs: GameState) -> list[Move]:
    """Generate all legal moves from the current game state."""
    moves = []

    # 1. Flip any face-down tableau cards that need flipping
    #    (This is mandatory and should be done first)
    for col in range(7):
        if gs.tableau[col].needs_flip():
            moves.append(Move(MoveType.FLIP_TABLEAU, from_col=col))
    if moves:
        return moves  # must flip before anything else

    # 2. Waste -> Foundation
    if gs.waste:
        card = gs.waste[-1]
        if _can_place_on_foundation(card, gs.foundations):
            moves.append(Move(MoveType.WASTE_TO_FOUNDATION, foundation=card.suit))

    # 3. Tableau -> Foundation
    for col in range(7):
        card = gs.tableau[col].top_card()
        if card and _can_place_on_foundation(card, gs.foundations):
            moves.append(
                Move(MoveType.TABLEAU_TO_FOUNDATION, from_col=col, foundation=card.suit)
            )

    # 4. Waste -> Tableau
    if gs.waste:
        card = gs.waste[-1]
        for col in range(7):
            if _can_place_on_tableau(card, gs.tableau[col]):
                moves.append(Move(MoveType.WASTE_TO_TABLEAU, to_col=col))

    # 5. Tableau -> Tableau (move sequences of face-up cards)
    for from_col in range(7):
        pile = gs.tableau[from_col]
        if not pile.face_up:
            continue
        # Try moving 1..len(face_up) cards from the bottom of the face-up stack
        for count in range(1, len(pile.face_up) + 1):
            bottom_card = pile.face_up[-count]  # bottom of the segment
            for to_col in range(7):
                if to_col == from_col:
                    continue
                if _can_place_on_tableau(bottom_card, gs.tableau[to_col]):
                    # Skip no-op: moving a King (full stack) to empty column from another empty
                    if (
                        bottom_card.rank == 12
                        and count == len(pile.face_up)
                        and not pile.face_down
                    ):
                        if gs.tableau[to_col].is_empty():
                            continue
                    moves.append(
                        Move(
                            MoveType.TABLEAU_TO_TABLEAU,
                            from_col=from_col,
                            to_col=to_col,
                            count=count,
                        )
                    )

    # 6. Draw from stock
    if gs.stock:
        moves.append(Move(MoveType.DRAW))

    # 7. Reset stock (flip waste back)
    if not gs.stock and gs.waste:
        moves.append(Move(MoveType.RESET_STOCK))

    return moves


# ---------------------------------------------------------------------------
# Apply move
# ---------------------------------------------------------------------------


def apply_move(gs: GameState, move: Move) -> None:
    """Apply a move to the game state (mutates in place)."""
    gs.moves_made += 1

    if move.type == MoveType.DRAW:
        # Draw up to DRAW_COUNT cards from stock to waste
        for _ in range(min(DRAW_COUNT, len(gs.stock))):
            gs.waste.append(gs.stock.pop())

    elif move.type == MoveType.RESET_STOCK:
        # Flip waste back to stock
        gs.stock = list(reversed(gs.waste))
        gs.waste.clear()
        gs.stock_passes += 1

    elif move.type == MoveType.WASTE_TO_FOUNDATION:
        card = gs.waste.pop()
        gs.foundations[card.suit].append(card)

    elif move.type == MoveType.WASTE_TO_TABLEAU:
        card = gs.waste.pop()
        gs.tableau[move.to_col].face_up.append(card)

    elif move.type == MoveType.TABLEAU_TO_FOUNDATION:
        card = gs.tableau[move.from_col].face_up.pop()
        gs.foundations[card.suit].append(card)

    elif move.type == MoveType.TABLEAU_TO_TABLEAU:
        src = gs.tableau[move.from_col]
        dst = gs.tableau[move.to_col]
        # Move 'count' cards from top of face_up
        moving = src.face_up[-move.count :]
        src.face_up = src.face_up[: -move.count]
        dst.face_up.extend(moving)

    elif move.type == MoveType.FLIP_TABLEAU:
        pile = gs.tableau[move.from_col]
        card = pile.face_down.pop()
        pile.face_up.append(card)


# ---------------------------------------------------------------------------
# Game runner
# ---------------------------------------------------------------------------


def play_game(seed: int, choose_move_fn, debug: bool = False) -> dict:
    """
    Play one game of Klondike solitaire.

    Args:
        seed: RNG seed for the deal
        choose_move_fn: function(game_state, legal_moves) -> Move or index
        debug: if True, print each move

    Returns:
        dict with keys: won, foundation_cards, moves_made, stock_passes
    """
    gs = deal_game(seed)
    seen_states: set[tuple] = set()

    if debug:
        print(f"\n{'=' * 60}")
        print(f"Game seed: {seed}")
        _print_state(gs)

    for _ in range(MAX_MOVES_PER_GAME):
        if gs.is_won():
            break

        # Cycle detection: if we've seen this exact state before, we're stuck
        key = gs.state_key()
        if key in seen_states:
            if debug:
                print("  [cycle detected — game stuck]")
            break
        seen_states.add(key)

        legal = get_legal_moves(gs)
        if not legal:
            break

        choice = choose_move_fn(gs, legal)

        # Accept either a Move object or an integer index
        if isinstance(choice, int):
            if choice < 0 or choice >= len(legal):
                break  # invalid choice = stuck
            move = legal[choice]
        elif isinstance(choice, Move):
            move = choice
        else:
            break

        if debug:
            print(f"  Move {gs.moves_made + 1}: {move}")

        apply_move(gs, move)

        if debug and move.type not in (
            MoveType.FLIP_TABLEAU,
            MoveType.DRAW,
            MoveType.RESET_STOCK,
        ):
            _print_state(gs)

    result = {
        "won": gs.is_won(),
        "foundation_cards": gs.total_foundation_cards(),
        "moves_made": gs.moves_made,
        "stock_passes": gs.stock_passes,
    }

    if debug:
        status = (
            "WON! 🎉"
            if gs.is_won()
            else f"LOST ({gs.total_foundation_cards()}/52 to foundation)"
        )
        print(f"\nResult: {status} in {gs.moves_made} moves")

    return result


# ---------------------------------------------------------------------------
# Evaluation (DO NOT CHANGE — this is the fixed metric)
# ---------------------------------------------------------------------------


def evaluate_strategy(
    choose_move_fn,
    num_games: int = NUM_EVAL_GAMES,
    seed_start: int = EVAL_SEED_START,
    verbose: bool = True,
) -> dict:
    """
    Evaluate a strategy over a fixed set of games.

    Returns dict with:
        win_rate:          fraction of games won (0.0 to 1.0)
        wins:              number of wins
        total:             number of games played
        avg_foundation:    average cards moved to foundation
        avg_moves:         average moves per game
        total_seconds:     wall clock time
    """
    t0 = time.time()
    wins = 0
    total_foundation = 0
    total_moves = 0

    for i in range(num_games):
        seed = seed_start + i
        result = play_game(seed, choose_move_fn)
        if result["won"]:
            wins += 1
        total_foundation += result["foundation_cards"]
        total_moves += result["moves_made"]

        # Progress reporting
        if verbose and (i + 1) % 1000 == 0:
            wr = wins / (i + 1)
            af = total_foundation / (i + 1)
            print(
                f"  [{i + 1:,}/{num_games:,}] win_rate={wr:.4f} avg_foundation={af:.1f}"
            )

    t1 = time.time()
    total = num_games

    stats = {
        "win_rate": wins / total,
        "wins": wins,
        "total": total,
        "avg_foundation": total_foundation / total,
        "avg_moves": total_moves / total,
        "total_seconds": t1 - t0,
    }

    if verbose:
        print()
        print("---")
        print(f"win_rate:         {stats['win_rate']:.6f}")
        print(f"wins:             {stats['wins']}")
        print(f"total_games:      {stats['total']}")
        print(f"avg_foundation:   {stats['avg_foundation']:.1f}")
        print(f"avg_moves:        {stats['avg_moves']:.1f}")
        print(f"total_seconds:    {stats['total_seconds']:.1f}")

    return stats


# ---------------------------------------------------------------------------
# Debug display
# ---------------------------------------------------------------------------


def _print_state(gs: GameState):
    """Print game state for debugging."""
    print(f"\n  Stock: {len(gs.stock)} | Waste: {len(gs.waste)}", end="")
    if gs.waste:
        # Show top 3 waste cards
        top3 = gs.waste[-3:] if len(gs.waste) >= 3 else gs.waste
        print(f" [{', '.join(str(c) for c in reversed(top3))}]", end="")
    print()

    fnd_str = "  Foundations: "
    for s in range(4):
        pile = gs.foundations[s]
        if pile:
            fnd_str += f"{pile[-1]} "
        else:
            fnd_str += f"[{SUITS[s]}:_] "
    print(fnd_str)

    print("  Tableau:")
    for col in range(7):
        pile = gs.tableau[col]
        down = f"({''.join('?' for _ in pile.face_down)})" if pile.face_down else "()"
        up = " ".join(str(c) for c in pile.face_up) if pile.face_up else "--"
        print(f"    [{col}] {down} {up}")


# ---------------------------------------------------------------------------
# Helpers exported for strategy authors
# ---------------------------------------------------------------------------


def foundation_accepts(gs: GameState, card: Card) -> bool:
    """Check if a card can go to its foundation."""
    return _can_place_on_foundation(card, gs.foundations)


def tableau_accepts(gs: GameState, col: int, card: Card) -> bool:
    """Check if a card can be placed on a tableau column."""
    return _can_place_on_tableau(card, gs.tableau[col])


def cards_above(gs: GameState, col: int, card: Card) -> int:
    """How many face-up cards are above (on top of) a card in a tableau column.
    Returns -1 if card not found."""
    pile = gs.tableau[col].face_up
    for i, c in enumerate(pile):
        if c == card:
            return len(pile) - i - 1
    return -1


# ---------------------------------------------------------------------------
# Main — verify engine + run baseline
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Klondike Solitaire engine")
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Play one game with debug output using this seed",
    )
    parser.add_argument(
        "--num-games",
        type=int,
        default=1000,
        help="Number of games for quick eval (default 1000)",
    )
    args = parser.parse_args()

    # Import the baseline strategy
    from strategy import choose_move

    if args.seed is not None:
        play_game(args.seed, choose_move, debug=True)
    else:
        print(f"Running baseline strategy over {args.num_games:,} games...")
        print()
        evaluate_strategy(choose_move, num_games=args.num_games)
