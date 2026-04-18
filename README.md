# AgentForge LLM

> Orchestrate mechanical development tasks via a local LLM, reducing Claude Code token consumption by ~42% through async task delegation and parallelization.

## Overview

AgentForge LLM is a **Model Context Protocol (MCP) Server** that sits between Claude Code and a locally-running Ollama instance. Claude acts as architect and auditor; the local LLM (`qwen2.5-coder:7b`) handles repetitive code generation tasks autonomously.

```
Claude Code (architect + auditor)
        │  MCP tool calls
        ▼
AgentForge MCP Server  (this project)
        │  HTTP REST
        ▼
Ollama API  →  qwen2.5-coder:7b (local inference)
        │
        ▼
/results/{task_id}/  →  Claude reviews and approves
```

## Key Features

- **6 MCP tools** exposed to Claude: `execute`, `batch`, `status`, `audit`, `pending`, `health`
- **8 task types**: Terraform boilerplate (variables/outputs/versions), metadata.json, CLAUDE.md, security analysis, document update, resource extraction
- **Async parallelism**: up to N tasks running concurrently via `asyncio.Semaphore`
- **Automatic validation**: runs `terraform validate`, JSON schema checks, etc. after each task
- **Full audit trail**: every task writes `manifest.json`, `raw_llm_output.txt`, `validation.json`, `audit.json`
- **CLI for review**: `agentforge pending`, `audit`, `approve`, `reject`, `run --plan`
- **Kubernetes-ready**: manifests for Ollama + AgentForge pods included

## Stack

| Layer | Technology |
|-------|-----------|
| MCP Server | [fastmcp](https://github.com/jlowin/fastmcp) |
| HTTP client | httpx (async) |
| Data validation | Pydantic v2 |
| CLI | Click + Rich |
| Local LLM | Ollama + qwen2.5-coder:7b |
| Container orchestration | Kubernetes (Minikube for local) |

## Quick Start

### Prerequisites

- Python 3.11+
- [Ollama](https://ollama.com) installed and running
- `qwen2.5-coder:7b` model pulled

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull the model (~4.7 GB)
ollama pull qwen2.5-coder:7b
```

### Install

```bash
git clone https://github.com/kratosvil/agentforge-llm
cd agentforge-llm

python3 -m venv .venv
source .venv/bin/activate
pip install -e .

cp .env.example .env
```

### Verify

```bash
agentforge health
# Ollama OK — version X.X.X
# Model qwen2.5-coder:7b available: YES
```

### Connect to Claude Desktop

Add to `~/.config/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "agentforge": {
      "command": "python3",
      "args": ["-m", "agentforge.server"],
      "cwd": "/path/to/agentforge-llm",
      "env": {
        "OLLAMA_HOST": "http://localhost:11434",
        "MODEL_NAME": "qwen2.5-coder:7b"
      }
    }
  }
}
```

See `mcp-config-snippet.json` for the full snippet with all environment variables.

## Usage

### Via Claude Code (MCP)

```python
# Check agent is ready
agentforge_health()

# Delegate a task
agentforge_execute({
  "task": {"type": "generate_boilerplate", "subtype": "terraform_variables"},
  "input": {
    "source_files": ["/path/to/module/main.tf"],
    "module_name": "networking",
    "layer": "platform"
  },
  "output": {"path": "./results/{task_id}/variables.tf", "format": "hcl"},
  "validation": {"command": "terraform validate", "working_dir": "./results/{task_id}/output/"}
})
# → {task_id, status, duration_seconds, output_path}

# Review and approve
agentforge_audit(task_id="<uuid>", approve=True)
```

### Via CLI

```bash
# List tasks waiting for review
agentforge pending

# Review a specific task
agentforge audit <task_id>

# Approve / reject
agentforge approve <task_id>
agentforge reject <task_id> --reason "Missing validation blocks"

# Run a full plan
agentforge run --plan plans/build-networking-module.json
```

## Supported Task Types

| Type | Subtype | Input | Output | Validation |
|------|---------|-------|--------|-----------|
| `generate_boilerplate` | `terraform_variables` | main.tf | variables.tf | terraform validate |
| `generate_boilerplate` | `terraform_outputs` | main.tf | outputs.tf | terraform validate |
| `generate_boilerplate` | `terraform_versions` | main.tf | versions.tf | terraform validate |
| `generate_metadata` | `module_metadata_json` | *.tf files | metadata.json | JSON parse |
| `generate_documentation` | `module_claude_md` | *.tf + metadata | CLAUDE.md | — |
| `analyze_security` | `tfsec_report` | *.tf files | tfsec_report.json | JSON parse |
| `update_document` | `estado_md` | existing doc | updated doc | — |
| `extract_structure` | `tf_resources` | *.tf files | resources.json | JSON parse |

## Configuration

All configuration is via environment variables (copy `.env.example` to `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API endpoint |
| `MODEL_NAME` | `qwen2.5-coder:7b` | Model to use for inference |
| `MAX_PARALLEL_TASKS` | `2` | Max concurrent Ollama calls |
| `TASK_TIMEOUT_SECONDS` | `300` | Per-task timeout (5 min) |
| `LLM_TEMPERATURE` | `0.1` | Low temperature = deterministic code output |

## Performance (target hardware: i7-3537U / 15.5 GB RAM / CPU-only)

| Metric | Baseline (Claude only) | With AgentForge |
|--------|----------------------|-----------------|
| Claude tokens per TF module | ~60,000 | ~35,000 (−42%) |
| Active Claude session time | ~45 min | ~20 min (−55%) |
| Modules built per session | 1 | 2–3 (parallel) |

## Kubernetes Deployment

```bash
# Apply all manifests
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/ollama-deployment.yaml
kubectl apply -f k8s/ollama-service.yaml

# Build and deploy AgentForge
docker build -t agentforge-server:latest -f k8s/Dockerfile .
kubectl apply -f k8s/agentforge-deployment.yaml
```

## Project Structure

```
agentforge-llm/
├── agentforge/
│   ├── server.py          # MCP Server (fastmcp) — 6 tools
│   ├── orchestrator.py    # Async task executor with concurrency control
│   ├── models.py          # Pydantic models: manifest, audit, batch
│   ├── config.py          # Central configuration from env vars
│   ├── cli.py             # CLI (click + rich)
│   ├── ollama/            # Async Ollama HTTP client
│   ├── handlers/          # One handler per task type
│   └── utils/             # Results storage, validator, logger
├── templates/             # 8 LLM prompt templates
├── k8s/                   # Kubernetes manifests + Dockerfile
├── plans/                 # Example execution plans
└── results/               # Task outputs (gitignored)
```

## Roadmap

- [x] v0.1.0 — MCP Server + 8 task types + CLI + K8s manifests
- [ ] v0.2.0 — Multi-host LAN: delegate to RTX 2070 node via `OLLAMA_HOST`
- [ ] v0.3.0 — Task dependency graph (DAG) for ordered plan execution
- [ ] v1.0.0 — Production-grade: metrics, retry logic, model fallback

## License

MIT
