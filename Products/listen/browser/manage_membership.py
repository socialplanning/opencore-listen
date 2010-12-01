from Acquisition import aq_inner
from Products.CMFCore.utils import _checkPermission
from Products.CMFCore.utils import getToolByName

from zope.component import getAdapter
from zope.annotation.interfaces import IAnnotations

from Products.Five import BrowserView
from Products.Five.browser.pagetemplatefile import ZopeTwoPageTemplateFile
from Products.SecureMailHost.SecureMailHost import EMAIL_RE

from BTrees.OOBTree import OOBTree

from Products.listen.interfaces import IMailingList
from Products.listen.interfaces import ISubscriptionList
from Products.listen.interfaces import IMembershipPolicy
from Products.listen.interfaces import IWriteMembershipList
from Products.listen.interfaces import IMembershipPendingList
from Products.listen.interfaces import IManagerTTWMembershipPolicy

from Products.listen.lib.browser_utils import encode
from Products.listen.permissions import SubscribeSelf

from Products.listen.content import PendingList

from Products.listen.i18n import _

from Products.listen.lib.common import is_email
from Products.listen.lib.common import lookup_email

from Products.listen.config import PROJECTNAME
from Products.listen.config import MEMBERSHIP_ALLOWED
from Products.listen.config import MEMBERSHIP_DENIED

class ManageMembersView(BrowserView):
    """A basic view of displaying subscribed members and allowed senders """

    def __init__(self, context, request):
        super(ManageMembersView, self).__init__(context, request)
        self.policy = getAdapter(context, IManagerTTWMembershipPolicy)
        self.mem_list = IWriteMembershipList(context)
    
    def __call__(self):
        if not self.request.get('save', None): return self.index()
        d = self.request.form
        self.errors = ''
        to_remove = []
        subscribed_list = set()
        wassubscribed_list = set()
        for name, value in d.items():
            if name.lower() == 'save' and value.lower() == 'save changes': continue
            valuetype, name = name.split('_', 1)
            if valuetype == 'remove':
                to_remove.append(name.decode('utf-8'))
            elif valuetype == 'subscribed':
                subscribed_list.add(name.decode('utf-8'))
            elif valuetype == 'wassubscribed':
                wassubscribed_list.add(name.decode('utf-8'))
        
        to_subscribe = subscribed_list - wassubscribed_list
        to_unsubscribe = wassubscribed_list - subscribed_list

        self._remove(to_remove)
        self._subscribe(to_subscribe)
        self._unsubscribe(to_unsubscribe)

        psm = ""
        to_add = d.get('add_email', None).strip()
        if to_add:
            subscribed = d.get('add_subscribed', None)
            if self._add(to_add, subscribed):
                psm += 'Added: %s.  ' % to_add
            else:
                psm += 'Bad user or email address: %s.  ' % to_add
            
        if to_remove:
            psm += _(u'Removed: %s.  ') % ', '.join(to_remove)
        if to_subscribe:
            psm += _(u'Subscribed: %s.  ') % ', '.join(to_subscribe)
        if to_unsubscribe:
            psm += 'Unsubscribed: %s.  ' % ', '.join(to_unsubscribe)


        if psm:
            context = aq_inner(self.context)
            plone_utils = getToolByName(context, 'plone_utils')
            plone_utils.addPortalMessage(psm)

        # since this means that we've been posted to
        # we should redirect
        self.request.response.redirect(self.nextURL())

    def nextURL(self):
        return '%s/%s' % (self.context.absolute_url(), self.__name__)

    def can_subscribe_others(self):
        return False

    def _add(self, user, subscribed, subscribe_directly=False):
        request = {'action': 'add_allowed_sender', 'email': user}
        policy_result = self.policy.enforce(request)
        if policy_result == MEMBERSHIP_ALLOWED:
            self.mem_list.add_allowed_sender(user)
        elif policy_result == MEMBERSHIP_DENIED:
            return False

        if subscribed:
            request = {'action': 'subscribe', 'email': user}

            if subscribe_directly and self.can_subscribe_others():
                self.mem_list.subscribe(user)
            else:
                result = self.policy.enforce(request)
                if result == MEMBERSHIP_ALLOWED:
                    self.mem_list.subscribe(user)
        return True

    def _remove(self, remove_list):
        for user in remove_list:
            if self.mem_list.is_subscribed(user):
                request = {'action': 'unsubscribe', 'email':user}
            else:
                request = {'action': 'remove_allowed_sender', 'email':user}
                
            if self.policy.enforce(request) == MEMBERSHIP_ALLOWED:
                self.mem_list.remove_allowed_sender(user)


    def _subscribe_user_directly(self, user):
        return False

    def _subscribe(self, add_list):
        can_subscribe_others = self.can_subscribe_others()
        for user in add_list:
            if can_subscribe_others and self._subscribe_user_directly(user):
                self.mem_list.subscribe(user)
                continue
            request = {'action': 'subscribe', 'email': user}
            policy_result = self.policy.enforce(request)
            if policy_result == MEMBERSHIP_ALLOWED:
                self.mem_list.subscribe(user)


    def _unsubscribe(self, remove_list):
        for user in remove_list:
            request = {'action': 'unsubscribe', 'email': user}
            if self.policy.enforce(request) == MEMBERSHIP_ALLOWED:
                self.mem_list.unsubscribe(user)


    def Title(self):
        return _(u'Manage Allowed Senders')

    def Description(self):
        return _(u'Manage Allowed Senders')

    def allowed_senders_data(self):
        return self.mem_list.allowed_senders_data

    def is_subscribed(self, user):
        return self.mem_list.is_subscribed(user)

    def pending_status(self, user):
        annot = IAnnotations(self.context)
        listen_annot = annot.setdefault(PROJECTNAME, OOBTree())

        subscribe_pending_list = getAdapter(self.context, IMembershipPendingList, 'pending_sub_email')
        unsubscribe_pending_list = getAdapter(self.context, IMembershipPendingList, 'pending_unsub_email')
        sub_mod_pending_list = getAdapter(self.context, IMembershipPendingList, 'pending_sub_mod_email')

        email_address = is_email(user) and user or lookup_email(user, self.context)

        inlist = lambda lst: lst.is_pending(email_address)
        status = lambda msg, lst: msg + lst.get_pending_time(email_address)

        status_msg = ''
        if inlist(subscribe_pending_list):
            status_msg += status('subscription pending user confirmation: ', subscribe_pending_list)
        if inlist(unsubscribe_pending_list):
            status_msg += status('unsubscription pending user confirmation: ', unsubscribe_pending_list)
        if inlist(sub_mod_pending_list):
            status_msg += status('subscription pending manager moderation: ', sub_mod_pending_list)

        return status_msg
