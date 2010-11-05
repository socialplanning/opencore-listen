from copy import deepcopy
from rfc822 import parseaddr
import base64
import email
import logging
import quopri
import re
import smtplib

from five.localsitemanager import make_objectmanager_site
from zope.i18nmessageid import Message
from zope.i18n import translate
from zope.schema.vocabulary import SimpleVocabulary
from zope.schema.vocabulary import SimpleTerm
from zope.schema.fieldproperty import FieldProperty
from zope.interface import implements
from zope.interface import directlyProvidedBy
from zope.interface import directlyProvides
from zope.interface import alsoProvides
from zope.app import zapi
from zope.app.component.interfaces import ISite
from zope.app.component.interfaces import IPossibleSite
from zope.app.container.interfaces import IObjectRemovedEvent
from zope.app.container.interfaces import IObjectAddedEvent
from zope.app.container.interfaces import IContainerModifiedEvent
from zope.app.interface import queryType
from OFS.interfaces import IObjectWillBeAddedEvent
from OFS.event import ObjectWillBeRemovedEvent
from zope.app.container.contained import ObjectAddedEvent
from zope.event import notify
from zope.component import getAdapter
from zope.component import getUtilitiesFor
from zope.component import adapter
from zope.component import adapts
from zope.component import getUtility

from Acquisition import aq_base

from Products.Five.site.localsite import FiveSite

from Products.CMFCore.utils import getToolByName
from Products.CMFCore.DynamicType import DynamicType
from Products.CMFCore.CMFCatalogAware import CMFCatalogAware

from Products.MailBoxer.MailBoxer import MaildropHostIsAvailable

from Products.listen import config
from Products.listen.lib.browser_utils import encode
from Products.listen.interfaces.events import NewMsgDeliveredEvent

from mailboxer_list import MailBoxerMailingList
from Products.listen.lib import default_email_text
from Products.listen.interfaces import IDigestStorage
from Products.listen.interfaces import IMailingList
from Products.listen.interfaces import IDigestMailingList
from Products.listen.interfaces import IMembershipList
from Products.listen.interfaces import IMembershipDigestList
from Products.listen.interfaces import ISearchableArchive
from Products.listen.interfaces import IWriteMembershipList
from Products.listen.interfaces import ISendMail
from Products.listen.interfaces import IListTypeChanged
from Products.listen.interfaces import IListTypeDefinition
from Products.listen.interfaces import IListType
from Products.listen.interfaces import IImportListType
from Products.listen.interfaces import IExportListType
from Products.listen.interfaces import IUserEmailMembershipPolicy
from Products.listen.interfaces import IEmailPostPolicy
from Products.listen.interfaces import ITTWPostPolicy
from Products.listen.interfaces import IManagerTTWMembershipPolicy
from Products.listen.interfaces.mailinglist import IDisplayListTypes

from plone.app.content.interfaces import INameFromTitle
from plone.intelligenttext.transforms import convertWebIntelligentPlainTextToHtml
from plone.mail import decode_header

from Products.listen.config import MEMBERSHIP_DENIED
from Products.listen.config import MEMBERSHIP_DEFERRED
from Products.listen.config import MEMBERSHIP_ALLOWED
from Products.listen.config import MEMBERSHIP_PIN_MISMATCH
from Products.listen.config import MEMBERSHIP_ERROR
from Products.listen.config import POST_ALLOWED

from Products.listen.content.digest import DigestConstructor

from Products.listen.lib.common import is_email
from Products.listen.lib.common import lookup_email
from Products.listen.lib.common import lookup_member_id
from Products.listen.i18n import _

logger = logging.getLogger('listen.mailinglist')

def addMailingList(self, id, title=u''):
    """ Add a Document """
    o = MailingList(id, title)
    self._setObject(id,o)



class MailingList(DynamicType, CMFCatalogAware, MailBoxerMailingList, FiveSite):
    """ A Mailing list implementation built on top of a customized MailBoxer.

    Let's see how this works:

    Let's set up the test rig, so that we can get our archived vocabulary
    working (the interface won't validate without the vocabulary):

        >>> import Products.Five
        >>> from Products.Five import zcml
        >>> zcml.load_config('meta.zcml', Products.Five)
        >>> from Products.listen.content import tests
        >>> zcml.load_config('configure.zcml', tests)

    First we create a new instance to play with:

        >>> from Products.listen.content import MailingList
        >>> test_list = MailingList(id="test_list", title=u"My Title")

    Make sure the object and class implement our interface:

        >>> from Products.listen.interfaces import IMailingList
        >>> from zope.interface.verify import verifyObject
        >>> from zope.interface.verify import verifyClass
        >>> verifyObject(IMailingList, test_list)
        True
        >>> verifyClass(IMailingList, MailingList)
        True

    Mark it as a public list
        >>> from Products.listen.interfaces.list_types import PublicListTypeDefinition
        >>> from Products.listen.interfaces.list_types import PostModeratedListTypeDefinition
        >>> from Products.listen.interfaces.list_types import MembershipModeratedListTypeDefinition
        >>> from Products.listen.interfaces import IPublicList
        >>> from Products.listen.interfaces import IMembershipModeratedList
        >>> from Products.listen.interfaces import IPostModeratedList
        >>> test_list.list_type = PublicListTypeDefinition
        >>> IPublicList.providedBy(test_list)
        True

    Set some basic default properties:

        >>> test_list.description = u'My Description'
        >>> test_list.mailto = 'address@example.com'

    Verify that we have our Title and Description for the UI:

        >>> test_list.Title()
        'My Title'
        >>> test_list.setTitle(u'My New Title')
        >>> test_list.title
        u'My New Title'
        >>> test_list.Description()
        'My Description'
        >>> test_list.setDescription(u'My New Description')
        >>> test_list.description
        u'My New Description'


    Check property validation:
    --------------------------

    The fields should reject inappropriate input:

        >>> from zope.schema._bootstrapinterfaces import RequiredMissing, WrongType, InvalidValue
        >>> try:
        ...     test_list.description = ['My Description']
        ... except WrongType, e:
        ...     print e
        ...
        (['My Description'], <type 'unicode'>)

    We need unicode for description and ASCII for the list address:
        >>> try:
        ...     test_list.description = 'My Description'
        ... except WrongType, e:
        ...     print e
        ...
        ('My Description', <type 'unicode'>)
        >>> try:
        ...     test_list.mailto = u'address@example.com'
        ... except WrongType, e:
        ...     print e
        ...
        (u'address@example.com', <type 'str'>)
        >>> try:
        ...     test_list.mailto = 'ad\xF4dress@example.com'
        ... except InvalidValue:
        ...     print "Invalid"
        ...
        Invalid


    Verify the mailto constraint.
    mailto that end in -manager should be rejected
        >>> test_list.mailto = 'invalid-manager@example.com'
        Traceback (most recent call last):
        ...
        ManagerMailTo: invalid-manager@example.com

    Invalid mailtos should get rejected
        >>> test_list.mailto = 'invalid email@example.com'
        Traceback (most recent call last):
        ...
        InvalidMailTo: invalid email@example.com

    The MailBoxer maillist property is now implemented using an adapter
    providing the ISubscriptionList interface.  We create a dumb partial
    implementation of ISubscriptionList in /tests/ to test (would be nice
    if we could use ztapi.provideAdapter here):

    Without an adapter provided, this should fail
        XXX test deactivated :) >> try:
        ...     test_list.maillist
        ... except TypeError, e:
        ...     print e
        ...
        ('Could not adapt', <MailingList at test_list>, <InterfaceClass Products.listen.interfaces.mailinglist.ISubscriptionList>)

    Attach the adapter through configuration:
        >>> configure_zcml = '''
        ... <configure xmlns="http://namespaces.zope.org/zope">
        ...    <adapter
        ...        for="Products.listen.interfaces.IMailingList"
        ...        provides="Products.listen.interfaces.ISubscriptionList"
        ...        factory="Products.listen.content.tests.Subscriptions"
        ...        />
        ... </configure>'''
        >>> zcml.load_string(configure_zcml)

    It should work now:
        XXX test deactivated :) >> test_list.maillist
        (u'addr1@example.com', u'addr2@example.com')

    Some interface methods are tested in the MailBoxerMailingList
    parent class.

    Verify that the mailing list object can be annotatable
        >>> from zope.annotation.interfaces import IAttributeAnnotatable
        >>> verifyObject(IAttributeAnnotatable, test_list)
        True
        >>> from zope.annotation.interfaces import IAnnotations
        >>> annot = IAnnotations(test_list)

    Setup membership tool
        >>> from Products.listen.content.tests import DummyMembershipTool
        >>> mtool = DummyMembershipTool('foo')
        >>> test_list.portal_membership = mtool
        >>> mtool.result = None

    Load the test content zcml
        >>> import Products.Five
        >>> from Products.Five import zcml
        >>> zcml.load_config('meta.zcml', Products.Five)
        >>> from Products.listen.content import tests
        >>> zcml.load_config('configure.zcml', tests)

    Check that we have the correct default list type
    And that we provide the correct default interface
        >>> IPublicList.providedBy(test_list)
        True

    Tests request Mail function---when a user requests membership
    on a public list
        >>> request = {}
        >>> request['Mail'] = '''To: list1@example.com
        ... From: test1@example.com
        ... Subject: subscribe
        ... Date: Wed, 5 Mar 2005 12:00:00 -0000
        ... '''
        >>> sent_emails = []
        >>> def patched_send(to, subject, body, mail_from=None, extra_headers={}):
        ...     if mail_from is None:
        ...         sent_emails.append((to, subject, body))
        ...     else:
        ...         sent_emails.append((to, subject, body, mail_from))
        >>> test_list.sendCommandRequestMail = patched_send
        >>> test_list.requestMail(request)
        True
        >>> 'We have received a subscription request' in sent_emails[0][2]
        True
        >>> request['Mail'] = '''To: list1@example.com
        ... From: test1@example.com
        ... Subject: Subscription confirmation (mail-command:subscribe-member test1@example.com [88440445])
        ... Date: Wed, 5 Mar 2005 12:00:00 -0000
        ... '''
        >>> test_list.requestMail(request)
        True
        >>> 'the pin you provided does not match' in sent_emails[1][2]
        True
        >>> request['Mail'] = '''To: list1@example.com
        ... From: Test1@example.com
        ... Subject: %s
        ... Date: Wed, 5 Mar 2005 12:00:00 -0000
        ... ''' % sent_emails[0][1]
        >>> test_list.requestMail(request)
        True
        >>> 'You are now subscribed' in sent_emails[2][2]
        True

    Verify that if we sent another valid request, we don't get a denied message back
        >>> len(sent_emails)
        3
        >>> test_list.requestMail(request)
        True
        >>> len(sent_emails)
        3

    Tests request Mail function---when a user requests membership
    on a membership-moderated list
        >>> from Products.listen.content import list_type_changed, ListTypeChanged
        >>> test_list.list_type = MembershipModeratedListTypeDefinition
        >>> list_type_changed(ListTypeChanged(test_list, IPublicList, IMembershipModeratedList))
        >>> IMembershipModeratedList.providedBy(test_list)
        True
        >>> IPublicList.providedBy(test_list)
        False
        >>> IPostModeratedList.providedBy(test_list)
        False
        >>> request = {}
        >>> request['Mail'] = '''To: list1@example.com
        ... From: test2@example.com
        ... Subject: subscribe
        ... Date: Wed, 5 Mar 2005 12:00:00 -0000
        ... '''
        >>> sent_emails = []
        >>> test_list.requestMail(request)
        True
        >>> 'We have received a subscription request' in sent_emails[0][2]
        True
        >>> request['Mail'] = '''To: list1@example.com
        ... From: test2@example.com
        ... Subject: Subscription confirmation (mail-command:subscribe-member test2@example.com [88440445])
        ... Date: Wed, 5 Mar 2005 12:00:00 -0000
        ... '''
        >>> test_list.requestMail(request)
        True
        >>> 'the pin you provided does not match' in sent_emails[1][2]
        True
        >>> request['Mail'] = '''To: list1@example.com
        ... From: test2@example.com
        ... Subject: %s
        ... Date: Wed, 5 Mar 2005 12:00:00 -0000
        ... ''' % sent_emails[0][1]
        >>> test_list.requestMail(request)
        True
        >>> 'Your request to join the My New Title mailing list is awaiting approval' in sent_emails[2][2]
        True

    Tests request Mail function---when a user sends an unsubscription request
    on a public list
        >>> test_list.list_type = PublicListTypeDefinition
        >>> list_type_changed(ListTypeChanged(test_list, IMembershipModeratedList, IPublicList))
        >>> request = {}
        >>> request['Mail'] = '''To: list1@example.com
        ... From: test1@example.com
        ... Subject: unsubscribe
        ... Date: Wed, 5 Mar 2005 12:00:00 -0000
        ... '''
        >>> sent_emails = []
        >>> test_list.requestMail(request)
        True
        >>> 'We have received a request to unsubscribe' in sent_emails[0][2]
        True
        >>> request['Mail'] = '''To: list1@example.com
        ... From: test1@example.com
        ... Subject: Unsubscription confirmation (mail-command:unsubscribe-member test1@example.com [88440445])
        ... Date: Wed, 5 Mar 2005 12:00:00 -0000
        ... '''
        >>> test_list.requestMail(request)
        True
        >>> 'the pin you provided does not match' in sent_emails[1][2]
        True
        >>> request['Mail'] = '''To: list1@example.com
        ... From: Test1@example.com
        ... Subject: %s
        ... Date: Wed, 5 Mar 2005 12:00:00 -0000
        ... ''' % sent_emails[0][1]
        >>> test_list.requestMail(request)
        True
        >>> 'You have been unsubscribed' in sent_emails[2][2]
        True

    Tests request Mail function---when a user sends an unsubscription request
    on a membership-moderated list
        >>> test_list.list_type = MembershipModeratedListTypeDefinition
        >>> list_type_changed(ListTypeChanged(test_list, IPublicList, IMembershipModeratedList))
        >>> request = {}
        >>> request['Mail'] = '''To: list1@example.com
        ... From: Test Dude <test1@example.com>
        ... Subject: unsubscribe
        ... Date: Wed, 5 Mar 2005 12:00:00 -0000
        ... '''
        >>> sent_emails = []
        >>> test_list.requestMail(request)
        True
        >>> 'We have received a request to unsubscribe' in sent_emails[0][2]
        True
        >>> request['Mail'] = '''To: list1@example.com
        ... From: Test Dude <test1@example.com>
        ... Subject: Unsubscription confirmation (mail-command:unsubscribe-member test1@example.com [88440445])
        ... Date: Wed, 5 Mar 2005 12:00:00 -0000
        ... '''
        >>> test_list.requestMail(request)
        True
        >>> 'the pin you provided does not match' in sent_emails[1][2]
        True
        >>> request['Mail'] = '''To: list1@example.com
        ... From: Test Dude <test1@example.com>
        ... Subject: %s
        ... Date: Wed, 5 Mar 2005 12:00:00 -0000
        ... ''' % sent_emails[0][1]
        >>> test_list.requestMail(request)
        True
        >>> 'You have been unsubscribed' in sent_emails[2][2]
        True

        try sending a message to the managers
        >>> test_list.managers = (u'flux@fleem.com',)
        >>> test_list.mailto = 'test_list@lists.listen.com'
        >>> message = ['from: lammy@morx.com',
        ...            'to: test_list-manager@lists.listen.com',
        ...            'subject: whatever',
        ...            '',
        ...            'message body']
        >>> message = '\\n'.join(message)
        >>> sent_emails = []
        >>> test_list.manager_mail(dict(Mail=message))
        True

        It doesn't barf if the TO is borken or missing.
        (Some messages might have the delivery address in BCC or CC...)
        >>> message = ['from: lammy@morx.com',
        ...            'subject: whatever',
        ...            '',
        ...            'message body']
        >>> message = '\\n'.join(message)
        >>> test_list.manager_mail(dict(Mail=message))
        False


        the email that gets sent out should have the from as the
        original from user, and should not be from the list
        >>> sent_emails
        [(u'flux@fleem.com', 'whatever', u'Inquiry from: lammy@morx.com\\n\\nmessage body', u'"[My New Title] List Manager" <test_list-manager@lists.listen.com>')]
 
        now try to send the mail to the managers without specifying the
        right to address
        >>> message = ['from: lammy@morx.com',
        ...            'to: bad-name@lists.listen.com',
        ...            'subject: whatever',
        ...            '',
        ...            'message body']
        >>> message = '\\n'.join(message)
        >>> sent_emails = []
        >>> test_list.manager_mail(dict(Mail=message))
        False
        >>> sent_emails
        []

        test validation error on mailto attribute
        >>> test_list.mailto = 'test-manager@lists.listen.com'
        Traceback (most recent call last):
        ...
        ManagerMailTo: test-manager@lists.listen.com


    Set up the dummies
        >>> from Products.listen.content.mailinglist import subscribe_new_managers
        >>> from Products.listen.interfaces import IMembershipList
        >>> from Products.listen.extras.tests import TestMailingList
        >>> from Products.listen.content.tests import DummyMember
        >>> mtool.getAuthenticatedMember = lambda: DummyMember(u'cantor@example.com', 'can tor', 'cantor@example.com')
        >>> test_list2 = TestMailingList()
        >>> test_list2.portal_membership = mtool

    Test the subscribe_new_managers function
        >>> test_list2.managers = (u'cantor@example.com', u'crux@example.com', u'celest@example.com', u'bogus_dude')
        >>> from zope.interface import alsoProvides
        >>> from zope.component import provideAdapter
        >>> from Products.listen.interfaces import IManagerTTWMembershipPolicy, IBaseList
        >>> from Products.listen.content.membership_policies import ManagerTTWMembershipPolicy
        >>> alsoProvides(test_list2, IBaseList)
        >>> provideAdapter(ManagerTTWMembershipPolicy, (IBaseList, IManagerTTWMembershipPolicy))
        >>> subscribe_new_managers(test_list2)
        >>> test_list2.message_count
        2
        >>> mem_list = IMembershipList(test_list2)
        >>> mem_list.allowed_senders
        [u'cantor@example.com', u'celest@example.com', u'crux@example.com']
        >>> mem_list.subscribers
        [u'cantor@example.com']

    Excercise processMail. Unfortunately this is a pain to set up.  First
    we need a mock implementation of IGetMailHost and MailHost.

        >>> # Need aq context to magically make component lookups work.
        >>> test_list = test_list.__of__(portal)
        >>> # Now a mock MailHost. This should move elsewhere, it's
        >>> # probably useful for other parts of listen tests.
        >>> class mockmh(object):
        ...     # Needs to pretend to be a Maildrop Host,
        ...     # this saves us a lot of pain mocking a MailHost...
        ...     # but only because we're relying on implementation
        ...     # details of listen. Oh well.
        ...     meta_type = 'Maildrop Host'
        ...     def _send(self, *args, **kw):
        ...         from Products.MailBoxer.MailBoxer import MAIL_PARAMETER_NAME
        ...         mailString = str(request[MAIL_PARAMETER_NAME])
        ...         from Products.MailBoxer.MailBoxerTools import splitMail
        ...         header = mailString.split('\\n\\n')[0]
        ...         print 'Mail sent!'
        ...         print header.strip()

        >>> mock_mh = mockmh()
        >>> from Products.listen.interfaces import IGetMailHost
        >>> from zope.interface import implements
        >>> class MockGetMH(object):
        ...     implements(IGetMailHost)
        ...     mail_host = mock_mh
        >>> from zope.component import getUtility, provideUtility
        >>> provideUtility(MockGetMH(), IGetMailHost)

    Also need to unregister the IMailHost utility and replace it w/ ours.

        >>> from Products.MailHost.interfaces import IMailHost
        >>> sm = portal.getSiteManager()
        >>> orig_mh = sm.getUtility(IMailHost)
        >>> ignore = sm.unregisterUtility(orig_mh, IMailHost)
        >>> sm.registerUtility(mock_mh, IMailHost)

    One more hack to get our mock mailhost used. This is lame but works for now.

        >>> import Products.listen.content.mailinglist
        >>> Products.listen.content.mailinglist.MaildropHostIsAvailable = True

    Finally ready. Let's make a request and fire that sucker up.

        >>> request['Mail'] = '''To: list1@example.com
        ... From: test1@example.com
        ... Subject: subscribe
        ... Date: Wed, 5 Mar 2005 12:00:00 -0000
        ... '''

        >>> status = test_list.processMail(request)
        Mail sent!
        To: list1@example.com
        From: test1@example.com
        Subject: subscribe
        Date: Wed, 5 Mar 2005 12:00:00 -0000
        <BLANKLINE>

        >>> from Products.listen.config import POST_ALLOWED
        >>> status == POST_ALLOWED
        True

    Let's try a malformed email. This will not be sent.
        >>> request['Mail'] = '''To: someone@example.com
        ... Subject: I have no sender, bwahaha
        ... Date: Wed, 5 Mar 2005 12:00:00 -0000
        ... '''

        >>> status = test_list.processMail(request)
        >>> status == POST_ALLOWED
        False

    """

    implements(IDigestMailingList, IPossibleSite, INameFromTitle)

    portal_type = "Mailing List"
    meta_type = "MailingList"
    default_view = 'mailinglist_view'
    content_icon  = 'mailboxer_icon.png'

    # Provide our basic properties with schema based validation
    title = FieldProperty(IMailingList['title'])
    description = FieldProperty(IMailingList['description'])
    mailto = FieldProperty(IMailingList['mailto'])
    archived = FieldProperty(IMailingList['archived'])
    managers = FieldProperty(IMailingList['managers'])

    def __init__(self, *args, **kwargs):
        super(MailingList, self).__init__(*args, **kwargs)
        self.list_type = IMailingList['list_type'].default

    def _get_list_type(self):
        list_marker = queryType(self, IListType)
        if list_marker is None: return None
        
        definition_name = list_marker.getTaggedValue('definition-name')
        return getUtility(IListTypeDefinition, name=definition_name)

    def _set_list_type(self, list_type_definition):
        old_list_type_definition = self.list_type
        list_marker = list_type_definition.list_marker

        if old_list_type_definition is None:
            alsoProvides(self, list_marker)

    list_type = property(fget=_get_list_type, fset=_set_list_type)

    # not a property so we don't lose acquisition context
    def digest_constructor(self):
        return DigestConstructor(self)

    # Define some DC fields for plone ui purposes
    def Title(self):
        """The portal catalog's text indices need encoded strings, or else
           they blow up.  It's got to be all unicode or no unicode (or
           perhaps TXNG)."""
        return encode(self.title, self)

    def setTitle(self, val):
        if isinstance(val, unicode):
            self.title = val
            return
        encoding = 'utf-8'
        # Some plone-iness here to get site encoding
        putils = getToolByName(self, 'plone_tool', None)
        if putils is not None:
            encoding = putils.getSiteEncoding()
        self.title = val.decode(encoding)

    def Description(self):
        """The portal catalog's text indices need encoded strings, or else
           they blow up.  It's got to be all unicode or no unicode (or
           perhaps TXNG)."""
        return encode(self.description or u'', self)

    def setDescription(self, val):
        self.description = val or u''

    def SearchableText(self):
        return self.Title() + ' ' + self.Description()


    # MailBoxer wants to use a simple property to store/retrieve the
    # subscribers, we want to use adapters.  We will provide the property
    # only for backwards compatibility with MailBoxer internals.
    def _getMailList(self):
        return IMembershipList(self).subscribers

    def _setMailList(self, value):
        mem_list = IWriteMembershipList(self)
        for mem in value:
            mem_list.subscribe(value)

    maillist = property(fget=_getMailList, fset=_setMailList)


    def _getAllowedSenders(self):
        return tuple(self.subscriber_data)
    allowed_senders = property(fget=_getAllowedSenders)

    @property 
    def manager_email(self):
        if not self.mailto:
            return False
        splitted = self.mailto.split('@')
        return splitted[0] + '-manager@' + splitted[-1]

    def manage_afterAdd(self, item, container):
        ## CMFCatalogAware.manage_afterAdd(self, item, container)
        # This only needs to be done when added via a z3 form, because object
        # creation will not be complete in the CMF way of doing things.
        if not self.getPortalTypeName():
            ttool = getToolByName(self, 'portal_types')
            fti = getattr(ttool, self.portal_type)
            fti._finishConstruction(self)
        # Make this possible site a real site
        if not ISite.providedBy(item):
            make_objectmanager_site(item)
        # Add search utility (catalog) if it's not already present
        sm = self.getSiteManager()
        # don't add the searchable archive if it's already there
        search = sm.queryUtility(ISearchableArchive)
        if search is None:
            search = zapi.createObject('listen.SearchUtilityFactory', self.catalog)
            sm.registerUtility(aq_base(search), ISearchableArchive)
        if not hasattr(self, 'ISearchableArchive'):
            self._setObject('ISearchableArchive', search)
        MailBoxerMailingList.manage_afterAdd(self, item, container)
        if not config.HAS_CONTAINER_EVENTS:
            notify(ObjectAddedEvent(self, container, self.getId()))

    def manage_beforeDelete(self, item, container):
        if not config.HAS_CONTAINER_EVENTS:
            notify(ObjectWillBeRemovedEvent(self, container, self.getId()))

    # Use allowedContentTypes to restrict the addable types:
    def allowedContentTypes( self ):
        return []

    # Don't show the contents tab here or on any children:
    def displayContentsTab(self):
        return False

    def fixupMessages(self):
        """A method to rearchive everything, and fix up encoding issues"""
        # don't bother with this stuff on removal, it's pointless
        search = zapi.getUtility(ISearchableArchive, context=self)
        # XXX: Assumes a ZCatalog based utility, we need to rebuild the whole
        # catalog after a move
        # Clear the catalog
        search.manage_catalogClear()
        # Our fix up and index method
        def index_meth(obj, *args):
            # body, address, title, and subject are unicode
            if not isinstance(obj.from_addr, unicode):
                obj.from_addr = decode_header(obj.from_addr)
            if not isinstance(obj.subject, unicode):
                obj.subject = decode_header(obj.subject)

            sender_name = parseaddr(obj.from_addr)[0]

            title_subj = len(obj.subject) > 20 and (obj.subject[:20]+' ...') \
                             or obj.subject
            if sender_name:
                obj.title = u"%s / %s" % (title_subj, sender_name)
            else:
                obj.title= title_subj
            if not isinstance(obj.body, unicode):
                # Default western european encoding, because other info has
                # been lost at this point.
                obj.body = obj.body.decode('iso-8859-1', 'replace')
            search.catalog_object(obj, *args)
        path = '/'.join(self.getPhysicalPath())
        search.ZopeFindAndApply(self, obj_metatypes=('MailingListMessage',),
                                apply_func=index_meth,
                                apply_path=path,
                                search_sub=1)
        # We refresh to catch the inter-message dependencies due to threading
        search.refreshCatalog()
        return "Done."


    def requestMail(self, request):
        # Handles un-/subscribe-requests and confirmations

        mailString = self.getMailFromRequest(request)
        (header, body) = self.splitMail(mailString)

        subject = self.mime_decode_header(header.get('subject',''))

        subscribe_regex = '^((un)?subscribe)\s*$'
        subscribe_match = re.search(subscribe_regex, subject, re.IGNORECASE)
        confirm_regex = 'mail-command:(un)?subscribe-member'
        confirm_match = re.search(confirm_regex, subject)
        
        if not subscribe_match and not confirm_match:
            return False

        sub_policy = getAdapter(self, IUserEmailMembershipPolicy)

        sender = self.mime_decode_header(header.get('from', ''))
        (name, email) = self.parseaddr(sender)
        email = email.lower()
        policy_result = sub_policy.enforce({'email':email, 'name':name, 'subject':subject})

        mail_sender = ISendMail(self)
        sub_list = IWriteMembershipList(self)
        
        if policy_result == MEMBERSHIP_ALLOWED:
            if 'unsubscribe' in subject:
                sub_list.unsubscribe(email)
                mail_sender.user_unsubscribe_confirm(email, name)
            elif 'subscribe' in subject:
                sub_list.subscribe(email)
                mail_sender.user_welcome(email, name)
        elif policy_result == MEMBERSHIP_PIN_MISMATCH:
            # send email to reject pin
            mail_sender.user_pin_mismatch(email, name)
        elif policy_result == MEMBERSHIP_DENIED:
            # check to see if the user has subscribed in the mean time
            if not sub_list.is_subscribed(email):
                # send email to say was denied, invalid confirmation, no record of request
                mail_sender.user_denied(email, name)
        elif policy_result in (MEMBERSHIP_DEFERRED,MEMBERSHIP_ERROR):
            # nothing needs to be done here
            # this case is handled in sub_policy.enforce() above
            pass
        return True

    def _is_reqest_ttw(self, request):
        return request.get('HTTP_REFERER')

    def _is_archived(self):
        return self.archived != 2

    def _email_from_header(self, header, key):
        # Extract a name and email address (lowercased) from the given header.
        # Either may be None.
        this_header = header.get(key, '')
        sender = self.mime_decode_header(this_header)
        (name, email) = self.parseaddr(sender)
        if email != None:
            email = email.lower().strip()
        if not email:
            msg = "No email address found in header %r. Headers:\n" % key
            logger.error(msg + '\n'.join(["%s: %s" % pair for pair in
                                          sorted(header.items())]))
        if name != None and type(name) != unicode:
            name = name.decode('utf8', 'replace')
        return name, email

    def processMail(self, request):
        mailString = self.getMailFromRequest(request)
        (header, body) = self.splitMail(mailString)

        (name, email) = self._email_from_header(header, 'from')

        interface = self._is_reqest_ttw(request) and ITTWPostPolicy or IEmailPostPolicy
        policy = getAdapter(self, interface)

        # store the post so it can be mailed easily
        post = dict(body=body, header=header)
        
        policy_result = policy.enforce(dict(name=name, email=email, post=post))
        # all functionality is handled in the post policy adapters
        if policy_result == POST_ALLOWED:
            self.listMail(request)
        return policy_result

    def manager_mail(self, request):
        """catches mail sent to manager_email"""

        mailString = self.getMailFromRequest(request)
        (header, body) = self.splitMail(mailString)

        name, email = self._email_from_header(header, 'to')
        if email != self.manager_email:
            return False

        # we have a mail intended for managers
        sender = self.mime_decode_header(header.get('from',''))
        subject = self.mime_decode_header(header.get('subject',''))
        body = 'Inquiry from: ' + sender + '\n\n' + body
        mail_sender = ISendMail(self)
        mail_sender.send_to_managers(subject, body)

        return True

    def _send_msgs(self, maillist, msg, returnpath):
        mh = getToolByName(self, 'MailHost')

        if ((MaildropHostIsAvailable and mh.meta_type=='Maildrop Host')):
            TransactionalMailHost = mh
            # Deliver each mail on its own with a transactional MailHost
            batchsize = 1
        else:
            TransactionalMailHost = None
            batchsize = self.getValueFor('batchsize')

        # start batching mails
        while maillist:
            # if no batchsize is set (default)
            # or batchsize is greater than maillist,
            # bulk all mails in one batch,
            # otherwise bulk only 'batch'-mails at once
            if (batchsize == 0) or (batchsize > len(maillist)):
                batch = len(maillist)
            else:
                batch = batchsize

            if TransactionalMailHost:
                 TransactionalMailHost._send(returnpath, maillist[0:batch], msg)
            else:
                smtpserver = smtplib.SMTP(mh.smtp_host, int(mh.smtp_port))
                if mh.smtp_userid:                    
                    smtpserver.login(mh.smtp_userid, mh.smtp_pass)
                smtpserver.sendmail(returnpath, maillist[0:batch], msg)
                smtpserver.quit()

            # remove already bulked addresses
            maillist = maillist[batch:]


    def listMail(self, request):
        """
        Test sending mail out

            >>> import Products.Five
            >>> from Products.Five import zcml
            >>> zcml.load_config('meta.zcml', Products.Five)
            >>> from Products.listen.content import tests
            >>> zcml.load_config('configure.zcml', tests)

        First we create a new instance to play with:

            >>> from Products.listen.content import MailingList
            >>> test_list = MailingList(id="test_list", title=u"Drink More")

        Set the mailing list address so that the test output makes more sense
            >>> test_list.mailto = 'drinkers@example.com'

        Add a subscriber to actually test sending out of the message
            >>> from Products.listen.content.subscriptions import SubscriptionList
            >>> sl = SubscriptionList(test_list)
            >>> sl.emails['college.kid@example.com'] = dict(subscriber=True)

        Patch the actual send on the mailing list
            >>> msgs = []
            >>> def patch_send(maillist, msg, returnpath):
            ...     msgs.append(msg)
            >>> test_list._send_msgs = patch_send

        Simulate sending a simple message
            >>> request = dict(Mail=('From: jim.beam@example.com\\n'
            ...                      'To: drinkers@example.com\\n'
            ...                      'Subject: Simple truth\\n'
            ...                      '\\nWhiskey'))
            >>> test_list.listMail(request)
            >>> print msgs[0]
            From: jim.beam@example.com
            To: drinkers@example.com
            Subject: [Drink More] Simple truth
            X-Mailer: MailBoxer
            Reply-To: drinkers@example.com
            Errors-To: drinkers-manager@example.com
            List-Subscribe: <mailto:drinkers@example.com?subject=subscribe>
            List-Unsubscribe: <mailto:drinkers@example.com?subject=unsubscribe>
            List-Id: drinkers@example.com
            Precedence: Bulk
            <BLANKLINE>
            Whiskey
            <BLANKLINE>
            --
            Archive: 
            To unsubscribe send an email with subject "unsubscribe" to drinkers@example.com.  Please contact drinkers-manager@example.com for questions.
            <BLANKLINE>
            >>> msgs[:] = []

        Turn off archiving
            >>> test_list.archived = 2

        Simulate sending a simple message
            >>> request = dict(Mail=('From: johnny.walker@example.com\\n'
            ...                      'To: drinkers@example.com\\n'
            ...                      'Subject: The key to life\\n'
            ...                      '\\nIs Whis key'))
            >>> test_list.listMail(request)
            >>> print msgs[0]
            From: johnny.walker@example.com
            To: drinkers@example.com
            Subject: [Drink More] The key to life
            X-Mailer: MailBoxer
            Reply-To: drinkers@example.com
            Errors-To: drinkers-manager@example.com
            List-Subscribe: <mailto:drinkers@example.com?subject=subscribe>
            List-Unsubscribe: <mailto:drinkers@example.com?subject=unsubscribe>
            List-Id: drinkers@example.com
            Precedence: Bulk
            <BLANKLINE>
            Is Whis key
            <BLANKLINE>
            --
            To unsubscribe send an email with subject "unsubscribe" to drinkers@example.com.  Please contact drinkers-manager@example.com for questions.
            <BLANKLINE>
            >>> msgs[:] = []

        Now test with encoded text in the subject and the body
            >>> request = dict(Mail=('From: worldtraveler@example.com\\n'
            ...                      'To: drinkers@example.com\\n'
            ...                      'Content-Type: text/plain; charset=utf-8\\n'
            ...                      'Content-Disposition: inline\\n'
            ...                      'Content-Transfer-Encoding: 8bit\\n'
            ...                      'Subject: \xe7\x9a\xba\\n'
            ...                      '\\n\xe7\x9a\xbe \xe7\x9a\xbe'))
            >>> test_list.listMail(request)
            >>> print msgs[0]
            From: worldtraveler@example.com
            To: drinkers@example.com
            Content-Type: text/plain; charset=utf-8
            Content-Disposition: inline
            Content-Transfer-Encoding: 8bit
            Subject: [Drink More] \xe7\x9a\xba
            X-Mailer: MailBoxer
            Reply-To: drinkers@example.com
            Errors-To: drinkers-manager@example.com
            List-Subscribe: <mailto:drinkers@example.com?subject=subscribe>
            List-Unsubscribe: <mailto:drinkers@example.com?subject=unsubscribe>
            List-Id: drinkers@example.com
            Precedence: Bulk
            <BLANKLINE>
            \xe7\x9a\xbe \xe7\x9a\xbe
            <BLANKLINE>
            --
            To unsubscribe send an email with subject "unsubscribe" to drinkers@example.com.  Please contact drinkers-manager@example.com for questions.
            <BLANKLINE>
            >>> msgs[:] = []

        Multipart messages
            >>> request = dict(Mail=('From: tequila_guy@example.com\\n'
            ...                      'To: drinkers@example.com\\n'
            ...                      'Subject: Tequila Tuesdays\\n'
            ...                      'MIME-Version: 1.0\\n'
            ...                      'Content-Type: multipart/alternative;\\n'
            ...                      '  boundary="----=_Part_7928_16493718.1220401254779"\\n'
            ...                      '\\n'
            ...                      '------=_Part_7928_16493718.1220401254779\\n'
            ...                      'Content-Type: text/plain; charset=WINDOWS-1252\\n'
            ...                      'Content-Transfer-Encoding: quoted-printable\\n'
            ...                      'Content-Disposition: inline\\n'
            ...                      '\\nComing up this Tuesday, all the Tequila you can drink.\\n\\n'
            ...                      '------=_Part_7928_16493718.1220401254779\\n'
            ...                      'Content-Type: text/html; charset=WINDOWS-1252\\n'
            ...                      'Content-Transfer-Encoding: quoted-printable\\n'
            ...                      'Content-Disposition: inline\\n'
            ...                      '\\n'
            ...                      '<p>Coming up this Tuesday, <b>all</b> the Tequila you can drink.</p>\\n\\n'
            ...                      '------=_Part_7928_16493718.1220401254779\\n'))
            >>> test_list.listMail(request)
            >>> print msgs[0]
            From: tequila_guy@example.com
            To: drinkers@example.com
            Subject: [Drink More] Tequila Tuesdays
            MIME-Version: 1.0
            Content-Type: multipart/alternative;
              boundary="----=_Part_7928_16493718.1220401254779"
            X-Mailer: MailBoxer
            Reply-To: drinkers@example.com
            Errors-To: drinkers-manager@example.com
            List-Subscribe: <mailto:drinkers@example.com?subject=subscribe>
            List-Unsubscribe: <mailto:drinkers@example.com?subject=unsubscribe>
            List-Id: drinkers@example.com
            Precedence: Bulk
            <BLANKLINE>
            ------=_Part_7928_16493718.1220401254779
            Content-Type: text/plain; charset=WINDOWS-1252
            Content-Transfer-Encoding: quoted-printable
            Content-Disposition: inline
            <BLANKLINE>
            Coming up this Tuesday, all the Tequila you can drink.
            <BLANKLINE>
            <BLANKLINE>
            --
            To unsubscribe send an email with subject "unsubscribe" to drinkers@example=
            .com.  Please contact drinkers-manager@example.com for questions.
            <BLANKLINE>
            ------=_Part_7928_16493718.1220401254779
            Content-Type: text/html; charset=WINDOWS-1252
            Content-Transfer-Encoding: quoted-printable
            Content-Disposition: inline
            <BLANKLINE>
            <p>Coming up this Tuesday, <b>all</b> the Tequila you can drink.</p>
            <div id=3D"footer" class=3D"footer"><br /><br />--<br />To unsubscribe send=
             an email with subject &quot;unsubscribe&quot; to <a href=3D"&#0109;ailto&#=
            0058;drinkers&#0064;example.com">drinkers&#0064;example.com</a>.  Please co=
            ntact <a href=3D"&#0109;ailto&#0058;drinkers-manager&#0064;example.com">dri=
            nkers-manager&#0064;example.com</a> for questions.<br /></div>
            ------=_Part_7928_16493718.1220401254779
            <BLANKLINE>
            <BLANKLINE>
            ------=_Part_7928_16493718.1220401254779--
            <BLANKLINE>
            >>> msgs[:] = []

        And multipart messages with attachments
            >>> request = dict(Mail=('From: vodka@example.com\\n'
            ...                      'To: drinkers@example.com\\n'
            ...                      'Subject: I like vodka\\n'
            ...                      'MIME-Version: 1.0\\n'
            ...                      'Content-Type: multipart/mixed; \\n'
            ...                      '  boundary="----=_Part_26204_30744128.1220553085489"\\n'
            ...                      '\\n'
            ...                      '\\n'
            ...                      '------=_Part_26204_30744128.1220553085489\\n'
            ...                      'Content-Type: multipart/alternative; \\n'
            ...                      '  boundary="----=_Part_26205_30325303.1220553085489"\\n'
            ...                      '\\n'
            ...                      '------=_Part_26205_30325303.1220553085489\\n'
            ...                      'Content-Type: text/plain; charset=ISO-8859-1\\n'
            ...                      'Content-Transfer-Encoding: 7bit\\n'
            ...                      'Content-Disposition: inline\\n'
            ...                      '\\n'
            ...                      'I like vodka!\\n'
            ...                      '\\n'
            ...                      '------=_Part_26205_30325303.1220553085489\\n'
            ...                      'Content-Type: text/html; charset=ISO-8859-1\\n'
            ...                      'Content-Transfer-Encoding: 7bit\\n'
            ...                      'Content-Disposition: inline\\n'
            ...                      '\\n'
            ...                      '<div dir="ltr">I like vodka!</div>\\n'
            ...                      '\\n'
            ...                      '------=_Part_26205_30325303.1220553085489--\\n'
            ...                      '\\n'
            ...                      '------=_Part_26204_30744128.1220553085489\\n'
            ...                      'Content-Type: text/html; name=bar.html\\n'
            ...                      'Content-Transfer-Encoding: base64\\n'
            ...                      'X-Attachment-Id: f_fkpps9lu0\\n'
            ...                      'Content-Disposition: attachment; filename=bar.html\\n'
            ...                      '\\n'
            ...                      'PGh0bWw+CiAgICA8Ym9keT5oZWxsbyE8L2JvZHk+CjwvaHRtbD4K\\n'
            ...                      '------=_Part_26204_30744128.1220553085489\\n'
            ...                      'Content-Type: text/plain; name=foo.txt\\n'
            ...                      'Content-Transfer-Encoding: base64\\n'
            ...                      'X-Attachment-Id: f_fkppsgh61\\n'
            ...                      'Content-Disposition: attachment; filename=foo.txt\\n'
            ...                      '\\n'
            ...                      'Zm9vCg==\\n'
            ...                      '------=_Part_26204_30744128.1220553085489--\\n'))
            >>> test_list.listMail(request)
            >>> print msgs[0]
            From: vodka@example.com
            To: drinkers@example.com
            Subject: [Drink More] I like vodka
            MIME-Version: 1.0
            Content-Type: multipart/mixed;
              boundary="----=_Part_26204_30744128.1220553085489"
            X-Mailer: MailBoxer
            Reply-To: drinkers@example.com
            Errors-To: drinkers-manager@example.com
            List-Subscribe: <mailto:drinkers@example.com?subject=subscribe>
            List-Unsubscribe: <mailto:drinkers@example.com?subject=unsubscribe>
            List-Id: drinkers@example.com
            Precedence: Bulk
            <BLANKLINE>
            <BLANKLINE>
            ------=_Part_26204_30744128.1220553085489
            Content-Type: multipart/alternative;
              boundary="----=_Part_26205_30325303.1220553085489"
            <BLANKLINE>
            ------=_Part_26205_30325303.1220553085489
            Content-Type: text/plain; charset=ISO-8859-1
            Content-Transfer-Encoding: 7bit
            Content-Disposition: inline
            <BLANKLINE>
            I like vodka!
            <BLANKLINE>
            <BLANKLINE>
            --
            To unsubscribe send an email with subject "unsubscribe" to drinkers@example.com.  Please contact drinkers-manager@example.com for questions.
            <BLANKLINE>
            ------=_Part_26205_30325303.1220553085489
            Content-Type: text/html; charset=ISO-8859-1
            Content-Transfer-Encoding: 7bit
            Content-Disposition: inline
            <BLANKLINE>
            <div dir="ltr">I like vodka!</div>
            <div id="footer" class="footer"><br /><br />--<br />To unsubscribe send an email with subject &quot;unsubscribe&quot; to <a href="&#0109;ailto&#0058;drinkers&#0064;example.com">drinkers&#0064;example.com</a>.  Please contact <a href="&#0109;ailto&#0058;drinkers-manager&#0064;example.com">drinkers-manager&#0064;example.com</a> for questions.<br /></div>
            ------=_Part_26205_30325303.1220553085489--
            <BLANKLINE>
            ------=_Part_26204_30744128.1220553085489
            Content-Type: text/html; name=bar.html
            Content-Transfer-Encoding: base64
            X-Attachment-Id: f_fkpps9lu0
            Content-Disposition: attachment; filename=bar.html
            <BLANKLINE>
            PGh0bWw+CiAgICA8Ym9keT5oZWxsbyE8L2JvZHk+CjwvaHRtbD4K
            ------=_Part_26204_30744128.1220553085489
            Content-Type: text/plain; name=foo.txt
            Content-Transfer-Encoding: base64
            X-Attachment-Id: f_fkppsgh61
            Content-Disposition: attachment; filename=foo.txt
            <BLANKLINE>
            Zm9vCg==
            ------=_Part_26204_30744128.1220553085489--
            <BLANKLINE>
            >>> msgs[:] = []

        On a base64 encoded message, the footer should be encoded too
            >>> import base64
            >>> msg = 'encoded'
            >>> enc_msg = base64.encodestring(msg)
            >>> request = dict(Mail=('From: secretmessage@example.com\\n'
            ...                      'To: drinkers@example.com\\n'
            ...                      'Subject: My message is\\n'
            ...                      'MIME-Version: 1.0\\n'
            ...                      'Content-Type: text/plain; charset=us-ascii\\n'
            ...                      'Content-Disposition: inline\\n'
            ...                      'Content-Transfer-Encoding: base64\\n'
            ...                      '\\n'
            ...                      '%s\\n' % enc_msg))
            >>> test_list.listMail(request)
            >>> print msgs[0]
            From: secretmessage@example.com
            To: drinkers@example.com
            Subject: [Drink More] My message is
            MIME-Version: 1.0
            Content-Type: text/plain; charset=us-ascii
            Content-Disposition: inline
            Content-Transfer-Encoding: base64
            X-Mailer: MailBoxer
            Reply-To: drinkers@example.com
            Errors-To: drinkers-manager@example.com
            List-Subscribe: <mailto:drinkers@example.com?subject=subscribe>
            List-Unsubscribe: <mailto:drinkers@example.com?subject=unsubscribe>
            List-Id: drinkers@example.com
            Precedence: Bulk
            <BLANKLINE>
            ...
            <BLANKLINE>
            >>> import email
            >>> mailmsg = email.message_from_string(msgs[0])
            >>> print base64.decodestring(mailmsg.get_payload())
            encoded
            <BLANKLINE>
            <BLANKLINE>
            --
            To unsubscribe send an email with subject "unsubscribe" to drinkers@example.com.  Please contact drinkers-manager@example.com for questions.
            <BLANKLINE>
            >>> msgs[:] = []

        Use a message that requires using quoted printable strings
            >>> msg = 'Beer before liquor, never been sicker. But, liquor is '
            >>> msg += 'quicker.\\n\\n-- \\nWise man\\n'
            >>> import quopri
            >>> enc_msg = quopri.encodestring(msg)

        On a quoted printable encoded message, the footer should be encoded too
            >>> request = dict(Mail=('From: quotedmessage@example.com\\n'
            ...                      'To: drinkers@example.com\\n'
            ...                      'Subject: My quoted message is\\n'
            ...                      'MIME-Version: 1.0\\n'
            ...                      'Content-Type: text/plain; charset=us-ascii\\n'
            ...                      'Content-Disposition: inline\\n'
            ...                      'Content-Transfer-Encoding: quoted-printable\\n'
            ...                      '\\n'
            ...                      '%s' % enc_msg))
            >>> test_list.listMail(request)
            >>> print msgs[0]
            From: quotedmessage@example.com
            To: drinkers@example.com
            Subject: [Drink More] My quoted message is
            MIME-Version: 1.0
            Content-Type: text/plain; charset=us-ascii
            Content-Disposition: inline
            Content-Transfer-Encoding: quoted-printable
            X-Mailer: MailBoxer
            Reply-To: drinkers@example.com
            Errors-To: drinkers-manager@example.com
            List-Subscribe: <mailto:drinkers@example.com?subject=subscribe>
            List-Unsubscribe: <mailto:drinkers@example.com?subject=unsubscribe>
            List-Id: drinkers@example.com
            Precedence: Bulk
            <BLANKLINE>
            ...
            >>> mailmsg = email.message_from_string(msgs[0])
            >>> print quopri.decodestring(mailmsg.get_payload())
            Beer before liquor, never been sicker. But, liquor is quicker.
            <BLANKLINE>
            --
            Wise man
            <BLANKLINE>
            <BLANKLINE>
            --
            To unsubscribe send an email with subject "unsubscribe" to drinkers@example.com.  Please contact drinkers-manager@example.com for questions.
            <BLANKLINE>
            >>> msgs[:] = []
        """

        # Send a mail to all members of the list.
        mailString = self.getMailFromRequest(request)

        # store mail in the archive? get context for the mail...
        context = None
        if self._is_archived():
            context = self.manage_addMail(mailString)
        if context is None:
            context = self

        msg_in_archive_url = context.absolute_url()

        putils = getToolByName(self, 'plone_utils', None)
        if putils is not None:
            site_encoding = putils.getSiteEncoding()
        else:
            site_encoding = 'utf-8'

        emailmsg = email.message_from_string(mailString)

        returnpath = self.getValueFor('returnpath')
        if not returnpath:
            returnpath = self.manager_email

        email_subject = emailmsg.get('Subject', 'No Subject')
        ml_title = '[%s]' % self.getValueFor('title')
        if ml_title not in email_subject:
            email_subject = '%s %s' % (ml_title, email_subject)

        def _set_header(header, value):
            if header in emailmsg:
                emailmsg.replace_header(header, value)
            else:
                emailmsg[header] = value

        _set_header('Subject', email_subject)
        _set_header('X-Mailer', self.getValueFor('xmailer'))
        _set_header('Reply-To', self.getValueFor('mailto'))
        _set_header('Errors-To', returnpath)
        _set_header('List-Subscribe', '<mailto:%s?subject=%s>' % (self.getValueFor('mailto'), self.getValueFor('subscribe')))
        _set_header('List-Unsubscribe', '<mailto:%s?subject=%s>' % (self.getValueFor('mailto'), self.getValueFor('unsubscribe')))
        _set_header('List-Id', self.getValueFor('mailto'))
        _set_header('Precedence', 'Bulk')

        # Get immediate delivery members along with digest subscribers
        digest_list = IMembershipDigestList(self)

        # Add message to the digest, if necessary, but before the
        # footer is attached, because digests have their own footer
        if digest_list.has_digest_subscribers():
            digest = IDigestStorage(self)
            # make a copy of the message so adding the footers to the
            # message object below won't impact the one stored in the
            # digest
            digmailmsg = deepcopy(emailmsg)
            # we also pass along the url of the message in a header
            # so we can display it in the digest
            # maybe it would be better to store only the relevant part and
            # construct the rest of the url when the digest is generated
            digmailmsg['X-listen-message-url'] = context.absolute_url()
            digest.add_message_to_digest(digmailmsg)

        if self._is_archived():
            email_footer = default_email_text.mail_footer_archived
        else:
            email_footer = default_email_text.mail_footer_unarchived
        email_footer = translate(Message(email_footer, mapping=dict(
                                           archive_url=msg_in_archive_url,
                                           mailto=self.mailto,
                                           manager_email=self.manager_email)))
        # the footer is unicode at this point
        # we'll take care of encoding it properly when we place on message

        # convenience function to obtain the charset of a particular msg
        def _msg_charset(msgpart):
            return msgpart.get_content_charset() or site_encoding

        # here we define a convenience function to attach a footer properly on
        # a message payload
        def _set_footer_with_encoding(msgpart, footer, html=False):
            """We attach the footer as appropriate for the transfer
               encoding on the message. The footer must be passed in
               as unicode.  If html is set to True, then we need to
               inject it into the document before the </body> tag
               instead of just appending it."""
            if not isinstance(footer, unicode):
                raise TypeError('Footer passed in must be unicode, but it is '
                                + footer)
            # this function is expected to be called on a message that is not
            # multipart
            if msgpart.is_multipart():
                raise TypeError('_set_footer_with_encoding must be called with'
                                ' a non multipart message')

            payload = msgpart.get_payload(decode=True)
            footer_encoding = _msg_charset(msgpart)
            if html:
                # look for </body> tag
                try:
                    index = payload.index('</body>')
                    with_footer = (payload[:index] +
                                   footer.encode(footer_encoding) +
                                   payload[index:])
                except ValueError:
                    # no </body>, just append it
                    html = False

            if not html:
                # might be html but w/o a </body> tag
                with_footer = payload + footer.encode(footer_encoding)

            transfer_encoding = msgpart.get('Content-Transfer-Encoding')
            if transfer_encoding is not None:
                transfer_encoding = transfer_encoding.lower()
                if transfer_encoding == 'quoted-printable':
                    msgpart.set_payload(quopri.encodestring(with_footer))
                elif transfer_encoding == 'base64':
                    msgpart.set_payload(base64.encodestring(with_footer))
                else:
                    # if it's 7bit, setting it un-encoded is fine
                    msgpart.set_payload(with_footer)
            else:
                # with no content transfer encoding, we simply set the payload
                msgpart.set_payload(with_footer)

        textbody = None
        htmlbody = None
        if emailmsg.is_multipart():
            # for multipart messages, we have to figure out which
            # message parts are the body and append the footer to only
            # those parts; Mailboxer assumes that the first text-y
            # part will be the body, we follow that lead.  assume an
            # initial multipart/alternative is a wrapper for plain
            # text and html text versions of the message body,
            # otherwise there's only one rendering of the body.

            # XXX this may not cover all possibilities... we need to
            # write tests for this against a large corpus of messages,
            # from a bunch of different email clients, to make sure
            # we're handling this correctly in as many cases as
            # possible
            
            alternatives = None
            for part in emailmsg.walk():
                if part.get_main_type() is None:
                    # no Content-Type, assume plain text if we don't
                    # already have a textbody
                    if textbody is None:
                        textbody = part
                        if alternatives is None:
                            break
                elif part.get_main_type().lower() == 'multipart' and \
                         part.get_subtype().lower() == 'alternative':
                    alternatives = [m for m in part.walk()]
                    alternatives = dict.fromkeys(alternatives)
                elif alternatives is not None and \
                         part not in alternatives:
                    # we're past the alternatives, we're done
                    break
                elif part.get_main_type().lower() == 'text':
                    if part.get_subtype().lower() == 'plain':
                        textbody = part
                    elif part.get_subtype().lower() == 'html':
                        htmlbody = part
                    if alternatives is None:
                        # there's only one, we're done
                        break

        else:
            if emailmsg.get_main_type() is None:
                # no Content-Type specified, assume plain text
                textbody = emailmsg
            elif emailmsg.get_main_type().lower() == 'text':
                if emailmsg.get_subtype().lower() == 'plain':
                    textbody = emailmsg
                elif emailmsg.get_subtype().lower() == 'html':
                    htmlbody = emailmsg

        # by here we've got the body message(s), append the footer
        if textbody is not None:
            # make sure we have a newline at the end of the message
            # before the footer
            footer = u'\n' + email_footer
            _set_footer_with_encoding(textbody, footer)

        if htmlbody is not None:
            # XXX do html mail clients have standard ids/classes
            # for styling?
            # XXX this is completely insufficient for injecting
            # the footer into an html message
            footer = (u'<div id="footer" class="footer"><br />%s</div>'
                      % convertWebIntelligentPlainTextToHtml(email_footer))
            _set_footer_with_encoding(htmlbody, footer, html=True)

        # send the message out to the immediate subscribers
        maillist = digest_list.nondigest_subscribers
        self._send_msgs(maillist, emailmsg.as_string(), returnpath)

        # fire an event notifying that a message was received
        notify(NewMsgDeliveredEvent(self))

    def send_digest(self):
        """
        Sends the digest and returns the number of messages sent.
        """
        digest_list = IMembershipDigestList(self)
        digest_storage = IDigestStorage(self)
        digest = digest_storage.get_digest()
        if not digest:
            # no digest messages, nothing to do
            return 0
        maillist = digest_list.digest_subscribers
        if not maillist:
            # no digest receivers, clear the digest and return
            digest_storage.consume_digest()
            return 0

        returnpath = self.getValueFor('returnpath')
        if not returnpath:
            returnpath = self.manager_email

        constructor = self.digest_constructor()
        # XXX 2 pass lock to recover gracefully from errors?
        digest = digest_storage.consume_digest()
        digest_msg = constructor.construct_digest(digest)
        self._send_msgs(maillist, digest_msg.as_string(), returnpath)
        return len(digest)


# Event listener to catalog mail_obj using the ISearchableArchive utility
def catalogMailBoxerMail(mail_obj, event):
    # We need to pass a context because the lookup tool leaves us in the
    # Application context.
    util = zapi.getUtility(ISearchableArchive, context=mail_obj)
    util.indexNewMessage(mail_obj)

# Event listeners for doing the normal catalog unregistration, etc.
def MailingListWillBeMoved(ml, event):
    if not IObjectWillBeAddedEvent.providedBy(event):
        ml.unindexObject()

def MailingListMoved(ml, event):
    if not IObjectRemovedEvent.providedBy(event) and \
       not IObjectAddedEvent.providedBy(event):
        # don't bother with this on removal, it's pointless, and it's already
        # done on add.
        ml.reindexObject()

def MailingListModified(ml, event):
    if not IContainerModifiedEvent.providedBy(event):
        ml.reindexObject()
    convert_manager_emails_to_memberids(ml)

def convert_manager_emails_to_memberids(ml):
    """
    Converts all email addresses listed into member ids.
    If it's not an email address, then it does a lookup to verify that the
    member id is valid. If it's not, the item is discarded silently.

    Create a test mailing list
        >>> from Products.listen.extras.tests import TestMailingList
        >>> test_ml = TestMailingList()

    Add some sample manager input
        >>> test_ml.managers = ('dummy1', u'valid-email@example.com', u'valid_user')

    Change what it means to be valid for the test
        >>> valid_ids = [u'valid_user']
        >>> from Products.listen.interfaces import IMemberLookup
        >>> from zope.component import getUtility
        >>> email_converter = getUtility(IMemberLookup)
        >>> email_converter._lookup_memberid = lambda memid:memid in valid_ids
        >>> email_converter.to_memberid = lambda email:email == u'valid-email@example.com' and u'other_valid_user' or None

    And finally call the function with our stubs set up
        >>> from Products.listen.content.mailinglist import convert_manager_emails_to_memberids
        >>> convert_manager_emails_to_memberids(test_ml)

    Verify new expected list of managers
        >>> test_ml.managers
        (u'other_valid_user', u'valid_user')
    """
    # make sure managers point to userids if available
    managers = list(ml.managers)
    to_remove = []
    for idx, manager in enumerate(managers):
        if is_email(manager):
            user_id = lookup_member_id(manager, ml)
            if user_id:
                managers[idx] = unicode(user_id)
        else:
            # make sure id exists
            if not lookup_email(manager, ml):
                to_remove.append(manager)
    ml.managers = tuple(set(managers) - set(to_remove))


def subscribe_new_managers(ml):
    policy = getAdapter(ml, IManagerTTWMembershipPolicy)
    mem_list = IWriteMembershipList(ml)

    new_managers = list(ml.managers)
    mtool = getToolByName(ml, 'portal_membership')
    creator = mtool.getAuthenticatedMember().getId()

    # subscribes the list creator directly
    if creator in new_managers:
        mem_list.subscribe(creator)
        new_managers.remove(creator)

    # sends all other managers a subscription confirmation email
    for manager in new_managers:
        request = {'action': 'add_allowed_sender', 'email': manager}
        policy_result = policy.enforce(request)
        if policy_result == MEMBERSHIP_ALLOWED:
            mem_list.add_allowed_sender(manager)

        request = {'action': 'subscribe', 'email': manager}
        policy.enforce(request)
    


def MailingListAdded(ml, event):
    # append properties to MailBoxer's list
    if not IContainerModifiedEvent.providedBy(event):
        ml.reindexObject()
    ml._properties += ({'id':'manager_email', 'type':'string', 'mode':'wd'},)
    convert_manager_emails_to_memberids(ml)
    subscribe_new_managers(ml)


# And a vocabulary
def archiveOptionsVocabulary(context):
    archive_options = [(_(u'The entire message, including attachments'),0), 
                       (_(u'The message text only'),1), 
                       (_(u'Do not archive messages'),2)]
    return SimpleVocabulary.fromItems(archive_options)


class ListTypeChanged(object):
    """ implementation to keep track of how a list type changed """
    implements(IListTypeChanged)
    def __init__(self, mailing_list, old_list_type, new_list_type):
        self.mailing_list = mailing_list
        self.old_list_type = old_list_type
        self.new_list_type = new_list_type

@adapter(IListTypeChanged)
def list_type_changed(event):
    """
    Setup object for testing
    >>> from Products.listen.extras.tests import TestMailingList
    >>> from Products.listen.content import tests
    >>> from Products.listen.interfaces import IMembershipPendingList
    >>> from Products.listen.interfaces import IPostPendingList
    >>> from Products.listen.interfaces import IWriteMembershipList
    >>> from zope.component import getAdapter
    >>> from zope.interface import directlyProvides
    >>> from Products.listen.interfaces import IPublicList
    >>> from Products.listen.interfaces import IPostModeratedList
    >>> from Products.listen.interfaces import IMembershipModeratedList
    
    >>> ml = TestMailingList()
    >>> mtool = tests.DummyMembershipTool('')
    >>> ml.portal_membership = mtool
    >>> mtool.result = None
    >>> posts_sent = []
    >>> def stub_listMail(post):
    ...    posts_sent.append(post)
    >>> ml.listMail = stub_listMail
    >>> pending_sub_mod_email = getAdapter(ml, IMembershipPendingList, 'pending_sub_mod_email')
    >>> pending_mod_post = getAdapter(ml, IPostPendingList, 'pending_mod_post')
    >>> pending_pmod_post = getAdapter(ml, IPostPendingList, 'pending_pmod_post')
    >>> mem_list = IWriteMembershipList(ml)
    >>> mem_list.allowed_senders_data
    {}

    Test a list change from public to post-moderated
    >>> sample_header = dict(From='peanut@example.com', To='some_list@example.com', Subject='I am Ten Ninjas')
    >>> sample_body = 'ninjas like to wail on guitars'
    >>> post = dict(header=sample_header, body=sample_body)
    >>> post2 = post.copy()
    >>> pending_mod_post.add('waiting@example.com', post=post)
    >>> pending_mod_post.add('waiting2@example.com', post=post2)
    >>> from Products.listen.content.mailinglist import ListTypeChanged, list_type_changed
    >>> ltc = ListTypeChanged(ml, IPublicList, IPostModeratedList)
    >>> directlyProvides(ml, IPublicList)
    >>> IPublicList.providedBy(ml)
    True
    >>> IMembershipModeratedList.providedBy(ml)
    False
    >>> IPostModeratedList.providedBy(ml)
    False
    >>> list_type_changed(ltc)
    >>> len(pending_mod_post.get_user_emails())
    0
    >>> len(pending_pmod_post.get_user_emails())
    2

    Test a list change from post-moderated to public when one post
    is from a subscriber (their post should be sent)
    >>> mem_list.subscribe('waiting2@example.com')
    >>> ltc = ListTypeChanged(ml, IPostModeratedList, IPublicList)
    >>> directlyProvides(ml, IPostModeratedList)
    >>> list_type_changed(ltc)
    >>> len(pending_mod_post.get_user_emails())
    1
    >>> len(pending_pmod_post.get_user_emails())
    0
    >>> posts_sent[0]['Mail']
    'To: some_list@example.com\\nFrom: peanut@example.com\\nSubject: I am Ten Ninjas\\r\\n\\r\\nninjas like to wail on guitars'

    Test a list change from public to membership-moderated and back and back
    >>> ltc = ListTypeChanged(ml, IPublicList, IMembershipModeratedList)
    >>> directlyProvides(ml, IPublicList)
    >>> list_type_changed(ltc)
    >>> mem_list.is_subscribed('peanut@happening.com')
    False
    >>> mem_list.is_subscribed('peanutbarn@happening.com')
    False
    >>> pending_sub_mod_email.add('peanut@happening.com')
    >>> pending_sub_mod_email.add('peanutbarn@happening.com')
    >>> ltc = ListTypeChanged(ml, IMembershipModeratedList, IPublicList)
    >>> directlyProvides(ml, IMembershipModeratedList)
    >>> list_type_changed(ltc)
    >>> mem_list.is_subscribed('peanut@happening.com')
    True
    >>> mem_list.is_subscribed('peanutbarn@happening.com')
    True
    >>> ltc = ListTypeChanged(ml, IPublicList, IMembershipModeratedList)
    >>> directlyProvides(ml, IPublicList)
    >>> list_type_changed(ltc)

    Test a list change from membership-moderated to post-moderated and back
    >>> pending_sub_mod_email.add('twix@happening.com')
    >>> pending_sub_mod_email.add('twixes@happening.com')
    >>> mem_list.is_subscribed('twix@happening.com')
    False
    >>> mem_list.is_subscribed('twixes@happening.com')
    False
    >>> ltc = ListTypeChanged(ml, IMembershipModeratedList, IPostModeratedList)
    >>> directlyProvides(ml, IMembershipModeratedList)
    >>> list_type_changed(ltc)
    >>> mem_list.is_subscribed('twix@happening.com')
    True
    >>> mem_list.is_subscribed('twixes@happening.com')
    True
    >>> len(pending_pmod_post.get_user_emails())
    1
    >>> len(posts_sent)
    1
    >>> mem_list.subscribe('waiting@example.com')
    >>> ltc = ListTypeChanged(ml, IPostModeratedList, IMembershipModeratedList)
    >>> directlyProvides(ml, IPostModeratedList)
    >>> list_type_changed(ltc)
    >>> len(posts_sent)
    2
    >>> len(pending_pmod_post.get_user_emails())
    0



    """

    old_list_type = event.old_list_type
    new_list_type = event.new_list_type
    if old_list_type == new_list_type: return

    ml = event.mailing_list
    export_adapter = IExportListType(ml)
    pending_members, pending_posts = export_adapter.clear()

    # remove the old list type and mark with the new one
    directlyProvides(ml, directlyProvidedBy(ml)-old_list_type)
    alsoProvides(ml, new_list_type)

    # now that the list is correctly marked, we can import
    import_adapter = IImportListType(ml)
    import_adapter.import_list(pending_members, pending_posts)


class ListTypeDisplayer(object):
    adapts(IListTypeDefinition)
    implements(IDisplayListTypes)

    def __init__(self, context):
        self.context = context

    def create_description(self):
        name = self.context.title
        description = self.context.description
        return '%(name)s<br /><span class="formHelp">%(description)s</span>' % locals()

def list_type_vocabulary(context):
    all_list_types = [lt for name, lt in getUtilitiesFor(IListTypeDefinition)]
    all_list_types.sort(key=lambda x:x.index)

    terms = []
    for lt in all_list_types:
        display = IDisplayListTypes(lt)
        name_and_description = display.create_description()
        term = SimpleTerm(lt, token=str(lt.title), title=name_and_description)
        terms.append(term)
        
    return SimpleVocabulary(terms)
