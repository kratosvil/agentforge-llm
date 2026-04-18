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
# Enums — tipos de tarea soportados en v1.0
# ---------------------------------------------------------------------------

class TaskType(str, Enum):
    GENERATE_BOILERPLATE = "generate_boilerplate"
    GENERATE_METADATA = "generate_metadata"
    GENERATE_DOCUMENTATION = "generate_documentation"
    ANALYZE_SECURITY = "analyze_security"
    UPDATE_DOCUMENT = "update_document"
    EXTRACT_STRUCTURE = "extract_structure"
    GENERATE_CODE = "generate_code"


class TaskSubtype(str, Enum):
    # generate_boilerplate
    TERRAFORM_VARIABLES = "terraform_variables"
    TERRAFORM_OUTPUTS = "terraform_outputs"
    TERRAFORM_VERSIONS = "terraform_versions"
    # generate_metadata
    MODULE_METADATA_JSON = "module_metadata_json"
    # generate_documentation
    MODULE_CLAUDE_MD = "module_claude_md"
    # analyze_security
    TFSEC_REPORT = "tfsec_report"
    # update_document
    ESTADO_MD = "estado_md"
    # extract_structure
    TF_RESOURCES = "tf_resources"
    # generate_code
    PYTHON_FUNCTION = "python_function"


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
    """Define el tipo y comportamiento de la tarea."""
    type: TaskType
    subtype: TaskSubtype
    priority: str = "normal"
    timeout_seconds: int = Field(default=300, ge=30, le=1800)

    @model_validator(mode="after")
    def validate_type_subtype_combo(self) -> "TaskDefinition":
        """Asegura que el subtype corresponde al type declarado."""
        valid_combos: dict[TaskType, list[TaskSubtype]] = {
            TaskType.GENERATE_BOILERPLATE: [
                TaskSubtype.TERRAFORM_VARIABLES,
                TaskSubtype.TERRAFORM_OUTPUTS,
                TaskSubtype.TERRAFORM_VERSIONS,
            ],
            TaskType.GENERATE_METADATA: [TaskSubtype.MODULE_METADATA_JSON],
            TaskType.GENERATE_DOCUMENTATION: [TaskSubtype.MODULE_CLAUDE_MD],
            TaskType.ANALYZE_SECURITY: [TaskSubtype.TFSEC_REPORT],
            TaskType.UPDATE_DOCUMENT: [TaskSubtype.ESTADO_MD],
            TaskType.EXTRACT_STRUCTURE: [TaskSubtype.TF_RESOURCES],
            TaskType.GENERATE_CODE: [TaskSubtype.PYTHON_FUNCTION],
        }
        allowed = valid_combos.get(self.type, [])
        if self.subtype not in allowed:
            raise ValueError(
                f"Subtype '{self.subtype}' no es valido para type '{self.type}'. "
                f"Permitidos: {[s.value for s in allowed]}"
            )
        return self


class InputDefinition(BaseModel):
    """Archivos fuente y contexto que el agente necesita para ejecutar la tarea."""
    source_files: list[str] = Field(default_factory=list)
    module_name: str = ""
    layer: str = ""                        # organization | platform | product
    description: str = ""                  # prompt libre para tareas generate_code
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
