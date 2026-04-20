.PHONY: help mcp-register mcp-status run-server test-health

VENV       := .venv/bin/python3
SERVER_CMD := -m agentforge.server
OLLAMA     := http://192.168.128.4:11434
MODEL      := codellama:13b
MAX_PAR    := 1
MAX_TOK    := 4096
MCP_SCOPE  := user

help:
	@echo "Targets disponibles:"
	@echo "  mcp-register  — registra/actualiza el servidor en Claude Code CLI (user scope)"
	@echo "  mcp-status    — muestra la config activa del MCP en Claude Code CLI"
	@echo "  run-server    — lanza el servidor MCP manualmente (debug)"
	@echo "  test-health   — verifica Ollama y modelo via CLI"

mcp-register:
	@echo "Actualizando agentforge en Claude Code CLI (scope: $(MCP_SCOPE))..."
	-claude mcp remove "agentforge" -s $(MCP_SCOPE) 2>/dev/null || true
	claude mcp add "agentforge" \
		-s $(MCP_SCOPE) \
		-e OLLAMA_HOST=$(OLLAMA) \
		-e MODEL_NAME=$(MODEL) \
		-e MAX_PARALLEL_TASKS=$(MAX_PAR) \
		-e LLM_MAX_TOKENS=$(MAX_TOK) \
		-- $(PWD)/$(VENV) $(SERVER_CMD)
	@echo "Listo. Abre una nueva sesion de Claude Code y verifica con agentforge_health."

mcp-status:
	claude mcp get agentforge

run-server:
	OLLAMA_HOST=$(OLLAMA) MODEL_NAME=$(MODEL) MAX_PARALLEL_TASKS=$(MAX_PAR) \
		LLM_MAX_TOKENS=$(MAX_TOK) $(VENV) $(SERVER_CMD)

test-health:
	cd $(PWD) && OLLAMA_HOST=$(OLLAMA) MODEL_NAME=$(MODEL) \
		$(VENV) -c "import asyncio; from agentforge.ollama.client import check_health; print(asyncio.run(check_health()))"
