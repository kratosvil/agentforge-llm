# Proceso de Desarrollo — AgentForge LLM

Documentacion del proceso de construccion del proyecto, decisiones tomadas
y guia de conexion para poner el sistema en marcha.

---

## Lo que se construyo en esta sesion

```
agentforge-llm/
├── agentforge/                  # Paquete principal Python
│   ├── __init__.py
│   ├── config.py                # Config central — leer env vars
│   ├── models.py                # Modelos Pydantic: manifest, audit, etc.
│   ├── orchestrator.py          # Nucleo: ejecuta tareas, maneja concurrencia
│   ├── server.py                # MCP Server con fastmcp (6 tools)
│   ├── cli.py                   # CLI con click + rich
│   ├── ollama/
│   │   ├── __init__.py
│   │   └── client.py            # Cliente httpx async para Ollama API
│   ├── handlers/
│   │   ├── __init__.py          # Dispatcher type+subtype -> handler
│   │   ├── generate.py          # variables.tf, outputs.tf, versions.tf
│   │   ├── metadata.py          # metadata.json
│   │   ├── documentation.py     # CLAUDE.md
│   │   ├── analyze.py           # tfsec_report.json
│   │   ├── update.py            # actualizar documentos existentes
│   │   └── extract.py           # resources.json
│   └── utils/
│       ├── __init__.py
│       ├── results.py           # Leer/escribir /results/{task_id}/
│       ├── validator.py         # Correr comandos de validacion async
│       └── logger.py            # Logger JSON estructurado
├── templates/                   # 8 prompt templates para Ollama
│   ├── terraform_variables.txt
│   ├── terraform_outputs.txt
│   ├── terraform_versions.txt
│   ├── module_metadata.txt
│   ├── module_claude_md.txt
│   ├── tfsec_report.txt
│   ├── estado_update.txt
│   └── tf_resources.txt
├── k8s/                         # Manifests Kubernetes
│   ├── namespace.yaml
│   ├── ollama-deployment.yaml
│   ├── ollama-service.yaml
│   ├── agentforge-deployment.yaml
│   └── Dockerfile
├── plans/
│   └── build-networking-module.json  # Plan de ejemplo
├── results/                     # Output de tareas (vacio, se llena al ejecutar)
├── manifests/                   # Manifests ejecutados
├── audit/                       # Logs JSON del sistema
├── pyproject.toml               # Dependencias Python
├── .env.example                 # Variables de entorno a configurar
└── mcp-config-snippet.json      # Snippet para claude_desktop_config.json
```

---

## Decisiones de diseno

### Por que fastmcp sobre el SDK oficial
`fastmcp` construye sobre el SDK oficial de Anthropic. Genera los schemas MCP
automaticamente desde type hints Python. Para este caso de uso (tools internas,
no publicadas en ningun registry), reduce el codigo a la mitad sin perder funcionalidad.

### Por que httpx async sobre requests
El MCP Server usa anyio (a traves de fastmcp). Si se usara `requests` bloqueante,
cada llamada a Ollama congela el event loop completo y ninguna otra tool puede
responder mientras la inferencia corre. Con `httpx.AsyncClient` las tareas
esperan I/O sin bloquear.

### Concurrencia con asyncio.Semaphore
El hardware tiene 15.5GB RAM. Cada instancia de qwen2.5-coder:7b usa ~6.5GB.
2 instancias = 13GB — dentro del limite con margen para el OS.
El semaforo en `orchestrator.py` garantiza que nunca corran mas de 2 tareas
a la vez, independientemente de cuantos manifests lleguen en un batch.

### Temperatura 0.1 para codigo
Temperatura alta = sampling mas aleatorio = mas variacion en el output.
Para codigo Terraform donde los nombres de recursos y atributos deben ser
exactos, temperatura 0.1 da outputs deterministas y correctos.
Temperatura 0.2 para documentacion (prosa tecnica) donde algo de variacion es aceptable.

### Validacion automatica por tipo de output
- HCL → `terraform validate` (detecta sintaxis invalida y referencias rotas)
- JSON → `json.loads()` en el handler (sin comando externo)
- Markdown → sin validacion (no hay linter de markdown util aqui)

---

## Lo que falta para que funcione (tu parte)

### Paso 1: Instalar Ollama y el modelo

```bash
# Instalar Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull del modelo (~4.7GB de descarga)
ollama pull qwen2.5-coder:7b

# Verificar que responde
ollama run qwen2.5-coder:7b "responde solo: OK"
```

### Paso 2: Benchmark de rendimiento

```bash
# Medir cuanto tarda una tarea real en tu CPU
time ollama run qwen2.5-coder:7b \
  "Generate a Terraform variables.tf for a VPC module with project_name and vpc_cidr variables. Output only HCL code."
```

**Criterio de aceptacion:**
- < 5 min → perfecto, el sistema funciona como disenado
- 5-10 min → aceptable, considera reducir MAX_PARALLEL_TASKS=1
- > 10 min → cambiar MODEL_NAME a `phi3.5:mini` en .env

### Paso 3: Instalar dependencias Python

```bash
cd ~/Desarrollo/agentforge-llm
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Paso 4: Configurar variables de entorno

```bash
cp .env.example .env
# Editar .env si necesitas cambiar algo (paths, modelo, concurrencia)
```

### Paso 5: Verificar que todo funciona

```bash
source .venv/bin/activate

# Verificar Ollama
agentforge health

# Deberia mostrar:
# Ollama OK — version X.X.X
# Modelo qwen2.5-coder:7b disponible: SI
```

### Paso 6: Conectar el MCP Server a Claude Desktop

```bash
# Ver el config actual
cat ~/.config/Claude/claude_desktop_config.json

# Agregar el bloque agentforge del archivo mcp-config-snippet.json
# IMPORTANTE: leer el archivo primero para no sobreescribir lo existente
```

---

## Como usar el sistema (flujo completo)

### Opcion A: Via MCP desde Claude Code

Una vez conectado el MCP Server, Claude puede:

```
# 1. Verificar que el agente esta listo
agentforge_health()

# 2. Ejecutar una tarea
agentforge_execute({
  "task": {"type": "generate_boilerplate", "subtype": "terraform_variables"},
  "input": {
    "source_files": ["/ruta/al/modulo/main.tf"],
    "module_name": "networking",
    "layer": "platform"
  },
  "output": {"path": "./results/{task_id}/variables.tf", "format": "hcl"},
  "validation": {"command": "terraform validate", "working_dir": "./results/{task_id}/output/"}
})
# Retorna: {task_id, status, duration_seconds, output_path}

# 3. Revisar el resultado
agentforge_audit(task_id="<uuid>")

# 4. Aprobar
agentforge_audit(task_id="<uuid>", approve=True)
```

### Opcion B: Via CLI desde terminal

```bash
source .venv/bin/activate

# Ver que hay pendiente
agentforge pending

# Revisar una tarea
agentforge audit <task_id>

# Aprobar
agentforge approve <task_id>

# Ejecutar un plan completo
agentforge run --plan plans/build-networking-module.json
```

---

## Parametros configurables (.env)

| Variable | Default | Cuando cambiar |
|----------|---------|----------------|
| `OLLAMA_HOST` | `http://localhost:11434` | Si Ollama corre en otro host (v2 multi-host) |
| `MODEL_NAME` | `qwen2.5-coder:7b` | Si el benchmark dice que es demasiado lento |
| `MAX_PARALLEL_TASKS` | `2` | Reducir a 1 si hay swap o lentitud extrema |
| `TASK_TIMEOUT_SECONDS` | `300` | Aumentar si las tareas hacen timeout antes de terminar |
| `LLM_TEMPERATURE` | `0.1` | No cambiar para codigo; 0.3 para experimentar con texto |

---

## Como agregar un nuevo tipo de tarea

El sistema esta disenado para extenderse sin tocar el runtime. Solo 3 pasos:

### Paso 1 — Agregar el subtype en `agentforge/models.py`

```python
class TaskSubtype(str, Enum):
    # ... existentes ...
    DOCKER_COMPOSE = "docker_compose"       # nuevo
    GITHUB_ACTIONS = "github_actions"       # nuevo
```

Y registrar la combinacion valida type+subtype:

```python
valid_combos = {
    # ... existentes ...
    TaskType.GENERATE_BOILERPLATE: [
        TaskSubtype.TERRAFORM_VARIABLES,
        TaskSubtype.DOCKER_COMPOSE,         # agregar aqui
    ],
}
```

### Paso 2 — Crear el template en `templates/`

Crear `templates/docker_compose.txt` con 3 secciones:

```
CONTEXT:
<describe el rol del modelo y el contexto del requerimiento>

INPUT:
<variables que el handler va a inyectar via .format()>

INSTRUCTION:
<instrucciones exactas — que generar, reglas, que NO hacer>

OUTPUT FORMAT:
<formato exacto del output — YAML/JSON/HCL/Markdown, sin fences, etc.>
```

La clave: ser especifico en INSTRUCTION. Cuanto mas preciso, mejor el output.

### Paso 3 — Registrar en `agentforge/handlers/__init__.py`

```python
HANDLER_MAP = {
    # ... existentes ...
    (TaskType.GENERATE_BOILERPLATE, TaskSubtype.DOCKER_COMPOSE): generate.handle,
}
```

Si la logica es muy distinta a los handlers existentes, crear `handlers/docker.py`
con su propia funcion `handle(manifest)` siguiendo el mismo patron.

### Eso es todo

El MCP Server, orquestador, CLI y sistema de auditoria lo recogen automaticamente.
Claude puede invocar el nuevo tipo con `agentforge_execute` sin ningun cambio adicional.

---

## Roadmap v2: multi-host LAN

El sistema ya esta preparado para v2. Solo requiere:
1. Instalar Ollama en el nodo Windows con CUDA
2. Cambiar `OLLAMA_HOST` al IP del nodo Windows en la LAN
3. Agregar autenticacion: API key en header `Authorization` (ver Ollama docs)

El codigo no necesita modificaciones — `OLLAMA_HOST` ya es configurable via env var.
