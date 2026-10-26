# Reinforcement Learning Fundamentals: the code

This is the Python behind every number on screen in the PhiloAI video *Reinforcement Learning Fundamentals: The Complete Guide From Scratch*.

The video covers the foundation that the rest of RL builds on:
- Markov decision processes, return and value;
- the Bellman equation, value iteration and policy iteration;
- exploration, and temporal difference (TD) learning;
- SARSA and Q-learning;
- the step up to policy gradients and RL for language models.

These files reproduce each of those results. The video works each number out by hand first, then checks it here. Every file is plain Python with no libraries, so each line maps to an idea from the video.

```bash
cd rl-basics
python3 value_iteration.py
```

Run the files from inside this folder, because some of them import each other.

| File | What it reproduces | In the video |
|---|---|---|
| [`value_iteration.py`](value_iteration.py) | Robo's apartment: the values on every tile (start tile −0.43, top-left 4.58) and the greedy rulebook | 23:15 Value iteration · 24:47 the code |
| [`policy_iteration.py`](policy_iteration.py) | Policy iteration from the "roll a die" rulebook: grade it, fix it, done in 2 rounds with the same values as value iteration | 25:50 Policy iteration |
| [`bandit.py`](bandit.py) | Three restaurants. "Greedy" stays at about 60% great nights; "curious" (ε-greedy, 10%) finds the taco place in 95% of lives | 31:54 Explore or exploit? |
| [`td_control.py`](td_control.py) | The TD update by hand (5.60, then 4.82); SARSA vs. Q-learning on the hallway by the stairs; Q-learning finding the apartment's values with no floor plan | 37:19 TD by hand · 43:25 the hallway · 44:39 who collects more · 46:38 Q-learning finds the way |
| [`policy_gradient_step.py`](policy_gradient_step.py) | One REINFORCE step (Williams, 1992): moves that led to a good trip become more likely | 51:45 Policy gradients |
| [`grpo_advantage.py`](grpo_advantage.py) | GRPO's group trick (Shao et al., 2024): each answer is judged against its own group, giving advantages +0.58 and −1.73 | 55:08 RLHF and GRPO |

The random numbers come from `mulberry32`, the same small generator the animations use, so the learning curves in the video and in this code match exactly.

## Want the real-world versions?

These files are deliberately tiny. Full implementations on messy, real problems (ads, scheduling, routing, pricing, cooling, LLM fine-tuning) are in the book [*Applied Reinforcement Learning: Business optimization and LLM fine-tuning*](https://www.manning.com/books/applied-reinforcement-learning) (Manning).
