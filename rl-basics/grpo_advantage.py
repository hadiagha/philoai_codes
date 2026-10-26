"""GRPO's core trick on one tiny example (Shao et al., 2024).

Ask the model one question several times, score each answer (1 = correct),
and judge every answer against its own group: advantage = (r - mean) / std.
"""
rewards = [1, 1, 0, 1]                      # "17 x 3 = ?" -> 51, 51, 41, 51
mean = sum(rewards) / len(rewards)
std = (sum((r - mean) ** 2 for r in rewards) / len(rewards)) ** 0.5
advantages = [(r - mean) / std for r in rewards]
print("mean %.2f  std %.3f  advantages %s" % (mean, std, ["%+.2f" % a for a in advantages]))
