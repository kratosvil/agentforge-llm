"""
AgentForge MCP Server — expone 4 tools a Claude Code via fastmcp.

Tools disponibles:
  agentforge_execute  — ejecuta un manifest (una tarea)
  agentforge_status   — consulta el estado de una tarea por task_id
  agentforge_audit    — lee el resultado de una tarea para revision de Claude
  agentforge_batch    — ejecuta multiples manifests en paralelo

Por que fastmcp:
  - Decorador @mcp.tool() genera el schema MCP automaticamente desde type hints
  - Maneja el protocolo stdio/SSE sin boilerplate
  - Construido sobre el SDK oficial de Anthropic

Como conectar a Claude Desktop:
  Agregar en ~/.config/Claude/claude_desktop_config.json:
  {
    "mcpServers": {
      "agentforge": {
        "command": "python3",
        "args": ["-m", "agentforge.server"],
        "env": {
          "OLLAMA_HOST": "http://localhost:11434",
          "MODEL_NAME": "qwen2.5-coder:7b"
        }
      }
    }
  }
"""

import asyncio
import json
from typing import Any

import anyio
from fastmcp import FastMCP

from agentforge.models import (
    AuditRecord, BatchRequest, ExecutionManifest,
)
from agentforge.ollama.client import check_health
from agentforge.orchestrator import execute_task, get_task_status
from agentforge.utils import (
    list_pending_review, mark_reviewed, read_audit, read_output_content,
)
from agentforge.md_parser import parse_requirements_md

mcp = FastMCP(
    name="agentforge",
    instructions=(
        "AgentForge LLM — Orquestador de tareas mecanicas via Ollama. "
        "Usa agentforge_execute para delegar tareas de generacion de codigo. "
        "Usa agentforge_audit para revisar y aprobar/rechazar resultados."
    ),
)


# ---------------------------------------------------------------------------
# Tool 1: Ejecutar una tarea
# ---------------------------------------------------------------------------

@mcp.tool()
async def agentforge_execute(manifest: dict[str, Any]) -> dict[str, Any]:
    """
    Ejecuta un Execution Manifest en background y retorna el task_id inmediatamente.

    El manifest define QUE generar, de DONDE leer los inputs y DONDE escribir
    el output. Claude construye el manifest; AgentForge lo ejecuta con Ollama
    sin bloquear la sesion.

    Args:
        manifest: Execution Manifest como dict. Debe tener los campos:
            - task: {type, subtype, timeout_seconds}
            - input: {source_files, module_name, layer}
            - output: {path, format}
            - validation: {command, working_dir} (opcional)

    Returns:
        {
            task_id: str,
            status: "queued",
            message: str
        }

    Flujo recomendado:
        1. agentforge_execute(manifest) → recibe task_id
        2. Continuar trabajando en otras cosas
        3. agentforge_status(task_id) para ver si termino
        4. agentforge_pending() para ver todas las tareas listas
        5. agentforge_audit(task_id) para revisar y aprobar
    """
    try:
        m = ExecutionManifest.model_validate(manifest)
    except Exception as e:
        return {"error": f"Manifest invalido: {e}", "status": "failed"}

    asyncio.create_task(execute_task(m))
    return {
        "task_id": m.task_id,
        "status": "queued",
        "message": "Tarea encolada en background. Usa agentforge_status para monitorear.",
    }


# ---------------------------------------------------------------------------
# Tool 2: Consultar estado
# ---------------------------------------------------------------------------

@mcp.tool()
async def agentforge_status(task_id: str) -> dict[str, Any]:
    """
    Consulta el estado actual de una tarea.

    Util para tareas largas: Claude puede iniciar la tarea y consultar
    el status periodicamente sin bloquear la sesion.

    Args:
        task_id: UUID de la tarea (retornado por agentforge_execute).

    Returns:
        {task_id, status, progress_message, duration_seconds, error}
    """
    record = get_task_status(task_id)
    if record is None:
        return {"error": f"Tarea no encontrada: {task_id}", "status": "not_found"}

    return {
        "task_id": task_id,
        "status": record.status.value,
        "duration_seconds": record.duration_seconds,
        "error": record.error,
        "claude_reviewed": record.claude_reviewed,
        "approved": record.approved,
    }


# ---------------------------------------------------------------------------
# Tool 3: Leer resultado para auditoria
# ---------------------------------------------------------------------------

@mcp.tool()
async def agentforge_audit(
    task_id: str,
    approve: bool | None = None,
) -> dict[str, Any]:
    """
    Lee el resultado de una tarea completada para revision de Claude.

    Si se pasa approve=True o approve=False, registra la decision en audit.json.
    Si no se pasa, solo retorna el contenido para que Claude lo revise.

    Args:
        task_id: UUID de la tarea.
        approve: True=aprobar, False=rechazar, None=solo leer.

    Returns:
        {
            task_id, status, output_content, validation_result,
            duration_seconds, approved
        }
    """
    record = read_audit(task_id)
    if record is None:
        return {"error": f"Tarea no encontrada: {task_id}", "status": "not_found"}

    output_content = read_output_content(task_id)

    if approve is not None:
        mark_reviewed(task_id, approve)

    return {
        "task_id": task_id,
        "status": record.status.value,
        "type": record.manifest.task.type,
        "subtype": record.manifest.task.subtype,
        "output_content": output_content,
        "validation": {
            "passed": record.validation.passed if record.validation else None,
            "command": record.validation.command if record.validation else "",
            "stdout": record.validation.stdout if record.validation else "",
            "stderr": record.validation.stderr if record.validation else "",
        },
        "duration_seconds": record.duration_seconds,
        "approved": record.approved,
    }


# ---------------------------------------------------------------------------
# Tool 4: Ejecutar lote en paralelo
# ---------------------------------------------------------------------------

@mcp.tool()
async def agentforge_batch(
    manifests: list[dict[str, Any]],
    max_parallel: int = 2,
) -> dict[str, Any]:
    """
    Ejecuta multiples manifests en paralelo y retorna todos los resultados.

    Usar cuando se pueden generar varios archivos del mismo modulo
    independientemente (variables.tf, outputs.tf, versions.tf).

    Args:
        manifests: Lista de Execution Manifests como dicts.
        max_parallel: Maximo de tareas simultaneas (default 2).

    Returns:
        {
            batch_id: str,
            total: int,
            completed: int,
            failed: int,
            tasks: [{task_id, status, duration_seconds, error}]
        }
    """
    try:
        validated = [ExecutionManifest.model_validate(m) for m in manifests]
    except Exception as e:
        return {"error": f"Manifest invalido en el batch: {e}", "status": "failed"}

    for m in validated:
        asyncio.create_task(execute_task(m))

    return {
        "batch_id": str(id(validated)),
        "total": len(validated),
        "status": "queued",
        "task_ids": [m.task_id for m in validated],
        "message": f"{len(validated)} tareas encoladas. Usa agentforge_pending() para ver resultados.",
    }


# ---------------------------------------------------------------------------
# Tool 5: Ejecutar desde archivo .md de requerimientos
# ---------------------------------------------------------------------------

@mcp.tool()
async def agentforge_from_md(
    md_file: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Lee un archivo .md de requerimientos y ejecuta la tarea definida en él.

    El .md debe tener frontmatter YAML con: type, subtype, format.
    El cuerpo del documento se usa como descripción del requerimiento.

    Args:
        md_file: Ruta absoluta o relativa al archivo .md.
        dry_run: Si True, solo parsea y retorna el manifest sin ejecutar.

    Returns:
        Si dry_run=False: resultado de ejecución igual a agentforge_execute.
        Si dry_run=True: el manifest que se habría ejecutado.

    Ejemplo de archivo .md:
        ---
        type: generate_code
        subtype: python_class
        format: python
        timeout: 180
        ---

        Genera una clase Python LRUCache con genéricos, capacity property,
        métodos get/put/delete/clear y dunder methods __len__, __contains__, __repr__.
    """
    try:
        manifest_dict = parse_requirements_md(md_file)
    except (FileNotFoundError, ValueError) as e:
        return {"error": str(e), "status": "failed"}

    if dry_run:
        return {"status": "dry_run", "manifest": manifest_dict}

    try:
        m = ExecutionManifest.model_validate(manifest_dict)
    except Exception as e:
        return {"error": f"Manifest inválido: {e}", "status": "failed"}

    asyncio.create_task(execute_task(m))
    return {
        "task_id": m.task_id,
        "status": "queued",
        "message": "Tarea encolada en background. Usa agentforge_status para monitorear.",
    }


# ---------------------------------------------------------------------------
# Tool 6: Health check
# ---------------------------------------------------------------------------

@mcp.tool()
async def agentforge_health() -> dict[str, Any]:
    """
    Verifica que Ollama esta disponible y el modelo esta cargado.

    Correr esto antes de encolar tareas para detectar problemas de conexion.

    Returns:
        {status, model, model_available, ollama_version}
    """
    return await check_health()


# ---------------------------------------------------------------------------
# Tool 7: Listar tareas pendientes de revision
# ---------------------------------------------------------------------------

@mcp.tool()
async def agentforge_pending() -> dict[str, Any]:
    """
    Lista todas las tareas completadas que no han sido revisadas por Claude.

    Returns:
        {count, tasks: [{task_id, type, subtype, duration_seconds, output_path}]}
    """
    pending = list_pending_review()
    return {
        "count": len(pending),
        "tasks": pending,
    }


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _record_to_response(record: AuditRecord) -> dict[str, Any]:
    """Convierte un AuditRecord al formato de respuesta de las tools."""
    from agentforge.config import RESULTS_DIR
    return {
        "task_id": record.task_id,
        "status": record.status.value,
        "duration_seconds": record.duration_seconds,
        "validation_passed": record.validation.passed if record.validation else None,
        "output_path": str(RESULTS_DIR / record.task_id / "output"),
        "error": record.error,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
