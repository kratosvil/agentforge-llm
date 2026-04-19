"""
Handler: generate_code

Genera codigo Python a partir de una descripcion libre en el manifest.
No requiere archivos fuente — usa input.description como prompt.

Flujo:
  1. Lee la descripcion del manifest
  2. Carga el template correspondiente al subtype
  3. Construye el prompt y envia a Ollama
  4. Retorna el codigo generado y el nombre del archivo de output
"""

from agentforge.models import ExecutionManifest
from agentforge.ollama.client import run_prompt
from agentforge.config import TEMPLATES_DIR


TEMPLATE_MAP = {
    "python_function": "python_function.txt",
}

OUTPUT_FILENAME_MAP = {
    "python_function": "output.py",
}


async def handle(manifest: ExecutionManifest) -> tuple[str, str]:
    """
    Ejecuta la tarea generate_code.

    Returns:
        (output_content, output_filename)

    Raises:
        FileNotFoundError: Si el template no existe.
        ValueError: Si falta description en el manifest o el modelo reporta error.
    """
    subtype = manifest.task.subtype

    if not manifest.input.description:
        raise ValueError(
            "generate_code requiere input.description — describe la funcion a generar."
        )

    template_file = TEMPLATES_DIR / TEMPLATE_MAP[subtype]
    if not template_file.exists():
        raise FileNotFoundError(f"Template no encontrado: {template_file}")

    template = template_file.read_text(encoding="utf-8")
    prompt = template.format(description=manifest.input.description)

    output = await run_prompt(
        prompt=prompt,
        timeout=manifest.task.timeout_seconds,
    )

    if output.startswith("ERROR:"):
        raise ValueError(f"El modelo reporto un error: {output}")

    output = _strip_markdown_fences(output)

    filename = OUTPUT_FILENAME_MAP[subtype]
    return output, filename


def _strip_markdown_fences(text: str) -> str:
    """Elimina fences de markdown que el modelo agrega aunque se le indique no hacerlo."""
    import re
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()
