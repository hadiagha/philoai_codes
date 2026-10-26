"""One REINFORCE step on a toy rulebook (Williams, 1992), from scratch.

The rulebook is a softmax over four moves (the same on every tile, to keep it tiny).
Robo's first trip used U, U, R, U, U, R, R, R, R and scored +2 (no discount).
REINFORCE: logits += lr * G * sum_t grad log pi(a_t), with grad log pi(a) = onehot(a) - pi.
"""
import math

MOVES = ["U", "R", "D", "L"]
TRIP = ["U", "U", "R", "U", "U", "R", "R", "R", "R"]
G, LR = 2.0, 0.1

def softmax(z):
    e = [math.exp(v) for v in z]
    return [v / sum(e) for v in e]

logits = [0.0] * 4
pi = softmax(logits)
grad = [sum((a == m) - pi[i] for a in TRIP) for i, m in enumerate(MOVES)]
logits = [z + LR * G * g for z, g in zip(logits, grad)]
print("before:", ", ".join("%s %.0f%%" % (m, 100 * p) for m, p in zip(MOVES, pi)))
print("after: ", ", ".join("%s %.0f%%" % (m, 100 * p) for m, p in zip(MOVES, softmax(logits))))
