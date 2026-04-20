# AgentForge-LLM

Orchestrates a local LLM (Ollama + codellama:13b) via MCP to execute mechanical code generation tasks in the background, freeing Claude's context window for high-level reasoning.

## How it works

```
Claude Code (architect)
    │  agentforge_execute(manifest)   → {task_id, status:"queued"}  <1s
    │
    ▼
AgentForge MCP Server (Python + fastmcp)
    │  async fire-and-forget via asyncio.create_task()
    │
    ▼
Ollama (codellama:13b)   ← RTX 2070 / LAN node
    │  results/ written locally
    ▼
agentforge_audit(task_id)   ← Claude reviews when ready
```

**Key benefit:** Claude generates a manifest, fires it, and continues working. The 150–500 tokens of boilerplate output never enter Claude's context — Ollama handles them locally.

## Architecture

```
Linux PC (orchestrator)              Windows 192.168.128.4 (inference)
────────────────────────             ──────────────────────────────────
Claude Code CLI                      Ollama :11434
AgentForge MCP (stdio)  →LAN→       codellama:13b (~7.4 GB VRAM)
results/ directory                   Ryzen 7 5700 / 32 GB RAM
```

## Requirements

- Python 3.11+
- [Ollama](https://ollama.com) running locally or on a LAN node
- `codellama:13b` pulled: `ollama pull codellama:13b`
- Claude Code CLI

## Installation

```bash
git clone https://github.com/kratosvil/agentforge-llm
cd agentforge-llm
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

All settings via environment variables (defaults in `agentforge/config.py`):

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama endpoint — override for LAN |
| `MODEL_NAME` | `codellama:13b` | Ollama model |
| `MAX_PARALLEL_TASKS` | `1` | Concurrency (RTX 2070 8GB → keep at 1) |
| `LLM_MAX_TOKENS` | `4096` | Max tokens per generation |
| `LLM_TEMPERATURE` | `0.1` | Low = deterministic output |
| `TASK_TIMEOUT_SECONDS` | `300` | Default task timeout |

## Register as MCP server

```bash
# Override OLLAMA with your LAN IP if needed:
OLLAMA=http://192.168.128.4:11434 make mcp-register

# Verify registration
make mcp-status
```

Open a **new** Claude Code session after registering. The MCP server spawns fresh each session.

## MCP Tools

### `agentforge_health`
Check Ollama connectivity and model availability.

### `agentforge_execute(manifest)`
Queue a task. Returns `{task_id, status: "queued"}` in <1s — never blocks.

### `agentforge_status(task_id)`
Poll task state: `"running" | "completed" | "failed"`.

### `agentforge_pending()`
List completed tasks not yet reviewed by Claude.

### `agentforge_audit(task_id, approve=None|True|False)`
Read output and optionally record approval. `None` = read only.

### `agentforge_batch(manifests)`
Queue multiple tasks at once. Returns list of task_ids immediately.

## Execution Manifest

```python
{
    "task": {
        "type": "generate_code",        # or generate_boilerplate
        "subtype": "python_class",
        "timeout_seconds": 90
    },
    "input": {
        "source_files": [],
        "module_name": "user_repository",
        "description": "Write a Python UserRepository class with CRUD methods: create(user_dict), get_by_id(id), get_all(), update(id, data), delete(id). In-memory dict storage."
    },
    "output": {
        "path": "/tmp/output/user_repo.py",
        "format": "python"
    }
}
```

## Supported subtypes & timeouts

| Subtype | Timeout | Notes |
|---------|---------|-------|
| `python_function` | 60s | Fast, reliable |
| `python_class` simple | 90s | Patterns, CRUD |
| `python_class` complex | 240s | Review algorithm logic |
| `python_unittest` | 60s | Verify expected values |
| `bash_script` | 90s | Give exact command spec |
| `terraform_module` | 150s | Review env/lifecycle blocks |
| `k8s_manifest` | 120s | Review API versions |
| `sql_schema` | 150s | Prefix spec with "GENERATE NEW" |
| `readme` | 200s | Heavy review — hallucinates details |

## Async workflow

```python
# 1. Fire (non-blocking)
task = agentforge_execute(manifest)        # <1s → {task_id, status:"queued"}

# 2. Keep working on other things...

# 3. Check status when convenient
agentforge_status(task["task_id"])         # "running" | "completed"

# 4. Review completed work
agentforge_pending()                       # see what finished
agentforge_audit(task_id, approve=None)    # read output

# 5. Approve or reject
agentforge_audit(task_id, approve=True)    # mark reviewed ✓
agentforge_audit(task_id, approve=False)   # reject → re-queue with corrections
```

## Known model bugs (codellama:13b)

| Context | Bug | Fix |
|---------|-----|-----|
| Terraform Lambda | `environment = var.env` | `environment { variables = var.env }` |
| K8s HPA | `autoscaling/v2beta1` | `autoscaling/v2` |
| K8s Deployment | `image: var IMAGE` literal | replace with real image |
| SQL spec | treats description as broken code | prefix "GENERATE NEW ... from scratch" |
| Bash curl | `curl \| grep "HTTP/2 200"` | `curl -o /dev/null -s -w '%{http_code}'` |
| Complex algorithms | Dijkstra → BFS without heapq | verify algorithm logic |
| BST delete (2 children) | successor not detached from subtree | check manually |

## Delegation rule

**Tasks >40 lines of output → delegate to AgentForge.**
Below that threshold, the manifest overhead costs as much as generating directly.

| Task | Claude direct | Via AgentForge | Saving |
|------|--------------|----------------|--------|
| Function <30 lines | ~$0.014 | ~$0.014 | ~0% |
| Class 50 lines | ~$0.024 | ~$0.014 | ~40% |
| Class 150 lines | ~$0.048 | ~$0.017 | ~65% |
| Session (10 modules) | ~$0.225 | ~$0.052 | ~77% |

## Benchmark

| Subtype | Pass rate (rounds 1+2) | Notes |
|---------|----------------------|-------|
| python_function | 100% | |
| python_class simple/medium | ~100% | |
| python_class complex | ~70% | logic bugs in algorithms |
| bash_script | 70% | needs command guidance |
| terraform_module | 100% | structural bugs present |
| k8s_manifest | 100% | deprecated API versions |
| sql_schema | 100% | |
| python_unittest | 50% | math errors in assertions |
| readme | 0% | not usable without heavy rewrite |

10-cycle benchmark (100 tasks) in progress — results in `docs/benchmark_cycles_tracking.json`.

## Project structure

```
agentforge-llm/
├── agentforge/
│   ├── server.py          MCP server — 6 tools, async fire-and-forget
│   ├── orchestrator.py    async task queue + PerfMonitor
│   ├── config.py          env-based config with safe defaults
│   ├── models.py          Pydantic models
│   ├── cli.py             click+rich CLI
│   ├── handlers/          7 task handlers
│   ├── ollama/client.py   httpx async (num_ctx=4096)
│   └── utils/             results, validator, logger, perf_monitor
├── templates/             8 prompt templates
├── k8s/                   Kubernetes manifests (Sprint 2)
├── docs/
│   ├── codellama13b_capability_map.md
│   └── benchmark_cycles_tracking.json
├── PROCESO.md
└── Makefile
```

## Roadmap

| Sprint | Status | |
|--------|--------|-|
| 1 | Done | Generic manifest system, universal handler |
| 1.1 | Done | codellama:13b, async fire-and-forget, benchmark |
| 2 | Pending | HTTP+SSE remote + API key auth (multi-client) |

## License

MIT
