"""
Cliente async para la API de Ollama.

Por que httpx y no requests:
  - El MCP Server es async (fastmcp usa anyio internamente)
  - httpx.AsyncClient no bloquea el event loop durante la inferencia
  - Una tarea esperando respuesta de Ollama no congela las demas

Temperatura 0.1 — critico para codigo. Mayor temperatura = alucinaciones
en nombres de variables, recursos AWS y bloques HCL.
"""

import httpx
from agentforge.config import OLLAMA_HOST, MODEL_NAME, LLM_TEMPERATURE, LLM_MAX_TOKENS

# System prompt base: instruye al modelo a ser estricto y no decorar el output.
# Los handlers lo combinan con instrucciones especificas por tipo de tarea.
BASE_SYSTEM_PROMPT = """You are an expert software engineer specializing in Python, \
infrastructure-as-code (Terraform, Kubernetes), SQL, and DevOps tooling.
You write clean, production-ready code and configuration on the first attempt.
You follow instructions EXACTLY and output ONLY what is requested — nothing more.
Rules:
- No markdown fences, no preambles, no trailing explanations.
- No inline comments unless the logic is genuinely non-obvious.
- If you are uncertain, output ERROR: <reason> and stop immediately.
- Produce complete, valid, runnable output every time."""


async def run_prompt(
    prompt: str,
    system: str | None = None,
    model: str = MODEL_NAME,
    temperature: float = LLM_TEMPERATURE,
    max_tokens: int = LLM_MAX_TOKENS,
    timeout: int = 300,
) -> str:
    """
    Envia un prompt a Ollama y retorna el texto generado.

    Args:
        prompt: El prompt de usuario con contexto e instrucciones.
        system: System prompt opcional. Si es None usa BASE_SYSTEM_PROMPT.
        model: Modelo Ollama a usar.
        temperature: Temperatura de sampling. 0.1 para codigo, 0.3-0.5 para texto.
        max_tokens: Limite de tokens en el output.
        timeout: Segundos antes de cancelar la peticion.

    Returns:
        El texto generado por el modelo, sin procesamiento adicional.

    Raises:
        httpx.TimeoutException: Si Ollama no responde en `timeout` segundos.
        httpx.HTTPStatusError: Si Ollama retorna un error HTTP.
        ValueError: Si la respuesta no tiene el campo 'response'.
    """
    system_prompt = system if system is not None else BASE_SYSTEM_PROMPT

    payload = {
        "model": model,
        "system": system_prompt,
        "prompt": prompt,
        "stream": False,  # Recibir respuesta completa, no streaming
        "options": {
            "temperature": temperature,
            "top_p": 0.9,
            "num_predict": max_tokens,
            "num_ctx": 4096,
            "stop": [],
        },
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{OLLAMA_HOST}/api/generate",
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    if "response" not in data:
        raise ValueError(f"Respuesta inesperada de Ollama: {data}")

    return data["response"].strip()


async def check_health() -> dict:
    """
    Verifica que Ollama esta disponible y el modelo esta cargado.

    Returns:
        {"status": "ok", "model": "...", "ollama_version": "..."}
        {"status": "error", "message": "..."}
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # Verificar que el servidor responde
            r = await client.get(f"{OLLAMA_HOST}/api/version")
            r.raise_for_status()
            version_data = r.json()

            # Verificar que el modelo esta disponible
            r2 = await client.get(f"{OLLAMA_HOST}/api/tags")
            r2.raise_for_status()
            tags = r2.json()
            models = [m["name"] for m in tags.get("models", [])]

            model_available = any(MODEL_NAME in m for m in models)

            return {
                "status": "ok" if model_available else "model_missing",
                "model": MODEL_NAME,
                "model_available": model_available,
                "available_models": models,
                "ollama_version": version_data.get("version", "unknown"),
            }
    except httpx.ConnectError:
        return {
            "status": "error",
            "message": f"No se puede conectar a Ollama en {OLLAMA_HOST}. Ejecuta: ollama serve",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
