from mailinglist import MailingList, addMailingList
from mailinglist import archiveOptionsVocabulary
from mailinglist import ListTypeChanged
from mailinglist import list_type_changed
from mailinglist import list_type_vocabulary
from mailinglist import convert_manager_emails_to_memberids
from send_mail import MailSender
from mail_message import MailMessage
from mail_message import MailFromString
from mail_message import SearchableMessage
from subscriptions import SubscriptionList
from subscriptions import WriteSubscriptionList
from subscriptions import MembershipList
from subscriptions import WriteMembershipList
from subscriptions import PendingList
from subscriptions import MembershipDigestList
from subscriptions import WriteMembershipDigestList
from subscriptions import PendingAllowedSenderModeration
from subscriptions import PendingSubscriptionEmail
from subscriptions import PendingSubscriptionModerationEmail
from subscriptions import PendingUnsubscriptionEmail
from subscriptions import PendingAllowedSenderSubscriptionEmail
from subscriptions import PendingModerationPost
from subscriptions import PendingPostModerationPost

from membership_policies import ModeratedTTWUserMembershipPolicy
from membership_policies import ManagerTTWMembershipPolicy
from membership_policies import UserMembershipPolicy
from membership_policies import ModeratedUserMembershipPolicy
from post_policies import PublicEmailPostPolicy
from post_policies import PublicTTWPostPolicy
from post_policies import PostModeratedEmailPostPolicy
from post_policies import PostModeratedTTWPostPolicy
from post_policies import MemModeratedEmailPostPolicy
from post_policies import MemModeratedTTWPostPolicy
from membership_handlers import ConfirmationHandler
from subscriptions import became_allowed_sender
from subscriptions import became_subscriber
from list_types import PublicListImport
from list_types import MembershipModeratedListImport
from list_types import PostModeratedListImport
from list_types import PublicListExport
from list_types import MembershipModeratedListExport
from list_types import PostModeratedListExport
from Products.listen.interfaces import IMembershipList

from Products.CMFCore.utils import getToolByName
from zExceptions import Unauthorized
from topp.utils import zutils
from opencore.interfaces import IProject

def archive_privacy(obj, event):
    # If the list doesn't have private archives we don't need to worry
    if not getattr(obj, 'private_archives', False):
        return

    auth = obj.openplans.aq_inner.acl_users.credentials_signed_cookie_auth
    creds = auth.extractCredentials(obj.REQUEST) or {}
    username = creds.get('login', None)
    if not username:
        raise Unauthorized()

    site = obj.openplans.aq_inner
    try:
        user = site.portal_memberdata[username]
    except:
        raise Unauthorized()

    mem_list = IMembershipList(obj)
    email = user.getEmail()

    if email in mem_list.subscribers:
        return

    if email in obj.managers or username in obj.managers:
        return

    project = zutils.aq_iface(obj, IProject)
    if not project:
        return Unauthorized()
    project_admins = project.projectMemberIds(admin_only=True)
    if username in project_admins:
        return

    # TODO: allow site admins

    raise Unauthorized()
