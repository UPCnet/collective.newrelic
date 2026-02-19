# Compatibilidad con Plone 6 y New Relic Python Agent reciente

## Resumen

Con los cambios aplicados en este fork, **collective.newrelic** es utilizable en **Plone 6.0.x** con un **agente New Relic Python moderno** (p. ej. 8.x o superior).

## Cambios realizados para Plone 6 / New Relic actual

### 1. `catalog_tool.py` (obligatorio)

- **Problema:** El paquete original usaba `newrelic.api.database_trace.DatabaseTrace` y `register_database_client`, API antigua ya no disponible en el agente New Relic reciente.
- **Solución:** Uso de `newrelic.agent.DatastoreTrace()` (context manager) con `product='Plone Catalog'`, `target`, `operation='searchResults'`, etc.
- La firma del wrapper se ha adaptado a `searchResults(self, query=None, **kw)` de Plone 6 y a llamadas legacy con `*args, **kw`.

### 2. `hooks.py` (obligatorio)

- **Problema:** `add_custom_parameter` está deprecado (deprecado en 8.3.0, eliminado en 11.0.0).
- **Solución:** Sustitución por `newrelic.agent.add_custom_attribute(key, value)`.

### 3. Resto de patches

- **zserverpublisher:** En Plone 6 se suele usar WSGI (waitress) sin ZServer; el import falla y el patch se omite correctamente (`except ImportError`). No hace falta ZServer para que el resto funcione.
- **zpublisher_mapply, transformchains, talinterpreter / chameleon_patch, cron4plone, newrelic_transaction:** Sin cambios; usan APIs que siguen existiendo (`FunctionTrace`, `background_task`, etc.). En Plone 6 se usa Chameleon, por lo que se carga `chameleon_patch` (no `talinterpreter`).
- **transformchains** sigue usando `six` (text_type, binary_type); opcional sustituir por `str`/`bytes` si se quiere eliminar la dependencia de six en entornos solo Python 3.

## Requisitos recomendados

- **Plone:** 6.0.x (probado con 6.0.6).
- **New Relic Python Agent:** >= 8.x (recomendado >= 11 si se usan solo custom attributes; con los cambios de este documento compatible con 8.x y superiores).
- **Python:** 3.9+ (acorde con Plone 6).

## Inicialización con genweb6.buildout

Si New Relic se inicializa en el script de arranque del buildout (antes de arrancar Zope), `collective.newrelic` detecta que el agente ya está inicializado y **no** llama de nuevo a `initialize()`, evitando doble inicialización.

## Dependencias del setup.py

- `newrelic`: sin pin explícito; usar una versión reciente (p. ej. >= 8.0).
- `repoze.xmliter`: sigue siendo dependencia del transform (RUM); en Plone 6 suele estar ya presente.
