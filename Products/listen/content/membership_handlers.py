from zope.interface import implements
from zope.annotation.interfaces import IAnnotations

from zope.component import getAdapter

from BTrees.OOBTree import OOBTree

from plone.mail import decode_header
from Products.MailBoxer import MailBoxerTools

from Products.listen.interfaces import IMessageHandler
from Products.listen.interfaces import IWriteMembershipList
from Products.listen.interfaces import ISendMail
from Products.listen.interfaces import IPostPendingList
from Products.listen.interfaces import IMembershipList

from Products.listen.config import PROJECTNAME
from Products.listen.content import PendingList

from Products.listen.lib.common import check_pin
from Products.listen.lib.common import send_pending_posts


class ConfirmationHandler(object):
    """
    adapter to handle cases where a user has confirmed a subscription
    request

    set up mailing lists and test objects
    >>> from Products.listen.extras.tests import TestMailingList
    >>> from Products.listen.content import tests
    >>> ml = TestMailingList()
    >>> mtool = tests.DummyMembershipTool('')
    >>> ml.portal_membership = mtool
    >>> mtool.result = None
    >>> mails_sent = []
    >>> def patched_sendCommandRequestMail(*args):
    ...     mails_sent.append(args)
    >>> ml.sendCommandRequestMail = patched_sendCommandRequestMail

    create a fake pin in the pending list
    >>> from zope.annotation.interfaces import IAnnotations
    >>> annot = IAnnotations(ml)
    >>> from Products.listen.config import PROJECTNAME
    >>> listen_annot = annot.setdefault(PROJECTNAME, {})
    >>> from BTrees.OOBTree import OOBTree
    >>> pend_list = listen_annot.setdefault('a_s_pending_sub_email',
    ...                                      OOBTree())
    >>> from Products.listen.lib.common import generate_pin
    >>> pin = generate_pin()
    >>> pend_list['lammy@zul.com'] = {'pin':pin}

    set up the handler with a fake request
    >>> message = ['from: lammy@zul.com',
    ...            'subject: Email confirmation (mail-command:confirm-member [%s])' % pin,
    ...            '', '']
    >>> message = '\\n'.join(message)
    >>> request = dict(Mail=message)
    >>> from Products.listen.content.membership_handlers import ConfirmationHandler
    >>> handler = ConfirmationHandler(ml, request)

    set up the handler with a fake request, and a bad pin
    >>> message = ['from: lammy@zul.com',
    ...            'subject: Email confirmation (mail-command:confirm-member [%s])' % 'bogus_pin',
    ...            '', '']
    >>> message = '\\n'.join(message)
    >>> request = dict(Mail=message)
    >>> from Products.listen.content.membership_handlers import ConfirmationHandler
    >>> handler = ConfirmationHandler(ml, request)

    process the mail and verify an email was sent out
    >>> handler.processMail()
    >>> dict(pend_list)
    {'lammy@zul.com': {'pin': '...'}}
    >>> from Products.listen.interfaces import IMembershipList
    >>> IMembershipList(ml).is_allowed_sender('lammy@zul.com')
    False
    >>> len(mails_sent)
    1

    now let's use a valid pin
    >>> message = ['from: lammy@zul.com',
    ...            'subject: Email confirmation (mail-command:confirm-member [%s])' % pin,
    ...            '', '']
    >>> message = '\\n'.join(message)
    >>> request = dict(Mail=message)
    >>> from Products.listen.content.membership_handlers import ConfirmationHandler
    >>> handler = ConfirmationHandler(ml, request)

    process the mail and verify email is allowed now
    >>> handler.processMail()
    >>> dict(pend_list)
    {}
    >>> IMembershipList(ml).is_allowed_sender('lammy@zul.com')
    True
    >>> len(mails_sent)
    1

    if a confirmation comes through and the user is already an allowed sender,
    then it should silently pass
    >>> len(mails_sent)
    1
    >>> handler.processMail()
    >>> len(mails_sent)
    1

    """

    implements(IMessageHandler)
    
    def __init__(self, context, request):
        self.context = context
        self.request = request

    def _get_a_s_pending_list(self):
        return self._get_pending_list('a_s_pending_sub_email')

    def _get_post_pending_list(self):
        return self._get_pending_list('pending_mod_post')

    def _get_pending_list(self, list_name):
        return getAdapter(self.context, IPostPendingList, list_name)

    def _send_pending_posts(self, email):
        post_list = self._get_post_pending_list()
        send_pending_posts(self.context, email, post_list)

    def add_allowed_sender(self, email):
        IWriteMembershipList(self.context).add_allowed_sender(email)

    def processMail(self):
        # XXX we need to go through pending interfaces ... maybe named adapters?
        # right now we are hard coding the annotations that we are using
        pend_list = self._get_a_s_pending_list()

        message = self.request.get('Mail')
        (header, body) = MailBoxerTools.splitMail(message)

        # get email-address
        sender = decode_header(header.get('from',''))
        (name, email) = MailBoxerTools.parseaddr(sender)
        email = email.encode('ascii', 'replace').lower()

        # get subject
        subject = decode_header(header.get('subject', ''))

        # if the user is already an allowed sender, we don't need to validate
        if IMembershipList(self.context).is_allowed_sender(email):
            return

        # check to see if the pin matches
        if not check_pin(dict(subject=subject, email=email), pend_list):
            mail_sender = ISendMail(self.context)
            mail_sender.user_pin_mismatch(email, name)
            return

        if pend_list.is_pending(email):
            self.add_allowed_sender(email)
            pend_list.remove(email)
        else:
            # XXX why are we getting in here?
            pass
