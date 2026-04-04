# Bookmark Classification Guide

Use this to decide where a new bookmark belongs. When in doubt, paste the LLM prompt at the bottom into an AI assistant.

---

## Taxonomy

### Development/
Non-language-specific software engineering: web protocols (HTTP, WebSocket, multipart), search engines, blog/CMS tooling, general dev articles, database performance.
- **Containers/** — Docker, Kubernetes, containerisation, anything about running/building containers
- **Tools/** — developer utilities, productivity tool, CLI tools, workflow guides

### Finance/
Quant trading, crypto, statistical arbitrage, market microstructure.

### Graphics/
3D graphics, rendering pipelines, shaders, WebGL/Three.js, ray tracing.

### ML-AI/
Any ML or AI content. Use the most specific subcategory first.
- **Agents/** — agentic systems, tool-using LLMs, multi-agent frameworks, memory/retrieval for agents
- **Computer-Vision/** — image/video models, CNNs, ViTs, detection, segmentation, self-supervised visual learning
- **Diffusion/** — diffusion models, score matching, sampling methods, DDPM/DDIM variants
- **General/** — everything else in ML: frameworks (JAX, PyTorch, MLX), training techniques, autodiff, GPU/CUDA, scaling, probabilistic ML, RAG, prompt engineering
- **LLMs/** — large language models specifically: architecture, training, fine-tuning, inference, benchmarks, courses
- **Reinforcement-Learning/** — RL algorithms, environments, policy learning, self-driving, game-playing agents

### Networking/
Network programming, TCP/IP, sockets, VPN (WireGuard), NAT traversal. Distinct from `Development/` — this is the *protocol/network layer*, not application-level web dev.

### Programming/
Language-specific deep dives. The focus must be the *language itself*, not what you build with it.
- **Algorithms/** — data structures, algorithmic techniques (independent of language)
- **C-CPP/** — C and C++ internals: ABI, atomics, templates, exception handling, memory model
- **Python/** — Python-specific: architecture patterns, internals, tooling

### Reading/
Book lists, PDF reading lists, sources for downloading books/papers.
- **Book-Sites/** — websites that host or provide access to books

### Science/
Formal/academic science and applied mathematics.
- **Control-Theory/** — Kalman filters, EKF/IEKF, MPC, state estimation, Lie groups applied to control
- **Mathematics/** — pure mathematics: geometry, algebra, quaternions, topology
- **Robotics/** — robot motion planning, optimal control, trajectory optimisation
- **Signal-Processing/** — FFT, filtering, spectral analysis, wavelets
- **Statistics/** — Bayesian methods, regression, estimation, hypothesis testing, nonparametric stats

### Security/
Cybersecurity, reverse engineering, exploits, low-level attack/defence.

### Systems/
Low-level systems: OS internals, concurrency (lock-free, spinlocks, green threads), shared libraries, memory, zero-copy, performance engineering.
- **Hardware/** — CPU architectures (Apple Silicon, NVIDIA), smart devices, hardware hacks

---

## Ambiguity Rules

| Scenario | Decision |
|---|---|
| ML + GPU/CUDA content | `ML-AI/General/` |
| Math *applied* to ML (e.g. KL divergence) | `ML-AI/General/` |
| Pure math (e.g. quaternion geometry) | `Science/Mathematics/` |
| Network *programming* (sockets, protocols) | `Networking/` |
| Web dev (HTTP, REST, multipart) | `Development/` |
| Container tooling (Docker, k8s) | `Development/Containers/` |
| OS / kernel / concurrency internals | `Systems/` |
| CPU / GPU *architecture* | `Systems/Hardware/` |
| Performance profiling *tools* | `Development/Tools/` |
| Performance of *systems code* | `Systems/` |
| RL applied to robotics | `ML-AI/Reinforcement-Learning/` |
| Control theory / state estimation | `Science/Control-Theory/` |
| Book / paper PDF link | `Reading/` |
| My own TODO / notes / drafts | `Meta/` (not Bookmarks) |

### When to create a new folder
Create a new subfolder only when:
1. You have **3 or more** bookmarks on the same distinct topic, AND
2. The topic is **not already well-represented** by an existing folder or parent folder.

Single items should go flat into the closest parent (e.g. a single Rust concurrency article → `Systems/`, not `Systems/Rust/`).

---

## LLM Classification Prompt

Copy the block below, fill in the bookmark details, and paste into any LLM:

---

```
You are classifying a bookmark into my personal Obsidian vault.

## Available folders
- Development/ — non-language-specific software engineering (web protocols, search engines, CMS, database perf)
  - Development/Containers/ — Docker, Kubernetes, container builds
  - Development/Tools/ — developer utilities, CLI tools, workflow guides
- Finance/ — quant trading, crypto, statistical arbitrage
- Graphics/ — 3D graphics, rendering, shaders, WebGL/Three.js
- ML-AI/Agents/ — agentic systems, tool-using LLMs, multi-agent frameworks
- ML-AI/Computer-Vision/ — image/video model, CNNs, ViTs, detection, segmentation
- ML-AI/Diffusion/ — diffusion models, DDPM/DDIM, score matching, samplers
- ML-AI/General/ — ML frameworks (JAX/PyTorch/MLX), training tricks, autodiff, GPU/CUDA, scaling, RAG, prompt engineering
- ML-AI/LLMs/ — large language models: architecture, fine-tuning, inference, courses
- ML-AI/Reinforcement-Learning/ — RL algorithms, environments, self-driving, game-playing
- Networking/ — TCP/IP, sockets, VPN, NAT traversal, network programming
- Programming/Algorithms/ — data structures and algorithmic techniques
- Programming/C-CPP/ — C/C++ internals: ABI, atomics, templates, exception handling
- Programming/Python/ — Python-specific: architecture patterns, internals
- Reading/ — book lists and PDF reading lists
- Reading/Book-Sites/ — websites that host or provide books
- Science/Control-Theory/ — Kalman filters, EKF, MPC, state estimation
- Science/Mathematics/ — pure mathematics: geometry, algebra, quaternions
- Science/Robotics/ — robot motion planning, optimal control
- Science/Signal-Processing/ — FFT, filtering, spectral analysis
- Science/Statistics/ — Bayesian methods, regression, nonparametric stats
- Security/ — cybersecurity, reverse engineering, exploits
- Systems/ — OS internals, concurrency, shared libraries, memory, performance
- Systems/Hardware/ — CPU/GPU architectures, smart devices

## Disambiguation rules
- ML + math content → ML-AI/General/ (not Science/Mathematics/)
- Pure math without ML angle → Science/Mathematics/
- Network *programming* → Networking/ (not Development/)
- Web protocols (HTTP, REST) → Development/
- OS / kernel / concurrency → Systems/
- CPU/GPU *architecture* → Systems/Hardware/
- Performance of *systems code* → Systems/

## Bookmark to classify
Title: [TITLE]
URL: [URL]
Brief description (optional): [DESCRIPTION]

## Task
1. State which single folder this bookmark belongs in.
2. Suggest a filename in Title-Kebab-Case.md format.
3. If none of the folders fit well AND there are likely 3+ similar bookmarks, suggest a new subfolder name.
4. Keep your response brief: folder path, filename, and one sentence of justification.
```

---
