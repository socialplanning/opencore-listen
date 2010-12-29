from plone.mail import decode_header

from zope.component import getAdapter
from zope.annotation.interfaces import IAnnotations

from Products.CMFCore.utils import getToolByName
from Products.Five import BrowserView
from Products.Five.browser.pagetemplatefile import ZopeTwoPageTemplateFile

from BTrees.OOBTree import OOBTree

from Products.listen.interfaces import IPostPolicy
from Products.listen.interfaces import IMembershipPolicy
from Products.listen.interfaces import IWriteMembershipList
from Products.listen.interfaces import IMembershipPendingList
from Products.listen.interfaces import IPostPendingList
from Products.listen.interfaces import IMembershipModeratedList
from Products.listen.interfaces import IPostModeratedList
from Products.listen.interfaces import IUserEmailMembershipPolicy
from Products.listen.interfaces import IEmailPostPolicy

from Products.listen.content import PendingList

from Products.listen.i18n import _

from Products.listen.config import PROJECTNAME
from Products.listen.config import MODERATION_FAILED

class ModerationView(BrowserView):
    """A view for moderating things """

    def __init__(self, context, request):
        super(ModerationView, self).__init__(context, request)
        self.mem_list = IWriteMembershipList(context)
        annot = IAnnotations(self.context)
        self.listen_annot = annot.setdefault(PROJECTNAME, OOBTree())
        self.mod_post_pending_list = getAdapter(context, IPostPendingList, 'pending_mod_post')
        self.pmod_post_pending_list = getAdapter(context, IPostPendingList, 'pending_pmod_post')
        self.sub_pending_list = getAdapter(context, IMembershipPendingList, 'pending_sub_mod_email')

    def __call__(self):
        d = self.request.form
        post = email = None
        action = ''
        postid = None
        reject_reason = ''
        plone_utils = getToolByName(self.context, 'plone_utils')

        # first check if mass moderating all posts
        if d.get('discard_all_posts', False):
            action = 'discard'
            policy = getAdapter(self.context, IEmailPostPolicy)
            for post in self.get_pending_lists():
                postid = post['postid']
                email = post['user']
                req = dict(action=action, email=email, postid=postid)
                policy_result = policy.enforce(req)
                if policy_result == MODERATION_FAILED:
                    plone_utils.addPortalMessage(_(u'Could not moderate!'),
                                                 type='error')
                    break
                else:
                    plone_utils.addPortalMessage(_(u'All posts discarded.'),
                                                 type='info')
            self.request.response.redirect(self.nextURL())
            return

        for name, value in d.items():
            if name.endswith('_approve') or \
               name.endswith('_discard') or \
               name.endswith('_reject'):
                action = name.split('_')[-1]
            elif name == 'postid':
                postid = int(value)
            elif name == 'email':
                email = value
            elif name == 'reject_reason':
                reject_reason = value            

        # we only need to check moderation if we have an action specified
        if action:
            # having a post id specified means that we need to moderate posts
            if postid is not None:
                # using email post policy
                # may have to try enforcing the ITTWPostPolicy as well on failure
                policy = getAdapter(self.context, IEmailPostPolicy)
                req = dict(action=action, email=email, postid=postid, reject_reason=reject_reason)
                policy_result = policy.enforce(req)
                if policy_result == MODERATION_FAILED:
                    plone_utils.addPortalMessage(_(u'Could not moderate!'),
                                                 type='error')
                else:
                    plone_utils.addPortalMessage(_(u'Post moderated.'),
                                                 type='info')
            else:
                # same idea between membership policy
                # may have to try the IUserTTWMembershipPolicy if the email policy fails
                policy = getAdapter(self.context, IUserEmailMembershipPolicy)
                req = dict(action=action, email=email, reject_reason=reject_reason)
                policy_result = policy.enforce(req)
                if policy_result == MODERATION_FAILED:
                    plone_utils.addPortalMessage(_(u'Could not moderate!'),
                                                 type='error')
                else:
                    plone_utils.addPortalMessage(_(u'Member moderated.'),
                                                 type='info')
            self.request.response.redirect(self.nextURL())
            return

        return self.index()

    def nextURL(self):
        return '%s/%s' % (self.context.absolute_url(), self.__name__)

    def _get_pending_list(self, pending_list):
        list_out = []
        for user_email in pending_list.get_user_emails():
            posts = pending_list.get_posts(user_email)
            user_name = pending_list.get_user_name(user_email) + ' <' + user_email + '>'
            for post in posts:
                header = post['header']
                body = post['body']
                subject = header.get("subject")
                
                try:
                    subject = decode_header(subject)
                except UnicodeDecodeError:
                    subject = subject.decode("utf-8", 'replace')

                postid = post['postid']
                list_out.append(dict(user=user_email, user_name=user_name, subject=subject, body=body, postid=postid))

        return list_out

    def get_pending_lists(self):
        return self.get_pending_mod_post_list() + self.get_pending_pmod_post_list()

    def get_pending_pmod_post_list(self):
        return self._get_pending_list(self.pmod_post_pending_list)

    def get_pending_mod_post_list(self):
        return self._get_pending_list(self.mod_post_pending_list)

    def Title(self):
        return 'Moderate Things'

    def Description(self):
        return 'Moderate Things'

    def is_post_moderated(self):
        return IPostModeratedList.providedBy(self.context)

    def is_membership_moderated(self):
        return IMembershipModeratedList.providedBy(self.context)

    def get_pending_members(self):
        list_out = []
        for user_email in self.sub_pending_list.get_user_emails():
            user_name = self.sub_pending_list.get_user_name(user_email) + ' <' + user_email + '>'
            list_out.append(dict(user=user_email, user_name=user_name))
        return list_out
