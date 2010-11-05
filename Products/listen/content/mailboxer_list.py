from Acquisition import aq_get
from DateTime import DateTime
from Products.CMFCore.utils import getToolByName
from Products.CMFPlone.utils import base_hasattr
from Products.MailBoxer.MailBoxer import FALSE
from Products.MailBoxer.MailBoxer import MailBoxer
from Products.MailBoxer.MailBoxer import TRUE
from Products.MailBoxer.MailBoxer import setMailBoxerProperties
from Products.MailBoxer.MailBoxerTools import splitMail
from Products.MailBoxer.messagevalidators import setDefaultValidatorChain
from Products.listen.interfaces import IMailFromString
from Products.listen.interfaces import IMessageHandler
from Products.listen.lib.browser_utils import getSiteEncoding
from Products.listen.lib.common import construct_simple_encoded_message
from email.Header import Header
from plone.mail import decode_header
from zope.app import zapi
from zope.component import queryMultiAdapter
import logging
import re
import rfc822
import zope.event


logger = logging.getLogger('listen.content.mailboxer_list')

# A REGEX for messages containing mail-commands
mail_command_re = re.compile('\(mail-command:([A-Za-z_-]+)',
                             re.IGNORECASE)


class MailBoxerMailingList(MailBoxer):
    """
    A slightly customized MailBoxer with some less cryptic method names
    """

    # Mailboxer wants the name of a catalog to acquire
    catalog = 'mail_catalog'

    def manage_mailboxer(self, REQUEST):
        """ Override to allow triggering of pluggable mail handlers
        """
        if self.checkMail(REQUEST):
            return FALSE
                
        # Check for subscription/unsubscription-request and confirmations
        if self.requestMail(REQUEST):
            return TRUE

        if self.adaptMail(REQUEST):
            return TRUE

        if self.manager_mail(REQUEST):
            return TRUE

        # Process the mail...
        self.processMail(REQUEST)
        return TRUE


    def manager_mail(self, REQUEST):
        # Intended for subclasses to override.
        return False
    
    def adaptMail(self, REQUEST):
        """Adapts an incoming request to a specialized view for handling
        mail if requested."""

        mailString = self.getMailFromRequest(REQUEST)
        (header, body) = splitMail(mailString)

        encoding = getSiteEncoding(self)
        subject = decode_header(str(Header(header.get('subject',''), 
                                           encoding,
                                           errors='replace')))

        command_match = re.search(mail_command_re, subject)
        if command_match:
            command_name = command_match.groups()[0]
            adapter = queryMultiAdapter((self, REQUEST), IMessageHandler,
                                        name=command_name)
            if adapter is not None:
                adapter.processMail()
                return True
        return False

    def sendCommandRequestMail(self, address, subject, body, from_address=None, extra_headers={}):
        if not address: 
            print ('Products.listen.content.MailBoxerMailingList.sendCommandRequestMail() '
                   'invalid address; user may have been deleted')
            return

        if from_address is None:
            from_address = self.mailto

        # Default headers:
        headers = {'X-Mailer': self.getValueFor('xmailer')}
        headers.update(extra_headers)
        encoding = getSiteEncoding(self)
        message = construct_simple_encoded_message(from_addr=from_address,
                                                   to_addr=address,
                                                   subject=subject,
                                                   body=body,
                                                   other_headers=headers,
                                                   encoding=encoding)
            
        # XXX: Acquire the MailHost, yuck
        mh = getToolByName(self, 'MailHost')
        mh.send(str(message))

    def manage_afterAdd(self, item, container, **kw):
        """Setup properties and sub-objects"""
        # Only run on add, not rename, etc.
        if not base_hasattr(self, 'mqueue'):
            setMailBoxerProperties(self, self.REQUEST, kw)
            # Setup the default checkMail validator chain
            setDefaultValidatorChain(self)

            # Add Archive
            archive = zapi.createObject('listen.ArchiveFactory', self.storage,
                                        title=u'List Archive')
            item._setObject(self.storage, archive)

            # Add moderation queue
            mqueue = zapi.createObject('listen.QueueFactory', self.mailqueue,
                                       title=u'Moderation queue')
            item._setObject(self.mailqueue, mqueue)

            ttool = getToolByName(self, 'portal_types', None)
            if ttool is not None:
                # If the archive/queue are CMF types then we must finish
                # constructing them.
                fti = ttool.getTypeInfo(mqueue)
                if fti is not None:
                    fti._finishConstruction(mqueue)
                fti = ttool.getTypeInfo(archive)
                if fti is not None:
                    fti._finishConstruction(archive)
        MailBoxer.manage_afterAdd(self, self.REQUEST, kw)

    # modified manage_addMail from MailBoxer.py to make things more modular
    def addMail(self, mailString):
        """ Store mail in date based folder archive.
            Returns created mail.  See IMailingList interface.
        """
        archive = aq_get(self, self.getValueFor('storage'), None)

        # no archive available? then return immediately
        if archive is None:
            return None

        (header, body) = splitMail(mailString)

        # if 'keepdate' is set, get date from mail,
        if self.getValueFor('keepdate'):
            timetuple = rfc822.parsedate_tz(header.get('date'))
            time = DateTime(rfc822.mktime_tz(timetuple))
        # ... take our own date, clients are always lying!
        else:
            time = DateTime()

        # now let's create the date-path (yyyy/mm)
        year  = str(time.year()) # yyyy
        month = str(time.mm())   # mm
        title = "%s %s"%(time.Month(), year)

        # do we have a year folder already?
        if not base_hasattr(archive, year):
            self.addMailBoxerFolder(archive, year, year, btree=False)
        yearFolder=getattr(archive, year)

        # do we have a month folder already?
        if not base_hasattr(yearFolder, month):
            self.addMailBoxerFolder(yearFolder, month, title)
        mailFolder=getattr(yearFolder, month)

        subject = header.get('subject', 'No Subject')
        sender = header.get('from','Unknown')

        # search a free id for the mailobject
        id = time.millis()
        while base_hasattr(mailFolder, str(id)):
             id = id + 1
        id = str(id)

        self.addMailBoxerMail(mailFolder, id, sender, subject, time,
                              mailString)
        mailObject = getattr(mailFolder, id)

        return mailObject

    # Override the original MailBoxer method
    manage_addMail = addMail

    # Componentize folder creation
    def addMailBoxerFolder(self, context, id, title, btree=True):
        """ Adds an archive-folder using a configured factory
        """
        folder = zapi.createObject('listen.FolderFactory',
                                   id, title, btree=btree)
        context._setObject(id, folder)

    # Componentize mail creation
    def addMailBoxerMail(self, folder, id, sender, subject, date, mail):
        # Strip out the list name from the subject, as it serves no purpose
        # in the archive.
        subject = subject.replace('[%s]' % self.getValueFor('title'), '')

        new_message = zapi.createObject('listen.MailFactory',
                                        id, sender, subject, date)
        folder._setObject(id, new_message)
        msg = getattr(folder, id)
        # Adapt message to provide methods for parsing mail and extracting
        # headers
        settable_msg = IMailFromString(msg)
        # This is ugly, but it is the MailBoxer way, last option means no
        # attachments.
        store_attachments = self.archived == 0
        # Set properties on message
        settable_msg.createMailFromMessage(mail, store_attachments)
        zope.event.notify(
            zope.app.event.objectevent.ObjectModifiedEvent(msg))
        
        return msg

    # For now use the builtin methods
    resetBounces = MailBoxer.manage_resetBounces
    moderateMail = MailBoxer.manage_moderateMail

    # Override getValueFor to always return ASCII encoded strings, as they
    # may be included in an email header or body.  We use 7-bit encoded
    # in the site encoding if the string won't convert to ascii.
    # Our mailing list title, and email addresses may be unicode, this will
    # convert them
    def getValueFor(self, key):
        # value = MailBoxer.getValueFor(self, key)
        # Simplify: we have no need for all the strange 'getter' magic that
        # MailBoxer does
        value = self.getProperty(key)
        encoding = getSiteEncoding(self)
        try:
            if hasattr(value, 'encode'):
                value = self._encodedHeader(value, encoding)
            elif isinstance(value, list) or isinstance(value, tuple):
                value = [self._encodedHeader(v, encoding) for v in value]
        except (UnicodeEncodeError, UnicodeDecodeError):
            # Just in case one of our 'utf-8' encoding attempts fails, we
            # give up
            pass
        except AttributeError:
            # No 'encode' method on a list element, so give up
            pass
        return value

    @staticmethod
    def _encodedHeader(value, encoding):
        """
        Given a value (or list of values) and an ecoding, return it
        encoded as per rfc2047 for use in a MIME message header.

        >>> from Products.listen.content.mailboxer_list import MailBoxerMailingList

        If the input can be converted to ascii, it will be, regardless
        of the encoding argument:

        >>> MailBoxerMailingList._encodedHeader('blah', 'utf8')
        'blah'

        If it can be encoded to the target encoding, it will be, and
        then encoded as per rfc2047:

        >>> input = u'\xbfhmm?'
        >>> MailBoxerMailingList._encodedHeader(input, 'utf8')
        '=?utf8?b?wr9obW0/?='
        >>> MailBoxerMailingList._encodedHeader(input.encode('utf8'), 'utf8')
        '=?utf8?b?wr9obW0/?='
        >>> raw = 'a string \345\276\267\345\233\275'
        >>> MailBoxerMailingList._encodedHeader(raw, 'utf8')
        '=?utf8?b?YSBzdHJpbmcg5b635Zu9?='

        All other cases will raise an exception. Typically this means
        a raw byte string in an incompatible encoding:

        >>> MailBoxerMailingList._encodedHeader(input.encode('latin1'), 'utf8')
        Traceback (most recent call last):
        ...
        UnicodeDecodeError: 'utf8' codec can't decode byte 0xbf in position 0: unexpected code byte
        """
        try:
            value = value.encode('ascii')
        except (UnicodeEncodeError, UnicodeDecodeError):
            try:
                value = Header(value.encode(encoding), encoding).encode()
            except UnicodeDecodeError:
                try:
                    value = Header(value, encoding).encode()
                except UnicodeDecodeError:
                    logger.error("Could not guess encoding of raw bytestring %r, there is probably a bug in the code that created this header." % value)
                    raise
        return value
