from Acquisition import aq_inner
from Acquisition import aq_parent
from BTrees.OOBTree import OOBTree
from OFS.SimpleItem import SimpleItem
from OFS.interfaces import IObjectWillBeAddedEvent
from OFS.interfaces import IObjectWillBeMovedEvent
from OFS.interfaces import IObjectWillBeRemovedEvent
from Products.Five import BrowserView
from Products.MailBoxer.MailBoxer import MAIL_PARAMETER_NAME
from Products.listen.interfaces import IListLookup
from email import message_from_string
from rfc822 import AddressList
from zExceptions import NotFound
from zope.app.component.hooks import getSite
from zope.app.component.hooks import setSite
from zope.app.container.interfaces import IContainerModifiedEvent
from zope.app.container.interfaces import IObjectAddedEvent
from zope.app.container.interfaces import IObjectMovedEvent
from zope.app.container.interfaces import IObjectRemovedEvent
from zope.app.event.interfaces import IObjectModifiedEvent
from zope.app.event.objectevent import IObjectCreatedEvent
from zope.app.exception.interfaces import UserError
from zope.component import ComponentLookupError
from zope.component import getUtility
from zope.interface import implements

import logging
logger = logging.getLogger('listen.list_lookup')

class ListDoesNotExist(Exception):
    """
    a custom exception to signal the specific
    error case of mailing a list that does not 
    exist
    """

class ListLookup(SimpleItem):
    """ An implementation of IListLookup which uses to To address in a message,
        to lookup which list to send a message to.

    Some framework setup:
        >>> import Products.Five
        >>> from Products.Five import zcml
        >>> zcml.load_config('meta.zcml', Products.Five)
        >>> zcml.load_config('permissions.zcml', Products.Five)
        >>> zcml.load_config("configure.zcml", Products.Five.site)
        >>> from Products.listen.utilities import tests
        >>> zcml.load_config('configure.zcml', tests)

    Now let's make a fake mailing list in our site
        >>> ml = tests.install_fake_ml(self.folder, suppress_events=True)
        >>> from zope.app.component.hooks import setSite
        >>> setSite(ml)

    Create our utility:
        >>> from Products.listen.utilities.list_lookup import ListLookup, ListDoesNotExist
        >>> ll = ListLookup('list_lookup').__of__(self.folder)

    Register the list:
        >>> ll.registerList(ml)
        >>> ll.getListForAddress(ml.mailto) == ml
        True

    Attempt to register it under another address:
        >>> from zope.app.exception.interfaces import UserError
        >>> ml.mailto = 'another@example.com'
        >>> try:
        ...     ll.registerList(ml)
        ... except UserError:
        ...     print "Raised expected error"
        ...
        Raised expected error
        >>> ll.getListForAddress(ml.mailto) == ml
        False

    Update the list address to the new address:
        >>> ll.updateList(ml)
        >>> ll.getListForAddress(ml.mailto) == ml
        True

    Add another list with the same address:
        >>> from Products.listen.utilities.tests import FakeMailingList
        >>> ml2 = FakeMailingList('ml2')
        >>> ml_id = self.folder._setObject('ml2', ml2)
        >>> ml2 = getattr(self.folder, ml_id)
        >>> ml2.mailto = ml.mailto
        >>> try:
        ...     ll.registerList(ml2)
        ... except UserError:
        ...     print "Raised expected error"
        ...
        Raised expected error

    Try to update an unregistered list:
        >>> try:
        ...     ll.updateList(ml2)
        ... except UserError:
        ...     print "Raised expected error"
        ...
        Raised expected error

    Let's try unregistering:
        >>> ll.unregisterList(ml)
        >>> ll.getListForAddress(ml.mailto)

    Unregistering a list that isn't registered shouldn't cause any problems:
        >>> ll.unregisterList(ml2)

    Let's send a mail:
        >>> ll.registerList(ml)
        >>> ll.deliverMessage({'Mail':'x-original-to: another@example.com\\r\\nTo: another@example.com\\r\\nFrom: me@me.com\\r\\nSubject: Bogus\\r\\n\\r\\nTest'})
        'Success another@example.com'

    And with an SMTP that doesn't set x-original-to:
        >>> ll.deliverMessage({'Mail':'To: another@example.com\\r\\nFrom: me@me.com\\r\\nSubject: Bogus\\r\\n\\r\\nTest'})
        'Success another@example.com'

    And another to a bad address:
        >>> from zExceptions import NotFound
        >>> try:
        ...     ll.deliverMessage({'Mail':'x-original-to: a_bad_address@example.com\\r\\nTo: another2@example.com\\r\\nFrom: me@me.com\\r\\nSubject: Bogus\\r\\n\\r\\nTest'})
        ... except ListDoesNotExist:
        ...     print "Raised expected error"
        ...
        Raised expected error
    """

    implements(IListLookup)

    def __init__(self, id='listen_list_lookup'):
        self.id = id
        self._mapping = OOBTree()
        self._reverse = OOBTree()
        self.__name__ = 'listen_lookup'

    # We need to provide a __parent__ property to be registerable
    def _getParent(self):
        return aq_parent(self)
    #__parent__ = property(_getParent)

    def registerList(self, ml):
        """See IListLookup interface documentation"""
        address = ml.mailto
        # normalize case
        if not address:
            # Our list does not have an address yet, this only happens when
            # the add form wasn't used.
            return
        address = address.lower()
        path = '/'.join(ml.getPhysicalPath())
        current_addr = self._reverse.get(path, None)
        current_path = self._mapping.get(address, None)
        if current_addr is not None:
            raise UserError, "This list is already registered, use "\
                             "updateList to change the address."
        if current_path is not None:
            raise UserError, "A list is already registered for this address,"\
                             " you must unregister it first."
        self._mapping[address] = path
        self._reverse[path] = address

    def updateList(self, ml):
        """See IListLookup interface documentation"""
        address = ml.mailto or ''
        # normalize case
        address = address.lower()
        path = '/'.join(ml.getPhysicalPath())
        current_addr = self._reverse.get(path, None)
        current_path = self._mapping.get(address, None)
        if (current_path is None and current_addr is not None and
                                                     current_addr != address):
            # The mailing list address has changed to one which is unknown
            del self._mapping[current_addr]
            self._reverse[path] = address
            self._mapping[address] = path
        elif current_addr == address and current_path == path:
            # Nothing has changed, do nothing
            pass
        elif current_addr is None and current_path is None:
            # The list is not registered at all, this happens when the addform
            # was not used, stupid CMF
            self.registerList(ml)
        else:
            # The new address is already registered
            raise UserError, "A list is already registered for this address"

    def unregisterList(self, ml):
        """See IListLookup interface documentation"""
        address = ml.mailto
        # normalize case
        current_ml = self._mapping.get(address, None)
        if not address:
            # We are deleting a list without an address
            if current_ml is not None:
                del self._reverse[current_ml]
            return
        address = address.lower()
        if current_ml == '/'.join(ml.getPhysicalPath()):
            del self._mapping[address]
            del self._reverse[current_ml]

    def getListForAddress(self, address):
        """See IListLookup interface documentation"""
        list_path = self._mapping.get(address, None)
        if list_path is not None:
            site = getSite()
            ml = site.unrestrictedTraverse(list_path)
            return aq_inner(ml)
        return None

    def deliverMessage(self, request):
        """See IListLookup interface documentation"""
        # XXX raising NotFound annoyingly hides the real problem so
        # I've added a bunch of logging.  I propose in the future we
        # change NotFound to something that actually gets logged.  But
        # I'm afraid to do that now because I don't know if we somehow
        # depend on getting a 404 here.
        message = str(request.get(MAIL_PARAMETER_NAME, None))
        if message is not None:
            message = message_from_string(message)
        else:
            logger.error("request.get(%s) returned None" % MAIL_PARAMETER_NAME)
            raise NotFound, "The message destination cannot be deterimined."
        # preferentially use the x-original-to header (is this postfix only?),
        # so that mails to multiple lists are handled properly
        address = message.get('x-original-to', None)
        if not address:
            address = message['to']
            cc = message['cc']
            if address and cc:
                    address = address + ', ' + cc
            elif cc:
                address = cc
        # normalize case
        if not address:
            import pprint
            logger.warn("No destination found in headers:\n%s" % pprint.pformat(message))
            raise NotFound, "The message destination cannot be deterimined."
        address = address.lower()
        if '-manager@' in address:
            address = address.replace('-manager@','@')
        address_list = AddressList(address)
        for ml_address in address_list:
           ml = self.getListForAddress(ml_address[1])
           if ml is not None:
               break
        else:
            # raise an error on bad requests, so that the SMTP server can
            # send a proper failure message.
            logger.warn("no list found for any of %r" % str(address_list))
            raise ListDoesNotExist, "The message address does not correspond to a "\
                             "known mailing list."
        setSite(ml)
        return ml.manage_mailboxer(request)

    def showAddressMapping(self):
        return [{'address':k, 'path':v} for k,v in self._mapping.items()]

    def purgeInvalidEntries(self):
        counter = 0
        for path in self._reverse.keys():
            list_obj = self.unrestrictedTraverse(path, None)
            if list_obj is None:
                address = self._reverse[path]
                del self._mapping[address]
                del self._reverse[path]
                counter += 1
        return counter


def changeMailingList(ml, event):
    """An event listener which registers and unregisters lists with the
       ListLookup utility on list changes.

    Some framework setup:
        >>> from zope.app.testing.placelesssetup import setUp, tearDown
        >>> import Products.Five
        >>> from Products.Five import zcml
        >>> setUp()
        >>> zcml.load_config('meta.zcml', package=Products.Five)
        >>> zcml.load_config('permissions.zcml', package=Products.Five)
        >>> zcml.load_config("configure.zcml", package=Products.Five.site)
        >>> from Products.listen.utilities import tests
        >>> zcml.load_config('configure.zcml', package=tests)

    Now let's make a fake mailing list in our site
        >>> from zope.app.component.hooks import setSite
        >>> app = self.folder
        >>> tests.enable_local_site(app)
        >>> setSite(app)
        >>> ml = tests.install_fake_ml(app, suppress_events=True)
        >>> setSite(ml)

    Then we setup our listener
        >>> from zope.app.event.interfaces import IObjectModifiedEvent
        >>> from zope.app.container.interfaces import IObjectMovedEvent
        >>> from OFS.interfaces import IObjectWillBeRemovedEvent
        >>> from Products.listen.utilities.list_lookup import changeMailingList
        >>> from zope.component import handle
        >>> from Products.listen.interfaces import IMailingList
        >>> handle([IMailingList, IObjectWillBeRemovedEvent], changeMailingList)
        >>> handle([IMailingList, IObjectMovedEvent], changeMailingList)
        >>> handle([IMailingList, IObjectModifiedEvent], changeMailingList)

    Create and register our utility.  Have to do some faking of the
    component registry stuff to get our mock environment to work:
        >>> from Products.listen.interfaces import IListLookup
        >>> from Products.listen.utilities.list_lookup import ListLookup
        >>> from Products.listen.lib.common import get_utility_for_context
        >>> sm = app.getSiteManager()
        >>> sm.registerUtility(ListLookup('list_lookup'), IListLookup)
        >>> tests.register_fake_component_adapter()
        >>> ll = get_utility_for_context(IListLookup, context=app)
        >>> print ll.getListForAddress(ml.mailto)
        None

    Send our added event:
        >>> from zope.event import notify
        >>> from zope.app.container.contained import ObjectAddedEvent
        >>> notify(ObjectAddedEvent(ml, app, 'ml'))
        >>> ll.getListForAddress(ml.mailto) == ml
        True

    Change the list and send an event:
        >>> ml.mailto = 'test2@example.com'
        >>> from zope.app.event.objectevent import ObjectModifiedEvent
        >>> notify(ObjectModifiedEvent(ml))
        >>> ll.getListForAddress(ml.mailto) == ml
        True

    Send a removal event, which should do nothing, as we rely on before
    removal:
        >>> from zope.app.container.contained import ObjectRemovedEvent
        >>> notify(ObjectRemovedEvent(ml, app, 'ml'))
        >>> ll.getListForAddress(ml.mailto) == ml
        True

    Send a before removal event:
        >>> from OFS.event import ObjectWillBeRemovedEvent
        >>> notify(ObjectWillBeRemovedEvent(ml))
        >>> ll.getListForAddress(ml.mailto) is None
        True

        >>> tearDown()
    """
    # Use the new parent object as the context, unless it is unavailable, then
    # use the list itself
    parent = None
    if hasattr(event, 'newParent'):
        parent = event.newParent
    if parent is None:
        parent = ml
    
    try:
        ll = getUtility(IListLookup)
    except ComponentLookupError:
        # site won't be set if you delete the Plone site from the ZMI
        orig_site = getSite()
        setSite(ml)
        ll = getUtility(IListLookup, context=ml)
        setSite(orig_site)
        
    if IObjectWillBeAddedEvent.providedBy(event):
        # Registration is taken care of after add
        pass
    elif IObjectWillBeRemovedEvent.providedBy(event):
        ll.unregisterList(ml)
    elif IObjectWillBeMovedEvent.providedBy(event):
        ll.unregisterList(ml)
    elif IObjectRemovedEvent.providedBy(event):
        # Unregistration is taken care of before removal
        pass
    elif IObjectModifiedEvent.providedBy(event):
        if not IContainerModifiedEvent.providedBy(event):
            ll.updateList(ml)
    elif IObjectAddedEvent.providedBy(event) or IObjectCreatedEvent.providedBy(event):
        ll.registerList(ml)
    elif IObjectMovedEvent.providedBy(event):
        ll.registerList(ml)


class ListLookupView(BrowserView):
    """A view for the list lookup which provides a form action"""
    def purge_entries(self):
        count = self.context.purgeInvalidEntries()
        return "Purged %s invalid entries"%count


class MailDeliveryView(BrowserView):
    """A simple view which hands off requests to the list lookup utility"""

    def __call__(self):
        ll = getUtility(IListLookup, context=self.context)
        try:
            return ll.deliverMessage(self.request)
        except ListDoesNotExist:
            raise NotFound, "The message address does not correspond to a known mailing list"
        except:
            message = str(self.request.get(MAIL_PARAMETER_NAME, None))
            logger.error("Listen delivery failed for message: \n%s" % message)
            raise
