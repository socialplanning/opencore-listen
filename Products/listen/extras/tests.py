from unittest import TestSuite
from zope.interface import implements
from zope.schema import Tuple
from zope.schema import TextLine
from zope.publisher.browser import TestRequest
from zope.testing.doctestunit import DocTestSuite
from Testing.ZopeTestCase import ZopeDocTestSuite
from Products.CMFPlone.tests import PloneTestCase

from Products.listen.content.tests import DummyAnnotableList
from Products.listen.interfaces import IMailingList

def setupBasicFieldRequestAndMembers(portal):
    """Some test setup for the member widget tests, creat a few members,
       return a Tuple based field, and a fake request"""
    field = Tuple(__name__='foo', title=u'Foo',
                  value_type=TextLine(title=u'member'))
    request = TestRequest(form={})
    field.context = portal #bind the field to the portal
    portal.portal_membership.addMember('test1', 'secret', ('Member',), (),
                                       properties={'fullname':'Test User 1',
                                                   'email': 'test1@example.com'
                                                   })
    portal.portal_membership.addMember('test2', 'secret', ('Member',), (),
                                       properties={'fullname':'Test User 2',
                                                   'email': 'test2@example.com'
                                                   })
    return field, request

class TestMailingList(DummyAnnotableList):

    implements(IMailingList)

    title = "MY LIST"
    list_owner = "List Owner <owner@lists.example.com>"
    mailto = "My List <list@lists.example.com>"
    message_sent = False
    message_count = 0
    confirm_count = 0
    bounce_count = 0
    managers = []
    manager_email = ''
    
    def absolute_url(self):
        return 'http://www.example.com/test_list'

    def pin(self, email):
        return "^%s^"%email

    def sendCommandRequestMail(self, address, subject, body, mail_from=None, extra_headers={}):
        self.message = [address, subject, body]
        self.message_count += 1

    def sendBounceTo(self, address, name, subject='No Subject'):
        self.bounce_count += 1
        self.bounce = [address, subject]

    def sendSubscribeConfirmationFor(self, email, name):
        self.confirm_count += 1
        self.confirm = [email, name]

    def listMail(self, post):
        pass

def setup_extras_tests(self):
     portal = self.portal
     import Products.Five
     from Products.Five import zcml
     zcml.load_config('meta.zcml', Products.Five)
     zcml.load_config('meta.zcml', Products.GenericSetup)
     zcml.load_config('permissions.zcml', Products.Five)
     zcml.load_config("configure.zcml", Products.Five.site)
     zcml.load_config('configure.zcml', Products.listen)
     zcml.load_config('configure.zcml', Products.listen.browser)

def test_suite():
    
    return TestSuite((
        ZopeDocTestSuite('Products.listen.extras.member_search',
                         test_class=PloneTestCase.FunctionalTestCase,
                         setUp=setup_extras_tests),
        ZopeDocTestSuite('Products.listen.extras.widgets',
                         test_class=PloneTestCase.FunctionalTestCase,
                         setUp=setup_extras_tests),
        ZopeDocTestSuite('Products.listen.extras.import_export'),
        ))
