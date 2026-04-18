"""
Handler: generate_documentation

Genera el CLAUDE.md de un modulo Terraform.
CLAUDE.md es el archivo de contexto que Claude lee al inicio de cada sesion
para entender el modulo sin releer todos los .tf.
"""

from pathlib import Path

from agentforge.models import ExecutionManifest
from agentforge.ollama.client import run_prompt
from agentforge.config import TEMPLATES_DIR


async def handle(manifest: ExecutionManifest) -> tuple[str, str]:
    """
    Genera CLAUDE.md a partir de los archivos del modulo.

    Returns:
        (markdown_content, "CLAUDE.md")
    """
    template_file = TEMPLATES_DIR / "module_claude_md.txt"
    if not template_file.exists():
        raise FileNotFoundError(f"Template no encontrado: {template_file}")

    template = template_file.read_text(encoding="utf-8")

    # Leer todos los archivos relevantes del modulo
    file_contents: dict[str, str] = {}
    for src_path in manifest.input.source_files:
        p = Path(src_path)
        if p.exists():
            file_contents[p.name] = p.read_text(encoding="utf-8")

    prompt = template.format(
        module_name=manifest.input.module_name or "unknown",
        layer=manifest.input.layer or "product",
        main_tf_content=file_contents.get("main.tf", ""),
        variables_tf_content=file_contents.get("variables.tf", ""),
        outputs_tf_content=file_contents.get("outputs.tf", ""),
        metadata_json_content=file_contents.get("metadata.json", "{}"),
    )

    output = await run_prompt(
        prompt=prompt,
        temperature=0.2,  # Ligeramente mas alto para prosa tecnica
        timeout=manifest.task.timeout_seconds,
    )

    if output.startswith("ERROR:"):
        raise ValueError(f"El modelo reporto un error: {output}")

    return output, "CLAUDE.md"
