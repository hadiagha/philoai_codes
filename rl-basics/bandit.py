"""Explore or exploit? Three restaurants, from scratch (no libraries).

    python3 bandit.py

Each night you pick one restaurant; it is either a great night (1) or not (0).
  0  your favorite pasta place   great 60% of nights
  1  the new taco place          great 75% of nights
  2  the sushi bar               great 40% of nights
"Greedy" always picks the best average so far. "Curious" (epsilon-greedy)
does the same, but 10% of nights picks a random place. Same RNG as the slides.
"""
from td_control import mulberry32

CHANCE = [0.60, 0.75, 0.40]
NIGHTS, RUNS = 1000, 500


def run(epsilon, rand):
    count, total = [0] * 3, [0.0] * 3
    great = []
    for _ in range(NIGHTS):
        if rand() < epsilon:
            k = int(rand() * 3)                                  # explore
        else:
            avg = [total[i] / count[i] if count[i] else 0.0 for i in range(3)]
            k = max(range(3), key=lambda i: avg[i])              # exploit (ties: first)
        r = 1 if rand() < CHANCE[k] else 0
        count[k] += 1
        total[k] += r
        great.append(r)
    return great, count


if __name__ == "__main__":
    for name, eps in (("greedy", 0.0), ("curious", 0.1)):
        rand = mulberry32(2024)
        curve, taco = [0.0] * NIGHTS, 0
        for _ in range(RUNS):
            great, count = run(eps, rand)
            curve = [c + g / RUNS for c, g in zip(curve, great)]
            taco += count[1] == max(count)
        print("%-8s great nights: first 100 %.1f%%, last 100 %.1f%%, overall %.1f%%; ends up at the taco place in %.0f%% of lives"
              % (name, 100 * sum(curve[:100]) / 100, 100 * sum(curve[-100:]) / 100, 100 * sum(curve) / NIGHTS, 100 * taco / RUNS))
