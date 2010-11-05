from zope.interface import Interface
from zope.interface import Attribute
from zope.schema import TextLine
from zope.schema import Text
from zope.schema import ASCII
from zope.schema import Datetime
from zope.schema import Tuple

from Products.listen.i18n import _

class IMailMessage(Interface):

    # This needs to be converted to unicode on input
    from_addr = TextLine(
        title = _(u"From"),
        description = _(u"The address the mail was sent from"),
        required = True,)

    # This needs to be converted to unicode on input
    subject = TextLine(
        title = _(u"Subject"),
        description = _(u"The subject of the email"),
        default = u"No Subject",
        required = False,)

    date = Datetime(
        title = _(u"Date"),
        description = _(u"The date the mail was sent"),
        required = True,)

    body = Text(
        title = _(u"Body"),
        description = _(u"The mail message body"),
        default = u'',
        required = False,)

    message_id = ASCII(
        title = _(u"Message Id"),
        description = _(u"The message id of this message."),
        default = '',
        required = False,)

    in_reply_to = ASCII(
        title = _(u"Reply To"),
        description = _(u"The message id that this mail is in reply to."),
        default = '',
        required = False,)

    references = Tuple(
        title = _(u"References"),
        description = _(u"Any message ids that this mail refers to."),
        value_type = ASCII(title=_(u"Reference"),),
        default = (),
        required = False,)

    other_headers = Tuple(
        title = _(u"Headers"),
        description = _(u"List of selected other headers: (key, value) pairs"),
        value_type = Tuple(
                           title = _(u"Header"),
                           value_type = ASCII(),
                           min_length = 2,
                           max_length = 2,),
        default = (),
        required = False,
        )


class IMailFromString(Interface):
    """ An interface for mail objects that wish to set their own values
        from a mail message. """

    def createMailFromMessage(message_string, attachments=False):
        """
           Automatically sets the properties of the message object
           based on an input mail message.  May optionally include
           attachments.
        """

    def addAttachment(filename, content, mime_type):
        """
           Adds an attachment to this message
        """


class ISearchableMessage(IMailMessage):
    """ An interface for mail objects that wish to be searchable, provides
        additional calculated properties and methods on which an object may be
        indexed."""

    def isInitialMessage():
        """Returns a boolean indicating whether this is the first message in
           a thread"""

    def SearchableText():
        """
           Returns a string containing all terms this content should be
           found by in a search (generally the body, subject, and addresses).
        """

    def modification_date():
        """
            Returns a DateTime indicating the time  a thread was last updated.
        """

    def responses():
        """
            Returns an integer indicating the number of responses in a thread.
        """

class IMessageHandler(Interface):
    """ An interface for objects which process incoming mail (e.g. for executing
    configuration changes via mail). """
    request = Attribute("A browser request containing a Mail key which is an "
                        "email message.")

    def processMail():
        """ Process a mail message contained within the adapted request """
