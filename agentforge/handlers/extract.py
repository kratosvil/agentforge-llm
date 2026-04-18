"""
Handler: extract_structure

Extrae la estructura de recursos de un modulo Terraform en JSON.
Util para que Claude entienda rapidamente que recursos crea un modulo
sin leer todo el HCL.
"""

import json
from pathlib import Path

from agentforge.models import ExecutionManifest
from agentforge.ollama.client import run_prompt
from agentforge.config import TEMPLATES_DIR


async def handle(manifest: ExecutionManifest) -> tuple[str, str]:
    """
    Extrae recursos, data sources y locals de archivos .tf.

    Returns:
        (json_structure, "resources.json")
    """
    template_file = TEMPLATES_DIR / "tf_resources.txt"
    if not template_file.exists():
        raise FileNotFoundError(f"Template no encontrado: {template_file}")

    template = template_file.read_text(encoding="utf-8")

    tf_contents: list[str] = []
    for src_path in manifest.input.source_files:
        p = Path(src_path)
        if p.exists():
            tf_contents.append(f"# {p.name}\n{p.read_text(encoding='utf-8')}")

    prompt = template.format(
        module_name=manifest.input.module_name or "unknown",
        tf_files_content="\n\n".join(tf_contents),
    )

    output = await run_prompt(
        prompt=prompt,
        timeout=manifest.task.timeout_seconds,
    )

    if output.startswith("ERROR:"):
        raise ValueError(f"El modelo reporto un error: {output}")

    try:
        json.loads(output)
    except json.JSONDecodeError as e:
        raise ValueError(f"Estructura extraida no es JSON valido: {e}")

    return output, "resources.json"
