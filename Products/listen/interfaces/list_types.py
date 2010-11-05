from zope.interface import Interface
from zope.interface.interfaces import IInterface
from zope.interface import Attribute
from zope.interface import implements
from zope.component import adapts
from zope.schema import InterfaceField
from zope.schema import Int

from Products.listen.i18n import _

class IListType(IInterface):
    """marker interface used to indicate the list type"""

class IBaseList(Interface):
    """base list"""

class IPublicList(IBaseList):
    """marker for a public list"""

class IPostModeratedList(IBaseList):
    """marker for a post moderated list"""

class IMembershipModeratedList(IBaseList):
    """marker for a membership moderated list"""

IPublicList.setTaggedValue('definition-name', 'public')
IPostModeratedList.setTaggedValue('definition-name', 'post-moderated')
IMembershipModeratedList.setTaggedValue('definition-name', 'membership-moderated')

class IListTypeDefinition(Interface):
    """used for indicating the type of mailing list"""
    
    title = Attribute("displayable title of list type")
    description = Attribute("displayable description of list type")

    list_marker = InterfaceField(title=_(u'list marker'),
                                 description=_(u'marked interface used to indicate the list type'),
                                 constraint=IListType.providedBy)

    index = Int(title=_(u'sort index'))

class ListDefinitionFactory(object):
    implements(IListTypeDefinition)
    
    def __init__(self, title, description, list_marker, index=100):
        self.title = title
        self.description = description
        self.list_marker = list_marker
        self.index = index

PublicListTypeDefinition = ListDefinitionFactory(
    title=_(u'Public List'),
    description=_(u'Anyone who confirms their email address is valid can post and receive messages.'),
    list_marker=IPublicList,
    index=100)

MembershipModeratedListTypeDefinition = ListDefinitionFactory(
    title=_(u'Members List'),
    description=_(u'Only those approved by the list managers can post and receive messages.'),
    list_marker=IMembershipModeratedList,
    index=300)

PostModeratedListTypeDefinition = ListDefinitionFactory(
    title=_(u'Announce List'),
    description=_(u'Anyone can receive messages, but each posted message has to be approved by the list managers first.'),
    list_marker=IPostModeratedList,
    index=200)


# interfaces to handle switching list types
# first the data is exported, and the list type is responsible for removing
# all pending data
# then the data is imported, and the new list type is responsible for
# setting up all pending data structures

class IImportListType(Interface):
    """interface to handle importing data into a new list type"""

    def import_list(pending_members, pending_posts):
        """Handle importing the new pending members into the new list type.
           Each will be a list of mappings, which contain any relevant
           information needed to add the new lists. For pending members, each
           mapping will at least contain email (may contain additional values,
           like pin or name) For the pending posts, each will at least contain
           email, header, and body. May also contain a value indicating the type
           of queue the post originally was in."""


class IExportListType(Interface):
    """interface to handle exporting data to a new list type"""

    def clear():
        """Return a tuple of all pending members, and pending posts or the list
           type. After exporting, the pending members/posts are removed from the
           list type. Each will be a list of mappings, which will contain at
           least the values specified in the format that the IImportListType
           interface expects."""
