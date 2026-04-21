"""
Modelos de datos del sistema AgentForge.

Pydantic valida la estructura de cada manifest al recibirlo.
Si Claude genera un manifest mal formado, falla aqui con un error claro
antes de enviar nada a Ollama.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Enums internos — estado y comportamiento del sistema (no expuestos al usuario)
# ---------------------------------------------------------------------------

class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class OnFailure(str, Enum):
    REPORT_AND_HALT = "report_and_halt"
    REPORT_AND_CONTINUE = "report_and_continue"
    RETRY_ONCE = "retry_once"


# ---------------------------------------------------------------------------
# Sub-modelos del manifest
# ---------------------------------------------------------------------------

class TaskDefinition(BaseModel):
    """Define el tipo y comportamiento de la tarea.

    type y subtype son strings libres — el sistema acepta cualquier valor.
    Si existe templates/{subtype}.txt se usa ese template.
    Si no existe, se usa input.description directamente como prompt.
    """
    type: str                              # generate_code, generate_boilerplate, cualquier string
    subtype: str                           # python_class, docker_compose, github_actions, etc.
    priority: str = "normal"
    timeout_seconds: int = Field(default=300, ge=30, le=1800)


class InputDefinition(BaseModel):
    """Archivos fuente y contexto que el agente necesita para ejecutar la tarea."""
    source_files: list[str] = Field(default_factory=list)
    module_name: str = ""
    layer: str = ""                        # organization | platform | product
    description: str = ""                  # prompt principal de la tarea
    context: str = ""                      # output previo para encadenar generaciones
    additional_context: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_source_files_exist(self) -> "InputDefinition":
        """Verifica que los archivos fuente existen antes de encolar la tarea."""
        for f in self.source_files:
            if not Path(f).exists():
                raise ValueError(f"Archivo fuente no encontrado: {f}")
        return self


class OutputDefinition(BaseModel):
    """Donde escribir el resultado y en que formato."""
    path: str                              # Puede contener {task_id} como placeholder
    format: str = "text"                   # hcl | json | markdown | text


class ValidationDefinition(BaseModel):
    """Comando de validacion a correr sobre el output generado."""
    command: str = ""                      # Vacio = sin validacion
    working_dir: str = ""
    expected_exit_code: int = 0


# ---------------------------------------------------------------------------
# Manifest principal — lo que Claude genera y AgentForge consume
# ---------------------------------------------------------------------------

class ExecutionManifest(BaseModel):
    """
    Contrato entre Claude Code y el agente Ollama.

    Claude crea este objeto y llama a agentforge.execute(manifest).
    AgentForge lo valida, ejecuta, y escribe resultados en /results/{task_id}/.
    """
    manifest_version: str = "1.0"
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_by: str = "claude-sonnet-4-6"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    project: str = ""
    model: str = ""  # Override del modelo — vacío = usar MODEL_NAME del config

    task: TaskDefinition
    input: InputDefinition
    output: OutputDefinition
    validation: ValidationDefinition = Field(default_factory=ValidationDefinition)
    on_failure: OnFailure = OnFailure.REPORT_AND_HALT


# ---------------------------------------------------------------------------
# Modelos de resultado — lo que AgentForge escribe en /results/
# ---------------------------------------------------------------------------

class ValidationResult(BaseModel):
    """Resultado de correr el comando de validacion sobre el output."""
    command: str
    exit_code: int
    stdout: str
    stderr: str
    passed: bool


class AuditRecord(BaseModel):
    """
    Metadata de ejecucion de una tarea. Claude lee esto para decidir APPROVE/REJECT.
    """
    task_id: str
    manifest: ExecutionManifest
    model: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_seconds: float | None = None
    status: TaskStatus = TaskStatus.QUEUED
    validation: ValidationResult | None = None
    error: str | None = None
    claude_reviewed: bool = False
    approved: bool | None = None          # None = pendiente de revision


# ---------------------------------------------------------------------------
# Modelo para ejecucion en lote
# ---------------------------------------------------------------------------

class BatchRequest(BaseModel):
    """Agrupa multiples manifests para ejecutar en paralelo."""
    manifests: list[ExecutionManifest]
    max_parallel: int = Field(default=2, ge=1, le=4)

    batch_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
