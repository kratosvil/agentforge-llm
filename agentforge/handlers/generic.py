"""
Handler genérico — acepta cualquier type+subtype.

Lógica de resolución:
  1. Si existe templates/{subtype}.txt → carga el template e inyecta variables
  2. Si no existe template → usa input.description directamente como prompt
  3. Si hay input.context → lo antepone al prompt para encadenar generaciones

El output_filename se deriva de manifest.output.format.
"""

import re

from agentforge.config import TEMPLATES_DIR
from agentforge.models import ExecutionManifest
from agentforge.ollama.client import run_prompt


_FORMAT_EXT = {
    "python": ".py",
    "hcl": ".tf",
    "json": ".json",
    "yaml": ".yaml",
    "markdown": ".md",
    "bash": ".sh",
    "sql": ".sql",
    "text": ".txt",
}


async def handle(manifest: ExecutionManifest) -> tuple[str, str]:
    """
    Ejecuta cualquier tarea usando template dinámico o descripción libre.

    Returns:
        (output_content, output_filename)

    Raises:
        ValueError: Si no hay template ni description.
    """
    subtype = manifest.task.subtype
    description = manifest.input.description
    context = manifest.input.context

    template_file = TEMPLATES_DIR / f"{subtype}.txt"

    if template_file.exists():
        template = template_file.read_text(encoding="utf-8")
        try:
            prompt = template.format(
                description=description,
                context=context or "",
                module_name=manifest.input.module_name,
                layer=manifest.input.layer,
            )
        except KeyError:
            # Template con variables no estándar — pasar sin format()
            prompt = template
        if context:
            prompt = f"Prior context / previous output:\n{context}\n\n{prompt}"
    else:
        if not description:
            raise ValueError(
                f"No existe template para subtype '{subtype}' "
                f"y input.description está vacío. Provee al menos uno de los dos."
            )
        prompt = description
        if context:
            prompt = f"Prior context / previous output:\n{context}\n\n{description}"

    output = await run_prompt(
        prompt=prompt,
        timeout=manifest.task.timeout_seconds,
    )

    if output.startswith("ERROR:"):
        raise ValueError(f"El modelo reportó un error: {output}")

    output = _strip_markdown_fences(output)

    ext = _FORMAT_EXT.get(manifest.output.format, ".txt")
    filename = f"output{ext}"

    return output, filename


def _strip_markdown_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()
