"""
Handler: analyze_security

Genera un reporte de seguridad en JSON para un modulo Terraform.
El modelo analiza los .tf y lista findings de seguridad siguiendo
las categorias de tfsec (sin necesitar tfsec instalado).

Util cuando tfsec no esta disponible en el entorno o cuando se quiere
un analisis semantico adicional que las reglas estaticas no capturan.
"""

import json
from pathlib import Path

from agentforge.models import ExecutionManifest
from agentforge.ollama.client import run_prompt
from agentforge.config import TEMPLATES_DIR


async def handle(manifest: ExecutionManifest) -> tuple[str, str]:
    """
    Analiza la seguridad de un modulo Terraform.

    Returns:
        (json_report, "tfsec_report.json")

    Raises:
        ValueError: Si el output no es JSON valido.
    """
    template_file = TEMPLATES_DIR / "tfsec_report.txt"
    if not template_file.exists():
        raise FileNotFoundError(f"Template no encontrado: {template_file}")

    template = template_file.read_text(encoding="utf-8")

    tf_contents: dict[str, str] = {}
    for src_path in manifest.input.source_files:
        p = Path(src_path)
        if p.exists() and p.suffix == ".tf":
            tf_contents[p.name] = p.read_text(encoding="utf-8")

    all_tf = "\n\n".join(
        f"# {name}\n{content}" for name, content in tf_contents.items()
    )

    prompt = template.format(
        module_name=manifest.input.module_name or "unknown",
        tf_files_content=all_tf,
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
        raise ValueError(f"Reporte de seguridad no es JSON valido: {e}")

    return output, "tfsec_report.json"
