"""
CLI de auditoria y operacion de AgentForge.

Comandos disponibles:
  agentforge health              — verifica Ollama disponible
  agentforge pending             — lista tareas esperando revision
  agentforge audit <task_id>     — muestra output de una tarea para revision
  agentforge approve <task_id>   — aprueba el output de una tarea
  agentforge reject <task_id>    — rechaza el output de una tarea
  agentforge run --plan <file>   — ejecuta un plan de tareas desde JSON
  agentforge status <task_id>    — consulta estado de una tarea

Por que Click + Rich:
  - Click maneja argumentos, opciones y subcomandos con muy poco codigo
  - Rich formatea tablas y colores en terminal para que la CLI sea legible
    cuando hay multiples tareas en cola
"""

import asyncio
import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich import box

from agentforge.config import RESULTS_DIR

console = Console()


# ---------------------------------------------------------------------------
# Grupo principal
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """AgentForge LLM — Orquestador de tareas mecanicas via Ollama."""
    pass


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------

@cli.command()
def health():
    """Verifica que Ollama esta disponible y el modelo esta cargado."""
    from agentforge.ollama.client import check_health
    result = asyncio.run(check_health())

    if result["status"] == "ok":
        console.print(f"[green]Ollama OK[/green] — version {result['ollama_version']}")
        console.print(f"Modelo [cyan]{result['model']}[/cyan] disponible: [green]SI[/green]")
    elif result["status"] == "model_missing":
        console.print(f"[yellow]Ollama OK[/yellow] — version {result['ollama_version']}")
        console.print(f"Modelo [cyan]{result['model']}[/cyan] disponible: [red]NO[/red]")
        console.print(f"Modelos disponibles: {result['available_models']}")
        console.print(f"\nEjecuta: [bold]ollama pull {result['model']}[/bold]")
    else:
        console.print(f"[red]ERROR:[/red] {result['message']}")


# ---------------------------------------------------------------------------
# pending
# ---------------------------------------------------------------------------

@cli.command()
def pending():
    """Lista tareas completadas pendientes de revision por Claude."""
    from agentforge.utils import list_pending_review
    tasks = list_pending_review()

    if not tasks:
        console.print("[green]No hay tareas pendientes de revision.[/green]")
        return

    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("TASK_ID", style="dim", width=36)
    table.add_column("TYPE", width=22)
    table.add_column("SUBTYPE", width=25)
    table.add_column("DURACION", width=10)
    table.add_column("OUTPUT")

    for t in tasks:
        duration = f"{t['duration_seconds']:.0f}s" if t['duration_seconds'] else "—"
        table.add_row(
            t["task_id"],
            t["type"],
            t["subtype"],
            duration,
            t["output_path"],
        )

    console.print(table)
    console.print(f"\n[bold]{len(tasks)}[/bold] tarea(s) pendientes.")
    console.print("Usa [cyan]agentforge audit <task_id>[/cyan] para revisar una tarea.")


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("task_id")
def audit(task_id: str):
    """Muestra el output de una tarea para revision manual."""
    from agentforge.utils import read_audit, read_output_content

    record = read_audit(task_id)
    if record is None:
        console.print(f"[red]Tarea no encontrada:[/red] {task_id}")
        return

    console.rule(f"[bold]Tarea {task_id[:8]}...[/bold]")
    console.print(f"Tipo:     [cyan]{record.manifest.task.type.value}[/cyan] / {record.manifest.task.subtype.value}")
    console.print(f"Estado:   [{'green' if record.status.value == 'completed' else 'red'}]{record.status.value}[/]")
    console.print(f"Duracion: {record.duration_seconds:.1f}s" if record.duration_seconds else "Duracion: —")

    if record.validation:
        passed_str = "[green]PASO[/green]" if record.validation.passed else "[red]FALLO[/red]"
        console.print(f"Validacion: {passed_str} ({record.validation.command})")
        if not record.validation.passed:
            console.print(f"[red]stderr:[/red] {record.validation.stderr[:300]}")

    console.rule("[bold]Output generado[/bold]")
    output = read_output_content(task_id)
    console.print(output if output else "[dim]Sin output[/dim]")
    console.rule()
    console.print("Usa [cyan]agentforge approve <task_id>[/cyan] o [cyan]agentforge reject <task_id>[/cyan]")


# ---------------------------------------------------------------------------
# approve
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("task_id")
def approve(task_id: str):
    """Aprueba el output de una tarea y la marca como lista para integrar."""
    from agentforge.utils import mark_reviewed, read_audit

    record = read_audit(task_id)
    if record is None:
        console.print(f"[red]Tarea no encontrada:[/red] {task_id}")
        return

    mark_reviewed(task_id, approved=True)
    console.print(f"[green]APROBADA[/green] — tarea {task_id[:8]}...")
    console.print(f"Output en: {RESULTS_DIR / task_id / 'output'}")


# ---------------------------------------------------------------------------
# reject
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("task_id")
@click.option("--reason", "-r", default="", help="Motivo del rechazo")
def reject(task_id: str, reason: str):
    """Rechaza el output de una tarea. Usa --reason para explicar el problema."""
    from agentforge.utils import mark_reviewed, read_audit

    record = read_audit(task_id)
    if record is None:
        console.print(f"[red]Tarea no encontrada:[/red] {task_id}")
        return

    mark_reviewed(task_id, approved=False)
    console.print(f"[red]RECHAZADA[/red] — tarea {task_id[:8]}...")
    if reason:
        console.print(f"Motivo: {reason}")
    console.print("Ajusta el manifest y vuelve a ejecutar con agentforge_execute.")


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("task_id")
def status(task_id: str):
    """Consulta el estado actual de una tarea."""
    from agentforge.orchestrator import get_task_status

    record = get_task_status(task_id)
    if record is None:
        console.print(f"[red]Tarea no encontrada:[/red] {task_id}")
        return

    color = {
        "queued": "yellow", "running": "cyan",
        "completed": "green", "failed": "red",
    }.get(record.status.value, "white")

    console.print(f"Estado:  [{color}]{record.status.value.upper()}[/{color}]")
    if record.duration_seconds:
        console.print(f"Tiempo:  {record.duration_seconds:.1f}s")
    if record.error:
        console.print(f"Error:   [red]{record.error}[/red]")


# ---------------------------------------------------------------------------
# run --plan
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--plan", "-p", required=True, type=click.Path(exists=True), help="Path al archivo de plan JSON")
def run(plan: str):
    """Ejecuta un plan de tareas desde un archivo JSON."""
    plan_data = json.loads(Path(plan).read_text())

    console.print(f"[bold]Plan:[/bold] {plan_data.get('plan_id', 'sin-id')}")
    console.print(f"Tareas: {len(plan_data.get('tasks', []))}")
    console.print()

    asyncio.run(_run_plan(plan_data))


async def _run_plan(plan_data: dict) -> None:
    """Ejecuta todas las tareas del plan respetando dependencias."""
    from agentforge.models import ExecutionManifest, TaskDefinition, InputDefinition, OutputDefinition
    from agentforge.orchestrator import execute_task
    from agentforge.config import RESULTS_DIR

    source_module = plan_data.get("source_module", "")
    output_dir = plan_data.get("output_dir", str(RESULTS_DIR))

    for task_spec in plan_data.get("tasks", []):
        task_type = task_spec["type"]
        subtype = task_spec["subtype"]

        # Construir source_files desde el modulo fuente
        source_dir = Path(source_module)
        source_files = [str(p) for p in source_dir.glob("*.tf")] if source_dir.exists() else []

        manifest = ExecutionManifest(
            project=plan_data.get("plan_id", ""),
            task=TaskDefinition(type=task_type, subtype=subtype),
            input=InputDefinition(
                source_files=source_files,
                module_name=source_dir.name if source_dir.exists() else "",
            ),
            output=OutputDefinition(
                path=f"{output_dir}/{{task_id}}/{subtype}",
                format="hcl" if "terraform" in subtype else "json",
            ),
        )

        console.print(f"[cyan]→[/cyan] Ejecutando {task_type}/{subtype}...")
        record = await execute_task(manifest)

        status_color = "green" if record.status.value == "completed" else "red"
        duration = f"{record.duration_seconds:.0f}s" if record.duration_seconds else "—"
        console.print(
            f"  [{status_color}]{record.status.value.upper()}[/{status_color}] "
            f"— {duration} — {record.task_id[:8]}..."
        )

        if record.error:
            console.print(f"  [red]Error:[/red] {record.error}")

    console.print("\n[bold green]Plan completado.[/bold green]")
    console.print("Revisa con: [cyan]agentforge pending[/cyan]")
