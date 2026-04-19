"""
Handler: generate_boilerplate

Genera archivos de boilerplate Terraform (variables.tf, outputs.tf, versions.tf)
a partir de un main.tf fuente.

Flujo:
  1. Lee los archivos fuente declarados en el manifest
  2. Carga el template correspondiente al subtype
  3. Construye el prompt con el contexto del modulo
  4. Envia a Ollama y obtiene HCL
  5. Retorna el HCL para que el orquestador lo persista y valide
"""

from pathlib import Path

from agentforge.models import ExecutionManifest
from agentforge.ollama.client import run_prompt
from agentforge.config import TEMPLATES_DIR


TEMPLATE_MAP = {
    "terraform_variables": "terraform_variables.txt",
    "terraform_outputs": "terraform_outputs.txt",
    "terraform_versions": "terraform_versions.txt",
}

OUTPUT_FILENAME_MAP = {
    "terraform_variables": "variables.tf",
    "terraform_outputs": "outputs.tf",
    "terraform_versions": "versions.tf",
}


async def handle(manifest: ExecutionManifest) -> tuple[str, str]:
    """
    Ejecuta la tarea generate_boilerplate.

    Returns:
        (output_content, output_filename) — el HCL generado y el nombre del archivo.

    Raises:
        FileNotFoundError: Si el template o un archivo fuente no existe.
        ValueError: Si el modelo genera un output que empieza con 'ERROR:'.
    """
    subtype = manifest.task.subtype
    template_file = TEMPLATES_DIR / TEMPLATE_MAP[subtype]

    if not template_file.exists():
        raise FileNotFoundError(f"Template no encontrado: {template_file}")

    template = template_file.read_text(encoding="utf-8")

    # Leer contenido de los archivos fuente
    source_contents = {}
    for src_path in manifest.input.source_files:
        p = Path(src_path)
        if p.exists():
            source_contents[p.name] = p.read_text(encoding="utf-8")

    # Construir el prompt reemplazando los placeholders del template
    prompt = template.format(
        module_name=manifest.input.module_name or "unknown",
        layer=manifest.input.layer or "product",
        source_file_content=source_contents.get("main.tf", "# No main.tf provided"),
        **{k: v for k, v in source_contents.items()},
        **manifest.input.additional_context,
    )

    output = await run_prompt(
        prompt=prompt,
        timeout=manifest.task.timeout_seconds,
    )

    if output.startswith("ERROR:"):
        raise ValueError(f"El modelo reporto un error: {output}")

    filename = OUTPUT_FILENAME_MAP[subtype]
    return output, filename
