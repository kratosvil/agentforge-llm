"""
Dispatcher de handlers.

Resolución en dos pasos:
  1. Si (type, subtype) tiene handler específico registrado → lo usa (backward compat)
  2. Si no → usa el handler genérico, que resuelve via template o description libre

Para agregar un tipo completamente nuevo solo hay que crear templates/{subtype}.txt.
No se necesita modificar este archivo ni models.py.
"""

from agentforge.handlers import generate, metadata, documentation, analyze, update, extract, generate_code
from agentforge.handlers import generic

# Handlers específicos para tipos legacy con lógica propia
_SPECIFIC_HANDLERS = {
    ("generate_boilerplate", "terraform_variables"): generate.handle,
    ("generate_boilerplate", "terraform_outputs"): generate.handle,
    ("generate_boilerplate", "terraform_versions"): generate.handle,
    ("generate_metadata", "module_metadata_json"): metadata.handle,
    ("generate_documentation", "module_claude_md"): documentation.handle,
    ("analyze_security", "tfsec_report"): analyze.handle,
    ("update_document", "estado_md"): update.handle,
    ("extract_structure", "tf_resources"): extract.handle,
    ("generate_code", "python_function"): generate_code.handle,
}


def get_handler(task_type: str, subtype: str):
    """
    Retorna el handler para el tipo de tarea.

    Primero busca en handlers específicos registrados.
    Si no encuentra, retorna el handler genérico.
    """
    return _SPECIFIC_HANDLERS.get((task_type, subtype), generic.handle)
