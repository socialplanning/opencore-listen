from Acquisition import aq_inner, aq_parent
from zope.interface import implements
from zope.app.container.interfaces import IContainerModifiedEvent
from zope.app.container.interfaces import INameChooser
from zope.app.exception.interfaces import UserError

from zExceptions import BadRequest

from Products.CMFCore.utils import getToolByName

# Content objects which wish to use the renamer must have title in the
# set_before_add parameter of their addform configuration, so that the
# title is set on the object before it is added.

class TitleBasedNameChooser:
    """A name chooser for a Zope object manager.  This is a simple adapter
       for container objects which chooses names automatically based on
       the title of objects to be added.

       Consider we have a simple OFS folder which is our container object,
       and a SimpleItem object we wish to add:

         >>> from OFS.Folder import Folder
         >>> test_folder = Folder('test_folder')
         >>> from OFS.SimpleItem import SimpleItem
         >>> test_file = SimpleItem('test_file')

       Let's adapt this folder to our INameChooser implementation:

         >>> name_chooser = TitleBasedNameChooser(test_folder)

       By default our name chooser should use any passed in id, if it is
       already in use it should attempt to find another name by appending a
       number:

         >>> name_chooser.chooseName('test_file', test_file)
         'test_file'
         >>> test_folder._setObject('test_file', SimpleItem('test_file'))
         'test_file'
         >>> name_chooser.chooseName('test_file', test_file)
         'test_file-1'

       When given a blank id it should use the objects class name, and if
       an object by that name already exists it should attempt to find
       another name by appending a number:

         >>> name_chooser.chooseName('', test_file)
         'SimpleItem'
         >>> test_folder._setObject('SimpleItem', SimpleItem('SimpleItem'))
         'SimpleItem'
         >>> name_chooser.chooseName('', test_file)
         'SimpleItem-1'

       The detection of name conflicts is done by the checkName method,
       it uses uses built in methods (checkId from plone or obj._checkId from
       OFS.ObjectManager) to determine if an id is valid and raises an
       exception otherwise.  It also tests whether an id is ascii only:

         >>> ni_hao = '\xe4\xbd\xa0\xe5\xa5\xbd'
         >>> from zope.app.exception.interfaces import UserError
         >>> try:
         ...     name_chooser.checkName(ni_hao, test_file)
         ... except UserError, e:
         ...     'The expected error occurred: %s'%e
         ...
         'The expected error occurred: Id must contain only ASCII characters.'
         >>> try:
         ...     name_chooser.checkName('test_file', test_file)
         ... except UserError, e: # Raised by check_id
         ...     'The expected error occurred: %s'%e
         ...
         'The expected error occurred: The id "test_file" is invalid - it is already in use.'
         >>> try:
         ...     name_chooser.checkName('_test_file', test_file)
         ... except UserError, e: # Raised by check_id
         ...     'The expected error occurred: %s'%e
         ...
         'The expected error occurred: The id "_test_file" is invalid because it begins with an underscore.'

       If 'plone_utils' from plone 2.1 is available via acquisition, then
       the name will be chosen based on the object's title.  Let's create a
       dummy plone_utils, and see how it is used to generate ids.  The dummy
       method just strips out whitespace, the real plone method is much
       smarter:

         >>> from Products.listen.utilities.tests.test_utilities import FakePloneTool
         >>> test_folder._setObject('plone_utils', FakePloneTool('plone_utils'))
         'plone_utils'
         >>> test_file.title = 'My Fake Title'
         >>> name_chooser.getIdFromTitle(test_file.title)
         'my-fake-title'

       The name choosing now uses this method as well:

         >>> name_chooser.chooseName('',test_file)
         'my-fake-title'

       But still prefers explicit ids, and does the normal checking:

         >>> name_chooser.chooseName('my-title',test_file)
         'my-title'
         >>> test_folder._setObject('my-fake-title', SimpleItem('my-fake-title'))
         'my-fake-title'
         >>> name_chooser.chooseName('',test_file)
         'my-fake-title-1'
         >>> test_file.title = ni_hao
         >>> try:
         ...     name_chooser.chooseName('',test_file)
         ... except UserError, e:
         ...     'The expected error occurred: %s'%e
         'The expected error occurred: Id must contain only ASCII characters.'

       When a unicode title is passed in we must get an ascii id back:
         >>> test_file.title = u'My Fake Title 2'
         >>> name_chooser.chooseName('',test_file)
         'my-fake-title-2'
    """

    implements(INameChooser)

    def __init__(self, context):
        self.context = context

    def checkName(self, name, object):
        # ObjectManager can only deal with ASCII names. Specially
        # ObjectManager._checkId can only deal with strings.
        try:
            name = name.encode('ascii')
        except UnicodeDecodeError:
            raise UserError, "Id must contain only ASCII characters."

        context = self.context
        # XXX: Try Plone check_id script this should become a view/adapter
        try:
            check_id = getattr(object.__of__(context), 'check_id', None)
        except AttributeError:
            # We may not have acquisition available
            check_id = None
        if check_id is not None:
            invalid = check_id(name, required=1)
            if invalid:
                raise UserError, invalid
        # Otherwise fallback on _checkId
        else:
            try:
                self.context._checkId(name, allow_dup=False)
            except BadRequest, e:
                msg = ' '.join(e.args) or "Id is in use or invalid"
                raise UserError, msg

    def chooseName(self, name, object):
        if not name:
            title = getattr(object, 'title', '')
            name = self.getIdFromTitle(title)
            if not name:
                name = object.__class__.__name__
        try:
            name = name.encode('ascii')
        except UnicodeDecodeError:
            raise UserError, "Id must contain only ASCII characters."

        dot = name.rfind('.')
        if dot >= 0:
            suffix = name[dot:]
            name = name[:dot]
        else:
            suffix = ''

        n = name + suffix
        i = 0
        while True:
            i += 1
            try:
                self.context._getOb(n)
            except AttributeError:
                break
            n = name + '-' + str(i) + suffix

        # Make sure the name is valid.  We may have started with
        # something bad.
        self.checkName(n, object)

        return n

    def getIdFromTitle(self, title):
        context = self.context
        plone_tool = getToolByName(context, 'plone_utils', None)
        if plone_tool is not None:
            return plone_tool.normalizeString(title)
        return None


def renameAfterCreation(obj, event):
    """Rename object after first edit.
    """
    # Do no rename when the object is first added
    if not IContainerModifiedEvent.providedBy(event):
        utils = getToolByName(obj, 'plone_utils')
        # Rename only if the current id is autogenerated
        if utils.isIDAutoGenerated(obj.id):
            parent = aq_inner(obj).getParentNode()
            if parent is not None:
                chooser = INameChooser(parent)
                newid = chooser.chooseName('', obj)
                parent.manage_renameObject(obj.id, newid)
    
