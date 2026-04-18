"""
Logger estructurado en JSON para el audit trail de AgentForge.

Por que JSON estructurado en lugar de logs de texto:
  - Claude puede leer audit.json directamente y entender que paso
  - Facilita debugging: grep por task_id, type, status
  - Preparado para ingestarse en un futuro sistema de observabilidad
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from agentforge.config import AUDIT_DIR


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write(entry: dict) -> None:
    """Escribe una linea JSON al log global y a stdout."""
    line = json.dumps(entry, default=str)

    # Append al log global del dia
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = AUDIT_DIR / f"agentforge-{today}.log"
    with open(log_file, "a") as f:
        f.write(line + "\n")

    # Tambien a stderr para visibilidad en tiempo real
    print(line, file=sys.stderr)


def log_task_start(task_id: str, task_type: str, subtype: str) -> None:
    _write({
        "ts": _ts(),
        "event": "task_start",
        "task_id": task_id,
        "type": task_type,
        "subtype": subtype,
    })


def log_task_end(
    task_id: str,
    status: str,
    duration_seconds: float,
    validation_passed: bool | None = None,
    error: str | None = None,
) -> None:
    entry: dict = {
        "ts": _ts(),
        "event": "task_end",
        "task_id": task_id,
        "status": status,
        "duration_seconds": round(duration_seconds, 2),
    }
    if validation_passed is not None:
        entry["validation_passed"] = validation_passed
    if error:
        entry["error"] = error
    _write(entry)


def log_ollama_call(task_id: str, model: str, prompt_chars: int) -> None:
    _write({
        "ts": _ts(),
        "event": "ollama_call",
        "task_id": task_id,
        "model": model,
        "prompt_chars": prompt_chars,
    })


def log_error(task_id: str, error: str, context: dict | None = None) -> None:
    entry: dict = {
        "ts": _ts(),
        "event": "error",
        "task_id": task_id,
        "error": error,
    }
    if context:
        entry["context"] = context
    _write(entry)
