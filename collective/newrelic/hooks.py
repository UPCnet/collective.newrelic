from AccessControl import getSecurityManager
from collective.newrelic.utils import logger, add_nr_attr
from zope.browser.interfaces import IBrowserView
from zope.browserresource.interfaces import IResource
from zope.pagetemplate.interfaces import IPageTemplate
import newrelic.agent
import newrelic.api
import os
from collective.newrelic.utils import PLACEHOLDER

# IPubAfterTraversal hook for naming our transactions!


def newrelic_transaction(event):

    try:
        request = event.request
        published = request.get('PUBLISHED', None)
        trans = newrelic.agent.current_transaction()

        try:
            klass = published.__class__
        except AttributeError:
            transname = PLACEHOLDER
        else:
            if klass.__module__ == 'Products.Five.metaclass':
                if klass.__bases__[0].__name__ == 'ViewMixinForTemplates':
                    try:
                        transname = os.path.basename(klass.index.filename)
                    except:
                        transname = PLACEHOLDER
                else:
                    klass = klass.__bases__[0]
                    transname = klass.__module__ + '.' + klass.__name__
            elif klass.__name__ in ('FSPageTemplate', 'FSControllerPageTemplate'):
                transname = os.path.basename(published._filepath)
            else:
                transname = klass.__module__ + '.' + klass.__name__

        if trans:
            # We only want to track the following:
            # 1. BrowserViews (but not the resource kind ..)
            # 2. PageTemplate (/skins/*/*.pt ) being used as views
            # 3. PageTemplates in ZMI
            if hasattr(trans, 'name_transaction'):
                rename_trans = trans.name_transaction
            else:
                rename_trans = trans.set_transaction_name

            if (IBrowserView.providedBy(published) or IPageTemplate.providedBy(published)) and not IResource.providedBy(published):
                rename_trans(transname, group='Zope2', priority=1)
                user_id = 'anonymous'
                user = getSecurityManager().getUser()
                if user is not None:
                    user_id = getattr(user, 'getId', lambda: None)() or getattr(user, 'getUserName', lambda: None)() or getattr(user, 'id', None) or user_id
                if user_id is None or user_id == '':
                    try:
                        from plone import api
                        user_id = api.user.get_current().getId()
                    except Exception:
                        pass
                if user_id is None or user_id == '':
                    auth = request.get('AUTHENTICATED_USER')
                    if auth is not None and hasattr(auth, 'getId'):
                        user_id = auth.getId()
                    elif auth is not None and hasattr(auth, 'getUserName'):
                        user_id = auth.getUserName()
                    else:
                        user_id = request.environ.get('REMOTE_USER') if isinstance(request.environ.get('REMOTE_USER'), str) else None
                if user_id is None or user_id == '':
                    user_id = 'anonymous'
                add_nr_attr('user', user_id)
                # Atributos para que Service Ops pueda enviarte la petición exacta (límite NR 255 bytes/atributo)
                try:
                    _max_attr = 255
                    path_info = request.get('PATH_INFO') or request.environ.get('PATH_INFO') or ''
                    add_nr_attr('path_info', path_info[:_max_attr])
                    add_nr_attr('request_method', (request.get('REQUEST_METHOD') or request.environ.get('REQUEST_METHOD') or '')[: _max_attr])
                    qs = request.get('QUERY_STRING') or request.environ.get('QUERY_STRING') or ''
                    if qs:
                        add_nr_attr('query_string', qs[:_max_attr])
                    add_nr_attr('request_summary', '{} {} [{}] {}'.format(
                        request.get('REQUEST_METHOD', request.environ.get('REQUEST_METHOD', '')),
                        path_info,
                        transname,
                        user_id,
                    )[:_max_attr])
                except Exception:
                    pass
                if hasattr(published, 'context') and hasattr(published.context, 'absolute_url'):  # Plone
                    add_nr_attr('id', published.context.id)
                    add_nr_attr('absolute_url', published.context.absolute_url())
                elif hasattr(published, 'id') and hasattr(published, 'absolute_url'):  # Zope
                    add_nr_attr('id', published.id)
                    add_nr_attr('absolute_url', published.absolute_url())
                else:
                    # We don't know what it is .. so no custom parameters!
                    logger.debug("Published has no context nor an id/absolute_url. Skipping custom parameters")

                logger.debug("Transaction: {0}".format(transname))
            else:
                # For debugging purpose
                logger.debug("NO transaction? : {0}   Browser: {1}  Resource: {2} PageTemplate: {3}".format(
                    transname,
                    IBrowserView.providedBy(published),
                    IResource.providedBy(published),
                    IPageTemplate.providedBy(published)))

    except Exception as e:
        # Log it and carry on.
        logger.exception(e)


def newrelic_precommit(event):
    request = event.request
    # Total de llamadas al catálogo en esta transacción (correlacionar span lento → catalog_query_N)
    try:
        from collective.newrelic.patches.catalog_tool import get_catalog_call_count
        n = get_catalog_call_count()
        if n:
            add_nr_attr('catalog_call_count', n)
    except Exception:
        pass
    for object in request.get('PARENTS', ())[::1]:
        conn = getattr(object, '_p_jar', None)
        if conn is not None and getattr(conn, 'getTransferCounts', None):
            loaded, stored = conn.getTransferCounts()
            add_nr_attr('zodb_loaded', loaded)
            add_nr_attr('zodb_stored', stored)
            break
