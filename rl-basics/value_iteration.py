"""Value iteration on the RL Basics grid world, from scratch (no libraries).

    python3 value_iteration.py

Grid (row 0 at the top):      . . . . G      G = treasure +10 (terminal)
                              . # . P .      P = pit      -10 (terminal)
                              . # . . .      # = wall
                              . . . # .      S = start
                              S . . . .      every move costs -1
"""
ROWS, COLS = 5, 5
WALLS = {(1, 1), (2, 1), (3, 3)}
TERMINALS = {(0, 4): 10, (1, 3): -10}
STATES = {(r, c) for r in range(ROWS) for c in range(COLS)} - WALLS

GAMMA = 0.9
MOVES = {"U": (-1, 0), "R": (0, 1), "D": (1, 0), "L": (0, -1)}

def step(s, a):
    nxt = (s[0] + MOVES[a][0], s[1] + MOVES[a][1])
    if nxt not in STATES:          # wall or edge: stay put
        nxt = s
    return nxt, TERMINALS.get(nxt, -1), nxt in TERMINALS

def value_iteration(theta=1e-6):
    V = {s: 0.0 for s in STATES}
    while True:
        new_V = {s: 0.0 if s in TERMINALS else max(
                     r + (0 if done else GAMMA * V[s2])
                     for s2, r, done in (step(s, a) for a in MOVES))
                 for s in STATES}
        if max(abs(new_V[s] - V[s]) for s in STATES) < theta:
            return new_V
        V = new_V


def greedy_policy(V):
    def q(s, a):
        s2, r, done = step(s, a)
        return r + (0 if done else GAMMA * V[s2])
    return {s: max(MOVES, key=lambda a: q(s, a)) for s in STATES if s not in TERMINALS}


if __name__ == "__main__":
    V = value_iteration()
    pi = greedy_policy(V)
    arrows = {"U": "↑", "R": "→", "D": "↓", "L": "←"}
    print("V(s), gamma = %.2f" % GAMMA)
    for r in range(ROWS):
        print("  ".join("  ####" if (r, c) in WALLS else ("  term" if (r, c) in TERMINALS else "%6.2f" % V[(r, c)]) for c in range(COLS)))
    print("\ngreedy policy")
    for r in range(ROWS):
        print("  ".join("#" if (r, c) in WALLS else ("G" if TERMINALS.get((r, c), 0) > 0 else "P") if (r, c) in TERMINALS else arrows[pi[(r, c)]] for c in range(COLS)))
