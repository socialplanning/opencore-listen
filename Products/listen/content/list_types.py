from zope.interface import implements
from zope.component import adapts, getAdapter

from Products.listen.interfaces import IWriteMembershipList
from Products.listen.interfaces import IImportListType
from Products.listen.interfaces import IExportListType
from Products.listen.interfaces import IPublicList
from Products.listen.interfaces import IPostModeratedList
from Products.listen.interfaces import IMembershipModeratedList
from Products.listen.interfaces import IPostPendingList
from Products.listen.interfaces import IMembershipPendingList
from Products.listen.interfaces import IMembershipList
from Products.listen.lib.common import send_pending_posts

class BaseImportExport(object):
    def __init__(self, context):
        self.context = context


class BaseListExport(BaseImportExport):
    """contains common functionality to clear pending lists"""

    def _clear_pending_list(self, interface, names):
        pending_items = []
        for name in names:
            pending_adapter = getAdapter(self.context, interface,
                                         name=name)
            for new_mapping in pending_adapter.clear():
                new_mapping['queue_name'] = name
                pending_items.append(new_mapping)
        return pending_items
        
    def clear(self):
        pending_members = self._clear_pending_list(
            IMembershipPendingList,
            self._member_pending_adapter_names)
        
        pending_posts = self._clear_pending_list(
            IPostPendingList,
            self._post_pending_adapter_names)

        return (pending_members, pending_posts)

    # subclasses can override these attributes as required
    # to clear their pending lists
    _member_pending_adapter_names = \
        ['pending_sub_email',
         'pending_unsub_email',
         'pending_a_s_mod_email']

    _post_pending_adapter_names = ['pending_mod_post']

class PublicListExport(BaseListExport):
    adapts(IPublicList)
    implements(IExportListType)

class PostModeratedListExport(BaseListExport):
    adapts(IPostModeratedList)
    implements(IExportListType)

    _post_pending_adapter_names = ['pending_mod_post',
                                   'pending_pmod_post']

    def __init__(self, context):
        BaseListExport.__init__(self, context)
        self.mem_list = IMembershipList(context)


class MembershipModeratedListExport(BaseListExport):
    adapts(IMembershipModeratedList)
    implements(IExportListType)

    _member_pending_adapter_names = \
        ['pending_sub_email',
         'pending_unsub_email',
         'pending_a_s_mod_email',
         'pending_sub_mod_email']


class BaseListImport(BaseImportExport):
    """contains common functionality for list import adapters"""

    def __init__(self, context):
        BaseImportExport.__init__(self, context)
        self.mem_list = IWriteMembershipList(context)

    def _import_pending_list(self, interface, pending_items, add_hook):
        for mapping in pending_items:
            email = mapping['email']
            queue_name = mapping.get('queue_name', '')

            if not add_hook(queue_name, email, mapping):
                pending_list_adapter = getAdapter(
                    self.context, interface, queue_name)
                if interface == IPostPendingList:
                    pending_list_adapter.add(
                        email, user_name=mapping.get('user_name',''), time=mapping['time'], post=mapping)
                else:
                    pending_list_adapter.add(email, **dict(mapping))

    def import_list(self, pending_members, pending_posts):

        self._import_pending_list(IMembershipPendingList,
                                  pending_members,
                                  self._add_membership_hook)

        self._import_pending_list(IPostPendingList,
                                  pending_posts,
                                  self._add_post_hook)

    # default stubs that subclasses can override to provide
    # custom functionality
    def _add_membership_hook(self, queue_name, email, mapping):
        return False

    def _add_post_hook(self, queue_name, email, mapping):
        return False

class PublicListImport(BaseListImport):
    adapts(IPublicList)
    implements(IImportListType)

    def _add_membership_hook(self, queue_name, email, mapping):
        if queue_name == 'pending_sub_mod_email':
            self.mem_list.subscribe(email)
            return True
        return False

    def _add_post_hook(self, queue_name, email, mapping):
        if queue_name == 'pending_pmod_post':
            if self.mem_list.is_allowed_sender(email):
                send_pending_posts(self.context, [mapping])
            else:
                adapter = getAdapter(
                    self.context, IPostPendingList, 'pending_mod_post')
                adapter.add(email, user_name=mapping.get('user_name',''), time=mapping['time'], post=mapping)
            return True
        return False


class MembershipModeratedListImport(BaseListImport):
    adapts(IMembershipModeratedList)
    implements(IImportListType)

    def _add_post_hook(self, queue_name, email, mapping):
        if queue_name == 'pending_pmod_post':
            if self.mem_list.is_allowed_sender(email):
                send_pending_posts(self.context, [mapping])
            else:
                adapter = getAdapter(
                    self.context, IPostPendingList, 'pending_mod_post')
                adapter.add(email, user_name=mapping.get('user_name',''), time=mapping['time'], post=mapping)
            return True
        return False

class PostModeratedListImport(BaseListImport):
    adapts(IPostModeratedList)
    implements(IImportListType)

    def _add_membership_hook(self, queue_name, email, mapping):
        if queue_name == 'pending_sub_mod_email':
            self.mem_list.subscribe(email)
            return True
        return False

    def _add_post_hook(self, queue_name, email, mapping):
        if queue_name == 'pending_mod_post':
            adapter = getAdapter(
                self.context, IPostPendingList, 'pending_pmod_post')
            adapter.add(email, user_name=mapping.get('user_name',''), time=mapping['time'], post=mapping)
            return True
        return False
