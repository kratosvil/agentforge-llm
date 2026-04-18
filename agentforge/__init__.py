"""
AgentForge LLM — Orquestador de tareas mecanicas via Ollama + MCP.

Arquitectura:
  Claude Code (arquitecto/auditor)
      -> AgentForge MCP Server (este paquete)
          -> Ollama API (qwen2.5-coder:7b)
              -> Validacion automatica
                  -> /results/{task_id}/
"""

__version__ = "0.1.0"
