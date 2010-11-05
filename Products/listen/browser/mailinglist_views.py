import zope
from zope.event import notify

from zope.interface.common import idatetime

from BTrees.OOBTree import OOBTree

from Acquisition import aq_inner
from AccessControl.interfaces import IRoleManager

from Products.Five import BrowserView
from Products.Five.browser.pagetemplatefile import ZopeTwoPageTemplateFile
from Products.SecureMailHost.SecureMailHost import EMAIL_RE

from Products.CMFCore.utils import _checkPermission
from Products.CMFCore.utils import getToolByName

from Products.statusmessages.interfaces import IStatusMessage

from Products.listen.interfaces import IMailingList
from Products.listen.interfaces import IWriteMembershipList
from Products.listen.interfaces import IMembershipList
from Products.listen.interfaces import IMembershipPolicy
from Products.listen.interfaces import IMembershipPendingList
from Products.listen.interfaces import IUserTTWMembershipPolicy
from Products.listen.interfaces import IUserEmailMembershipPolicy

from Products.listen.content import archiveOptionsVocabulary

from Products.listen.lib.browser_utils import encode, obfct_de
from Products.listen.lib.common import assign_local_role
from Products.listen.permissions import SubscribeSelf

from Products.listen.i18n import _
from Products.listen.lib.common import is_email
from Products.listen.lib.common import lookup_email

from Products.listen.config import PROJECTNAME
from Products.listen.config import MEMBERSHIP_ALLOWED
from Products.listen.config import MEMBERSHIP_DEFERRED

from Products.listen.content import ListTypeChanged

from zope.component import getAdapter
from zope.app.annotation.interfaces import IAnnotations

from Products.listen.i18n import _

class MailingListView(BrowserView):
    """A basic view of a mailing list"""

    def __call__(self):
        sub_action = self.request.get('subscribe_member', None)
        unsub_action = self.request.get('unsubscribe_member', None)
        email_action = self.request.get('subscribe_email', None)
        self.request.set('enable_border', True)
        self.errors = errors = {}

        logged_in_mem = self._get_logged_in_user()
        self.user_logged_in = False
        if logged_in_mem:
            self.user_email = lookup_email(logged_in_mem.getId(), self.context)
            self.user_logged_in = True
        else:
            #XXX what should this be?
            self.user_email = ''

        self.mem_list = IWriteMembershipList(self.context)

        # the appropriate sub_policy needs to be instantiated
        # depending on list type
        self.sub_policy = getAdapter(self.context, IUserTTWMembershipPolicy)

        if sub_action:
            self.subscribe()
        elif unsub_action:
            self.unsubscribe()
        elif email_action:
            address = self.request.get('email_address', None)
            if not address:
                errors['email_address'] = _('An email address is required')
            elif EMAIL_RE.match(address) is None:
                errors['email_address'] = _('This email address is invalid')
            elif self.mem_list.is_subscribed(address):
                errors['email_address'] = \
                                 _('This email address is already subscribed')
            else:
                # everything is OK, send a request mail the
                # appropriate sub_policy needs to be instantiated
                # depending on list type
                sub_policy_for_email = getAdapter(self.context, IUserEmailMembershipPolicy)

                ret = sub_policy_for_email.enforce({'email':address,
                                                    'subject':'subscribe'})
                if ret == MEMBERSHIP_ALLOWED:
                    # make user a subscriber
                    self.mem_list.subscribe(address)
                    self.request.set('portal_status_message', 'Email subscribed')
                elif ret == MEMBERSHIP_DEFERRED:
                    self.request.set('portal_status_message',
                                     'Subscription request sent')
                else:
                    self.request.set('portal_status_message', 'Bad email address')
                    
                # Blank the email field to avoid the postback
                self.request.set('email_address', '')
                self.request.set('subscribe_email', '')

        return self.index()

    def Title(self):
        return encode(self.context.title, self.context)

    def Description(self):
        return encode(self.context.description, self.context)

    def address(self):
        if not self.context.mailto:
            return u''
        return obfct_de(encode(self.context.mailto, self.context))

    def archived(self):
        archived = self.context.archived
        vocab = archiveOptionsVocabulary(self.context)
        return vocab.getTerm(archived).token + '. '
    
    def is_archived(self):
        return self.context._is_archived()

    def list_managers(self):
        managers = []
        creator = self.context.Creator()
        for manager in self.context.managers:
            if manager == creator:
                managers.append('%s (creator)' % manager)
            else:
                managers.append(manager)
        return managers

    def list_title(self):
        return self.context.Title()

    def list_type(self):
        list_type = self.context.list_type
        if list_type is None:
            return _(u'List Type not set')
        return '%s. %s' % (list_type.title, list_type.description)

    def subscribe_keyword(self):
        # Mailboxer stores the subject line keyword used for subscribing as
        # a property
        return self.context.getValueFor('subscribe')

    def unsubscribe_keyword(self):
        # Mailboxer stores the subject line keyword used for unsubscribing as
        # a property
        return self.context.getValueFor('unsubscribe')

    def subscribe(self):
        req = {'action':'subscribe', 'email':self.user_email}
        if self.user_logged_in:
            req['use_logged_in_user'] = True
        ret = self.sub_policy.enforce(req)
                                       
        if ret == MEMBERSHIP_ALLOWED:
            self.mem_list.subscribe(self.user_email)
            self.request.set('portal_status_message',
                             'You have been subscribed')
            pass
        elif ret == MEMBERSHIP_DEFERRED:
            self.request.set('portal_status_message',
                             'Your subscription request is pending moderation '
                             'by the list manager.')       

    def unsubscribe(self):
        self.mem_list.unsubscribe(self.user_email)
        self.request.set('portal_status_message', 'You have been unsubscribed')

    def _get_logged_in_user(self):
        mtool = getToolByName(self.context, 'portal_membership')
        return mtool.getAuthenticatedMember()

    def isSubscribed(self):
        if self.user_email:
            return self.mem_list.is_subscribed(self.user_email)
        else:
            return False

    def isPending(self):
        annot = IAnnotations(self.context)
        sub_mod_pending_list = getAdapter(self.context,
                                          IMembershipPendingList,
                                          'pending_sub_mod_email')

        return sub_mod_pending_list.is_pending(self.user_email)

    def canSubscribe(self):
        return _checkPermission(SubscribeSelf, self.context)

    def manager_email(self):
        if not self.context.manager_email:
            return u''
        return obfct_de(self.context.manager_email)


class MailingListArchiveView(BrowserView):
    """A basic view for the mailing list archive.
    """
    def name(self):
        return encode(self.context.title, self.context)
    
    def archive(self):
        return self.context.archive


from zope.formlib import form
from base import EditForm

from zope.app.form.browser import TextAreaWidget
from zope.app.form.browser import ASCIIWidget
from zope.app.form.browser import RadioWidget
from Products.listen.browser.listwidget.widget import DynamicListWidget


class DescriptionWidget(TextAreaWidget):
    width = 40
    height = 3


def create_radio_widget(field, request):
    return RadioWidget(field, field.vocabulary, request)

listen_form_fields = form.FormFields(IMailingList)
listen_form_fields['description'].custom_widget = DescriptionWidget
listen_form_fields['mailto'].custom_widget = ASCIIWidget
listen_form_fields['archived'].custom_widget = create_radio_widget
listen_form_fields['list_type'].custom_widget = create_radio_widget
listen_form_fields['managers'].custom_widget = DynamicListWidget


class MailingListAddForm(form.AddForm):
    """A form for adding MailingList objects.
    """
    form_fields = listen_form_fields
    
    portal_type = 'MailingList'

    label = _(u"Add Mailing List")

    def _assign_local_roles_to_managers(self, ml):
        assign_local_role('Owner', ml.managers, IRoleManager(ml))

    def createAndAdd(self, data):
        # use aq_inner, or else the obj will be wrapped in this view,
        # will screw up acquired security settings (esp. local roles)
        context = aq_inner(self.context)
        plone_utils = getToolByName(context, 'plone_utils')
        list_id = plone_utils.normalizeString(data['title'])

        context.invokeFactory(self.portal_type, list_id)
        list_ob = context._getOb(list_id)

        old_list_type = list_ob.list_type.list_marker
        new_list_type = data.get('list_type').list_marker

        form.applyChanges(list_ob, self.form_fields, data)

        # ensure correct role is set for users
        self._assign_local_roles_to_managers(list_ob)
        
        # XXX this ObjectCreatedEvent event would normally come before
        # the ObjectAddedEvent
        notify(zope.app.event.objectevent.ObjectCreatedEvent(list_ob))
        notify(ListTypeChanged(list_ob, old_list_type, new_list_type))
        self._finished_add = True

        status = IStatusMessage(self.request)
        status.addStatusMessage(_('Mailing list added.'), type=u'info')

        self._next_url = list_ob.absolute_url()

        return list_ob

    def nextURL(self):
        return self._next_url


class MailingListEditForm(EditForm):
    """A form for editing MailingList objects.
    """
    form_fields = listen_form_fields

    label = _(u"Edit Mailing List")

    def _assign_local_roles_to_managers(self):
        ml = self.context
        assign_local_role('Owner', ml.managers, IRoleManager(ml))

    @form.action(_('label_save', u'Save'), condition=form.haveInputWidgets)
    def handle_save_action(self, action, data):
        old_list_type = self.context.list_type.list_marker
        new_list_type = data.get('list_type').list_marker

        if form.applyChanges(self.context, self.form_fields, data,
                             self.adapters):
            # ensure correct role is set for users
            self._assign_local_roles_to_managers()
            notify(zope.app.event.objectevent.ObjectModifiedEvent(self.context))
            notify(ListTypeChanged(self.context, old_list_type, new_list_type))
            self.status = _(u"Your changes have been saved.")
        else:
            self.status = _(u"No changes need to be saved.")
        return ""

    @form.action(_('label_cancel', u'Cancel'), validator=lambda *a: ())
    def handle_cancel_action(self, action, data):
        self.status = _(u"Edit cancelled.")
        return ""
