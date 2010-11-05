# Some skeleton adapters, factories, and tools for tests.

from Acquisition import Implicit
from OFS.Folder import Folder
from OFS.SimpleItem import Item
from Products.listen.interfaces import ISubscriptionList
from zope.annotation.attribute import AttributeAnnotations
from zope.component.interfaces import IFactory
from zope.interface import implementedBy
from zope.interface import implements

import logging

# A dummy subscription adapter
class Subscriptions(object):
    implements(ISubscriptionList)
    subscribers = (u'addr1@example.com',u'addr2@example.com')
    def __init__(self, context):
        self.context = context

# A dummy "Mailing List' which is Anotatable, for use with Subscription
# interfaces
class DummyAnnotableList(AttributeAnnotations):
    reset = False
    title = 'Dummy'
    get_value_fors = {}
    def __init__(self):
        AttributeAnnotations.__init__(self, self)
    def resetBounces(self, addresses):
        self.reset = True
    def getValueFor(self, value):
        # allow user of test to specify certain values if necessary
        # otherwise we just blindly return what gets passed in
        return self.get_value_fors.get(value, value)

class DummyAnnotableAcqList(DummyAnnotableList, Implicit, Item):
    pass

# Some dummy CMF objects
class DummyMembershipTool(object):
    def __init__(self, user):
        self.user = user
    def isAnonymousUser(self):
        return self.user.getId() == 'anon'
    def getAuthenticatedMember(self):
        return self.user
    def getMemberById(self, user_id):
        return getattr(self, user_id)
    def searchForMembers(self, **kw):
        email = kw['email']
        for i in self.__dict__:
            prop = self.__dict__[i]
            if type(prop) is DummyMember:
                if prop.email == email:
                    return [prop]

        return None


class DummyMember(object):
    def __init__(self, id, fullname, email):
        self.id = id
        self.fullname = fullname
        self.email = email
    def getId(self):
        return self.id
    def getProperty(self, prop, default=None):
        return getattr(self, prop, default)
    # for brain conversion
    def _getObject(self):
        return self

# Dummy factories
class SimpleFolderFactory:
    implements(IFactory)
    def __call__(self, id, title, **kwargs):
        folder = Folder(id)
        folder.title = title
        return folder
    
    def getInterfaces(self):
        return implementedBy(Folder)
    
SimpleFolderFactory = SimpleFolderFactory()

def start_log_capture(name=''):
    """Temporarily swallow logging.
    """
    logger = logging.getLogger(name)
    logger._oldpropagate = logger.propagate
    logger._oldhandlers = logger.handlers
    logger.propagate = 0
    class MockHandler(logging.Handler):

        def emit(self, record):
            # Print the message, useful for doctest.
            #print "Logged:"
            #print "%s: %s" % (record.levelname, record.msg)
            pass

    logger.handlers = [MockHandler()]


def stop_log_capture(name=''):
    logger = logging.getLogger(name)
    if hasattr(logger, '_oldhandlers'):
        logger.handlers = logger._oldhandlers
    if hasattr(logger, '_oldpropagate'):
        logger.propagate = logger._oldpropagate

