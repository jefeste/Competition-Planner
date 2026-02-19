# Equissima Scheduler: Max-Plus Eventing Optimizer

> **Optimizing Equestrian Triathlons using Tropical Algebra.**
> An algorithmic scheduling engine that guarantees optimal flow for Eventing competitions (Concours Complet) with shared resource constraints.

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://complet.streamlit.app)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Live Demo
**Try the application here:** [https://complet.streamlit.app](https://complet.streamlit.app)
*(If the app is sleeping, click "Yes, get this app back up" to wake it up)*

---

## The Challenge
Eventing (Concours Complet) is a logistical triathlon. Every rider must complete three phases: **Dressage**, **Cross Country**, and **Show Jumping**, in a strict sequence with fixed rest times.

The complexity explodes due to physical constraints:

| Real World Constraint | Mathematical Translation |
| :--- | :--- |
| **"The Triathlon"** (Sequence is fixed) | **Sequentiality:** $x_{i}(k) = x_{i-1}(k) + p_{i-1}$ (No-wait flow shop) |
| **"Shared Arena"** (Dressage blocks Jumping) | **Resource Interlock:** $x_{dress}(k) \ge x_{jump}(k-1) + \text{buffer}$ |
| **"Traffic Jam"** (Bottlenecks) | **Eigenvalue:** The system converges to a stable cycle time $\lambda$ (the bottleneck). |
| **"Optimal Schedule"** | **Spectral Theorem:** The schedule becomes periodic: $x(k+\sigma) = x(k) + \sigma \cdot \lambda$ |

👉 **[Read the Mathematical Proof & Theory](./PREUVE.md)** (Deep dive into the spectral theorem application).

---

## Key Features

### 1. Intelligent Scheduling 
Instead of guessing, the algorithm detects the **spectral periodicity** of the competition.
*   **Conflict-Free Guarantee:** Mathematically ensures no rider ever overlaps on a shared arena.
*   **$O(1)$ Complexity:** Once the pattern is detected (steady state), generating the schedule for 10 or 10,000 riders takes the same instant time.

### 2. Bottleneck Diagnostic 
The app doesn't just give you a schedule; it tells you *why* it takes that long.
*   **Analytic Solver:** Identifies exactly which phase is slowing down the whole day (e.g., *"The shared arena transition is costing you 40 minutes total"*).
*   **Sensitivity Analysis:** Suggests specific optimizations (e.g., *"Reducing the transition by 1 min will save 18 min total"*).

### 3. Visualization & Export
*   Interactive Gantt Chart (Matplotlib).
*   Visual identification of shared resource usage.

---

## How It Works

The engine operates in three layers:

1.  **Modeling:** The constraints (durations, resets, shared arenas) are converted into a Max-Plus matrix $\mathcal{A}$.
2.  **Pattern Detection:** The system computes the **eigenvalue** $\lambda$ (cycle time) and **eigenvector** (schedule pattern) of the matrix. It identifies the "steady state" regime where the schedule repeats identically.
3.  **Pattern Duplication:** Instead of simulating every rider step-by-step (which is slow and error-prone), the engine duplicates the optimal pattern, applying the calculated time shift $\lambda$.

This approach transforms an NP-hard scheduling problem into a linear algebra problem, solved instantly 

---

## Author
**Jérémy Digard** - *Engineering Student at EPFL*
Developed for [Equissima](https://equissima.ch).
