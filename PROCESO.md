# Proceso de Desarrollo — AgentForge LLM

Documentacion del proceso de construccion, decisiones tomadas y guia de uso.

---

## Estado actual del proyecto

| Sprint | Estado | Descripcion |
|--------|--------|-------------|
| Sprint 1 | **COMPLETADO** | Sistema generico, handler universal, md_parser, validacion built-in, LLM_MAX_TOKENS 4096 |
| Sprint 1.1 | **COMPLETADO** | Upgrade codellama:13b, fix EOS, Makefile, async fire-and-forget |
| Sprint 2 | Pendiente | HTTP+SSE remoto + auth (solo necesario para multi-cliente; setup actual LAN ya funciona) |

**Modelo activo:** `codellama:13b`  
**Hardware inferencia:** RTX 2070 8GB VRAM (PC separado en LAN)  
**OLLAMA_HOST:** `http://192.168.128.4:11434`  
**MAX_PARALLEL_TASKS:** 1 (codellama:13b usa ~7.4GB VRAM — una sola instancia en RTX 2070)

---

## Estructura del proyecto

```
agentforge-llm/
├── agentforge/
│   ├── config.py          # Config central via env vars
│   ├── models.py          # Pydantic: ExecutionManifest, AuditRecord, TaskStatus
│   ├── orchestrator.py    # Nucleo: ejecuta tareas, semaforo de concurrencia
│   ├── server.py          # MCP Server (fastmcp) — 7 tools
│   ├── cli.py             # CLI click + rich
│   ├── md_parser.py       # Parser de archivos .md con frontmatter YAML
│   ├── ollama/client.py   # Cliente httpx async para Ollama API
│   ├── handlers/          # Dispatcher type+subtype → handler
│   └── utils/             # results, validator, logger, perf_monitor
├── templates/             # Prompt templates para Ollama
├── docs/
│   └── codellama13b_capability_map.md  # Benchmark completo — que delegar y que no
├── k8s/                   # Manifests Kubernetes (setup alternativo)
├── plans/                 # Planes de ejemplo
├── results/               # Output de tareas por task_id
├── tests/                 # Test manifests .md
├── Makefile               # make mcp-register, make run-server, make test-health
└── pyproject.toml
```

---

## Flujo de uso — async fire-and-forget (comportamiento actual)

A partir de Sprint 1.1, `agentforge_execute` y `agentforge_batch` retornan
**inmediatamente** con un `task_id`. La tarea corre en background. La consola
de Claude queda libre para seguir trabajando.

```
1. Claude encola tarea(s):
   agentforge_execute(manifest)
   → {"task_id": "uuid", "status": "queued"}   ← retorna en <1s

2. Claude sigue trabajando en otras cosas (la tarea corre en background en la 2070)

3. Cuando sea conveniente, Claude consulta estado:
   agentforge_status(task_id)
   → {"status": "running" | "completed" | "failed", "duration_seconds": ...}

4. Ver todo lo que termino sin revisar:
   agentforge_pending()
   → {count: N, tasks: [...]}

5. Auditar resultado:
   agentforge_audit(task_id, approve=None)   # solo leer
   agentforge_audit(task_id, approve=True)   # leer + aprobar
   agentforge_audit(task_id, approve=False)  # leer + rechazar (re-encolar con spec corregida)
```

### Encolar multiples tareas
```python
agentforge_batch([manifest1, manifest2, manifest3], max_parallel=1)
→ {"batch_id": "...", "total": 3, "status": "queued", "task_ids": [...]}
# Todas corren en background secuencialmente
```

### Ejecutar desde archivo .md
```python
agentforge_from_md("/ruta/al/requerimiento.md")
# El .md tiene frontmatter YAML con type/subtype/format
# El cuerpo es la descripcion del requerimiento
```

---

## Cuando delegar a AgentForge vs generar directamente con Claude

**Regla de corte: tareas que generen mas de ~40 lineas de codigo → delegar a AgentForge.**

Por debajo de ese umbral, el overhead del manifest + audit consume tokens similares
a la generacion directa. El ahorro real empieza en tareas medianas-complejas.

| Tipo de tarea | Delegar | Razon |
|--------------|---------|-------|
| CRUD / Repository (50+ lineas) | SI | 65-80% menos output tokens |
| Design patterns conocidos | SI | 70% ahorro, calidad equivalente |
| Scaffold multi-archivo (Terraform, K8s) | SI | 75%+ ahorro |
| Funcion simple < 30 lineas | NO | Overhead iguala el ahorro |
| Algoritmos complejos (Dijkstra, parsers) | NO | Alta tasa de bugs silenciosos |
| Codigo de seguridad / pagos | NO | Requiere razonamiento critico |
| Refactoring de codigo existente | NO | Riesgo de romper comportamiento |

Ver benchmark completo: `docs/codellama13b_capability_map.md`

---

## Timeouts recomendados por tipo de tarea

```
python_function simple:    60s
python_class medio:        90s
python_class complejo:    240s   ← BST/grafos necesitan 100-170s
bash_script:               90s
terraform_module:         150s
k8s_manifest:             120s
sql_schema:               150s
readme / documentacion:   200s
```

---

## Decisiones de diseño

### Async fire-and-forget (Sprint 1.1)
`agentforge_execute` usa `asyncio.create_task(execute_task(m))` para lanzar
la tarea en el event loop de fastmcp sin bloquear el tool call. Permite a Claude
seguir en la sesion mientras codellama:13b genera en la 2070.

### Por que fastmcp sobre SDK oficial
Genera schemas MCP automaticamente desde type hints Python. Para tools internas
reduce el codigo a la mitad. `@mcp.tool()` convierte cualquier funcion async en una tool MCP.

### Por que httpx async
El MCP Server corre en anyio. Con `requests` bloqueante cada llamada a Ollama
congela el event loop. Con `httpx.AsyncClient` las tareas esperan I/O cooperativamente.

### Semaforo asyncio para concurrencia
`asyncio.Semaphore(MAX_PARALLEL_TASKS=1)` en orchestrator garantiza que solo
una tarea corra en Ollama a la vez. Con codellama:13b (7.4GB VRAM) en RTX 2070
(8GB), no hay margen para paralelo.

### Sistema de subtype libre (Sprint 1)
No se usa un Enum fijo para subtypes — se acepta cualquier string. Si no hay
template registrado, se usa el `input.description` como prompt directo. Esto
permite delegar cualquier tipo de tarea sin tocar el codigo del servidor.

### Temperatura 0.1 para codigo
Outputs deterministas. Para codigo donde atributos y nombres deben ser exactos,
la variacion aleatoria es un bug, no una feature.

---

## Registro de bugs conocidos en codellama:13b

Bugs recurrentes que Claude debe corregir en auditoria:

| Contexto | Bug | Fix |
|----------|-----|-----|
| `aws_lambda_function` | `environment = var` | `environment { variables = var }` |
| K8s Deployment | `image: var IMAGE` (literal) | Reemplazar con imagen real |
| K8s HPA | `autoscaling/v2beta1` deprecated | Usar `autoscaling/v2` |
| SQL spec | Trata descripcion como codigo con errores | Iniciar con "GENERATE NEW ... from scratch" |
| Bash curl | `curl \| grep "HTTP/2 200"` (busca en body) | `curl -o /dev/null -s -w '%{http_code}'` |
| Python validacion | `isinstance` despues de usar el valor | Mover type check al inicio |
| Algoritmos | Dijkstra implementado como BFS sin heapq | No delegar algoritmos de optimizacion |

---

## Setup inicial (referencia)

```bash
# 1. Dependencias
cd ~/Desarrollo/agentforge-llm
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# 2. Verificar conectividad con la 2070
curl http://192.168.128.4:11434/api/tags | python3 -m json.tool

# 3. Registrar MCP en Claude Code CLI
make mcp-register

# 4. Abrir nueva sesion de Claude Code y verificar
# agentforge_health() → {"status": "ok", "model": "codellama:13b"}
```

---

## Roadmap

### Sprint 2 — HTTP+SSE remoto (pendiente, baja urgencia)
Solo necesario si se quiere conectar AgentForge desde multiples clientes
(otras maquinas, CI/CD, celular). Para el setup actual (esta PC → 2070 LAN)
el sistema stdio ya funciona correctamente.

Requiere:
- FastAPI endpoint POST /tasks (recibe manifest, retorna task_id)
- SSE endpoint GET /tasks/{id}/stream (eventos de progreso en tiempo real)
- API key en header Authorization
- Cliente MCP actualizado para HTTP en vez de stdio
