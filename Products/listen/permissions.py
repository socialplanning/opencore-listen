from Products.CMFCore.permissions import setDefaultRoles

AddMailingList = "Listen: Add list"
setDefaultRoles(AddMailingList, ('Manager',))

AddMailMessage = "Listen: Add mail message"
setDefaultRoles(AddMailMessage, ('Manager','Owner'))

ManageSubscriptions= "Listen: Manage subscriptions"
setDefaultRoles(ManageSubscriptions, ('Manager','Owner'))

InviteSubscribers = "Listen: Invite subscribers"
setDefaultRoles(InviteSubscribers, ('Manager', 'Owner'))

ViewSubscribers= "Listen: View subscribers"
setDefaultRoles(ViewSubscribers, ('Manager','Owner'))

SubscribeSelf = "Listen: Subscribe self"
setDefaultRoles(SubscribeSelf, ('Manager','Owner', 'Member', 'Anonymous'))

ModerateMessage = "Listen: Moderate message"
setDefaultRoles(ModerateMessage, ('Manager','Owner'))

EditMailingList = "Listen: Edit mailing list"
setDefaultRoles(EditMailingList, ('Manager','Owner'))

ExportMailingListArchives = "Listen: Export mailing list archives"
setDefaultRoles(ExportMailingListArchives, ('Manager','Owner'))

ImportMailingListArchives = "Listen: Import mailing list archives"
setDefaultRoles(ImportMailingListArchives, ('Manager','Owner'))

ExportMailingListSubscribers = "Listen: Export mailing list subscribers"
setDefaultRoles(ExportMailingListSubscribers, ('Manager','Owner'))

ImportMailingListSubscribers = "Listen: Import mailing list subscribers"
setDefaultRoles(ImportMailingListSubscribers, ('Manager'))
