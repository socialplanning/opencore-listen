from zope.interface import Interface
from zope.interface.interfaces import IInterface
from zope.app.annotation.interfaces import IAnnotatable
from zope.schema import TextLine
from zope.schema import Text
from zope.schema import ASCII
from zope.schema import Choice
from zope.schema import Bool
from zope.schema import Tuple
from zope.schema import Dict
from zope.schema import Set
from zope.schema import ValidationError
from zope.interface.interface import Attribute
from zope.interface import Invalid
from zope.component import getUtility
from zope.app.component.hooks import getSite

from Products.listen.i18n import _
from Products.listen.lib.is_email import is_email
from Products.listen.interfaces.list_types import PublicListTypeDefinition
from Products.listen.interfaces.utilities import IListLookup

class IPendingList(Interface):
    """
    For managing a list of items.  Stores a dictionary with the items 
    and a dictionary of other values.
    """

    def get_user_emails():
        """
        return the list of all pending emails
        """

    def add(item, **values):
        """ 
        adds item to pending list marked with **values
        """

    def remove(item):
        """ 
        removes item from pending list
        """

    def is_pending(item):
        """ 
        returns if item is in the pending list
        """

    def get_user_pin(user_email):
        """
        returns the last pin used for a user's email
        """

    def get_pending_time(user_email):
        """
        returns a time indicating a user's pending status
        """

    def get_user_name(user_email):
        """
        returns the full name associated with the user_email
        """

    def clear():
        """
        removes all pending items, and returns a list of mapping objects
        """

class IMembershipPendingList(IPendingList):
    """
    For managing pending members
    """

class IPostPendingList(IPendingList):
    """
    For managing pending posts
    """

    def pop_post(user_email, postid):
        """
        removes the post with post index 'postid'
        from the list of posts from 'user_email'
        """

    def get_posts(user_email):
        """
        returns as an iterable the list of all posts for a user
        """

class ManagerMailTo(ValidationError):
    __doc__ = _(u"You cannot have a list address with '-manager@'")

class InvalidMailTo(ValidationError):
    __doc__ = _(u"The value entered is not a valid email address.")

class DuplicateMailTo(ValidationError):
    __doc__ = _(u"This address is already in use by another list.")

def check_mailto(value):
    # check if the user entered in -manager in the list name
    if '-manager@' in value: raise ManagerMailTo(value)

    # check if email are valid
    if not is_email(value): raise InvalidMailTo(value)

    # check if another list has the same mailto
    site = getSite()
    if IMailingList.providedBy(site):
        # we know we have a mailing list, so we ASSUME we're on
        # the edit page and thus allow the list mailto to be the
        # same as the mailing list of the current site
        # (as you should be able to change the address of the
        # current list to itself). Note this is hacky...
        if value == site.mailto:
            return True

    ll = getUtility(IListLookup)
    if ll.getListForAddress(value): raise DuplicateMailTo(value)

    return True


class IMailingList(Interface):
    """
       A de facto interface for some MailBoxer-y things, includes the
       basic public features, minus those that are useful primarily
       for smtp2zope.py
    """

    title = TextLine(
        title = _(u"Title"),
        description = _(u""),
        required = True,)

    description = Text(
        title = _(u"Description"),
        description = _(u"A description of the mailing list."),
        default=u'',
        required = False)

    mailto = ASCII(
        title = _(u"List Address"),
        description = _(u"Main address for the mailing list."),
        required = True,
        constraint = check_mailto,)

    manager_email = Attribute("The published address which general inquiries about the "
                         "list will be sent to.  Usually listtitle-manager@lists.example.com.")

    managers = Tuple( 
        title = _(u"Managers"), 
        description = _(u"The people who maintain the list.  Managers can " 
                         "edit list settings and can edit the list of allowed " 
                         "senders / subscribers.  Managers receive moderation " 
                         "requests, general inquiries and any bounced mail."),
        default = (),
        required = True,
        value_type = TextLine(title=_(u"Manager"),),)

    list_type = Choice( 
        title = _(u"List Type"), 
        description = _(u"The policy that defines the behavior of the list."),
        vocabulary = 'List Types',
        default = PublicListTypeDefinition,
        required = True)

    archived = Choice(
        title = _(u"Archival method"),
        description = _(u"When archiving is enabled, all messages sent to "
                         "the list will be saved on the server.  You may "
                         "choose whether to archive just the message text, "
                         "or include attachments."),
        vocabulary = "Archive Options",
        default = 0,
        required = True,
        )

        
# These methods really belong in an adapter(s), but because we are using
# MailBoxer they are part of the content object.

    def addMail(message_string):
        """
           Parses a mail message into a string and stores it in the archive
           as an IMailMessage.  Returns the resulting mail message object.
        """

    def checkMail(request):
        """
           Extracts a message from an HTTP request checks its validity.
           Returns None if the mail passes validation, otherwise it returns
           a string describing the error.  Expects a request variable 'Mail'
           containing the mail message with headers.
        """

    def requestMail(request):
        """
           Extracts an (un)subscribe request message from an HTTP request and
           processes it.  Expects a request variable 'Mail' containing the
           mail message with headers.
        """

    def processMail(request):
        """
           Extracts a message from an HTTP request and processes it for the
           mailing list.  Checks the validity of the sender and whether
           moderation is needed.  Expects a request variable 'Mail' containing
           the mail message with headers
        """

    def moderateMail(request):
        """
           Processes an HTTP request for information on what to do with a
           specific mail message in the moderation queue.  Expects the request
           to contain an 'action' ('approve' or 'discard'), a 'pin' used to
           authenticate the moderator, and an 'mid' which is the id of the
           mail object in the moderation queue.  Expects a request variable
           'Mail' containing the mail message with headers
        """

    def bounceMail(request):
        """
           Extracts a bounce message from an HTTP request and processes it to
           note any subscriber addresses that resulted in bounces.
        """

    def resetBounces(addresses):
        """
           Remove specified email addresses from the list of recipients with
           bounced messages.
        """

    def sendCommandRequestMail(address, subject, body):
        """
           Sends an administrative mail to the user requesting a response
           so that list commands can be executed.
        """

# XXX: this method needs to be public for now, so it does not belong in the
# interface
#    def pin(email):
#        """
#           Generates a pin from an email address, using an internal hash
#        """
#
# XXX: Can't add this to the interface because that causes it to become
# non-public, and individual method permission declarations don't seem to be
# working in Five
#     def uniqueMessageId():
#         """
#             Generate a message id for messages which are missing one.
#         """


class IDigestMailingList(IMailingList):
    """
    Extends mailing list interface w/ API for explicit digest support.
    """
    def send_digest():
        """
        Retrieves digested messages, constructs digest, and sends the
        digest to any digest subscribers.
        """

class IMembershipPolicy(Interface):
    def enforce(request):
        """
        Tries to handle a membership request.  Expects an HTTP
        request object from which the confirmation info will be
        extracted.  Returns a return code to represent the results,
        e.g. SUSBCRIPTION_ALLOWED, SUBSCRIPTION_DEFERRED,
        SUBSCRIPTION_DENIED.
        """

class IPostPolicy(Interface):
    def enforce(request):
        """
        Handles message posts.  Expects an HTTP request object 
        from which the post info will be extracted.  Returns 
        a return code to represent the results.
        """

class IUserEmailMembershipPolicy(IMembershipPolicy):
    """handle subscription requests via email"""

class IUserTTWMembershipPolicy(IMembershipPolicy):
    """handle subscription requests through the web"""

class IManagerTTWMembershipPolicy(IMembershipPolicy):
    """handle manager subscriptions requests through the web"""

class IEmailPostPolicy(IPostPolicy):
    """handle posts through email"""

class ITTWPostPolicy(IPostPolicy):
    """handle posts through the web"""

# XXX use these interfaces in the default subscription adapter
# class ISubscriptionTypes(Interface):
#     subscription_types = Dict()
#     """
#     A mapping of supported subscription types, keys are the subscription
#     type names (corresponding to the names used for named adapters),
#     values are data points of the subscription types (e.g. descriptions
#     for use in the UI).
#     """

# class IWriteSubscriptionTypes(ISubscriptionTypes):
#     def addSubscriptionType(type_name):
#         """
#         Adds a subscription type of the specified name to the set of
#         supported types.
#         """

#     def removeSubscriptionType(type_name):
#         """
#         Removes a subscription type of the specified name from the set
#         of supported types.
#        """

class ISubscriptionList(Interface):
    subscribers = Set() #email addresses of all subscribers

    def is_subscribed(subscriber, type_name=None):
        """ 
        Checks to see if 'subscriber' is a subscriber.  'subscriber' can be
        any of the set of supported subscription types (e.g. email address,
        userid).  If type_name is provided, this specifies the intended
        subscription type; if not, the implementation is responsible for
        making a best guess about the intended type.
        """

class IWriteSubscriptionList(ISubscriptionList):

    def subscribe(subscriber, type_name=None):
        """
        Makes 'subscriber' a subscriber of the list.  'subscriber' can be
        any of the supported subscription types.
        """

    def unsubscribe(subscriber, type_name=None):
        """
        Unsubscribes 'subscriber.'  'subscriber' can any of the supported
        subscription types.
        """
    

class IMembershipList(ISubscriptionList):
    allowed_senders = Set() #email addresses of all allowed senders
    allowed_senders_data = Dict() #full dictionary of emails and userid for 
                                  #allowed senders and their subscription status

    def is_allowed_sender(allowed_sender):
        """ 
        Checks to see if 'allowed_sender' is an allowed sender.  'allowed_sender' 
        can be either an email address or a userid.
        """

class IWriteMembershipList(IMembershipList):

    def add_allowed_sender(allowed_sender):
        """ 
        Makes 'allowed_sender' an allowed sender.  'allowed sender' can be 
        either an email address or a userid.  If it is an email address, it
        checks to see if there is a userid corresponding with the address
        and makes it an allowed sender instead of the email.
        """

    def remove_allowed_sender(allowed_sender):
        """ 
        Removes 'allowed_sender' from the list of allowed senders.  'allowed
        sender' can be either an email address or a userid.
        """

class IMembershipDigestList(IMembershipList):
    digest_subscribers = Set() # addresses of subscribers who rec'v digests
    nondigest_subscribers = Set() # addresses of non-digest subscribers

    def is_digest_subscriber(subscriber):
        """
        Returns True or False based on whether or not the provided
        subscriber identifier represents a subscriber who receives in
        digest mode.
        """

    def has_digest_subscribers():
        """
        Returns True or False based on whether or not there is one or
        more digest subscribers for the context list.
        """

class IWriteMembershipDigestList(IMembershipDigestList):
    def make_digest_subscriber(subscriber):
        """
        Converts a regular subscriber into a digest subscriber.
        Specified subscriber MUST already be a subscriber to the list
        or a ValueError will be raised.
        """

    def unmake_digest_subscriber(subscriber):
        """
        Converts a digest subscriber back to a regular subscriber.
        Specified subscriber MUST already be a digest subscriber or a
        ValueError will be raised.
        """

class IMembershipHandler(IWriteMembershipList):
    """ contain additional methods to subscribe/add an allowed sender from a pending state """

    def message_received(request):
        """ called when a confirmation message has been received from a user """


class ISendMail(Interface):
    """
    Provides convenient methods to send mail 
    """
    def user_subscribe_request(user_email, user_name, pin):
        """ """

    def user_unsubscribe_request(user_email, user_name, pin):
        """ """

    def user_mod(user_email, user_name):
        """ """

    def user_sub_mod(user_email, user_name):
        """ """

    def manager_mod(user_email, user_name):
        """ """

    def user_pin_mismatch(user_email, user_name):
        """ """

    def user_welcome(user_email, user_name):
        """ """

    def user_denied(user_email, user_name):
        """ """

    def user_unsubscribe_confirm(user_email, user_name):
        """ """

    def user_already_pending(user_email, user_name, pin):
        """ """

    def user_mem_mod_already_pending(user_email, user_name):
        """ """

    def user_post_request(user_email, user_name, pin):
        """ """

    def manager_mod_post_request(user_email, user_name):
        """ """

    def user_post_mod_notification(user_email, user_name):
        """ """

    def user_post_mod_subscribe_notification(user_email, user_name):
        """ """

    def send_to_managers(mail_from, subject, message):
        """ """


class IHaveSubscribers(IAnnotatable):
    """
        A marker interface indicating that an object wants to provide
        subscribers
    """

class IListArchive(Interface):
    """
        A marker interface to indicate that a folder contains a list archive.
    """


class IListArchiveSubFolder(IListArchive):
    """
        A marker interface to indicate that a folder is part of a list archive.
    """


class IModerationQueue(Interface):
    """
        A marker interface to indicate that a folder contains a moderation
        queue.
    """

class IBecameAnAllowedSender(Interface):
    """
        Interface to indicate that a user has just recently become an allowed sender
    """
    email = TextLine()

class IBecameASubscriber(Interface):
    """
        Interface to indicate that a user has just recently become a subscriber
    """
    email = TextLine()


class ISubscriberRemoved(Interface):
    """
        Interface to indicate that a user has just recently become a non-subscriber
    """
    email = TextLine()

class IAllowedSenderRemoved(Interface):
    """
        Interface to indicate that a user has just recently become a non-allowed-sender
    """
    email = TextLine()
    
class IListTypeChanged(Interface):
    """
        Interface to handle changing from one list type to another
    """
    old_list_type = TextLine()
    new_list_type = TextLine()
    mailing_list = TextLine()

class IMigrateList(Interface):
    """ Interface to help migrating mailing lists """

    def is_updated(ml):
        """lets you know if the list is already migrated"""

    def migrate(ml):
        """perform the migration from an old list version to a new list version"""

class IDisplayListTypes(Interface):
    """ Interface to display list type descriptions """

    def create_description():
        """ create the html description of a list type """
