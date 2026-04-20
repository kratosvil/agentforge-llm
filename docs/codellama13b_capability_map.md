# codellama:13b — Mapa de Capacidades para AgentForge

**Modelo:** codellama:13b  
**Hardware:** RTX 2070 8GB VRAM (PC separado, OLLAMA_HOST en LAN)  
**Fecha benchmark:** 2026-04-20  
**Total tareas ejecutadas:** 12 (Python x7, Terraform, Bash, K8s YAML, SQL, Markdown)

---

## Resumen ejecutivo

codellama:13b es sólido para scaffold y boilerplate. Domina CRUD, design patterns
y estructura de archivos de infraestructura. Falla en algoritmos con lógica sutil
(Dijkstra, parsers, BST delete) produciendo bugs silenciosos. Siempre requiere
revisión antes de ejecutar en producción.

---

## Regla de corte — cuando vale la pena delegar

**Umbral: tareas que generen más de ~40 líneas → delegar a AgentForge.**

Por debajo de ese umbral, el overhead del manifest + audit consume tokens similares
a la generación directa con Claude. El ahorro real empieza en tareas medianas.

### Análisis de costo (Claude Sonnet 4.6: $3/MTok input, $15/MTok output)

| Tarea | Claude directo | Via AgentForge | Ahorro |
|-------|---------------|----------------|--------|
| Función simple <30 líneas | ~$0.014 | ~$0.014 | ~0% |
| Clase media 50 líneas | ~$0.024 | ~$0.014 | ~40% |
| Clase compleja 150 líneas | ~$0.048 | ~$0.017 | ~65% |
| Sesión completa (10 módulos) | ~$0.225 | ~$0.052 | ~77% |

**El beneficio mayor no es el costo — es la ventana de contexto.**
Cuando Claude genera 150 líneas, esas ~3000 tokens de output saturan el contexto
y comprimen decisiones arquitecturales anteriores. Con AgentForge, la generación
ocurre fuera del contexto de Claude: la ventana queda limpia para razonamiento
de alto nivel.

---

## Tiempos de referencia

| Tipo de tarea | Tiempo típico | Timeout recomendado |
|--------------|---------------|---------------------|
| python_function simple | 25-40s | 60s |
| python_class medio (3-6 métodos) | 35-65s | 90s |
| python_class complejo (BST, grafos) | 100-170s | 240s |
| terraform_module | 50s | 120s |
| bash_script | 25-35s | 90s |
| k8s_manifest (3 resources) | 48s | 120s |
| sql_schema + query | 50-55s | 150s |
| readme / documentación | 100s | 200s |

> **Importante:** el modelo NO produce output parcial si hay timeout. Si la tarea
> falla por timeout, no hay nada recuperable — re-encolar con timeout más alto.

---

## Mapa de delegación

### DELEGAR CON CONFIANZA (revisión rápida suficiente)

- **CRUD / Repository classes** — sigue instrucciones exactas, 10 métodos sin problemas
- **Design patterns** — Observer, Factory, Singleton, Strategy: código limpio e idiomático
- **Data model / config classes** — sin lógica de negocio compleja
- **Tests unitarios** — los genera espontáneamente cuando reconoce el contexto
- **SQL DDL** — CREATE TABLE, FK constraints, indexes: sintaxis correcta
- **Terraform scaffold** — IAM roles, recursos AWS básicos, variables.tf, outputs.tf
- **Kubernetes YAML** — Deployment, Service, HPA: estructura correcta
- **README / documentación** — todas las secciones, tablas, code blocks

### DELEGAR CON REVISIÓN CRÍTICA (verificar lógica antes de usar)

- **Async/asyncio** — estructura OK, detalles de API fallan (nombres de excepciones, retornos)
- **Bash scripts** — dar spec exacta de comandos; sin guidance usa curl incorrectamente
- **SQL queries complejas** — LEFT JOIN + WHERE = INNER JOIN efectivo sin advertencia
- **Terraform bloques anidados** — `environment { variables = var }` vs `environment = var`
- **Kubernetes** — API versions deprecadas, placeholders literales inválidos
- **BST / árboles** — insert/search/inorder correctos; `delete` con dos hijos produce bugs

### NO DELEGAR (bugs silenciosos frecuentes)

- **Algoritmos de optimización** — Dijkstra implementado como BFS sin heapq
- **Parsers / tokenizers** — cambia approach sin avisar (implementó notación prefija sin decirlo)
- **Validación crítica** — bugs en email uniqueness, orden de type guards
- **Código de seguridad / pagos** — no apto para lógica crítica
- **Refactoring de código existente** — no probado, riesgo alto

---

## Comportamientos especiales a conocer

### SQL: trata descripciones como código existente
En primer intento puede rechazar generando, reportando "errores en el código".
Interpreta la descripción como SQL ya escrito con problemas.  
**Solución:** iniciar con "GENERATE NEW ... from scratch" o "Create these tables:"

### Bash: curl incorrecto sin guidance
Sin spec específica usa `curl | grep "HTTP/2 200"` (busca en body, nunca matchea).  
**Solución:** especificar `curl -o /dev/null -s -w '%{http_code}'`

### Terraform: environment block
Siempre escribe `environment = var.env_vars` en `aws_lambda_function`.  
**Fix:** cambiar a `environment { variables = var.env_vars }`

### Kubernetes: image placeholder literal
Escribe `image: var IMAGE` literalmente. No es Helm ni Kustomize — es inválido.  
**Fix:** reemplazar con imagen real o `image: "REPLACE_ME"`

### Markdown: genera headers con `===` en vez de `#`
Técnicamente válido pero rompe algunos renderers.  
**Fix:** buscar/reemplazar en post-proceso si necesitas `#` headers.

---

## Tabla de subtypes probados

| subtype | Funciona | Notas |
|---------|----------|-------|
| `python_function` | Sí | Rápido, confiable |
| `python_class` | Sí | Revisar lógica compleja |
| `python_unittest` | Sí | Genera espontáneamente |
| `bash_script` | Sí | Dar spec de comandos exactos |
| `terraform_module` | Sí | Revisar bloques anidados |
| `k8s_manifest` | Sí | Revisar API versions y placeholders |
| `sql_schema` | Sí | Iniciar spec con "GENERATE NEW" |
| `readme` | Sí | Timeout 200s mínimo |

---

## Timeouts en código

```python
TIMEOUTS = {
    "python_function":      60,
    "python_class":         90,   # simple-medio
    "python_class_complex": 240,  # algoritmos, >6 métodos con lógica
    "bash_script":          90,
    "terraform_module":     150,
    "k8s_manifest":         120,
    "sql_schema":           150,
    "readme":               200,
    "python_unittest":      60,
}
```

---

## Flujo de delegación recomendado

```
# Encolar (no bloquea)
agentforge_execute(manifest)  →  {task_id, status: "queued"}  <1s

# Seguir trabajando...

# Consultar cuando sea conveniente
agentforge_status(task_id)    →  {status: "running"|"completed"|"failed"}
agentforge_pending()          →  {count: N, tasks: [...]}

# Auditar
agentforge_audit(task_id, approve=None)   # leer
agentforge_audit(task_id, approve=True)   # aprobar y marcar revisado
agentforge_audit(task_id, approve=False)  # rechazar → re-encolar con spec corregida
```
