"""Policy iteration on the same apartment: rate the rulebook, fix it, repeat.

    python3 policy_iteration.py

Starts from the die rulebook (each move 1 in 4) and alternates
  evaluate:  V(s) = average over the note's moves of  r + GAMMA * V(s')     (no max)
  improve:   new note = the move(s) with the best  r + GAMMA * V(s')
until no note changes. Ends on the same values as value_iteration.py.
"""
from value_iteration import GAMMA, MOVES, ROWS, COLS, STATES, TERMINALS, WALLS, step

TILES = sorted(s for s in STATES if s not in TERMINALS)


def q(V, s, a):
    s2, r, done = step(s, a)
    return r + (0 if done else GAMMA * V[s2])


def evaluate(pi, theta=1e-6):
    """How good is each tile if Robo follows the notes pi? (ties: split evenly)"""
    V = {s: 0.0 for s in STATES}
    while True:
        new_V = {s: 0.0 if s in TERMINALS else sum(q(V, s, a) for a in pi[s]) / len(pi[s]) for s in STATES}
        if max(abs(new_V[s] - V[s]) for s in STATES) < theta:
            return new_V
        V = new_V


def improve(V):
    """On every tile, point the note at the best move(s)."""
    pi = {}
    for s in TILES:
        best = max(q(V, s, a) for a in MOVES)
        pi[s] = [a for a in MOVES if abs(q(V, s, a) - best) < 1e-9]
    return pi


def show(V, pi):
    arrows = {"U": "↑", "R": "→", "D": "↓", "L": "←"}
    for r in range(ROWS):
        cells = []
        for c in range(COLS):
            s = (r, c)
            if s in WALLS:
                cells.append("   ####  ")
            elif s in TERMINALS:
                cells.append("   term  ")
            else:
                cells.append("%6.2f %-2s" % (V[s], "".join(arrows[a] for a in pi[s]) if len(pi[s]) < 4 else "🎲"))
        print(" ".join(cells))


if __name__ == "__main__":
    pi = {s: list(MOVES) for s in TILES}   # the die: every move, 1 in 4
    for rnd in range(1, 20):
        V = evaluate(pi)
        new_pi = improve(V)
        changed = sum(1 for s in TILES if not set(pi[s]) <= set(new_pi[s]))
        print("round %d · evaluate: start tile %.2f, top-left %.2f · improve: %d of %d notes change"
              % (rnd, V[(4, 0)], V[(0, 0)], changed, len(TILES)))
        show(V, pi)
        print()
        if changed == 0:
            break
        pi = new_pi
