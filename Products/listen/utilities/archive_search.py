import transaction

from zope.interface import implements
from zope.app.container.interfaces import IObjectRemovedEvent
from zope.app.container.interfaces import IObjectAddedEvent

from Products.ZCatalog.ZCatalog import ZCatalog
from Products.ZCTextIndex.Lexicon import CaseNormalizer
from Products.ZCTextIndex.Lexicon import Splitter
from Products.ZCTextIndex.Lexicon import StopWordRemover

from Products.CMFPlone.utils import base_hasattr

from Products.listen.interfaces import ISearchableArchive
from Products.listen.interfaces import ISearchableMessage
from Products.listen.lib.common import get_utility_for_context

class MailCatalog(ZCatalog):
    """A specialized catalog for mailing lists."""
    id = "mail_catalog"

    # Stolen from CMF's CatalogTool
    def __init__(self, id):
        ZCatalog.__init__(self, id)
        self._initIndexes()

    # Reimplement to use the searchable object wrapper, so that objects are
    # always reindexed with full calculated metadata.
    def catalog_object(self, obj, uid, *args, **kwargs):
        search_obj = ISearchableMessage(obj)
        ZCatalog.catalog_object(self, search_obj, uid, *args, **kwargs)

    # Should be using CMFSetup for this
    def _initIndexes(self):
        # Content indexes
        self._catalog.indexes.clear()
        for index_name, index_type, extra in self.enumerateIndexes():
            self.addIndex(index_name, index_type, extra=extra)

        # Cached metadata
        self._catalog.names = ()
        self._catalog.schema.clear()
        for column_name in self.enumerateColumns():
            self.addColumn(column_name)

    def enumerateIndexes(self):

        idxs = ( ('from_addr', 'FieldIndex')
               , ('date', 'Managable FieldIndex')
               , ('in_reply_to', 'FieldIndex')
               , ('references', 'KeywordIndex')
               , ('getId', 'FieldIndex')
               , ('message_id', 'FieldIndex')
               , ('path', 'ExtendedPathIndex')
               , ('isInitialMessage', 'FieldIndex')
               , ('responses', 'FieldIndex')
               , ('modification_date', 'Managable FieldIndex')
               )
        return tuple([(n, t, None) for n, t in idxs])

    def enumerateColumns(self):
        """Return a sequence of schema names to be cached.

        Creator is deprecated and may go away, use listCreators!
        """
        return ( 'subject'
               , 'from_addr'
               , 'date'
               , 'message_id'
               , 'getId'
               , 'references'
               , 'in_reply_to'
               , 'responses'
               , 'modification_date'
               , 'isInitialMessage'
               )

    def manage_afterAdd(self, item, container):
        # Add the necessary Text indexes and make the date index efficient
        if item is self and not base_hasattr(self, 'mail_lexicon'):
            class args:
                def __init__(self, **kw):
                    self.__dict__.update(kw)

            self.manage_addProduct['ZCTextIndex'].manage_addLexicon(
                'mail_lexicon',
                elements=[
                    args(group='Case Normalizer', name='Case Normalizer'),
                    args(group='Stop Words', name=" Don't remove stop words"),
                    args(group='Word Splitter', name="Unicode Whitespace splitter"),
                ]
                )

            extra = args( doc_attr = 'SearchableText',
                          lexicon_id = 'mail_lexicon',
                          index_type  = 'Okapi BM25 Rank' )
            if 'SearchableText' in self.indexes():
                self.manage_delIndex(['SearchableText'])
            self.manage_addIndex('SearchableText', 'ZCTextIndex', extra=extra)

            extra = args( doc_attr = 'subject',
                          lexicon_id = 'mail_lexicon',
                          index_type  = 'Okapi BM25 Rank' )
            if 'subject' in self.indexes():
                self.manage_delIndex(['subject'])
            self.manage_addIndex('subject', 'ZCTextIndex', extra=extra)

            self.Indexes['date'].manage_changeProperties(TermType='DateTimeInteger')
            self.clearIndex('date')


class ZCatalogSearchArchive(MailCatalog):
    """An implementation of ISearchableArchive that uses an internal ZCatalog.

    Perform some basic test configuration:
        >>> import Products.Five
        >>> from Products.Five import zcml
        >>> zcml.load_config('meta.zcml', Products.Five)
        >>> zcml.load_config("permissions.zcml", Products.Five)
        >>> zcml.load_config("configure.zcml", Products.Five.site)
        >>> from Products.listen.utilities import tests
        >>> zcml.load_config('configure.zcml', tests)

    Let's get ourselves something that looks like a Mailing List, and register
    our utility with it:
        >>> ml = tests.install_fake_ml(self.folder)
        >>> from zope.app.component.hooks import setSite
        >>> setSite(ml)
        >>> from Products.listen.interfaces import ISearchableArchive
        >>> from Products.listen.lib.common import get_utility_for_context
        >>> search = get_utility_for_context(ISearchableArchive, context=ml)

    Ensure that our catalog has the expected indexes and metadata:
        >>> search.indexes()
        ['responses', 'modification_date', 'from_addr', 'getId', 'SearchableText', 'references', 'isInitialMessage', 'date', 'path', 'in_reply_to', 'message_id', 'subject']
        >>> search.schema()
        ['responses', 'modification_date', 'from_addr', 'getId', 'references', 'date', 'isInitialMessage', 'in_reply_to', 'message_id', 'subject']

    Let's create a new message and register it with the catalog:
        >>> from Products.listen.interfaces import IMailFromString
        >>> from zope.app.zapi import createObject
        >>> mail_id = 'message1'
        >>> from_addr = 'test@example.com'
        >>> list_addr = 'list@example.com'
        >>> subject = 'Test Message'
        >>> date = 'Mon, 07 Nov 2005 15:30 +000'
        >>> message_id = '<message_num1@example.com>'
        >>> new_message = createObject('listen.MailFactory',
        ...                            mail_id, from_addr, subject, date)
        >>> new_id = ml._setObject(mail_id, new_message)
        >>> new_message = getattr(ml, new_id)
        >>> mail_string = '''From: %s
        ... To: %s
        ... Subject: %s
        ... Date: %s
        ... Message-ID: %s
        ...
        ... A new message.'''%(from_addr, list_addr, subject, date, message_id)
        >>> IMailFromString(new_message).createMailFromMessage(mail_string)
        >>> search.indexNewMessage(new_message)
        >>> new_message.body
        u'A new message.'
        >>> new_message.from_addr
        u'test@example.com'

    Perform some searches on our new message
        >>> results = search.getToplevelMessages()
        >>> len(results)
        1
        >>> results[0].message_id
        '<message_num1@example.com>'
        >>> results[0].getId
        'message1'
        >>> search.resolveMessageId(message_id).message_id
        '<message_num1@example.com>'

    There is no thread yet:
        >>> search.getNextInThread(message_id)
        >>> search.getParentMessage(message_id)
        >>> search.getNextByDate(message_id)
        >>> search.getPreviousByDate(message_id)
        >>> search.getMessageReplies(message_id)
        []
        >>> search.getMessageReferrers(message_id)
        []

    Add a response:
        >>> mail_id2 = 'message2'
        >>> from_addr2 = 'test2@example.com'
        >>> list_addr2 = 'list@example.com'
        >>> subject2 = 'Re: Test Message'
        >>> date2 = 'Mon, 07 Nov 2005 15:35 +000'
        >>> message_id2 = '<message_num2@example.com>'
        >>> in_reply_to2 = '<message_num1@example.com>'
        >>> references2 = '<message_num1@example.com>'
        >>> new_message2 = createObject('listen.MailFactory',
        ...                             mail_id2, from_addr2, subject2, date2)
        >>> new_id = ml._setObject(mail_id2, new_message2)
        >>> new_message2 = getattr(ml, new_id)
        >>> mail_string2 = '''From: %s
        ... To: %s
        ... Subject: %s
        ... Date: %s
        ... Message-ID: %s
        ... In-Reply-To: %s
        ... References: %s
        ...
        ... A new response.'''%(from_addr2, list_addr2, subject2, date2, message_id2, in_reply_to2, references2)
        >>> IMailFromString(new_message2).createMailFromMessage(mail_string2)
        >>> search.indexNewMessage(new_message2)

    Perform some more searches:
        >>> results = search.getToplevelMessages()
        >>> len(results)
        1
        >>> search.getNextInThread(message_id).message_id
        '<message_num2@example.com>'
        >>> search.getParentMessage(message_id2).message_id
        '<message_num1@example.com>'
        >>> search.getNextByDate(message_id).message_id
        '<message_num2@example.com>'
        >>> search.getPreviousByDate(message_id2).message_id
        '<message_num1@example.com>'
        >>> results = search.getMessageReplies(message_id)
        >>> len(results)
        1
        >>> results[0].message_id
        '<message_num2@example.com>'
        >>> results = search.getMessageReferrers(message_id)
        >>> len(results)
        1
        >>> results[0].message_id
        '<message_num2@example.com>'

    Search for a particular string in all messages:
        >>> results = search(SearchableText='response')
        >>> len(results)
        1

    Search for a particular string in all messages:
        >>> results = search.search('not this')
        Traceback (most recent call last):
        ...
        ParseError: Token 'ATOM' required, 'not' found

"""

    implements(ISearchableArchive)

    def indexNewMessage(self, message_object):
        """See interface docs"""
        #Override indexObject to adapt the mail object with additional search parameters

        url = '/'.join( message_object.getPhysicalPath() )
        self.catalog_object(message_object, url)

    def getToplevelMessages(self, start=None, end=None, recent_first=False):
        """See interface docs."""
        query = {'isInitialMessage': True,
                 'sort_on': 'date'}
        if recent_first:
            # Sort using the special variable containing the date of the most
            # recent response.
            query['sort_on'] = 'modification_date'
            query['sort_order'] = 'descending'
        if start and not end:
            query['date']={'query':[start], 'range':'min'}
        elif end and not start:
            query['date']={'query':[end], 'range':'max'}
        elif end and start:
            query['date']={'query':[start,end], 'range':'min:max'}
        results = self.searchResults(query)
        return results

    def getMessageReplies(self, message_id):
        """See interface docs."""
        results = self.searchResults(in_reply_to=message_id, sort_on='date')
        return results

    def getMessageReferrers(self, message_id, reversed=False):
        """See interface docs.  Despite the fact that the RFC is very clear
        about what should go in the references field, many mailers to not
        include the full thread in this list.  Nearly all mailers include the
        initial mssage of the thread and the the direct parent, though some
        (Outlook) don't bother to set the header. SearchableMessage has a
        workaround for messages with no header set, but messages with only a
        partial list in references will yield bad results.  As a result we
        can't really depend on this field for anything but getting the
        thread from the initial message in a thread (only then because of
        the outlook workaround in SearchableMessage, and perhaps some other
        mailers will mess this up)."""
        results = self.searchResults(references=message_id, sort_on='date',
                    sort_order=(reversed and 'descending' or 'ascending'))
        return results

    def resolveMessageId(self, message_id):
        """See interface docs"""
        results = self.searchResults(message_id=message_id)
        return results and results[0] or None

    def resolveMessageIds(self, message_ids):
        """See interface docs"""
        results = self.searchResults(message_id=message_ids, sort_on = 'date')
        return results

    def getNextInThread(self, message_id):
        """See interface docs"""
        replies  = self.getMessageReplies(message_id)
        if replies:
            return replies[0]
        referrers = self.getMessageReferrers(message_id)
        if referrers:
            return referrers[0]
        return self._getNextMessage(message_id)

    def getParentMessage(self, message_id):
        """See interface docs"""
        message = self.resolveMessageId(message_id)
        if message is None:
            return None
        reply_to = message.in_reply_to
        if not reply_to:
            # Use references if there is no parent
            reply_to = message.references
            if not reply_to:
                # No ancestors
                return None
        # We want to get the most recent (i.e. latest) message referred to
        results = self.searchResults(message_id=reply_to, sort_on='date',
                          sort_order='reversed')
        return results and results[0] or None

    def getNextByDate(self, message_id):
        """See interface docs"""
        message = self.resolveMessageId(message_id)
        if message is None:
            return None
        result = self.searchResults(date = {'query': message.date, 'range': 'min'},
                              sort_on = 'date')
        found_msg = False
        for brain in result:
            # Skip all messages up to the current message
            # BBB: We should probably be using AdvancedQuery to get a
            # deterministic order here in case messages arrive in the same
            # second.
            if found_msg:
                return brain
            if brain.message_id == message_id:
                found_msg = True
        return None

    def getPreviousByDate(self, message_id):
        """See interface docs"""
        message = self.resolveMessageId(message_id)
        if message is None:
            return None
        result = self.searchResults(date = {'query': message.date, 'range': 'max'},
                              sort_on = 'date', sort_order='descending')
        found_msg = False
        for brain in result:
            # Skip all messages up to the current message
            # BBB: We should probably be using AdvancedQuery to get a
            # deterministic order here in case messages arrive in the same
            # second.
            if found_msg:
                return brain
            if brain.message_id == message_id:
                found_msg = True
        return None

    def getAllMessagesInPath(self, path, recent_first=False):
        result = self.searchResults(path={'query': path, 'depth': -1},
                              sort_on = 'date',
                  sort_order = (recent_first and 'descending' or 'ascending'))
        return result

    def search(self, text):        
        return self.searchResults(SearchableText=text)

    def _getNextMessage(self, message_id):
        """Finds the next message in the thread not including responses to
        the current message.  To do this we walk along our ancestors
        looking for any later sibling messages."""

        message = self.resolveMessageId(message_id)
        if message is None:
            return None
        start_id = message_id
        start_date = message.date
        # This is the reference message, we want to find siblings of it
        prev_msg = start_id
        # The is our immediate ancestor, we use it to search for siblings
        current_msg = message.in_reply_to
        current_date = start_date
        while current_msg:
            # Find all older siblings of prev_msg (including the message
            # itself unfortunately)
            result = self.searchResults(in_reply_to=current_msg,
                            date = {'query': current_date, 'range': 'min'},
                            sort_on = 'date')
            found_prev = False
            for brain in result:
                # Attempt to avoid cyclical threads when messages arrive at
                # the same time by skipping all siblings that are returned
                # before prev_msg.
                # XXX: We should probably be using AdvancedQuery to get a
                # deterministic order here, in case messages arrive in the
                # same second.
                if found_prev:
                    return brain
                if brain.message_id == prev_msg:
                    found_prev = True
            resolved_msg = self.resolveMessageId(current_msg)
            if resolved_msg is not None:
                prev_msg = current_msg
                current_msg = resolved_msg.in_reply_to
                current_date = resolved_msg.date
            else:
                return None
        return None


def SearchableListMoved(ml, event):
    if not IObjectRemovedEvent.providedBy(event):
        # don't bother with this stuff on removal, it's pointless
        search = get_utility_for_context(ISearchableArchive, context=ml)
        # XXX: Assumes a ZCatalog based utility, we need to rebuild the whole
        # catalog after a move
        # Clear the catalog
        search.manage_catalogClear()
        # Add the moved messages to the catalog, then reindex again to make sure
        # that we don't get any threading inconsistencies.
        index_meth = search.catalog_object
        path = '/'.join(ml.getPhysicalPath())
        search.ZopeFindAndApply(ml, obj_metatypes=('MailingListMessage',),
                                apply_func=index_meth,
                                apply_path=path,
                                search_sub=1)
        search.refreshCatalog()
