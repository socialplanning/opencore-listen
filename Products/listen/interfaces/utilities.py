from zope.interface import Interface
from zope.app.component.interfaces.registration import IRegisterable

from Products.listen.i18n import _
from Products.ZCatalog.interfaces import IZCatalog
from zope.interface.interface import Attribute

class ISearchableArchive(IZCatalog):
    """An interface providing mailing list search methods"""

    def indexNewMessage(message_object):
        """Index a new message for searching"""

    def getToplevelMessages(start=None, end=None, recent_first=True):
        """Get a list of proxies for all messages that are at the top of a
           thread in order by date, optionally restricted to a specific date
           range and/or sorted by the most recently responded to message."""

    def getMessageReplies(message_id):
        """Returns a list of proxies for all messages that directly respond
           to the given message_id (only the idrect responses)"""

    def getMessageReferrers(message_id, reversed=True):
        """Returns a list of proxies for all messages that directly respond
           to the given message_id (i.e. the entire thread), ordered by date,
           optionally sorted in reverse with most recent reply first."""

    def getNextInThread(message_id):
        """Returns a proxy for the next message in the thread"""

    def getParentMessage(message_id):
        """Returns a proxy for the parent of the givern message_id"""

    def getNextByDate(message_id):
        """Returns a proxy for the next message by date"""

    def getPreviousByDate(message_id):
        """Returns a proxy for the previous message by date"""

    def resolveMessageId(message_id):
        """Returns a proxy for the message for a given message id"""

    def resolveMessageIds(message_id_list):
        """Returns a list of message proxies for a given set of message ids"""

    def search(text):
        """Returns a list of message proxies that have text in their
        subject, body, or from address."""

class IListLookup(IRegisterable):
    """An interface providing a means of looking up list objects based on
       the list address.  Provides facilities for registering and
       unregistering lists."""

    def registerList(ml):
        """Registers a mailing list so that it may be looked up by mail-to
           address.  Will raise a UserError if the address or mailing list
           is already registered."""

    def updateList(ml):
        """Updates the address of an already registered list.  Will raise a
           UserError if the address is already registered."""

    def unregisterList(ml):
        """Unregisters a mailing list, should only unregister the list if the
           address of the list corresponds to an existing registration for
           the given mailing list.  Fails silently."""

    def getListForAddress(address):
        """Returns an IMailingList object corresponding to the address given,
           or None iuf no list is found."""

    def deliverMessage(request):
        """Delivers a mail message included in the 'Mail' request variable to
           the appropriate mailing list, as determined by the envelope
           address.  Raises a NotFound error if an appropriate list cannot be
           found."""

    def showAddressMapping():
        """Display a mapping of email addresses -> mailing list paths"""

class IMemberLookup(IRegisterable):
    """An interfaces providing a way to translate from 'tokens' (ie member ids)
       -> email addresses"""

    def to_email_address(tokens):
        """Translate the tokens to email addresses"""

    def to_memberid(email):
        """Translate the email address to a member id, or None"""


class IGetMailHost(IRegisterable):
    """A utility for getting the mail host object"""
    mail_host = Attribute("returns the mail host")


class IObfuscateEmails(IRegisterable):
    """An interfaces providing a way to obfuscate email messages"""

    def obfuscate(value, deobfuscate=True):
        """returns value with email addresses obfuscated;
        if deobfuscate is True, the obfuscated emails are returned
        with a javascript deobfuscation capability"""
