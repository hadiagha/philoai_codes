"""SARSA vs Q-learning, from scratch (no libraries).

    python3 td_control.py

Reproduces every learning number in the video:
  1. Robo's apartment (same 5x5 grid as value_iteration.py): Q-learning from
     experience only, no floor plan -> the same values value iteration found.
  2. The hallway by the stairs (4x10): SARSA learns the safe route,
     Q-learning learns the edge route, and SARSA collects more reward while learning.
  3. The TD update by hand (slide "TD, by hand").

The random numbers come from mulberry32, the same generator the slides use
(Philo.viz.rng), so the browser and this file produce identical results.
"""
from collections import defaultdict


def mulberry32(seed):
    a = seed & 0xFFFFFFFF

    def rand():
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = ((a ^ (a >> 15)) * (1 | a)) & 0xFFFFFFFF
        t = ((t + (((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF)) & 0xFFFFFFFF) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296
    return rand


MOVES = {"U": (-1, 0), "R": (0, 1), "D": (1, 0), "L": (0, -1)}


class World:
    def __init__(self, rows, cols, walls, terminals, start, step_reward=-1):
        self.rows, self.cols, self.start = rows, cols, start
        self.terminals, self.step_reward = terminals, step_reward
        self.states = {(r, c) for r in range(rows) for c in range(cols)} - set(walls)

    def step(self, s, a):
        nxt = (s[0] + MOVES[a][0], s[1] + MOVES[a][1])
        if nxt not in self.states:     # wall or edge: stay put
            nxt = s
        return nxt, self.terminals.get(nxt, self.step_reward), nxt in self.terminals


APARTMENT = World(5, 5, walls=[(1, 1), (2, 1), (3, 3)], terminals={(0, 4): 10, (1, 3): -10}, start=(4, 0))
HALLWAY = World(4, 10, walls=[], terminals={(3, 9): 10, **{(3, c): -100 for c in range(1, 9)}}, start=(3, 0))


# ---- the code shown on the slide "One line apart" (keep identical) ----
GAMMA, ALPHA, EPSILON = 0.9, 0.5, 0.1

def epsilon_greedy(Q, s, rand):
    if rand() < EPSILON:                      # explore
        return list(MOVES)[int(rand() * 4)]
    return max(MOVES, key=lambda a: Q[s, a])  # exploit

def learn(world, method, episodes, rand):
    Q = defaultdict(float)
    for _ in range(episodes):
        s, done = world.start, False
        a = epsilon_greedy(Q, s, rand)
        while not done:
            s2, r, done = world.step(s, a)
            a2 = epsilon_greedy(Q, s2, rand)
            if method == "sarsa":
                nxt = Q[s2, a2]                     # my actual next move
            else:
                nxt = max(Q[s2, b] for b in MOVES)  # the best next move
            target = r + (0 if done else GAMMA * nxt)
            Q[s, a] += ALPHA * (target - Q[s, a])
            s, a = s2, a2
    return Q
# ---- end of slide code ----


def learn_tracked(world, method, episodes, rand, snapshots=()):
    """Same algorithm as learn(), plus per-episode reward and Q snapshots for the plots."""
    Q = defaultdict(float)
    rewards, snaps = [], {}
    for ep in range(episodes):
        s = world.start
        a = epsilon_greedy(Q, s, rand)
        done, total = False, 0
        while not done:
            s2, r, done = world.step(s, a)
            a2 = epsilon_greedy(Q, s2, rand)
            if method == "sarsa":
                nxt = Q[s2, a2]
            else:
                nxt = max(Q[s2, b] for b in MOVES)
            target = r + (0 if done else GAMMA * nxt)
            Q[s, a] += ALPHA * (target - Q[s, a])
            s, a = s2, a2
            total += r
        rewards.append(total)
        if ep + 1 in snapshots:
            snaps[ep + 1] = dict(Q)
    return Q, rewards, snaps


def greedy_path(world, Q, max_len=60):
    s, path = world.start, [world.start]
    while s not in world.terminals and len(path) < max_len:
        a = max(MOVES, key=lambda a: Q[s, a])
        s = world.step(s, a)[0]
        path.append(s)
    return path


def values(world, Q):
    return {s: max(Q[s, a] for a in MOVES) for s in world.states if s not in world.terminals}


def show_values(world, V):
    for r in range(world.rows):
        print("  ".join("  ####" if (r, c) not in world.states else ("  term" if (r, c) in world.terminals else "%6.2f" % V[(r, c)]) for c in range(world.cols)))


if __name__ == "__main__":
    # 1. Robo's apartment, Q-learning from experience (seed 7)
    rand = mulberry32(7)
    Q, rewards, snaps = learn_tracked(APARTMENT, "q", 500, rand, snapshots=(1, 10, 50, 500))
    for ep in (1, 10, 50, 500):
        print("\nApartment, Q-learning, values after %d episodes" % ep)
        show_values(APARTMENT, values(APARTMENT, defaultdict(float, snaps[ep])))
    print("greedy route:", greedy_path(APARTMENT, Q))

    # 2. Hallway: one run each for the routes (seed 1), then 50 runs for the reward curves
    for method in ("sarsa", "q"):
        Q = learn(HALLWAY, method, 500, mulberry32(1))
        p = greedy_path(HALLWAY, Q)
        print("\nHallway %-5s route (%d moves): %s" % (method, len(p) - 1, p))
    RUNS, EPS = 50, 500
    for method in ("sarsa", "q"):
        curve, falls = [0.0] * EPS, 0
        for run in range(RUNS):
            _, rw, _ = learn_tracked(HALLWAY, method, EPS, mulberry32(1000 + run))
            curve = [c + x / RUNS for c, x in zip(curve, rw)]
            falls += sum(x <= -90 for x in rw[100:])
        late = sum(curve[100:]) / (EPS - 100)
        print("Hallway %-5s episodes 101-500: average reward per trip %.1f, falls %.1f%%"
              % (method, late, 100 * falls / (RUNS * (EPS - 100))))

    # 3. TD update by hand
    alpha, gamma = 0.5, 0.9
    V_here, V_next = 5.0, 8.0
    target = -1 + gamma * V_next
    delta = target - V_here
    V_here += alpha * delta
    print("\nTD by hand #1: target %.2f, delta %+.2f, new V %.2f" % (target, delta, V_here))
    target = -1 + gamma * V_here           # bumped the sofa: stayed on the same tile
    delta = target - V_here
    V_here += alpha * delta
    print("TD by hand #2: target %.2f, delta %+.2f, new V %.2f" % (target, delta, V_here))
