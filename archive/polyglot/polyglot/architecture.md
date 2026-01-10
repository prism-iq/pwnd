# L Investigation - Polyglot Architecture

## The Human Body Metaphor

```
                    ┌─────────────────────────────────────┐
                    │           SVELTE (Mouth)            │
                    │    User speaks, system responds     │
                    │           Port: 5173                │
                    └─────────────────┬───────────────────┘
                                      │
                    ┌─────────────────▼───────────────────┐
                    │       NODE.JS (Lungs) :3000         │
                    │    Breathes data in and out         │
                    │  SSE streaming, WebSocket, I/O      │
                    └────┬────────────────────────────┬───┘
                         │                            │
          ┌──────────────▼──────────────┐   ┌────────▼─────────────────┐
          │      GO (Brain) :8085       │   │   PYTHON (Veins) :8002   │
          │   Decisions, coordination   │   │  LLM data flow, AI/ML    │
          │   Rate limiting, routing    │   │  Synthesizes knowledge   │
          └──────────────┬──────────────┘   └──────────────────────────┘
                         │
    ════════════════════════════════════════════════════════
    ║            C++ SYNAPSES (Universal Bridge)           ║
    ║  Transforms signals between all neurons perfectly    ║
    ║  FFI library - works with Rust, Go, Python, Node     ║
    ════════════════════════════════════════════════════════
                         │
         ┌───────────────┼───────────────┐
         │               │               │
  ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
  │RUST (Cells) │ │  BASH       │ │  POSTGRES   │
  │   :9001     │ │  (Nerves)   │ │  (Memory)   │
  │ Extraction  │ │  scripts    │ │   Storage   │
  │   Rayon     │ │ Build/deploy│ │   Recall    │
  └─────────────┘ └─────────────┘ └─────────────┘
```

## Organ Responsibilities

| Organ | Language | Port | Function | Strength |
|-------|----------|------|----------|----------|
| **Mouth** | Svelte | 5173 | User interface, speaks results | Reactive, compiled |
| **Lungs** | Node.js | 3000 | Breathes data in/out, SSE/WS | Async I/O, real-time |
| **Brain** | Go | 8085 | Decisions, coordination, routing | Concurrency, speed |
| **Veins** | Python | 8002 | LLM flow, AI synthesis | ML ecosystem |
| **Cells** | Rust | 9001 | Entity extraction, parsing | Memory safe, parallel |
| **Synapses** | C++ | FFI | Transform signals, universal bridge | Hard code, always works |
| **Nerves** | Bash | - | Build, deploy, signals | Scripting, automation |
| **Memory** | PostgreSQL | 5432 | Storage, recall, persistence | ACID, reliability |

## Data Flow (Circulation)

```
1. User speaks (Svelte mouth)
      │
      ▼
2. Lungs inhale request (Node.js SSE)
      │
      ▼
3. Brain analyzes & decides (Go strategy)
      │
      ├─────────────┬─────────────┐
      ▼             ▼             ▼
4. Cells extract   Blood searches   Veins synthesize
   (Rust regex)    (C++ TF-IDF)     (Python LLM)
      │             │             │
      └─────────────┴─────────────┘
                    │
                    ▼
5. Brain combines results (Go aggregation)
      │
      ▼
6. Lungs exhale response (Node.js SSE stream)
      │
      ▼
7. Mouth speaks answer (Svelte UI)
```

## Build Chain (Nervous System)

```bash
# One command builds the entire body
./build-all.sh build

# Start all organs
./build-all.sh start

# Check vital signs
./build-all.sh health

# Stop all organs
./build-all.sh stop
```

### Build Order (Nervous Impulses)

1. **Blood (C++)** - Build shared library first (fastest compilation)
2. **Cells (Rust)** - Links to C++ via FFI, parallel extraction
3. **Brain (Go)** - Routing and decisions, uses Rust results
4. **Veins (Python)** - LLM service, receives from brain
5. **Lungs (Node.js)** - Orchestrates all services
6. **Mouth (Svelte)** - Frontend, talks to lungs

## Performance Targets (Vital Signs)

| Metric | Target | Current |
|--------|--------|---------|
| Response time | < 5s | 6.2s |
| Extraction (Rust) | < 5ms | 3ms |
| Search (C++) | < 10ms | 8ms |
| LLM synthesis | < 4s | 3.8s |
| Throughput | 100 req/s | 85 req/s |

## Championship Architecture (15-year dominance)

This polyglot design ensures:

1. **Performance**: C++ blood carries data at near-hardware speed
2. **Safety**: Rust cells guarantee memory safety in hot paths
3. **Intelligence**: Python veins leverage cutting-edge AI
4. **Concurrency**: Go brain handles thousands of simultaneous decisions
5. **Real-time**: Node.js lungs breathe data with minimal latency
6. **User Experience**: Svelte mouth speaks beautifully compiled UI
7. **Automation**: Bash nerves deploy and maintain the system

Each organ does what it does best. Together, they form an unbeatable system.
