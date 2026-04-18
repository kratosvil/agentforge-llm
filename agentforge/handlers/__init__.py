"""
Dispatcher de handlers — mapea TaskType+TaskSubtype al handler correcto.

Para agregar un nuevo tipo de tarea:
  1. Crear el archivo handler en este directorio
  2. Agregar el mapeo en HANDLER_MAP
  3. Agregar el TaskSubtype en models.py
"""

from agentforge.models import TaskType, TaskSubtype
from agentforge.handlers import generate, metadata, documentation, analyze, update, extract

# Mapeo (type, subtype) -> funcion handler async
HANDLER_MAP = {
    (TaskType.GENERATE_BOILERPLATE, TaskSubtype.TERRAFORM_VARIABLES): generate.handle,
    (TaskType.GENERATE_BOILERPLATE, TaskSubtype.TERRAFORM_OUTPUTS): generate.handle,
    (TaskType.GENERATE_BOILERPLATE, TaskSubtype.TERRAFORM_VERSIONS): generate.handle,
    (TaskType.GENERATE_METADATA, TaskSubtype.MODULE_METADATA_JSON): metadata.handle,
    (TaskType.GENERATE_DOCUMENTATION, TaskSubtype.MODULE_CLAUDE_MD): documentation.handle,
    (TaskType.ANALYZE_SECURITY, TaskSubtype.TFSEC_REPORT): analyze.handle,
    (TaskType.UPDATE_DOCUMENT, TaskSubtype.ESTADO_MD): update.handle,
    (TaskType.EXTRACT_STRUCTURE, TaskSubtype.TF_RESOURCES): extract.handle,
}


def get_handler(task_type: TaskType, subtype: TaskSubtype):
    """
    Retorna la funcion handler para el tipo de tarea dado.

    Raises:
        KeyError: Si la combinacion type+subtype no tiene handler registrado.
    """
    key = (task_type, subtype)
    if key not in HANDLER_MAP:
        raise KeyError(
            f"No hay handler para ({task_type.value}, {subtype.value}). "
            f"Registrados: {[f'{t.value}/{s.value}' for t, s in HANDLER_MAP]}"
        )
    return HANDLER_MAP[key]
