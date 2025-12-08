# Eventing Competition Planner
Concours Complet Scheduler & Optimizer
Eventing Planner is a  tool  to automate and visualize the scheduling of Eventing competition (Concours Complet d'Équitation). It manages the timing between Dressage, Cross Country, and Show Jumping (CSO), ensuring safety buffers are met while optimizing the flow of candidates.


# Live Demo
Web App : https://complet.streamlit.app
Clic "Yes, get this app back up" to launch the app if it is in standby mode.

# Key Features
Interactive Gantt Chart: Visualize the entire day's schedule at a glance.
Two Scheduling Modes:
Manual: You define the specific intervals between riders.
Auto-Optimization: The algorithm calculates the tightest possible schedule based on safety constraints ("Reset" times).
Conflict Detection:
Prevents overlap between phases for the same rider.
Shared Arena Support: Intelligently manages schedules when Dressage and Show Jumping share the same physical paddock, adding transition buffers automatically.
Customizable: Adjust durations for every phase (Dressage, Cross, Jump) and transition pauses.
Exportable: Generate professional charts ready for printing or sharing with judges and stewards.


# How It Works
This tool solves the "Job Shop Scheduling" problem applied to equestrian sports.

### 1. The Timeline Logic
Each rider follows a strict sequence: Start ➔ Dressage ➔ Pause 1 ➔ Cross ➔ Pause 2 ➔ Jump

### 2. The Optimization Algorithm ("Greedy Approach")
In Auto Mode, the system uses a greedy algorithm to find the Earliest Start Time for each rider:
It respects the physical duration of the tests.
It enforces Reset Times (time needed for the jury or track crew to reset between riders).
It checks for Resource Conflicts (e.g., if the Jumping arena is occupied by a previous rider while the current rider needs to do Dressage in the same location).
It assigns the first available slot that satisfies all constraints, minimizing dead time.
