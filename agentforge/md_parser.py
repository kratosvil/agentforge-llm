"""
Parser de archivos .md de requerimientos.

Formato del archivo:
    ---
    type: generate_code
    subtype: python_class
    format: python
    timeout: 120
    module_name: auth
    layer: platform
    ---

    Descripción libre del requerimiento...
    Puede ser multilinea, incluir ejemplos, restricciones, etc.

El frontmatter YAML define los metadatos de la tarea.
El cuerpo del documento se usa como input.description.
Si el frontmatter tiene 'context_file', lee ese archivo y lo pasa como input.context.
"""

from pathlib import Path
from typing import Any


def parse_requirements_md(file_path: str) -> dict[str, Any]:
    """
    Lee un archivo .md de requerimientos y retorna un dict listo para ExecutionManifest.

    Args:
        file_path: Ruta al archivo .md.

    Returns:
        Dict compatible con ExecutionManifest.model_validate().

    Raises:
        FileNotFoundError: Si el archivo no existe.
        ValueError: Si el frontmatter es inválido o faltan campos obligatorios.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Archivo de requerimientos no encontrado: {file_path}")

    content = path.read_text(encoding="utf-8").strip()

    frontmatter, description = _split_frontmatter(content)
    meta = _parse_frontmatter(frontmatter)

    task_type = meta.get("type", "generate_code")
    subtype = meta.get("subtype", "")
    if not subtype:
        raise ValueError("El frontmatter debe incluir 'subtype'.")

    output_format = meta.get("format", "text")
    timeout = int(meta.get("timeout", 300))
    module_name = meta.get("module_name", "")
    layer = meta.get("layer", "")
    output_path = meta.get("output_path", f"./results/{{task_id}}/output")

    context = ""
    context_file = meta.get("context_file", "")
    if context_file:
        ctx_path = Path(context_file)
        if ctx_path.exists():
            context = ctx_path.read_text(encoding="utf-8")

    return {
        "task": {
            "type": task_type,
            "subtype": subtype,
            "timeout_seconds": timeout,
        },
        "input": {
            "description": description.strip(),
            "module_name": module_name,
            "layer": layer,
            "context": context,
        },
        "output": {
            "path": output_path,
            "format": output_format,
        },
    }


def _split_frontmatter(content: str) -> tuple[str, str]:
    """Separa el bloque frontmatter YAML del cuerpo del documento."""
    if not content.startswith("---"):
        return "", content

    parts = content[3:].split("---", 1)
    if len(parts) < 2:
        return "", content

    return parts[0].strip(), parts[1].strip()


def _parse_frontmatter(frontmatter: str) -> dict[str, str]:
    """Parsea el frontmatter YAML simple (key: value, sin anidamiento)."""
    if not frontmatter:
        return {}
    result = {}
    for line in frontmatter.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
    return result
