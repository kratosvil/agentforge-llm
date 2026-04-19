"""
Configuracion central del proyecto.
Lee variables de entorno con fallback a valores por defecto.
Todas las partes del sistema importan desde aqui — un solo lugar para cambiar config.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --- Rutas base ---
BASE_DIR = Path(__file__).parent.parent
RESULTS_DIR = Path(os.getenv("RESULTS_DIR", BASE_DIR / "results"))
MANIFESTS_DIR = Path(os.getenv("MANIFESTS_DIR", BASE_DIR / "manifests"))
AUDIT_DIR = Path(os.getenv("AUDIT_DIR", BASE_DIR / "audit"))
TEMPLATES_DIR = Path(os.getenv("TEMPLATES_DIR", BASE_DIR / "templates"))

# --- Ollama ---
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
MODEL_NAME = os.getenv("MODEL_NAME", "qwen2.5-coder:7b")

# --- Comportamiento del agente ---
# Maximo 2 tareas en paralelo: qwen2.5-coder:7b usa ~6.5GB RAM c/u
# 2 instancias = 13GB — dentro del limite de 15.5GB del hardware
MAX_PARALLEL_TASKS = int(os.getenv("MAX_PARALLEL_TASKS", "2"))

# Timeout por tarea: 300s = 5 min (criterio de aceptacion del plan)
TASK_TIMEOUT_SECONDS = int(os.getenv("TASK_TIMEOUT_SECONDS", "300"))

# Temperatura baja = output determinístico (critico para codigo)
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))


def ensure_dirs() -> None:
    """Crea los directorios de trabajo si no existen."""
    for d in [RESULTS_DIR, MANIFESTS_DIR, AUDIT_DIR]:
        d.mkdir(parents=True, exist_ok=True)
