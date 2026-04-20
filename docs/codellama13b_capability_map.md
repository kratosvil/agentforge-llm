# codellama:13b — Mapa de Capacidades para AgentForge

**Modelo:** codellama:13b  
**Hardware:** RTX 2070 8GB VRAM (PC separado, OLLAMA_HOST en LAN)  
**Benchmark round 1+2:** 2026-04-20 — 22 tareas  
**Benchmark 10 ciclos:** 2026-04-20 — 100 tareas (10 ciclos × 10 subtypes)  

---

## Resumen ejecutivo

codellama:13b es sólido para scaffold y boilerplate bajo carga baja. Con carga
sostenida (muchas tareas consecutivas) el tiempo de inferencia se multiplica x10-15
y la tasa de fallos sube. Los timeouts deben calibrarse según el escenario de uso:
modo frío/cálido (pocas tareas) vs modo batch (muchas tareas seguidas).

---

## Pass rates — datos estadísticos (10 ciclos, 100 tareas)

| Subtype | Pass rate | Muestra | Observaciones |
|---------|-----------|---------|---------------|
| bash_script | **100%** | 10/10 | Más robusto de todos |
| k8s_manifest | **100%** | 10/10 | Consistente, solo revisar API versions |
| python_class_complex | 90% | 9/10 | Mejor de lo esperado |
| python_class_medium | 80% | 8/10 | Confiable |
| python_function | 85% | 17/20 | Rápido en frío, lento en batch |
| python_unittest | 70% | 7/10 | Fallos por timeout en batch |
| terraform_module | 70% | 7/10 | Bugs estructurales + timeouts |
| sql_schema | **40%** | 4/10 | Muy sensible a carga acumulada |
| python_class_simple | **30%** | 3/10 | Sorprendente — timeout en batch |

**Global: 75/100 (75%)** — en carga sostenida. En frío (rounds 1+2): ~80-85%.

---

## Regla crítica: modo frío vs modo batch

**Este es el hallazgo más importante del benchmark de 10 ciclos.**

| Escenario | Tiempo típico | Factor |
|-----------|--------------|--------|
| Modelo frío (primera tarea del día) | 15-500s | 1x |
| Modelo cálido (2-5 tareas recientes) | 30-500s | 1-2x |
| **Batch sostenido (50+ tareas seguidas)** | **500-3700s** | **10-15x** |

**Conclusión:** con carga acumulada el modelo no libera recursos completamente
entre inferencias. La RTX 2070 acumula trabajo y el tiempo escala linealmente
con la posición en la cola.

**Recomendación:** en batch largo, intercalar pausas de 30-60s entre bloques
de 10 tareas, o aceptar que los timeouts en modo batch son 10x los normales.

---

## Timeouts recomendados

### Modo frío/cálido (pocas tareas, uso normal diario)

```python
TIMEOUTS_COLD = {
    "python_function":      60,
    "python_class":         90,    # simple/medio
    "python_class_complex": 240,   # algoritmos, >6 métodos
    "bash_script":          90,
    "terraform_module":     150,
    "k8s_manifest":         120,
    "sql_schema":           150,
    "readme":               200,
    "python_unittest":      60,
}
```

### Modo batch sostenido (10+ tareas seguidas)

```python
TIMEOUTS_BATCH = {
    "python_function":      1800,   # 30 min
    "python_class":         2000,   # ~33 min
    "python_class_complex": 4000,   # ~67 min
    "bash_script":          2500,   # ~42 min
    "terraform_module":     4000,   # ~67 min
    "k8s_manifest":         4000,   # ~67 min
    "sql_schema":           2500,   # ~42 min
    "python_unittest":      4000,   # ~67 min
}
```

> **Nota:** el modelo NO produce output parcial si hay timeout. Si falla por
> timeout, no hay nada recuperable — re-encolar con timeout más alto.

---

## Tiempos de referencia por modo

### Modo frío (benchmark round 1+2, 22 tareas)

| Tipo | Tiempo típico |
|------|---------------|
| python_function simple | 16-36s |
| python_class medio | 37-90s |
| python_class complejo (BST) | 203s |
| python_unittest | 238s |
| bash_script | 251s |
| terraform_module | 302s |
| k8s_manifest | 339s |
| sql_schema | 391s |
| readme | 499s |

### Modo batch (benchmark 10 ciclos, 100 tareas — promedio por subtype)

| Tipo | AVG | MIN | MAX |
|------|-----|-----|-----|
| python_function | 1633s | 24s | 3504s |
| python_class_simple | 907s | 74s | 1896s |
| python_class_medium | 1712s | 92s | 3095s |
| python_class_complex | 1795s | 120s | 3622s |
| python_unittest | 1949s | 170s | 3654s |
| bash_script | 1889s | 180s | 3684s |
| terraform_module | 2130s | 542s | 3739s |
| k8s_manifest | 1965s | 215s | 3762s |
| sql_schema | 1295s | 612s | 2226s |

---

## Regla de corte — cuando vale la pena delegar

**Umbral: tareas que generen más de ~40 líneas → delegar a AgentForge.**

### Análisis de costo (Claude Sonnet 4.6: $3/MTok input, $15/MTok output)

| Tarea | Claude directo | Via AgentForge | Ahorro |
|-------|---------------|----------------|--------|
| Función simple <30 líneas | ~$0.014 | ~$0.014 | ~0% |
| Clase media 50 líneas | ~$0.024 | ~$0.014 | ~40% |
| Clase compleja 150 líneas | ~$0.048 | ~$0.017 | ~65% |
| Sesión completa (10 módulos) | ~$0.225 | ~$0.052 | ~77% |

**El beneficio mayor no es el costo — es la ventana de contexto.**
Cuando Claude genera 150 líneas, esas ~3000 tokens de output saturan el contexto.
Con AgentForge, la generación ocurre fuera del contexto de Claude.

---

## Mapa de delegación

### DELEGAR CON CONFIANZA (100% pass rate en 10 ciclos)

- **bash_script** — 10/10. Dar spec exacta de comandos. Muy robusto.
- **k8s_manifest** — 10/10. Solo revisar API versions deprecadas.
- **CRUD / Repository classes** — sigue instrucciones exactas
- **Design patterns** — Observer, Factory, Strategy: código limpio
- **SQL DDL** — CREATE TABLE, FK, indexes: sintaxis correcta
- **Terraform scaffold** — IAM, Lambda, recursos AWS básicos

### DELEGAR CON REVISIÓN CRÍTICA

- **python_class_complex** — 90%. Revisar lógica de algoritmos.
- **python_class_medium** — 80%. Revisar async/threading.
- **terraform_module** — 70%. Revisar bloques `environment`, lifecycle.
- **python_unittest** — 70%. Verificar valores esperados en assertions.

### DELEGAR SOLO EN FRÍO (malo en batch)

- **sql_schema** — 40% en batch, ~100% en frío. Usar "GENERATE NEW ... from scratch".
- **python_class_simple** — 30% en batch (timeouts). En frío es confiable.

### NO DELEGAR

- **Algoritmos de optimización** — Dijkstra → BFS sin heapq
- **Parsers / tokenizers** — cambia approach sin avisar
- **Validación crítica** — seguridad, pagos
- **README / documentación** — 0% usable. Alucina completamente.
- **Refactoring de código existente** — no probado, riesgo alto

---

## Bugs recurrentes (corregir en auditoría)

| Contexto | Bug | Fix |
|----------|-----|-----|
| Terraform Lambda | `environment = var` | `environment { variables = var }` |
| K8s HPA | `autoscaling/v2beta1` | `autoscaling/v2` |
| K8s Deployment | `image: var IMAGE` literal | imagen real o REPLACE_ME |
| SQL spec | trata descripción como código con errores | "GENERATE NEW ... from scratch" |
| Bash curl | `curl \| grep "HTTP/2 200"` | `curl -o /dev/null -s -w '%{http_code}'` |
| BST delete (2 hijos) | sucesor no se desconecta del subárbol | verificar delete manualmente |
| Dijkstra | implementa BFS sin heapq | siempre verificar algoritmos de grafos |
| python_unittest | errores en valores esperados (ej: count_vowels) | revisar assertions numéricas |
| Terraform narrativo | envuelve código en texto explicativo | stripear en post-proceso |

---

## Comportamientos especiales

### SQL: trata descripciones como código existente
**Solución:** iniciar con "GENERATE NEW ... from scratch" o "Create these tables:"

### Bash: curl incorrecto sin guidance
**Solución:** especificar `curl -o /dev/null -s -w '%{http_code}'`

### Terraform: environment block
Siempre escribe `environment = var.env_vars`.  
**Fix:** cambiar a `environment { variables = var.env_vars }`

### Kubernetes: image placeholder literal
Escribe `image: var IMAGE` literalmente.  
**Fix:** reemplazar con imagen real o `image: "REPLACE_ME"`

### Modo batch: degradación de performance
Con 50+ tareas seguidas, el tiempo por tarea escala x10-15.  
**Fix:** pausas de 30-60s cada 10 tareas, o usar TIMEOUTS_BATCH.

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
agentforge_audit(task_id, approve=True)   # aprobar
agentforge_audit(task_id, approve=False)  # rechazar → re-encolar con timeout corregido
```

---

## Tabla de subtypes probados (datos combinados)

| subtype | Pass frío | Pass batch | Recomendación |
|---------|-----------|------------|---------------|
| `bash_script` | ~70% (r1+2) | **100%** | Siempre delegar |
| `k8s_manifest` | ~100% | **100%** | Siempre delegar |
| `python_function` | 100% | 85% | Delegar en frío |
| `python_class` simple | ~100% | 30% | Solo en frío |
| `python_class` medio | ~100% | 80% | Delegar con revisión |
| `python_class` complejo | ~70% | 90% | Delegar, revisar lógica |
| `python_unittest` | 50% | 70% | Revisar assertions |
| `terraform_module` | 100% | 70% | Delegar, revisar bloques |
| `sql_schema` | 100% | 40% | Solo en frío |
| `readme` | 0% | N/A | No delegar |
