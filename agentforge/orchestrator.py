"""
Orquestador de tareas — nucleo del sistema AgentForge.

Responsabilidades:
  1. Recibir un manifest (de Claude via MCP o de la CLI)
  2. Encolar la tarea respetando el limite de concurrencia
  3. Llamar al handler correcto segun type+subtype
  4. Persistir el output y el audit record
  5. Correr la validacion automatica
  6. Reportar el resultado

Concurrencia:
  asyncio.Semaphore(MAX_PARALLEL_TASKS) limita cuantas tareas corren
  simultaneamente. Con hardware i7-3537U / 15.5GB:
    MAX_PARALLEL_TASKS=2 → hasta 13GB RAM en uso (2 x qwen2.5-coder:7b)
    Reducir a 1 si el sistema muestra swap o slowdown.
"""

import asyncio
from datetime import datetime, timezone

from agentforge.config import MAX_PARALLEL_TASKS, RESULTS_DIR, ensure_dirs
from agentforge.handlers import get_handler
from agentforge.models import AuditRecord, ExecutionManifest, TaskStatus, OnFailure
from agentforge.utils import (
    write_manifest, write_raw_output, write_output_file,
    write_validation, write_audit, run_validation,
    log_task_start, log_task_end, log_error,
)
from agentforge.utils.perf_monitor import PerfMonitor

# Semaforo global — controla cuantas tareas Ollama corren en paralelo
_semaphore = asyncio.Semaphore(MAX_PARALLEL_TASKS)

# Registro en memoria de tareas activas {task_id: AuditRecord}
# Complementa los archivos en disco — util para consultas de status en tiempo real
_active_tasks: dict[str, AuditRecord] = {}


async def execute_task(manifest: ExecutionManifest) -> AuditRecord:
    """
    Ejecuta un manifest completo: handler + validacion + persistencia.

    Este es el metodo principal del sistema. Lo llama el MCP Server
    cuando Claude invoca agentforge.execute().

    Args:
        manifest: El manifest validado por Pydantic.

    Returns:
        AuditRecord con el resultado completo de la ejecucion.
    """
    ensure_dirs()
    task_id = manifest.task_id

    # Inicializar audit record y persistir estado inicial
    record = AuditRecord(
        task_id=task_id,
        manifest=manifest,
        model=manifest.created_by,
        started_at=datetime.now(timezone.utc),
        status=TaskStatus.QUEUED,
    )
    _active_tasks[task_id] = record
    write_manifest(task_id, manifest)
    write_audit(task_id, record)

    log_task_start(task_id, manifest.task.type.value, manifest.task.subtype.value)

    # Adquirir slot de concurrencia — bloquea aqui si ya hay MAX_PARALLEL_TASKS corriendo
    async with _semaphore:
        record.status = TaskStatus.RUNNING
        write_audit(task_id, record)

        from agentforge.utils.results import get_task_dir
        monitor = PerfMonitor(task_id, get_task_dir(task_id))
        monitor.start()

        try:
            handler = get_handler(manifest.task.type, manifest.task.subtype)

            # Ejecutar el handler con timeout de la tarea
            output_content, output_filename = await asyncio.wait_for(
                handler(manifest),
                timeout=manifest.task.timeout_seconds,
            )

            # Resolver el path de output (reemplazar {task_id} si esta presente)
            resolved_output_path = manifest.output.path.replace("{task_id}", task_id)
            import re
            output_filename_from_path = re.sub(r".*[/\\]", "", resolved_output_path) or output_filename

            # Persistir el output generado
            write_raw_output(task_id, output_content)
            write_output_file(task_id, output_filename, output_content)

            # Correr validacion automatica
            validation_result = await run_validation(manifest.validation, task_id)
            write_validation(task_id, validation_result)

            # Determinar estado final
            if validation_result.passed:
                record.status = TaskStatus.COMPLETED
            else:
                if manifest.on_failure == OnFailure.REPORT_AND_HALT:
                    record.status = TaskStatus.FAILED
                    record.error = f"Validation failed: {validation_result.stderr}"
                else:
                    # REPORT_AND_CONTINUE: marcar completado de todas formas
                    # Claude vera el validation.passed=False en el audit
                    record.status = TaskStatus.COMPLETED

            record.validation = validation_result

        except asyncio.TimeoutError:
            record.status = TaskStatus.FAILED
            record.error = f"Task timed out after {manifest.task.timeout_seconds}s"
            log_error(task_id, record.error)

        except Exception as e:
            record.status = TaskStatus.FAILED
            record.error = str(e)
            log_error(task_id, str(e))

        finally:
            await monitor.stop()

            record.finished_at = datetime.now(timezone.utc)
            if record.started_at:
                delta = record.finished_at - record.started_at
                record.duration_seconds = delta.total_seconds()

            write_audit(task_id, record)
            _active_tasks[task_id] = record

            log_task_end(
                task_id=task_id,
                status=record.status.value,
                duration_seconds=record.duration_seconds or 0,
                validation_passed=record.validation.passed if record.validation else None,
                error=record.error,
            )

    return record


async def execute_batch(
    manifests: list[ExecutionManifest],
    max_parallel: int = MAX_PARALLEL_TASKS,
) -> list[AuditRecord]:
    """
    Ejecuta multiples manifests con el limite de concurrencia especificado.

    Las tareas sin dependencias entre si corren en paralelo.
    El semaforo interno controla que no haya mas de max_parallel corriendo a la vez.

    Args:
        manifests: Lista de manifests a ejecutar.
        max_parallel: Override del limite de concurrencia para este batch.

    Returns:
        Lista de AuditRecord en el mismo orden que los manifests recibidos.
    """
    # Override temporal del semaforo para este batch
    batch_semaphore = asyncio.Semaphore(max_parallel)

    async def run_with_semaphore(m: ExecutionManifest) -> AuditRecord:
        async with batch_semaphore:
            return await execute_task(m)

    results = await asyncio.gather(
        *[run_with_semaphore(m) for m in manifests],
        return_exceptions=False,
    )
    return list(results)


def get_task_status(task_id: str) -> AuditRecord | None:
    """
    Consulta el estado de una tarea en memoria primero, luego en disco.

    Returns:
        AuditRecord si la tarea existe, None si no.
    """
    if task_id in _active_tasks:
        return _active_tasks[task_id]

    # Buscar en disco (tarea de una sesion anterior)
    from agentforge.utils import read_audit
    return read_audit(task_id)
