"""
Handler: update_document

Actualiza documentos de texto estructurado (estado.md, README, etc.)
con nuevos campos o secciones proporcionados en el manifest.

A diferencia de los otros handlers, este no genera contenido desde cero:
toma el documento existente y aplica los cambios especificados en
manifest.input.additional_context["updates"].
"""

from pathlib import Path

from agentforge.models import ExecutionManifest
from agentforge.ollama.client import run_prompt
from agentforge.config import TEMPLATES_DIR


async def handle(manifest: ExecutionManifest) -> tuple[str, str]:
    """
    Actualiza un documento de texto con nuevos campos.

    El manifest debe incluir en additional_context:
        - "target_file": path al archivo a actualizar
        - "updates": dict con los campos a actualizar y sus nuevos valores

    Returns:
        (updated_content, filename)
    """
    template_file = TEMPLATES_DIR / "estado_update.txt"
    if not template_file.exists():
        raise FileNotFoundError(f"Template no encontrado: {template_file}")

    template = template_file.read_text(encoding="utf-8")
    ctx = manifest.input.additional_context

    target_file = ctx.get("target_file", "")
    updates = ctx.get("updates", {})
    filename = Path(target_file).name if target_file else "document.md"

    # Leer el documento actual si existe
    current_content = ""
    if target_file and Path(target_file).exists():
        current_content = Path(target_file).read_text(encoding="utf-8")

    prompt = template.format(
        target_file=target_file,
        current_content=current_content or "# (documento vacio)",
        updates=str(updates),
    )

    output = await run_prompt(
        prompt=prompt,
        temperature=0.15,
        timeout=manifest.task.timeout_seconds,
    )

    if output.startswith("ERROR:"):
        raise ValueError(f"El modelo reporto un error: {output}")

    return output, filename
