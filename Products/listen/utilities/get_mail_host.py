from zope.interface import implements

from Products.CMFCore.utils import getToolByName

from OFS.SimpleItem import SimpleItem

from Products.listen.interfaces import IGetMailHost

class GetMailHost(SimpleItem):
    """
    this class is registered as a local utility
    """
    
    implements(IGetMailHost)

    def __init__(self, context):
        self.mhost = getToolByName(context, 'MailHost')

    @property
    def mail_host(self):
        return self.mhost

    
