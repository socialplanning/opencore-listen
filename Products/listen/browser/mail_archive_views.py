from AccessControl import Unauthorized
from Acquisition import aq_chain
from Acquisition import aq_inner
from DateTime import DateTime
import re
import urllib
from zope.app import zapi

from Products.Five import BrowserView

from Products.listen.interfaces import ISearchableArchive
from Products.listen.interfaces import IMembershipList
from Products.listen.interfaces import IMailingList
from Products.CMFCore.utils import getToolByName
from Products.CMFPlone.PloneBatch import Batch
from Products.ZCTextIndex import ParseTree

from Products.listen.lib.browser_utils import messageStructure
from Products.listen.lib.browser_utils import catalogMessageIterator
from Products.listen.lib.browser_utils import format_date
from Products.listen.lib.browser_utils import generateThreadedMessageStructure
from Products.listen.lib.browser_utils import decode
from Products.listen.lib.browser_utils import encode, obfct_de
from Products.listen.lib.browser_utils import getSiteEncoding

from Products.listen.config import POST_DENIED
from Products.listen.config import POST_DEFERRED
from Products.listen.config import POST_ALLOWED

from Products.listen.lib.common import construct_simple_encoded_message

from Products.listen.i18n import _
from zope.i18nmessageid import Message

class ArchiveBaseView(BrowserView):
    """A base class for archive views"""

    def __init__(self, context, request):
        BrowserView.__init__(self, context, request)
        self.search = zapi.getUtility(ISearchableArchive)
        self._mailing_list = None
        self._can_post = None
        request.set('disable_border', True)

    def getMailingList(self):
        if self._mailing_list is None:
            # climb aq chain to get the mailing list object
            for parent in aq_chain(aq_inner(self.context)):
                if IMailingList.providedBy(parent):
                    self._mailing_list = [aq_inner(parent)]
                    break
        return self._mailing_list[0]

    def listTitle(self):
        """The title of the list"""
        ml = self.getMailingList()
        if ml is not None:
            return ml.Title().decode('utf8')
        return _(u'No Title')

    def listDescription(self):
        """The Description of the list"""
        ml = self.getMailingList()
        if ml is not None:
            return encode(ml.description, ml)
        return ''

    def listAddress(self):
        """The list address"""
        ml = self.getMailingList()
        if ml is not None:
            return obfct_de(encode(ml.mailto, ml))
        return _(u'No address')

    def canPost(self):
        """Can the current user post to this list"""

        # If we've already calculated this, use it again
        if self._can_post is not None:
            return self._can_post
        # Otherwise default to false 
        self._can_post = False

        # if member is logged in, they should be able to post to the list
        ml = self.getMailingList()
        mtool = getToolByName(self.context, 'portal_membership')
        if not mtool.isAnonymousUser():
            self._can_post = True

        return self._can_post



class ArchiveForumView(ArchiveBaseView):
    """A view that displays messages in a forum like manner with the threads
       as topics."""

    def Title(self):
        title = _('label_archive_views_forum', u'Forum view for ${list}')
        title = Message(title, mapping={ u'list': self.listTitle(), })
        return title

    def getTopics(self):
        """Returns a list of dicts containing information about the initial messages in threads.
        """
        batch = self.request.get('batch', True)
        batch_size = int(self.request.get('b_size', 25))
        batch_start = int(self.request.get('b_start', 0))
        context = self.context
        topic_list = []
        search = self.search
        getToplevelMessages = search.getToplevelMessages
        getMessageReferrers = search.getMessageReferrers
        messages = getToplevelMessages(recent_first=True)
        mem_list = IMembershipList(self.getMailingList())
        if batch:
            messages = Batch(messages, batch_size, batch_start)
        for message in messages:
            msg_dict = messageStructure(message, sub_mgr=mem_list)
            msg_dict['responses'] = message.responses or 0
            msg_dict['last_post'] = format_date(message.modification_date,
                                                                     context)
            msg_dict['url'] = msg_dict['url'] +'/forum_view'
            topic_list.append(msg_dict)
        messages.topic_list = topic_list
        return messages


class ArchiveDateView(ArchiveBaseView):
    """A view that displays the list of months for which there are archived
       messages."""

    def Title(self):
        title = _('label_archive_views_date', u'Archive by date for ${title}')
        title = Message(title, mapping={ u'title': self.listTitle(), })
        return title

    def getAvailableDates(self):
        years = []
        for year in self.context.objectValues():
            year_struct = {'title':year.title,
                           'url': year.absolute_url(),
                           'children':[]}
            for month in year.objectValues():
                # We should translate the month names here
                month_struct = {'title': month.title,
                                'url': month.absolute_url()}
                year_struct['children'].append(month_struct)
            years.append(year_struct)
        return years

class SubFolderDateView(ArchiveBaseView):
    """A view which shows a full listing of all messages within a given
       archive subfolder (i.e. by date)"""

    def Title(self):
        title = _('label_archive_list_archive_view', u'${list} archive for ${date}')
        title = Message(title, mapping={ u'list': self.listTitle(),
                                         u'date':  self.context.title, })
        return title

    def getThreadedMessageStructure(self):
        path = '/'.join(self.context.getPhysicalPath())
        messages = self.search.getAllMessagesInPath(path)
        structure = {'base_level': {'children':[]}}
#        subscription = IMemberSubscriptionList(self.getMailingList())
        thread = generateThreadedMessageStructure(structure, messages,
                                                  sub_mgr=self.context)
        return thread['base_level']['children']

    def getMessageList(self):
        path = '/'.join(self.context.getPhysicalPath())
        messages = self.search.getAllMessagesInPath(path)
#        subscription = IMemberSubscriptionList(self.getMailingList())
        return catalogMessageIterator(messages, sub_mgr=self.context)

class ArchiveNewTopicView(ArchiveBaseView):

    def __call__(self):
        # Make sure that the current user is allowed to post:
        if not self.canPost():
            raise Unauthorized, \
                "You do not have permission to respond to this message."
        # Save the referring URL, either from the template form, or the
        # HTTP_REFERER, otherwise just use the message url.
        referring_url = (self.request.get('referring_url', None) or
                              self.request.get('HTTP_REFERER', None) or
                              self.context.absolute_url())
        self.referring_url = urllib.splitquery(referring_url)[0]
        submitted = self.request.get('submit', None)
        cancelled = self.request.get('cancel', None)
        if cancelled:
            return self.request.response.redirect(self.referring_url+
                                    '?portal_status_message=Post%20Cancelled')
        if submitted:
            self.errors = {}
            body = self.request.get('body', None)
            subject = self.request.get('subject', None)
            if not body:
                self.errors['body'] = _('You must enter a message')
            if not subject:
                self.errors['subject'] = _('You must enter a subject for your message.')
            if not self.member_address():
                self.errors['subject'] = _('The current user has no address.')
            if not self.errors:
                message = self.createMessage()
                ml = self.getMailingList()
                self.request.set('Mail', message)
                result = ml.processMail(self.request)
                if result == POST_ALLOWED:
                    return self.request.response.redirect(self.referring_url+
                                    '?portal_status_message=Post%20Sent')
                elif result == POST_DEFERRED:
                    return self.request.response.redirect(self.referring_url+
                                    '?portal_status_message=Post%20Pending%20Moderation')
                elif result == POST_DENIED:
                    return self.request.response.redirect(self.referring_url+
                                    '?portal_status_message=Post%20Rejected:%20You%20already%20have%20a%20post%20pending%20moderation.')
                else:
                    return self.request.response.redirect(self.referring_url+
                                    '?portal_status_message=Post%20Error')
                    

                    
        return self.index()

    def new_message_id(self):
        """An id for the new message"""
        ml = self.getMailingList()
        return ml.uniqueMessageId()

    def list_address(self):
        """This is needed to fill in the To field"""
        ml = self.getMailingList()
        return ml.mailto

    def rfc_date(self):
        return DateTime().rfc822()

    def member_address(self):
        mtool = getToolByName(self.context, 'portal_membership')
        email = mtool.getAuthenticatedMember().getProperty('email', None)
        name = mtool.getAuthenticatedMember().getProperty('fullname', None)
        if name:
            return '%s <%s>'%(name.decode('utf8'),email)
        return email

    def createMessage(self):
        """Generate a basic message, MailBoxer will take care of all the
           important headers, hopefully."""
        headers = {'Message-Id': self.new_message_id(),
                   'Date': self.rfc_date(),}
        ml = self.getMailingList()
        encoding = getSiteEncoding(ml)
        body = decode(self.request.get('body'), ml)
        subject = decode(self.request.get('subject'), ml)
        message = construct_simple_encoded_message(from_addr=self.member_address(),
                                                   to_addr=self.list_address(),
                                                   subject=subject,
                                                   body=body,
                                                   other_headers=headers,
                                                   encoding=encoding)
        return message.as_string()


class ArchiveSearchView(ArchiveBaseView):

    messages = None
    
    def __call__(self, *args, **kw):
        # Do the search before rendering the template,
        # to be sure PSMs are set.
        self.messages = self._searchArchive()
        return self.index(*args, **kw)


    def Title(self):
        title = _('label_archive_search', u'Search messages in ${title}')
        title = Message(title, mapping={ u'title': self.listTitle(), })
        return title

    def _searchArchive(self, text=None):
        messages = []
        batch = self.request.get('batch', True)
        batch_size = int(self.request.get('b_size', 25))
        batch_start = int(self.request.get('b_start', 0))
        text = text or decode(self.request.get('search_text'), '')
        context = self.context
        subscription = IMembershipList(self.getMailingList())
        if text:
            text = text.strip()
            try:
                messages = self.search.search(text)
            except ParseTree.ParseError, inst:
                if "Token 'ATOM' required, 'EOF' found" in str(inst) or "Token 'EOF' required" in str(inst):
                    self.request.set('portal_status_message', _(u'Invalid Search: Search phrase cannot end with \'and\', \'or\', or \'not\''))
                elif "Token 'ATOM' required" in str(inst):
                    self.request.set('portal_status_message', _(u'Invalid Search: Search phrase cannot begin with \'and\', \'or\', or \'not\''))
                elif "a term must have at least one positive word" in str(inst):
                    self.request.set('portal_status_message', _(u'Invalid Search: Search phrase cannot begin with \'not\''))
                elif "Query contains only common words" in str(inst):
                    self.request.set('portal_status_message', _(u'Invalid Search: Search phrase must contain words other than \'and\', \'or\', and \'not\''))
            else:
                messages = catalogMessageIterator(messages, sub_mgr=subscription)
                if len(messages) == 0:
                    self.request.set('portal_status_message', _(u'There were no messages found'))
        if batch:
            messages = Batch(messages, batch_size, batch_start)

        return messages

    def searchArchive(self, text=None):
        if self.messages is None:
            self.messages = self._searchArchive(text=text)
        return self.messages
