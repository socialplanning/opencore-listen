import zope
from zope.component import getUtility
from zope.component import adapts
from zope.interface import implements
from zope.formlib.form import Form
from zope.formlib.form import action
from zope.formlib.form import Fields
from zope.app.annotation.interfaces import IAnnotations
from zope.event import notify

from persistent.list import PersistentList
from BTrees.OOBTree import OOBTree

from Products.Five.browser.pagetemplatefile import ZopeTwoPageTemplateFile

from Products.listen.interfaces import IMailingList
from Products.listen.interfaces import IListLookup
from Products.listen.interfaces import IMigrateList
from Products.listen.interfaces import IWriteMembershipList
from Products.listen.interfaces.list_types import PublicListTypeDefinition
from Products.listen.interfaces.list_types import PostModeratedListTypeDefinition
from Products.listen.interfaces.list_types import MembershipModeratedListTypeDefinition
from Products.listen.config import PROJECTNAME
from Products.listen.interfaces import IPostPendingList

from Products.MailBoxer.MailBoxerTools import splitMail

from zope.component import getAdapter

from Products.listen.i18n import _

from rfc822 import parseaddr

from Products.listen.content import convert_manager_emails_to_memberids

from Products.CMFCore.utils import getToolByName

class MigrationView(Form):
    """view to migrate mailing lists"""

    form_fields = Fields()
    result_template = ZopeTwoPageTemplateFile('browser/migration.pt')

    @action(_('label_migrate', u'Migrate'))
    def handle_migrate_action(self, action, data):

        # permission checking needed since setting the permission
        # in zcml doesn't seem to work
        mtool = getToolByName(self.context, 'portal_membership')
        if not mtool.checkPermission('Manage Portal', self.context):
            return 'permission denied'


        ll = getUtility(IListLookup)
        mappings = ll.showAddressMapping()
        self.nlists = len(mappings)
        self.results = []
        for mapping in mappings:
            path = mapping['path']
            try:
                ml = self.context.unrestrictedTraverse(path)
                migrator = IMigrateList(ml)
                return_msg = migrator.migrate()
                absolute_url = ml.absolute_url()
            except AttributeError:
                return_msg = 'Error: List not found'
                absolute_url = ''

            self.results.append({'url':absolute_url, 'title':path, 'msg':return_msg})
        return self.result_template.render()

    def results(self):
        return self.results

    def num_lists(self):
        return self.nlists

class TestMigration(object):
    implements(IMigrateList)
    adapts(IMailingList)

    def __init__(self, context):
        self.context = context

    def is_updated(self):
        return False

    def migrate(self):
        return 'successfully migrated'


class ListMigrationFromPropertiesToPolicies(object):
    implements(IMigrateList)
    adapts(IMailingList)

    def __init__(self, context):
        self.context = context
        annot = IAnnotations(context)
        self.listen_annot = annot.setdefault(PROJECTNAME, OOBTree())
        self.migration_annot = self.listen_annot.setdefault('migration', PersistentList())        

    def is_updated(self):
        return 'policy_migration' in self.migration_annot or (not hasattr(self.context, 'list_type'))

    def migrate(self):
        if self.is_updated(): 
            return 'already migrated'
        
        # set the appropriate list type based on the previous settings
        # this may need to mark the appropriate interface on the mailing
        # list as well
        if self.context.moderated:
            self.context.list_type = PostModeratedListTypeDefinition
        elif self.context.closed:
            self.context.list_type = MembershipModeratedListTypeDefinition
        else:
            self.context.list_type = PublicListTypeDefinition

        # copy over the membership stuff
        annot = IAnnotations(self.context)
        listen_annot = annot.get('listen', {})
        old_subscribers = listen_annot.get('subscribers', [])

        # create the new annotations by using current adapters
        mem_list = IWriteMembershipList(self.context)
        for subscriber in old_subscribers:
            mem_list.subscribe(subscriber)

        # unsubscribe (but leave as allowed senders) those who don't 
        # receive mail
        nomail = listen_annot.get('norecvmail', [])
        for allowed_sender in nomail:
            mem_list.unsubscribe(allowed_sender)

        # copy over the moderation messages
        self.mod_post_pending_list = getAdapter(self.context, IPostPendingList, 'pending_pmod_post')
        for i in self.context.mqueue.objectIds():
            (header, body) = splitMail(self.context.mqueue[i])
            post = {'header':header, 'body':body}
            (user_name, user_email) = parseaddr(header.get('from', ''))
            self.mod_post_pending_list.add(user_email, user_name=user_name, post=post)

        # creates list managers from moderators and list owner
        managers = []
        managers.append(self.context.list_owner)
        for moderator in self.context.moderators:
            managers.append(moderator)
        self.context.managers = tuple(managers)
        convert_manager_emails_to_memberids(self.context)

        # translate archived vocabulary
        if self.context.archived == 'not archived':
            self.context.archived = 2
        elif self.context.archived == 'plain text':
            self.context.archived = 1
        elif self.context.archived == 'with attachments':
            self.context.archived = 0
        else:
            return 'error translating archive option'

        # annotate the list to say the migration completed
        self.migration_annot.append('policy_migration')

        return 'successfully migrated'
