# Bellman Optimality vs Advantage Learning

A reinforcement-learning coursework exercise implemented in a ChainWalk environment.

The assignment compares a standard Bellman optimality update with Advantage Learning and examines how the update rule affects policy quality and action separation.

## Problem setup

- 11 states, from (s_0) to (s_{10})
- two actions: move left or move right
- intended transition probability 0.7, reverse transition probability 0.3
- self-loop behavior at the boundaries
- reward regions centered on the ChainWalk endpoints

## Evaluation

The experiment records two measures:

- **Performance bound** — the infinity-norm gap between the evaluated policy and the theoretical optimum.
- **Action gap** — the mean absolute difference between the two action values across states.

The checked-in figures show the evolution of these measures during iterative updates. The theoretical value function is used as a reference for interpreting convergence.

## Run

```bash
python chainwalk_dp.py
```

## Files

- `chainwalk_dp.py` — experiment and plotting code
- `DP_ChainWalk_Results.png` — summary result
- `chainwalk_dp_results.png` — performance-bound plot
- `chainwalk_dp_detailed.png` — action-gap detail

This is course material for reinforcement learning and optimal control, kept separate from the selected product work in the repository root.
