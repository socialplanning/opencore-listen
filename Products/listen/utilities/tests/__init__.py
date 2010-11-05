# Make a module and provide some skeleton adapters, factories, and tools
from OFS.Folder import Folder
from Acquisition import Implicit
from Acquisition import aq_base
from Acquisition import aq_chain

from Products.Five.component import enableSite
from Products.Five.component.interfaces import IObjectManagerSite
from Products.Five.site.localsite import FiveSite

from Products.listen.interfaces import IMailingList
from Products.listen.interfaces import IMailMessage
from Products.listen.interfaces import ISearchableMessage
from Products.listen.interfaces import ISearchableArchive
from Products.listen.content import SearchableMessage
from Products.listen.utilities.archive_search import ZCatalogSearchArchive

from zope.app.component.interfaces import ISite
from zope.component import provideAdapter
from zope.component.globalregistry import base
from zope.component.interfaces import IComponentLookup
from zope.component.persistentregistry import PersistentComponents
from zope.interface import directlyProvides

# We need some Zope2 stuff to make and test a real catalog
from Testing.ZopeTestCase import Zope2
# We need a couple of index Products
Zope2.installProduct('ExtendedPathIndex')
Zope2.installProduct('ZCTextIndex')
Zope2.installProduct('ManagableIndex')
# A catalog needs a zope, sadly.
app = Zope2.app()

# A dummy mailing list which acts as a possible Site
# interface and the views.
class FakeMailingList(Implicit, Folder, FiveSite):

    mailto = None

    def __init__(self, id):
        self.id = id
        self._msgs = []

    def manage_mailboxer(self, request):
        return 'Success %s'%self.mailto

    def _getProducts(self):
        return app._getProducts()

    def addMail(self, msg):
        self._msgs.append(msg)
        return FakeMessage(msg)

class FakeMessage:

    def __init__(self, msg, from_addr=None, subject=None, body=None, 
                 message_id=None, date=None, references=None, 
                 in_reply_to=None, has_attachment=False):
        self.msg = msg
        self.from_addr = from_addr
        self.subject = subject
        self.body = body
        self.message_id = message_id
        self.date = date
        self.references = references
        self.in_reply_to = in_reply_to
        self.has_attachment = has_attachment

    def getId(self):
        return self.msg

    def objectIds(self, spec=None):
        if self.has_attachment:
            return ['fileid1']
        else:
            return []
        
    def _getOb(self, id):
        return FakeFile()

    def getObject(self):
        return self


class FakeFile(object):
    def __init__(self):
        self.title = "fake.txt"
        self.data = "Do you want to die, Mr. Bond?"

    def getContentType(self):
        return "text/plain"
    


def fake_component_adapter(obj):
    return obj.getSiteManager()

def register_fake_component_adapter():
    provideAdapter(fake_component_adapter,
                   adapts=(ISite,),
                   provides=IComponentLookup)
register_fake_component_adapter()

provideAdapter(SearchableMessage,
               adapts=(IMailMessage,),
               provides=ISearchableMessage)

def enable_local_site(obj):
    enableSite(obj, iface=IObjectManagerSite)
    for parent in aq_chain(obj)[1:]:
        if ISite.providedBy(parent):
            p_sm = parent.getSiteManager()
            bases = (p_sm,) + p_sm.__bases__
            break
    else:
         bases = (base,)   
    components = PersistentComponents()
    components.__bases__ = bases
    obj.setSiteManager(components)

def install_searchable_archive(ml, suppress_events=False):
    mail_catalog = ZCatalogSearchArchive('ISearchableArchive')
    ml._setObject('ISearchableArchive', mail_catalog,
                  suppress_events=suppress_events)
    mail_catalog = ml.ISearchableArchive
    mail_catalog.manage_afterAdd(mail_catalog, ml)
    sm = ml.getSiteManager()
    sm.registerUtility(mail_catalog, aq_base(ISearchableArchive))

def install_fake_ml(container, mailto='fake_address@example.com',
                    suppress_events=False):
    ml = FakeMailingList('ml')
    directlyProvides(ml, IMailingList)
    ml_id = container._setObject('ml', ml, suppress_events=suppress_events)
    ml = getattr(container, ml_id)
    enable_local_site(ml)
    install_searchable_archive(ml, suppress_events=suppress_events)
    ml.mailto = mailto
    return ml
