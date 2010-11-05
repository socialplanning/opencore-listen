from DateTime import DateTime
import re
import urllib
from rfc822 import parseaddr

from zope.i18n import translate
from zope.app import zapi
from zope.formlib import form
from zope.component import getSiteManager

from Acquisition import aq_chain
from Acquisition import aq_inner, aq_parent
from AccessControl import Unauthorized

from Products.Five import BrowserView
from Products.Five.browser.pagetemplatefile import ZopeTwoPageTemplateFile
from Products.CMFCore.utils import getToolByName

from Products.listen.interfaces import ISearchableArchive
from Products.listen.interfaces import ISearchableMessage
from Products.listen.interfaces import IMailMessage
from Products.listen.interfaces import IMembershipList
from Products.listen.interfaces import IMailingList

from Products.listen.lib.browser_utils import createReplyStructure
from Products.listen.lib.browser_utils import createReplyStructureFromReferrers
from Products.listen.lib.browser_utils import catalogMessageIterator
from Products.listen.lib.browser_utils import messageStructure
from Products.listen.lib.browser_utils import getAttachmentsForMessage
from Products.listen.lib.browser_utils import format_date
from Products.listen.lib.browser_utils import rewrapMessage
from Products.listen.lib.browser_utils import stripSignature
from Products.listen.lib.browser_utils import getAddressInfo
from Products.listen.lib.browser_utils import decode
from Products.listen.lib.browser_utils import encode, obfct_de, obfct
from Products.listen.lib.browser_utils import escape
from Products.listen.lib.browser_utils import getSiteEncoding

from Products.listen.config import POST_DENIED
from Products.listen.config import POST_DEFERRED
from Products.listen.config import POST_ALLOWED
from Products.listen.config import POST_ERROR

from Products.listen.lib.common import construct_simple_encoded_message

from Products.listen.i18n import _
from zope.i18nmessageid import Message



# case insensitively match the 're:' in a subject line
subject_regex = re.compile('^RE:', re.IGNORECASE)


class MailMessageView(BrowserView):
    """A simple view class which allows access to the message properties."""

    def __init__(self, context, request):
        self._context = [context]
        self.request = request
        self._mail_info = None
        self._mailing_list = None
        self._subscription = None
        self._can_reply = None
        # We don't want an editable border for message views (e.g. no contents tab)
        request.set('disable_border', True)

    # hack around nasty Five acquisition nightmare by using a list as a
    # container
    def _getContext(self):
        return self._context[0]

    context = property(_getContext)

    # I replaced the old version of getMailingList() (which used __parent__
    # instead of aq_parent()) with the version in mail_archive_views.py because
    # the other version  was returning mailing list objects whose paths
    # included an additional /<listname>/<listname> which was causing problems.
    # (The specific issue was that calling getObject() on the brains associated
    # with replies failed. Updating the function below fixed this, I'm not sure why...)
    def getMailingList(self):
        if self._mailing_list is None:
            # climb aq chain to get the mailing list object
            for parent in aq_chain(aq_inner(self.context)):
                if IMailingList.providedBy(parent):
                    self._mailing_list = [aq_inner(parent)]
                    break
        return self._mailing_list[0]

    def subject(self):
        return encode(self.context.subject, self.getMailingList())

    def mail_from(self):
        if self._mail_info is None:
            self._mail_info = getAddressInfo(self.context,
                                             self.getSubManager())
        return obfct(self._mail_info[1])

    def mail_from_name(self, do_encode=True):
        addr = self.context.from_addr
        name = parseaddr(addr)[0] or addr
        if do_encode:
            return encode(name, self.getMailingList())
        else:
            return name

    def from_id(self):
        if self._mail_info is None:
            self._mail_info = getAddressInfo(self.context,
                                             self.getSubManager())
        return self._mail_info[0]

    def date(self):
        return format_date(self.context.date, self.context)

    def title(self):
        return encode(self.context.title, self.getMailingList())

    def body(self):
        # XXX: We need to make this smarter to use blockquote for quotes
        # create html links for urls, and filter out email addresses of
        # portal/list members. Do we want to filter email addresses of
        # non-members?
        return obfct_de(escape(encode(self.context.body, self.getMailingList())))

    def id(self):
        return self.context.getId()

    def url(self):
        return self.context.absolute_url()

    def attachments(self):
        message = self.context
        return getAttachmentsForMessage(message)

    def canReply(self):
        """Can the current user reply to this message"""
        # If we've already calculated this, use it again
        if self._can_reply is not None:
            return self._can_reply
        # Otherwise default to false 
        self._can_reply = False

        ml = self.getMailingList()
        mtool = getToolByName(self.context, 'portal_membership')
        if not mtool.isAnonymousUser():
            self._can_reply = True
           
        return self._can_reply


    def getSubManager(self):
        # Get the subscription manager lazily, avoiding view acquisition
        # wierdness by wrapping it in a list
        if self._subscription is None:
            ml = self.getMailingList()
            self._subscription = [IMembershipList(ml)]
        return self._subscription[0]

    def folderURL(self):
        # Hacky acquisition
        return aq_parent(aq_inner(self.context)).absolute_url()

    def archiveURL(self):
        # Extra Hacky acquisition
        return aq_parent(aq_inner(
            aq_parent(aq_inner(
            aq_parent(aq_inner(self.context)))))).absolute_url()



class MessageReplyView(MailMessageView):
    """A view for making replies to this message"""

    def __call__(self):
        # Make sure that the current user is allowed to reply:
        if not self.canReply():
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
                                    '?portal_status_message=Reply%20Cancelled')
        if submitted:
            self.errors = {}
            ml = self.getMailingList()
            body = decode(self.request.get('body', None), ml)
            subject = decode(self.request.get('subject', None), ml)
            if not body or body == self.reply_body(use_empty=True):
                self.errors['body'] = _(u'You must enter a message')
            if not subject:
                self.errors['subject'] = _(
                    u'You must enter a subject for your message.')
            if not self.member_address():
                self.errors['subject'] = _(u'The current user has no address.')
            if not self.errors:
                message = self.createReply()
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

    def orig_message_id(self):
        """This is needed to fill in the In-Reply-To field"""
        return self.context.message_id

    def list_address(self):
        """This is needed to fill in the In-Reply-To field"""
        ml = self.getMailingList()
        return ml.mailto

    def reply_references(self):
        """Returns the list of references for any mail generated in response
           to the viewed message"""
        return ' '.join(self.context.references + (self.orig_message_id(),))

    def rfc_date(self):
        return DateTime().rfc822()

    def member_address(self):
        mtool = getToolByName(self.context, 'portal_membership')
        email = mtool.getAuthenticatedMember().getProperty('email', None)
        name = mtool.getAuthenticatedMember().getProperty('fullname', None)
        if name:
            return '%s <%s>'%(name,email)
        return email

    def reply_subject(self):
        req_subject = self.request.get('subject', None)
        if req_subject:
            return req_subject
        subject = self.subject()
        if not subject_regex.match(subject):
            subject = 'Re: %s'%subject
        return subject

    def reply_body(self, use_empty=False):
        """Add quote characters and attribution to original body."""
        req_body = self.request.get('body', None)
        if req_body and not use_empty:
            return req_body

        # Remove message signature
        stripped_body = stripSignature(self.context.body)
        quoted_body = rewrapMessage(stripped_body, add_quote=True)

        attribution = _("reply-attribution", u"On ${date}, ${author} wrote:")
        attribution = Message(attribution, mapping={
            u'date': self.date(),
            u'author': self.mail_from_name(do_encode=False)})
        return translate(attribution) + '\r\n' + quoted_body + '\r\n'

    def createReply(self):
        """Generate a basic reply message, MailBoxer will take care of all the
           important headers, hopefully."""
        headers = {'Message-Id': self.new_message_id(),
                   'In-Reply-To': self.orig_message_id(),
                   'References': self.reply_references(),
                   'Date': self.rfc_date(),}
        ml = self.getMailingList()
        encoding = getSiteEncoding(ml)
        body = rewrapMessage(decode(self.request.get('body'), ml))
        subject = decode(self.request.get('subject'), ml)
        message = construct_simple_encoded_message(from_addr=unicode(self.member_address(),encoding),
                                                   to_addr=self.list_address(),
                                                   subject=subject,
                                                   body=body,
                                                   other_headers=headers,
                                                   encoding=encoding)
        return message.as_string()

class ThreadedMailMessageView(MailMessageView):
    """A view which handles resolving the targets of in-reply-to and
       references"""

    def __init__(self, context, request):
        MailMessageView.__init__(self, context, request)
        self.search = zapi.getUtility(ISearchableArchive)
        self.message_id = self.context.message_id

    def subject(self):
        return obfct_de(escape(encode(self.context.subject, self.getMailingList())))

    def getReplies(self):
        """See ISearchableArchive documentation"""
        return catalogMessageIterator(
                  self.search.getMessageReplies(self.message_id),
                                                 sub_mgr=self.getSubManager())

    def getReferrers(self):
        """See ISearchableArchive documentation"""
        return catalogMessageIterator(
                self.search.getMessageReferrers(self.message_id),
                                                 sub_mgr=self.getSubManager())

    def getNextInThread(self):
        """See ISearchableArchive documentation"""
        msg = self.search.getNextInThread(self.message_id)
        return msg and messageStructure(msg, sub_mgr=self.getSubManager())

    def getParentMessage(self):
        """See ISearchableArchive documentation"""
        msg = self.search.getParentMessage(self.message_id)
        return msg and messageStructure(msg, sub_mgr=self.getSubManager())

    def getNextByDate(self):
        """See ISearchableArchive documentation"""
        msg = self.search.getNextByDate(self.message_id)
        return msg and messageStructure(msg, sub_mgr=self.getSubManager())

    def getPreviousByDate(self):
        """See ISearchableArchive documentation"""
        msg = self.search.getPreviousByDate(self.message_id)
        return msg and messageStructure(msg, sub_mgr=self.getSubManager())

    def getReplyStructure(self):
        """Creates a structure for a thread tree"""
        return createReplyStructure(self.context, self.search,
                                        sub_mgr=self.getSubManager())


class ForumMailMessageView(ThreadedMailMessageView):
    """A view which displays every message in a thread at once, similar to
       a forum."""

    def __init__(self, context, request):
        ThreadedMailMessageView.__init__(self, context, request)
        self._reply_cache = None
        # Check if we have cookies for the forum view parameters, then check
        # the request and set long lived cookies if appropriate
        self.flat = self.request.get('flat_view', None)
        if self.flat is not None:
            self.request.RESPONSE.setCookie('listen_flat_forum',
                        int(self.flat),
                        expires=(DateTime().toZone('UTC') + 10000).rfc822(),
                        max_age=10000)
        else:
            self.flat = self.request.get('listen_flat_forum', 0)
        self.flat = int(self.flat)

        self.newest_first = self.request.get('newest_first', None)
        if self.newest_first is not None:
            self.request.RESPONSE.setCookie('listen_recent_first_forum',
                        int(self.newest_first),
                        expires=(DateTime().toZone('UTC') + 10000).rfc822(),
                        max_age=10000)
        else:
            self.newest_first = self.request.get('listen_recent_first_forum', 0)
        self.newest_first = int(self.newest_first)

    def getMessageBodies(self):
        """Creates a structure for a thread tree"""
        if self.flat:
            message = messageStructure(self.context, sub_mgr=self.getSubManager(),
                                       full_message=True)
            message['children'] = []
            results = self.search.getMessageReferrers(self.context.message_id,
                                                   reversed=self.newest_first)
            for msg in results:
                child = messageStructure(msg, sub_mgr=self.getSubManager(),
                                         full_message=True)
                child['children']=[]
                message['children'].append(child)
            return message
        # If the method was already called it should be cached, use it.  If
        # not call it and cache it.
        reply_struct = self._reply_cache
        if reply_struct is None:
            try:
                reply_struct = createReplyStructureFromReferrers(
                    self.context, self.search, full_message=True,
                    sub_mgr=self.getSubManager(),
                    newest_first=self.newest_first)
            except KeyError:
                # This happens when we have parentless messages in the
                # thread.  Fall back to the equivalent, but slower,
                # way of creating the structure.
                reply_struct = createReplyStructure(
                    self.context, self.search, full_message=True,
                    sub_mgr=self.getSubManager())
            # Cache this in case we need it for the thread display
            self._reply_cache = reply_struct
        return reply_struct

    def getReplyStructure(self):
        """Creates a structure for a thread tree, use cache generated from
           getMessageBodies if possible, as they may each be run."""
        reply_struct = self._reply_cache
        if reply_struct is None:
            try:
                # Use the more efficient method
                reply_struct = createReplyStructureFromReferrers(self.context,
                                  self.search, sub_mgr=self.getSubManager(),
                                  newest_first=self.newest_first)
            except KeyError:
                reply_struct = createReplyStructure(
                    self.context, self.search,
                    sub_mgr=self.getSubManager())
            self._reply_cache = reply_struct
        return reply_struct


_MARKER =[]
class SearchDebugView(MailMessageView):
    """A view for showing the generated search information"""

    def __init__(self, context, request):
        MailMessageView.__init__(self, context, request)
        self._context = [ISearchableMessage(context)]

    def isInitialMessage(self):
        return self.context.isInitialMessage()

    def references(self):
        return self.context.references()

    def in_reply_to(self):
        return self.context.in_reply_to()

    def modification_date(self):
        return self.context.modification_date()

    def responses(self):
        return self.context.responses()


class MailMessageAddForm(form.AddForm):
    """A form for adding MailMessage objects.
    """
    form_fields = form.FormFields(IMailMessage)


class MailMessageEditForm(form.EditForm):
    """A form for editing MailMessage objects.
    """
    form_fields = form.FormFields(IMailMessage)
