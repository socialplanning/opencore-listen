from zope.interface import implements
from zope.interface import directlyProvides
from zope.interface import implementedBy
from zope.interface import Declaration
from zope.component.interfaces import IFactory

from OFS.Folder import Folder
from Products.BTreeFolder2.BTreeFolder2 import BTreeFolder2 as BTreeFolder

from Products.listen.interfaces import IModerationQueue
from Products.listen.interfaces import IListArchive
from Products.listen.interfaces import IListArchiveSubFolder

from Products.listen.utilities.archive_search import ZCatalogSearchArchive

from mail_message import MailMessage


class MailFactory:
    """A factory for mail objects, feel free to provide your own to use a
       custom class."""
    implements(IFactory)

    def __call__(self, id, from_addr, subject, date, **kwargs):
        message = MailMessage(id, from_addr, subject, date, **kwargs)
        return message

    def getInterfaces(self):
        return implementedBy(MailMessage)


class QueueFactory:
    """A factory for the moderation queue, feel free to provide your own."""
    implements(IFactory)

    def __call__(self, id, title):
        # The queue might get large, and we don't want it showing its
        # contents in navigation
        mqueue = BTreeFolder(id)
        mqueue.title = title
        directlyProvides(mqueue,IModerationQueue)
        return mqueue

    def getInterfaces(self):
        return Declaration(IModerationQueue,)


class ArchiveFactory:
    """A factory for the mail archive, feel free to provide your own."""
    implements(IFactory)

    def __call__(self, id, title):
        archive = Folder(id)
        archive.title = title
        directlyProvides(archive, IListArchive)
        return archive

    def getInterfaces(self):
        return Declaration(IListArchive,)


class FolderFactory:
    """A factory for the mail archive, feel free to provide your own."""
    implements(IFactory)

    def __call__(self, id, title, **kwargs):
        if kwargs.get('btree', None):
            folder = BTreeFolder(id)
        else:
            folder = Folder(id)
        folder.title = title
        directlyProvides(folder, IListArchiveSubFolder)
        return folder

    def getInterfaces(self):
        # Folder and BTreeFolder should implement the same things
        return Declaration(IListArchiveSubFolder,)


class SearchUtilityFactory:
    """A factory for the search catalog, feel free to provide your own."""
    implements(IFactory)

    def __call__(self, id):
        catalog = ZCatalogSearchArchive(id)
        return catalog

    def getInterfaces(self):
        return implementedBy(ZCatalogSearchArchive)


# Factories are instances
MailFactory = MailFactory()
QueueFactory = QueueFactory()
ArchiveFactory = ArchiveFactory()
FolderFactory = FolderFactory()
SearchUtilityFactory = SearchUtilityFactory()