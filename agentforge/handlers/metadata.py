"""
Handler: generate_metadata

Genera metadata.json para un modulo Terraform.
El metadata.json es el contrato de un modulo: inputs, outputs, dependencias,
hints para LLMs. Se usa en tf-modules-forge para que Claude entienda cada
modulo sin leer todos los .tf.
"""

import json
from pathlib import Path

from agentforge.models import ExecutionManifest
from agentforge.ollama.client import run_prompt
from agentforge.config import TEMPLATES_DIR


async def handle(manifest: ExecutionManifest) -> tuple[str, str]:
    """
    Genera metadata.json a partir de los archivos .tf de un modulo.

    Returns:
        (json_content, "metadata.json")

    Raises:
        ValueError: Si el output del modelo no es JSON valido.
    """
    template_file = TEMPLATES_DIR / "module_metadata.txt"
    if not template_file.exists():
        raise FileNotFoundError(f"Template no encontrado: {template_file}")

    template = template_file.read_text(encoding="utf-8")

    # Leer todos los archivos .tf del modulo
    tf_files: dict[str, str] = {}
    for src_path in manifest.input.source_files:
        p = Path(src_path)
        if p.exists() and p.suffix == ".tf":
            tf_files[p.name] = p.read_text(encoding="utf-8")

    prompt = template.format(
        module_name=manifest.input.module_name or "unknown",
        layer=manifest.input.layer or "product",
        version=manifest.input.additional_context.get("version", "1.0.0"),
        main_tf_content=tf_files.get("main.tf", ""),
        variables_tf_content=tf_files.get("variables.tf", ""),
        outputs_tf_content=tf_files.get("outputs.tf", ""),
    )

    output = await run_prompt(
        prompt=prompt,
        timeout=manifest.task.timeout_seconds,
    )

    if output.startswith("ERROR:"):
        raise ValueError(f"El modelo reporto un error: {output}")

    # Verificar que el output es JSON valido antes de retornarlo
    try:
        json.loads(output)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"El modelo genero JSON invalido: {e}\n\nOutput recibido:\n{output[:500]}"
        )

    return output, "metadata.json"
