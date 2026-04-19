"""
Gestiona la escritura y lectura de resultados en /results/{task_id}/.

Estructura de directorios por tarea:
    results/
    └── {task_id}/
        ├── manifest.json       — copia del manifest ejecutado
        ├── output/
        │   └── {filename}      — archivo generado por Ollama
        ├── validation.json     — resultado del comando de validacion
        ├── audit.json          — metadata de ejecucion (para Claude)
        └── raw_llm_output.txt  — output crudo del modelo (para debug)
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from agentforge.config import RESULTS_DIR
from agentforge.models import AuditRecord, ExecutionManifest, ValidationResult


def get_task_dir(task_id: str) -> Path:
    """Retorna (y crea si no existe) el directorio de resultados para una tarea."""
    d = RESULTS_DIR / task_id
    (d / "output").mkdir(parents=True, exist_ok=True)
    return d


def write_manifest(task_id: str, manifest: ExecutionManifest) -> None:
    """Guarda el manifest en disco al inicio de la ejecucion."""
    path = get_task_dir(task_id) / "manifest.json"
    path.write_text(manifest.model_dump_json(indent=2))


def write_raw_output(task_id: str, raw: str) -> None:
    """Guarda el output crudo del LLM para debugging."""
    path = get_task_dir(task_id) / "raw_llm_output.txt"
    path.write_text(raw, encoding="utf-8")


def write_output_file(task_id: str, filename: str, content: str) -> Path:
    """
    Escribe el archivo generado por el agente en output/.

    Returns:
        Path absoluto al archivo escrito.
    """
    output_path = get_task_dir(task_id) / "output" / filename
    output_path.write_text(content, encoding="utf-8")
    return output_path


def write_validation(task_id: str, result: ValidationResult) -> None:
    """Persiste el resultado de la validacion."""
    path = get_task_dir(task_id) / "validation.json"
    path.write_text(result.model_dump_json(indent=2))


def write_audit(task_id: str, record: AuditRecord) -> None:
    """Actualiza el audit.json. Se llama al inicio y al final de cada tarea."""
    path = get_task_dir(task_id) / "audit.json"
    path.write_text(record.model_dump_json(indent=2))


def read_audit(task_id: str) -> AuditRecord | None:
    """Lee el audit.json de una tarea. Retorna None si no existe."""
    path = RESULTS_DIR / task_id / "audit.json"
    if not path.exists():
        return None
    return AuditRecord.model_validate_json(path.read_text())


def read_output_content(task_id: str) -> str:
    """Lee el contenido del archivo generado (el primero que encuentre en output/)."""
    output_dir = RESULTS_DIR / task_id / "output"
    if not output_dir.exists():
        return ""
    files = list(output_dir.iterdir())
    if not files:
        return ""
    return files[0].read_text(encoding="utf-8")


def list_pending_review() -> list[dict]:
    """
    Lista todas las tareas completadas que aun no han sido revisadas por Claude.

    Returns:
        Lista de dicts con {task_id, type, subtype, status, duration_seconds, output_path}
    """
    if not RESULTS_DIR.exists():
        return []

    pending = []
    for task_dir in sorted(RESULTS_DIR.iterdir()):
        audit_file = task_dir / "audit.json"
        if not audit_file.exists():
            continue
        try:
            record = AuditRecord.model_validate_json(audit_file.read_text())
            if record.status.value == "completed" and not record.claude_reviewed:
                pending.append({
                    "task_id": record.task_id,
                    "type": record.manifest.task.type,
                    "subtype": record.manifest.task.subtype,
                    "status": record.status.value,
                    "duration_seconds": record.duration_seconds,
                    "output_path": str(task_dir / "output"),
                })
        except Exception:
            continue
    return pending


def mark_reviewed(task_id: str, approved: bool) -> None:
    """Marca una tarea como revisada por Claude con decision APPROVE o REJECT."""
    record = read_audit(task_id)
    if record is None:
        raise ValueError(f"Tarea no encontrada: {task_id}")
    record.claude_reviewed = True
    record.approved = approved
    write_audit(task_id, record)
