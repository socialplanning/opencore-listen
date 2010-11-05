from random import random

from zope.interface import implements

from zope.i18nmessageid import Message, MessageFactory
from zope.i18n import translate

from Products.listen.interfaces import ISendMail
from Products.listen.lib import default_email_text
from Products.listen.lib.browser_utils import getSiteEncoding
from Products.listen.lib.common import create_request_from
from Products.listen.lib.common import is_email
from Products.listen.lib.common import lookup_email
from Products.listen.lib.common import lookup_emails

from Products.listen.i18n import _

def nonascii_username(user_email, user_name):
    if user_name:
        if type(user_name) == unicode:
            return user_name
        return user_name.decode('utf-8', 'replace')
    return user_email
    
class MailSender(object):
    """
    Setup object for testing
    >>> from Products.listen.extras.tests import TestMailingList
    >>> from Products.listen.content import tests
    >>> ml = TestMailingList()
    >>> ml.managers = []
    >>> from Products.listen.content.send_mail import MailSender
    >>> ms = MailSender(ml)
    
    Test sending user_mod, make sure mock message is
    as expected.
    TestMailingList counts messages and keeps the last message
    as [address, subject, body]
    >>> ms.user_mod('fee@feem.com', 'feemer')
    >>> ml.message_count
    1
    >>> ml.message[0]
    'fee@feem.com'
    >>> ml.message[1]
    u'Membership awaiting approval'
    >>> 'feemer' in ml.message[2]
    True
    
    Test user_welcome additionally, as it uses a mapping in
    the message factory.
    >>> ms.user_welcome('fee@feem.com', 'feemer')
    >>> ml.message[0]
    'fee@feem.com'
    >>> ml.message[1]
    u'Welcome to MY LIST'
    
    Let's test user_welcome with a non-ASCII username too:
    >>> ms.user_welcome('fee@feem.com', "féemer")
    >>> ml.message[0]
    'fee@feem.com'
    >>> ml.message[1]
    u'Welcome to MY LIST'

    Exercise send_to_managers
    Make sure no message is sent if there are no managers
    >>> ms.manager_mod('fee@feem.com', 'feemer')
    >>> ml.message_count
    3
    >>> ml.managers = ['manager@feem.com']
    >>> ms.manager_mod('fee@feem.com', 'feemer')
    >>> ml.message_count
    4
    >>> ml.message[0]
    'manager@feem.com'
    >>> ml.message[1]
    u'Membership awaiting approval'

    Sanity checks for i18n. Are translations actually taking place?
    ===============================================================
    
    Set up the test translation domain.
    Messages translated to the 'test' language are returned as
    u'[[domain][message id (message if different)]]'
    >>> from zope.i18n.testmessagecatalog import TestMessageFallbackDomain
    >>> ld = TestMessageFallbackDomain(domain_id=u'listen')
    >>> from zope.component import provideUtility
    >>> provideUtility(ld, name='listen')
    >>> from zope.i18n import translate
    >>> from Products.listen.i18n import _
    
    Check translate with 'test' specified
    >>> translate( _(u'Membership awaiting approval'), target_language='test' )
    u'[[listen][Membership awaiting approval]]'
    
    Test against our mail routines with standard fallback
    >>> ms.user_mod('fee@feem.com', 'feemer')
    >>> ml.message[1]
    u'Membership awaiting approval'
    
    Now, test against our mail routines with 'test' language for fallback.
    >>> save_fallbacks = ld._fallbacks
    >>> ld._fallbacks = ['test']
    >>> ms.user_mod('fee@feem.com', 'feemer')
    >>> ml.message[1]
    u'[[listen][Membership awaiting approval]]'

    test with a mapping
    >>> ms.user_welcome('fee@feem.com', 'feemer')
    >>> ml.message[1]
    u'[[listen][welcome_to_list (Welcome to MY LIST)]]'


    check translation in send_to_managers
    >>> ms.manager_mod('fee@feem.com', 'feemer')
    >>> ml.message[1]
    u'[[listen][Membership awaiting approval]]'

    It should not blow up on non-ascii byte strings. (bug #50)
    >>> ms.send_to_managers('Pe\xc3\xb1ate!', '\\n\\nPe\xc3\xb1ate again!\\n')

    Clean up    
    >>> ld._fallbacks = save_fallbacks
    
    """

    implements(ISendMail)

    def __init__(self, context):
        self.context = context

        
    def user_subscribe_request(self, user_email, user_name, pin):
        user_name = nonascii_username(user_email, user_name)
        subject = "Subscription confirmation (mail-command:subscribe-member %s [%s])" % (user_email, pin)
        body = default_email_text.user_subscribe_request
        mapping = { 'fullname': user_name,
                    'listname': self.context.title,
                    'listmanager': self.context.manager_email, }
        body = Message(body, mapping=mapping)
        
        self.context.sendCommandRequestMail(user_email, subject, translate(body))

    def user_unsubscribe_request(self, user_email, user_name, pin):
        user_name = nonascii_username(user_email, user_name)
        subject = "Unsubscription confirmation (mail-command:unsubscribe-member %s [%s])" % (user_email, pin)
        body = default_email_text.user_unsubscribe_request
        mapping = { 'fullname': user_name,
                    'listname': self.context.title,
                    'listmanager': self.context.manager_email, }
        body = Message(body, mapping=mapping)
        self.context.sendCommandRequestMail(user_email, subject, translate(body))
        

    def user_mod(self, user_email, user_name):
        user_name = nonascii_username(user_email, user_name)
        subject = _("Membership awaiting approval")
        body = default_email_text.user_mod
        mapping = { 'fullname': user_name,
                    'listname': self.context.title,
                    'listmanager': self.context.manager_email, }
        body = Message(body, mapping=mapping)
        self.context.sendCommandRequestMail(user_email, translate(subject), translate(body))

    def user_sub_mod(self, user_email, user_name):
        user_name = nonascii_username(user_email, user_name)
        subject = _("Membership awaiting approval")
        body = default_email_text.user_sub_mod
        mapping = { 'fullname': user_name,
                    'listname': self.context.title,
                    'listmanager': self.context.manager_email, }
        body = Message(body, mapping=mapping)
        self.context.sendCommandRequestMail(user_email, translate(subject), translate(body))

    def manager_mod(self, user_email, user_name):
        user_name = nonascii_username(user_email, user_name)
        subject = _("Membership awaiting approval")
        body = default_email_text.manager_mod
        mapping = { 'fullname': user_name,
                    'listname': self.context.title,
                    'mod_url': self.context.absolute_url() + '/moderation',}
        body = Message(body, mapping=mapping)
        self.send_to_managers(translate(subject), translate(body))

    def user_pin_mismatch(self, user_email, user_name):
        user_name = nonascii_username(user_email, user_name)
        subject = _("Membership denied")
        body = default_email_text.user_pin_mismatch
        mapping = { 'fullname': user_name,
                    'listname': self.context.title,
                    'listmanager': self.context.manager_email, }
        body = Message(body, mapping=mapping)
        self.context.sendCommandRequestMail(user_email, translate(subject), translate(body))

    def user_welcome(self, user_email, user_name):
        user_name = nonascii_username(user_email, user_name)
        subject = _("welcome_to_list", "Welcome to ${title}", mapping={'title' : self.context.title})
        body = default_email_text.user_welcome
        mapping = { 'fullname': user_name,
                    'listname': self.context.title,
                    'listaddress': self.context.mailto,
                    'listmanager': self.context.manager_email, }
        body = Message(body, mapping=mapping)
        self.context.sendCommandRequestMail(user_email, translate(subject), translate(body))

    def user_denied(self, user_email, user_name):
        user_name = nonascii_username(user_email, user_name)
        subject = _("Membership denied")
        body = default_email_text.user_denied
        mapping = { 'fullname': user_name,
                    'listname': self.context.title,
                    'listmanager': self.context.manager_email, }
        body = Message(body, mapping=mapping)
        self.context.sendCommandRequestMail(user_email, translate(subject), translate(body))

    def user_unsubscribe_confirm(self, user_email, user_name):
        user_name = nonascii_username(user_email, user_name)
        subject = _("Unsubscription confirmed")
        body = default_email_text.user_unsubscribe_confirm
        mapping = { 'fullname': user_name,
                    'listname': self.context.title,
                    'listmanager': self.context.manager_email, }
        body = Message(body, mapping=mapping)
        self.context.sendCommandRequestMail(user_email, translate(subject), translate(body))

    def user_already_pending(self, user_email, user_name, pin):
        user_name = nonascii_username(user_email, user_name)
        subject = "Email confirmation (mail-command:confirm-member %s [%s])" % (user_email, pin)
        body = default_email_text.user_already_pending
        mapping = { 'fullname': user_name,
                    'listname': self.context.title,
                    'listmanager': self.context.manager_email, }
        body = Message(body, mapping=mapping)
        self.context.sendCommandRequestMail(user_email, subject, translate(body))

    def user_mem_mod_already_pending(self, user_email, user_name):
        user_name = nonascii_username(user_email, user_name)
        subject = _("Membership approval already pending")
        body = default_email_text.user_mem_mod_already_pending
        mapping = { 'fullname': user_name,
                    'listname': self.context.title,
                    'listmanager': self.context.manager_email, }
        body = Message(body, mapping=mapping)
        self.context.sendCommandRequestMail(user_email, translate(subject), translate(body))

    def user_post_request(self, user_email, user_name, pin):
        user_name = nonascii_username(user_email, user_name)
        subject = "Email confirmation (mail-command:confirm-member %s [%s])" % (user_email, pin)
        body = default_email_text.user_post_request
        mapping = { 'fullname': user_name,
                    'listaddress': self.context.mailto,
                    'listname': self.context.title,
                    'listmanager': self.context.manager_email, }
        body = Message(body, mapping=mapping)
        self.context.sendCommandRequestMail(user_email, subject, translate(body))

    def manager_mod_post_request(self, user_email, user_name, post):
        user_name = nonascii_username(user_email, user_name)
        subject = _(u"Post requiring moderation")
        body = default_email_text.manager_mod_post_request
        boundary = u'Boundary-%s-%s' % (random(), random())
        post_msg = create_request_from(post)['Mail'].decode('utf-8', 'replace')
        mapping = { 'fullname': user_name,
                    'mod_url': self.context.absolute_url() + '/moderation',
                    'listname': self.context.title,
                    'post': post_msg,
                    'boundary': boundary,}
        body = Message(body, mapping=mapping)
        extra_headers = {'Content-Type': u'multipart/mixed; boundary=%s' % boundary,
                         'Mime-Version': u'1.0',}
        self.send_to_managers(translate(subject), translate(body), extra_headers)

    def user_post_mod_notification(self, user_email, user_name):
        user_name = nonascii_username(user_email, user_name)
        subject = _("Message pending moderation")
        body = default_email_text.user_post_mod_notification
        mapping = { 'fullname': user_name,
                    'listname': self.context.title,
                    'listmanager': self.context.manager_email, }
        body = Message(body, mapping=mapping)
        self.context.sendCommandRequestMail(user_email, translate(subject), translate(body))

    def user_post_mod_subscribe_notification(self, user_email, user_name):
        user_name = nonascii_username(user_email, user_name)
        subject = _("Message pending moderation")
        body = default_email_text.user_post_mod_subscribe_notification
        mapping = { 'fullname': user_name,
                    'listaddress': self.context.mailto,
                    'listname': self.context.title,
                    'listmanager': self.context.manager_email, }
        body = Message(body, mapping=mapping)
        self.context.sendCommandRequestMail(user_email, translate(subject), translate(body))

    def send_to_managers(self, subject, message, extra_headers={}):
        # create a list of valid manager emails 
        manager_emails = []
        for manager in self.context.managers:
            if not is_email(manager):
                manager = lookup_email(manager.encode('ascii'), self.context)
            if manager not in manager_emails and manager:
                manager_emails.append(manager)

        if not len(manager_emails):
            return False

        list_manager_emails = ', '.join(manager_emails)
        sender = '"%s" <%s>' % ('[' + self.context.title + '] List Manager', self.context.manager_email)
        try:
            message = translate(message)
        except UnicodeDecodeError:
            # Argh, a raw byte string.
            encoding = getSiteEncoding(self)
            message = translate(message.decode(encoding))
            
        self.context.sendCommandRequestMail(list_manager_emails, subject, translate(message), sender, extra_headers=extra_headers)

    def user_post_rejected(self, user_email, user_name, reject_reason):
        user_name = nonascii_username(user_email, user_name)
        subject = _("Post rejected")
        body = default_email_text.user_post_rejected
        mapping = { 'fullname': user_name,
                    'listname': self.context.title,
                    'reject_reason': reject_reason,
                    'listmanager': self.context.manager_email, }
        body = Message(body, mapping=mapping)
        self.context.sendCommandRequestMail(user_email, subject, translate(body))

    def user_sub_rejected(self, user_email, user_name, reject_reason):
        user_name = nonascii_username(user_email, user_name)
        subject = _("Subscription request rejected")
        body = default_email_text.user_sub_rejected
        mapping = { 'fullname': user_name,
                    'listname': self.context.title,
                    'reject_reason': reject_reason,
                    'listmanager': self.context.manager_email, }
        body = Message(body, mapping=mapping)
        self.context.sendCommandRequestMail(user_email, translate(subject), translate(body))
