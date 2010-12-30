import random
import re

from zope.component import getAdapter

from Products.listen.lib.common import is_email, lookup_email, lookup_member_id

from BTrees.OOBTree import OOBTree

from zope.interface import implements
from zope.app.annotation.interfaces import IAnnotations

from Products.listen.interfaces import IMembershipPolicy
from Products.listen.interfaces import ISendMail
from Products.listen.interfaces import IWriteMembershipList
from Products.listen.interfaces import IMembershipPendingList

from Products.listen.content import PendingList

from Products.listen.config import PROJECTNAME

from Products.listen.config import MEMBERSHIP_DENIED
from Products.listen.config import MEMBERSHIP_DEFERRED
from Products.listen.config import MEMBERSHIP_ALLOWED
from Products.listen.config import MEMBERSHIP_PIN_MISMATCH
from Products.listen.config import MEMBERSHIP_ERROR
from Products.listen.config import MODERATION_SUCCESSFUL
from Products.listen.config import MODERATION_FAILED

from Products.listen.lib.common import check_pin
from Products.listen.lib.common import generate_pin
from Products.listen.lib.common import is_confirm
from Products.listen.lib.common import is_unsubscribe
from Products.listen.lib.is_email import email_regex

class BaseMembershipPolicy(object):
    """
    Setup object for testing
    >>> from Products.listen.extras.tests import TestMailingList
    >>> from Products.listen.content import tests
    >>> ml = TestMailingList()
    >>> ml.managers = ['manager@example.com']
    >>> from Products.listen.content.membership_policies import BaseMembershipPolicy
    >>> p = BaseMembershipPolicy(ml)
    >>> p.mail_sender.user_subscribe_request('fee@feem.com', 'feemer', '12345676')
    >>> p.mail_sender.user_mod('fee@feem.com', 'feemer')
    >>> p.mail_sender.manager_mod('fee@feem.com', 'feemer')
    >>> ml.message_count
    3

    """

    def __init__(self, context):
        self.context = context
        annot = IAnnotations(context)
        self.listen_annot = annot.setdefault(PROJECTNAME, OOBTree())
        self.mail_sender = ISendMail(context)
        self.mem_list = IWriteMembershipList(self.context)


    def _get_email_for_pin(self, request, pend_list):
        email = request.get('email', None)
        return email

    def _check_pin(self, request, pend_list):
        email = self._get_email_for_pin(request, pend_list)
        new_request = request.copy()
        new_request['email'] = email
        return check_pin(new_request, pend_list)

    def _is_confirm(self, request):
        return is_confirm(request)

    def _is_unsubscribe(self, request):
        return is_unsubscribe(request)
       

class UserMembershipPolicy(BaseMembershipPolicy):
    """
    Adapter to handle the case where a user tries to subscribe through
    email. The list cannot be membership moderated

    Anyone can subscribe to a public or post moderated list by sending
    an email with subscribe in the subject.

    Setup object for testing
    >>> from Products.listen.extras.tests import TestMailingList
    >>> from Products.listen.content import tests
    >>> ml = TestMailingList()
    >>> mtool = tests.DummyMembershipTool(None)
    >>> mtool.result = None
    >>> ml.portal_membership = mtool
    >>> from Products.listen.content.membership_policies import UserMembershipPolicy
    >>> p = UserMembershipPolicy(ml)

    Monkey patch the send mail method to instead trigger a test result
    >>> sent_emails = []
    >>> def patched_send(to, name, pin):
    ...     sent_emails.append((to, pin))
    >>> p.mail_sender.user_subscribe_request = patched_send

    try an incomplete request
    >>> from Products.listen.config import MEMBERSHIP_ERROR, MEMBERSHIP_DEFERRED, MEMBERSHIP_PIN_MISMATCH, MEMBERSHIP_ALLOWED
    >>> p.enforce({}) == MEMBERSHIP_ERROR
    True

    try a subscribe request while logged in
    >>> p.enforce({'subject':'subscribe', 'use_logged_in_user': True}) == MEMBERSHIP_ALLOWED
    True

    try a new subscription request
    >>> p.enforce({'email':'foo@bar.com' , 'subject':'subscribe me'}) == MEMBERSHIP_DEFERRED
    True
    >>> len(sent_emails)
    1
    >>> email, pin = sent_emails.pop(0)
    >>> email
    'foo@bar.com'

    try to confirm that request with a mismatched pin
    >>> import random
    >>> new_pin = str(random.random())[-8:]
    >>> while new_pin == pin:
    ...     new_pin = str(random.random())[-8:]
    >>> conf_subject = 'Re: subscription confirmation [%s]' % new_pin
    >>> request = {'email': 'foo@bar.com', 'subject': conf_subject}
    >>> p.enforce(request) == MEMBERSHIP_PIN_MISMATCH
    True

    try with a correct pin
    >>> conf_subject = 'Re: subscription confirmation [%s]' % pin
    >>> request = {'email': 'foo@bar.com', 'subject': conf_subject}
    >>> p.enforce(request) == MEMBERSHIP_ALLOWED
    True

    try to confirm a user that has not first sent a subscription request
    >>> from Products.listen.config import MEMBERSHIP_DENIED
    >>> p.enforce({'email':'lucy@bar.com', 'subject': conf_subject}) == MEMBERSHIP_DENIED
    True

    if we try to subscribe an allowed sender, then we should get subscribed right away
    >>> from Products.listen.interfaces import IWriteMembershipList
    >>> mlist = IWriteMembershipList(ml)
    >>> mlist.add_allowed_sender('fubar@fu.bar')
    >>> p.enforce({'email': 'fubar@fu.bar', 'subject': 'subscribe'}) == MEMBERSHIP_ALLOWED
    True

    if we try to confirm somebody from a separate email address, it should confirm the request
    >>> sent_emails[:] = []
    >>> p.enforce({'email': 'john.wayne@example.com', 'subject': 'subscribe'}) == MEMBERSHIP_DEFERRED
    True
    >>> email, pin = sent_emails.pop(0)
    >>> conf_subject = 'Re: Subscription Confirmation john.wayne@example.com [%s]' % pin
    >>> p.enforce({'email': 'bad.guy@example.com', 'subject': conf_subject}) == MEMBERSHIP_ALLOWED
    True

    """

    implements(IMembershipPolicy)

    def __init__(self, context):
        BaseMembershipPolicy.__init__(self, context)
        self.subscribe_pending_list = getAdapter(context, IMembershipPendingList, 'pending_sub_email')
        self.unsubscribe_pending_list = getAdapter(context, IMembershipPendingList, 'pending_unsub_email')

    def _get_email_for_pin(self, request, pend_list):
        if pend_list == self.unsubscribe_pending_list:
            return request.get('email', None)

        subject = request.get('subject', '')
        m = email_regex.search(subject)
        if m:
            user_email = m.group(1)
        else:
            user_email = request.get('email', None)
        return user_email

    def enforce(self, request):
        user_email = request.get('email', None)
        user_name = request.get('name', None)

        use_logged_in_user = request.get('use_logged_in_user', None)

        if use_logged_in_user:
            return MEMBERSHIP_ALLOWED

        if user_email is None:
            return MEMBERSHIP_ERROR

        # handle unsubscription requests/confirmation
        if self._is_unsubscribe(request):
            if self._is_confirm(request):

                if self.unsubscribe_pending_list.is_pending(user_email):

                    if not self._check_pin(request, self.unsubscribe_pending_list):
                        return MEMBERSHIP_PIN_MISMATCH

                    self.unsubscribe_pending_list.remove(user_email)
                    return MEMBERSHIP_ALLOWED
                else:
                    return MEMBERSHIP_DENIED

            else:
                pin = generate_pin()
                self.mail_sender.user_unsubscribe_request(user_email, user_name, pin)
                self.unsubscribe_pending_list.add(user_email, subscriber=True, pin=pin)
                return MEMBERSHIP_DEFERRED

        # handle subscription requests/confirmation
        if self._is_confirm(request):

            # if there is an email on the subject, we should use that one
            # instead of the email address passed in
            # if the from address is different but they still have the correct
            # pin number in the subject for the other email address, we should
            # confirm the subscription
            user_email = self._get_email_for_pin(request, self.subscribe_pending_list)

            if self.subscribe_pending_list.is_pending(user_email):

                if not self._check_pin(request, self.subscribe_pending_list):
                    return MEMBERSHIP_PIN_MISMATCH

                self.subscribe_pending_list.remove(user_email)
                return MEMBERSHIP_ALLOWED
            else:
                return MEMBERSHIP_DENIED

        else:
            if self.mem_list.is_allowed_sender(user_email):
                return MEMBERSHIP_ALLOWED
            pin = generate_pin()
            self.mail_sender.user_subscribe_request(user_email, user_name, pin)
            self.subscribe_pending_list.add(user_email, subscriber=True, pin=pin)
            return MEMBERSHIP_DEFERRED


class ManagerTTWMembershipPolicy(BaseMembershipPolicy):
    """
    Adapter to handle the case where a manager manages membership ttw

    A manager can add any member or email address to become an allowed
    sender, but when trying to subscribe someone, a confirmation email
    is sent out to that email address.

    The request variable should contain:
    action = 'add_allowed_sender' | 'subscribe' 
    user = 'john@doe.com' | 'JesseParker'

    Setup object for testing
    >>> from Products.listen.extras.tests import TestMailingList
    >>> from Products.listen.content import tests
    >>> ml = TestMailingList()
    >>> from Products.listen.content.membership_policies import ManagerTTWMembershipPolicy
    >>> p = ManagerTTWMembershipPolicy(ml)

    Monkey patch the send mail method to instead trigger a test result
    >>> sent_emails = []
    >>> def patched_send(to, name, pin):
    ...     sent_emails.append((to, pin))
    >>> p.mail_sender.user_subscribe_request = patched_send

    try an incomplete request
    >>> from Products.listen.config import MEMBERSHIP_ERROR, MEMBERSHIP_DEFERRED, MEMBERSHIP_ALLOWED
    >>> p.enforce({}) == MEMBERSHIP_ERROR
    True

    try a new subscription request
    >>> p.enforce({'email':'foo@bar.com' , 'action':'subscribe'}) == MEMBERSHIP_DEFERRED
    True
    >>> len(sent_emails)
    1
    >>> email, pin = sent_emails.pop(0)
    >>> email
    'foo@bar.com'

    try a new allowed_sender request
    >>> p.enforce({'email':'pete@bar.com' , 'action':'add_allowed_sender'}) == MEMBERSHIP_ALLOWED
    True
    >>> len(sent_emails)
    0

    """

    implements(IMembershipPolicy)

    def __init__(self, context):
        BaseMembershipPolicy.__init__(self, context)
        self.subscribe_pending_list = getAdapter(context, IMembershipPendingList, 'pending_sub_email')

    def _get_email_from(self, member_or_email):
        return is_email(member_or_email) and member_or_email \
                                          or lookup_email(member_or_email, self.context)

    def enforce(self, request):
        action = request.get('action')
        user = request.get('email')
        removals = ['remove_allowed_sender', 'unsubscribe']
        if action is None or user is None: 
            return MEMBERSHIP_ERROR

        email = self._get_email_from(user)
        if email is None or email == '' or not is_email(email) and action not in removals:
            return MEMBERSHIP_DENIED

        if action == 'add_allowed_sender':
            return MEMBERSHIP_ALLOWED
        elif action == 'subscribe':
            pin = generate_pin()

            self.mail_sender.user_subscribe_request(email, user, pin)                
            self.subscribe_pending_list.add(email, subscriber=True, pin=pin)
            return MEMBERSHIP_DEFERRED
        elif action == 'remove_allowed_sender':
            return MEMBERSHIP_ALLOWED
        elif action == 'unsubscribe':
            if email: # we might be unsubbing a bogus member
                self.mail_sender.user_unsubscribe_confirm(email, user)
            return MEMBERSHIP_ALLOWED


class ModeratedUserMembershipPolicy(BaseMembershipPolicy):
    """
    Adapter to handle the case where a user tries to subscribe through
    email to a moderated-membership list by sending a message with
    'subscribe' in the subject.

    Setup object for testing
    >>> from Products.listen.extras.tests import TestMailingList
    >>> from Products.listen.content import tests
    >>> ml = TestMailingList()
    >>> from Products.listen.content.membership_policies import ModeratedUserMembershipPolicy
    >>> p = ModeratedUserMembershipPolicy(ml)
    >>> mtool = tests.DummyMembershipTool('')
    >>> ml.portal_membership = mtool
    >>> mtool.result = None

    Monkey patch the send mail method to instead trigger a test result
    >>> sent_emails = []
    >>> sent_mod_emails = []
    >>> def patched_send(to, name, pin):
    ...     sent_emails.append((to, pin))
    >>> p.mail_sender.user_subscribe_request = patched_send
    >>> p.mail_sender.user_sub_rejected = patched_send
    >>> p.mail_sender.user_unsubscribe_request = patched_send
    >>> def patched_mod_send(to, name):
    ...     sent_mod_emails.append(to)
    >>> p.mail_sender.manager_mod = patched_mod_send
    
    try an incomplete request
    >>> from Products.listen.config import MEMBERSHIP_ERROR, MEMBERSHIP_DEFERRED, MEMBERSHIP_ALLOWED
    >>> p.enforce({}) == MEMBERSHIP_ERROR
    True

    try a new subscription request
    >>> p.enforce({'email':'foo@bar.com' , 'subject':'subscribe me'}) == MEMBERSHIP_DEFERRED
    True
    >>> len(sent_emails)
    1
    >>> email, pin = sent_emails.pop(0)
    >>> email
    'foo@bar.com'

    try to confirm that request with a mismatched pin
    >>> import random
    >>> new_pin = str(random.random())[-8:]
    >>> while new_pin == pin:
    ...     new_pin = str(random.random())[-8:]
    >>> conf_subject = 'Re: subscription confirmation [%s]' % new_pin
    >>> request = {'email': 'foo@bar.com', 'subject': conf_subject}
    >>> from Products.listen.config import MEMBERSHIP_PIN_MISMATCH
    >>> p.enforce(request) == MEMBERSHIP_PIN_MISMATCH
    True

    try with a correct pin
    >>> conf_subject = 'Re: subscription confirmation [%s]' % pin
    >>> request = {'email': 'foo@bar.com', 'subject': conf_subject}
    >>> p.enforce(request) == MEMBERSHIP_DEFERRED
    True
    >>> len(sent_mod_emails)
    1

    approve a deferred subscription request
    >>> request = {'email': 'foo@bar.com', 'action':'Approve'}
    >>> from Products.listen.config import MODERATION_SUCCESSFUL, MEMBERSHIP_DENIED
    >>> p.enforce(request) == MODERATION_SUCCESSFUL
    True

    try to confirm a user that has not first sent a subscription request
    >>> p.enforce({'email':'lucy@bar.com', 'subject': conf_subject}) == MEMBERSHIP_DENIED
    True

    unsubscribe member
    >>> sent_emails = []
    >>> request = {'email': 'foo@bar.com', 'subject': 'unsubscribe'}
    >>> p.enforce(request) == MEMBERSHIP_DEFERRED
    True
    >>> email, pin = sent_emails.pop(0)
    >>> conf_subject = 'Re: unsubscribe confirmation [%s]' % pin
    >>> request = {'email': 'foo@bar.com', 'subject': conf_subject}
    >>> p.enforce(request) == MEMBERSHIP_ALLOWED
    True

    try a subscription request from someone who is already an allowed sender
    >>> from Products.listen.interfaces import IWriteMembershipList
    >>> mem_list = IWriteMembershipList(ml)
    >>> sent_emails = []
    >>> mem_list.add_allowed_sender('hiya@doom.com')
    >>> request = {'email': 'hiya@doom.com', 'subject': 'subscribe'}
    >>> p.enforce(request) == MEMBERSHIP_ALLOWED
    True

    handle a new subscription request reject it
    >>> p.enforce({'email':'folly@shame.com' , 'subject':'subscribe me'}) == MEMBERSHIP_DEFERRED
    True
    >>> email, pin = sent_emails.pop(0)
    >>> conf_subject = 'Re: subscription confirmation [%s]' % pin
    >>> request = {'email': 'folly@shame.com', 'subject': conf_subject}
    >>> p.enforce(request) == MEMBERSHIP_DEFERRED
    True
    >>> request = {'email': 'folly@shame.com', 'action':'reject', 'reject_reason':'sorry man'}
    >>> p.enforce(request) == MODERATION_SUCCESSFUL
    True
    >>> sent_emails
    [('folly@shame.com', 'sorry man')]

    handle a new subscription request discard it
    >>> p.enforce({'email':'fleem@shame.com' , 'subject':'subscribe me'}) == MEMBERSHIP_DEFERRED
    True
    >>> email, pin = sent_emails.pop(0)
    >>> conf_subject = 'Re: subscription confirmation [%s]' % pin
    >>> request = {'email': 'fleem@shame.com', 'subject': conf_subject}
    >>> p.enforce(request) == MEMBERSHIP_DEFERRED
    True
    >>> sent_emails=[]
    >>> request = {'email': 'fleem@shame.com', 'action':'discarD'}
    >>> p.enforce(request) == MODERATION_SUCCESSFUL
    True
    >>> len(sent_emails)
    0


    """

    implements(IMembershipPolicy)

    def __init__(self, context):
        BaseMembershipPolicy.__init__(self, context)
        self.subscribe_pending_list = getAdapter(context, IMembershipPendingList, 'pending_sub_email')
        self.unsubscribe_pending_list = getAdapter(context, IMembershipPendingList, 'pending_unsub_email')
        self.sub_mod_pending_list = getAdapter(context, IMembershipPendingList, 'pending_sub_mod_email')

    def enforce(self, request):
        user_email = request.get('email')
        user_name = request.get('name')
        action = request.get('action','').lower()
        if user_email is None:
            return MEMBERSHIP_ERROR

        if action:
            self.sub_mod_pending_list.remove(user_email)
            if action == 'approve':
                self.mem_list.subscribe(user_email)
                self.mail_sender.user_welcome(user_email, user_name)
            elif action == 'discard':
                pass
            elif action == 'reject':
                self.mail_sender.user_sub_rejected(user_email, user_name, request.get('reject_reason'))
            return MODERATION_SUCCESSFUL



        # handle unsubscription requests/confirmation
        if self._is_unsubscribe(request):
            if self._is_confirm(request):

                if self.unsubscribe_pending_list.is_pending(user_email):

                    if not self._check_pin(request, self.unsubscribe_pending_list):
                        return MEMBERSHIP_PIN_MISMATCH

                    self.unsubscribe_pending_list.remove(user_email)
                    return MEMBERSHIP_ALLOWED
                else:
                    return MEMBERSHIP_DENIED

            else:
                pin = generate_pin()
                self.mail_sender.user_unsubscribe_request(user_email, user_name, pin)
                self.unsubscribe_pending_list.add(user_email, subscriber=True, pin=pin)
                return MEMBERSHIP_DEFERRED

        # handle subscription requests/confirmation
        if self._is_confirm(request):

            if self.subscribe_pending_list.is_pending(user_email):
                if not self._check_pin(request, self.subscribe_pending_list):
                    return MEMBERSHIP_PIN_MISMATCH

                self.subscribe_pending_list.remove(user_email)

                if self.mem_list.is_allowed_sender(user_email):
                    return MEMBERSHIP_ALLOWED
                else:
                    self.sub_mod_pending_list.add(user_email, user_name=user_name)
                    self.mail_sender.user_sub_mod(user_email, user_name)
                    self.mail_sender.manager_mod(user_email, user_name)
                    return MEMBERSHIP_DEFERRED
            else:
                return MEMBERSHIP_DENIED

        else:
            if self.mem_list.is_allowed_sender(user_email):
                return MEMBERSHIP_ALLOWED
            pin = generate_pin()
            self.mail_sender.user_subscribe_request(user_email, user_name, pin)
            self.subscribe_pending_list.add(user_email, subscriber=True, pin=pin)
            return MEMBERSHIP_DEFERRED


class ModeratedTTWUserMembershipPolicy(BaseMembershipPolicy):
    """
    Adapter to handle the case where a logged in user tries to subscribe ttw to
    a moderated-membership list

    On adding a new user as an allowed sender/subscriber, an email
    should be sent to the managers. 

    The request variable should contain:
    action = 'add_allowed_sender' | 'subscribe' 
    user = 'john@doe.com' | 'JesseParker'

    Setup object for testing
    >>> from Products.listen.extras.tests import TestMailingList
    >>> from Products.listen.content import tests
    >>> ml = TestMailingList()
    >>> from Products.listen.content.membership_policies import ModeratedTTWUserMembershipPolicy
    >>> p = ModeratedTTWUserMembershipPolicy(ml)
    >>> mtool = tests.DummyMembershipTool('')
    >>> ml.portal_membership = mtool
    >>> mtool.result = None


    Monkey patch the send mail method to instead trigger a test result
    >>> sent_mod_emails = []
    >>> def patched_mod_send(to, user):
    ...     sent_mod_emails.append(to)
    >>> p.mail_sender.manager_mod = patched_mod_send

    try an incomplete request
    >>> from Products.listen.config import MEMBERSHIP_ERROR, MEMBERSHIP_DEFERRED, MEMBERSHIP_ALLOWED
    >>> p.enforce({}) == MEMBERSHIP_ERROR
    True

    try a new subscription request
    >>> p.enforce({'email':'foo@bar.com' , 'action':'subscribe'}) == MEMBERSHIP_DEFERRED
    True
    >>> sent_mod_emails
    ['foo@bar.com']

    try a new allowed_sender request
    >>> p.enforce({'email':'pete@bar.com' , 'action':'add_allowed_sender'}) == MEMBERSHIP_DEFERRED
    True
    >>> len(sent_mod_emails)
    2
    
    subscribe an allowed sender (should not require moderation)
    >>> from Products.listen.interfaces import IWriteMembershipList
    >>> mem_list = IWriteMembershipList(ml)
    >>> mem_list.add_allowed_sender('as@peanut.com')
    >>> mem_list.is_allowed_sender('as@peanut.com')
    True
    >>> mem_list.is_subscribed('as@peanut.com')
    False
    >>> p.enforce({'email':'as@peanut.com', 'action':'subscribe'}) == MEMBERSHIP_ALLOWED
    True

    """

    implements(IMembershipPolicy)

    def __init__(self, context):
        BaseMembershipPolicy.__init__(self, context)
        self.sub_mod_pending_list = getAdapter(context, IMembershipPendingList, 'pending_sub_mod_email')
        self.a_s_mod_pending_list = getAdapter(context, IMembershipPendingList, 'pending_a_s_mod_email')
        

    def enforce(self, request):
        action = request.get('action')
        user = request.get('email')
        if action is None or user is None: 
            return MEMBERSHIP_ERROR

        user_email = is_email(user) and user or lookup_email(user, self.context)
        user_name = is_email(user) and lookup_member_id(user, self.context) or user

        if action == 'add_allowed_sender':
            self.a_s_mod_pending_list.add(user)
        elif action == 'subscribe':
            if self.mem_list.is_allowed_sender(user):
                return MEMBERSHIP_ALLOWED
            self.sub_mod_pending_list.add(user, user_name=user_name)
        else:
            return MEMBERSHIP_DENIED           

        self.mail_sender.manager_mod(user_email, user_name)
        return MEMBERSHIP_DEFERRED
