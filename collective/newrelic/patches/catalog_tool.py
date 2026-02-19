import threading
import newrelic.agent

from Products.CMFPlone.CatalogTool import CatalogTool
from collective.newrelic.utils import logger, add_nr_attr

CatalogTool.original_cmfplone_catalogtool_searchResults = CatalogTool.searchResults

# Contador por transacción (misma request) para correlacionar span lento → query
_catalog_tls = threading.local()
_MAX_CATALOG_QUERIES_STORED = 25  # límite atributos por transacción

# Claves que no exponemos en atributos (seguridad / ruido)
_CATALOG_ATTR_SKIP = frozenset((
    'allowedRolesAndUsers', 'effectiveRange', 'show_inactive',
))


def _catalog_call_index():
    """Devuelve el índice de la llamada actual al catálogo en esta transacción (1-based)."""
    trans = newrelic.agent.current_transaction()
    txn_id = id(trans) if trans else None
    if not hasattr(_catalog_tls, 'txn_id') or _catalog_tls.txn_id != txn_id:
        _catalog_tls.txn_id = txn_id
        _catalog_tls.count = 0
    _catalog_tls.count += 1
    return _catalog_tls.count


def get_catalog_call_count():
    """Total de llamadas a searchResults en la transacción actual (para precommit)."""
    return getattr(_catalog_tls, 'count', 0)


def _catalog_query_summary(query, kw, max_len=255):
    """Resumen seguro y acotado de query+kw para New Relic (límite 255 bytes/atributo)."""
    parts = []
    if query is not None:
        if isinstance(query, dict):
            safe_q = {k: v for k, v in query.items() if k not in _CATALOG_ATTR_SKIP}
            parts.append(repr(safe_q))
        else:
            parts.append(repr(query))
    safe_kw = {k: v for k, v in kw.items() if k not in _CATALOG_ATTR_SKIP}
    if safe_kw:
        parts.append(repr(safe_kw))
    s = ' '.join(parts)
    if len(s) > max_len:
        s = s[: max_len - 3] + '...'
    return s or '(empty)'


def newrelic_searchResults(self, *args, **kw):
    # Compatible con Plone 6 (query=None, **kw) y llamadas legacy (REQUEST=...)
    request_environ = getattr(self, 'REQUEST', None) or {}
    if not isinstance(request_environ, dict):
        request_environ = getattr(request_environ, 'environ', {}) or {}
    host = request_environ.get('REMOTE_HOST') if isinstance(request_environ, dict) else None
    port = str(request_environ.get('SERVER_PORT', '')) or None if isinstance(request_environ, dict) else None
    db_name = self.getId()
    query = args[0] if args else kw.get('query')
    kw_copy = kw.copy()
    try:
        summary = _catalog_query_summary(query, kw_copy)
    except Exception:
        summary = '(summary error)'
    call_index = _catalog_call_index()
    with newrelic.agent.DatastoreTrace(
            product='Plone Catalog',
            target=db_name,
            operation='searchResults',
            host=host,
            port_path_or_id=port,
            database_name=db_name,
    ):
        add_nr_attr('catalog_call_index', call_index)
        if call_index <= _MAX_CATALOG_QUERIES_STORED:
            add_nr_attr('catalog_query_{}'.format(call_index), summary)
        elif call_index == _MAX_CATALOG_QUERIES_STORED + 1:
            add_nr_attr('catalog_query_overflow', True)
        result = self.original_cmfplone_catalogtool_searchResults(*args, **kw)
    return result


CatalogTool.searchResults = newrelic_searchResults
logger.info("Patched Products.CMFPlone.CatalogTool:CatalogTool.searchResults with instrumentation")
