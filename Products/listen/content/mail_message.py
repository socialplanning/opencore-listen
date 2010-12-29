import email
import re
from rfc822 import parseaddr

from zope.interface import implements
from zope.annotation.interfaces import IAnnotations

from OFS.Folder import Folder
from DateTime import DateTime
from Acquisition import aq_get
from BTrees.OOBTree import OOBTree

from Products.CMFPlone.utils import base_hasattr
from plone.mail import decode_header

from Products.MailBoxer.MailBoxerTools import convertHTML2Text

from Products.listen.interfaces import IMailMessage
from Products.listen.interfaces import ISearchableArchive
from Products.listen.interfaces import ISearchableMessage
from Products.listen.config import PROJECTNAME
from Products.listen.lib.browser_utils import encode, obfct
from Products.listen.content.mailboxer_tools import unpackMail
from Products.listen.lib.common import get_utility_for_context

_marker = []

# split on whitespace
REF_REGEX = re.compile(r'\s+')
CHARSET_REGEX = re.compile(r'charset=([^;\s]+)')


# Perhaps we can be even simpler than Folder
# We need persistence, acquisition, and a few standard methods.  We need to
# enforce permission mappings defined on the parent, but no need for individual
# permissions or roles on mail objects.
class MailMessage(Folder):
    """ A Mailng list implementation
    """

    implements(IMailMessage)

    # Though this is not a CMF type the plone ui expects a portal_type
    meta_type = portal_type = "MailingListMessage"

    body = ''
    message_id = ''
    in_reply_to = ''
    references = ()
    other_headers = ()

    # Stop zope from complaining about 'security declaration for
    # nonexistent method', by ensuring that we have class attributes
    # with all the names listed in IMailMessage.
    from_addr = None
    subject = None
    date = None

    def __init__(self, id, from_addr, subject, date=None, **kwargs):
        from_addr = from_addr.decode('utf-8', 'replace')
        self.from_addr = decode_header(email.Header.Header(from_addr))

        subject = subject.decode('utf-8', 'replace')
        self.subject = decode_header(email.Header.Header(subject))
        # date is expected to be a DateTime or None
        if not isinstance(date, DateTime):
            self.date = DateTime(date)
        else:
            self.date = date

        sender_name = parseaddr(self.from_addr)[0]

        title_subj = len(self.subject) > 20 and (self.subject[:20]+' ...') \
                         or self.subject
        if sender_name:
            self.title = u"%s / %s" % (title_subj, sender_name)
        else:
            self.title= title_subj

        Folder.__init__(self, id)

    # Provide a Title to make plone happy
    def Title(self):
        """An encoded title"""
        return obfct(encode(self.title, self))

    def Description(self):
        """An encoded description"""
        return encode(self.body[:50] + ' ...', self)


class MailFromString(object):
    """An adapter for mail messages that allows them to parse the text of a
       mail message and set all properties appropriately.  Uses
       MailBoxerTools."""

    def __init__(self, context):
        self.context = context

    def createMailFromMessage(self, msg_string, attachments=False):
        context = self.context

        (TextBody, ContentType, HtmlBody, Attachments) = unpackMail(msg_string)
        if attachments:
            for file in Attachments:
                self.addAttachment(file['filename'],
                                   file['filebody'],
                                   file['maintype'] + '/' + file['subtype'])

        # This must be encoded text. Attempt to use specificed encoding to
        # convert to unicode, otherwise default to iso-8859-1, which is a
        # a reasonable superset of 7-bit ascii, and more common than utf-8
        # for email.  The RFCs indicate that no specified encoding means 7-bit
        # ascii, so this should be safe.
        encoding = 'iso-8859-1'
        # ContentType is only set for the TextBody
        if ContentType:
            body = TextBody
            # find charset
            encoding_match = CHARSET_REGEX.search(ContentType)
            if encoding_match:
                encoding = encoding_match.groups()[0]
        else:
            body = convertHTML2Text(HtmlBody)

        try:
            body = body.decode(encoding, 'replace')
        except LookupError:
            # The email specified an invalid encoding
            body = body.decode('iso-8859-1', 'replace')

        msg = email.message_from_string(msg_string)
        in_reply_to = msg.get('in-reply-to', context.in_reply_to).strip()
        references = msg.get('references', '').strip()
        # split references on whitespace
        if references:
            references = REF_REGEX.split(references)
        else:
            references = ()
        message_id = msg.get('message-id', context.message_id).strip()
        if not message_id:
            # XXX: This method is acquired inappropriately from the parent
            # MailBoxer for now
            message_id = context.uniqueMessageId()
        # Use a regexp to optionally pull in other headers
        other_headers = []
        # Attempt to acquire the headers regex from our MailingList
        headers_regexp = aq_get(context, 'headers', None)
        if headers_regexp is not None:
            if headers_regexp:
                for (key, value) in msg.items():
                    if (re.match(headers_regexp, key, re.IGNORECASE) and
                        key not in ['subject', 'date', 'from', 'in_reply_to',
                                    'references', 'message_id']):
                        other_headers.append((key, value.strip()))

        context.body = body
        context.in_reply_to = in_reply_to
        context.references = tuple(references)
        context.message_id = message_id
        context.other_headers = tuple(other_headers)

    def addAttachment(self, filename, content, mime_type):
        """Adds a zope file object as an attachemnt"""

        sub_type = mime_type.split('/')[-1]
        attach_id = DateTime().millis()
        # to be sure: test and search for a free id...
        while base_hasattr(self.context, "%s.%s" % (attach_id, sub_type)):
            attach_id = attach_id + 1
        self.context.manage_addFile("%s.%s" % (attach_id, sub_type),
                                    title=filename,
                                    file=content,
                                    content_type=mime_type)

class SearchableMessage(object):
    """An adapter providing the ISearchableMessage interface for MailMessages"""

    implements(ISearchableMessage)

    def __init__(self, context):
        self.context = context
        # This is called during message creation (e.g. from Application), so
        # context needs to be passed explicitly.
        self.search = get_utility_for_context(ISearchableArchive,
                                              context=context)
        self.annotations = IAnnotations(context)
        self.list_data = self.annotations.get(PROJECTNAME)
        self._refs_calculated = False
        if self.list_data is None:
            self.list_data = self.annotations[PROJECTNAME] = OOBTree()

    def SearchableText(self):
        """Returns body, subject, and from address."""
        context  = self.context
        body = context.body
        if not isinstance(body, unicode):
            body = body.decode("utf8", "replace")
        subject = context.subject
        if not isinstance(subject, unicode):
            subject = subject.decode("utf8", "replace")
        from_addr = context.from_addr
        if not isinstance(from_addr, unicode):
            from_addr = from_addr.decode("utf8", "replace")
        blob = u' '.join([body, subject, from_addr])
        return blob.encode("ascii", "replace")

    def isInitialMessage(self):
        """Returns True if the object has no references and is not in reply to
           any other messages."""
        context = self.context
        is_reply = (context.references or context.in_reply_to)
        if not is_reply:
            return True
        # Check that parent message exists, if not check to see if any
        # of the references exist.
        if not self.in_reply_to():
            return True
        return False

    def in_reply_to(self):
        """If the parent object is somehow missing check to see if any of the
           referred messages are available"""
        parent = self.list_data.get('index_parent', None)
        if parent:
            return parent
        context = self.context
        parent_message = self.search.resolveMessageId(context.in_reply_to)
        # Return True if parent message is not found in archive
        if parent_message is None:
            references = context.references and \
                         self.search.resolveMessageIds(context.references)
            if len(references):
                self.list_data['index_parent'] = references[-1].message_id
            else:
                self.list_data['index_parent'] = ''
        else:
            self.list_data['index_parent'] = context.in_reply_to
        return self.list_data['index_parent']

    def references(self):
        context = self.context
        list_data = self.list_data
        # This method is called multiple times during indexing, store the
        # result on the object and use it if available.
        if context.in_reply_to and not (self._refs_calculated
                                        or context.references):
            message = context
            parents = []
            # Walk the in_reply_to chain to build the references list
            while message is not None:
                parent = self.search.getParentMessage(message.message_id)
                if parent is not None:
                    parents.append(parent.message_id)
                message = parent
            # initial message should be on top per RFC
            parents.reverse()
            refs = tuple(parents)
            context.references = refs
        else:
            refs = context.references
        if refs and not self._refs_calculated:
            # If we want to be able to make a list of the threads most
            # recently responded to, the we need to also catalog the date of
            # response on the toplevel message.
            # This is an archive viewing optimization which should help
            # tremendously when archives get large, unfortunately it slows
            # down message archiving considerably.  Make sure we never double
            # count.
            # XXX: Setting attributes directly on the mail object is hacky,
            # but does this optimization info really belong in the schema?
            resolved_refs = self.search.resolveMessageIds(refs)
            if resolved_refs and not list_data.has_key('counted_on_parent'):
                # Get the first referenced message and assume it is the start
                # of the thread.
                try:
                    # use unrestricted get object to prevent unauthorized
                    # errors when posting through email
                    initial = resolved_refs[0]._unrestrictedGetObject()
                    annotations = IAnnotations(initial)
                    data = annotations[PROJECTNAME]
                    data['modification_date'] = context.date
                    # Set the count
                    data['responses'] = data.setdefault('responses', 0) + 1
                    self.search.indexNewMessage(initial)
                    # Set an attribute to prevent reupdating the parent, on
                    # reindex.
                    list_data['counted_on_parent'] = True
                except AttributeError:
                    # We can't do a getObject without a request
                    pass
        self._refs_calculated = True
        return refs

    def modification_date(self):
        return self.list_data.get('modification_date', None) or \
                                                        self.context.date
    def responses(self):
        return self.list_data.get('responses', None) or 0

    # Override getattr so that we provide access to the MailMessage properties
    def __getattr__(self, name, default=_marker):
        if default is _marker:
            return getattr(self.context, name)
        else:
            return getattr(self.context, name, default)
