##############################################################################
#
# Copyright (c) 2004, 2005 Zope Corporation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
"""Test listen content.

"""

import unittest

# Get our monkeys lined up

from zope.app.component.hooks import setSite, setHooks
from zope.component.testing import tearDown as zcTearDown
from zope.testing import doctest

from Products.listen.interfaces import IMemberLookup
from Products.listen.interfaces import IListLookup
from Products.listen.utilities.list_lookup import ListLookup
from Products.listen.utilities.token_to_email import MemberToEmail
from Products.listen.content.tests import start_log_capture, stop_log_capture

optionflags = doctest.REPORT_ONLY_FIRST_FAILURE | doctest.ELLIPSIS | doctest.NORMALIZE_WHITESPACE # | doctest.REPORT_NDIFF

def test_suite():
    import unittest
    from Testing.ZopeTestCase import FunctionalDocTestSuite
    from Testing.ZopeTestCase import FunctionalDocFileSuite
    from Products.PloneTestCase.PloneTestCase import FunctionalTestCase
    # XXX 'digest' tests need to be first, b/c they depend on some
    # traversal adapter registrations that won't exist once the CA
    # registration is torn down in the tearDown function
    all_tests = unittest.TestSuite((
            FunctionalDocTestSuite('Products.listen.content.digest',
                                   setUp=setup_utility,
                                   tearDown=tearDown,
                                   test_class=FunctionalTestCase,
                                   optionflags=optionflags),
            FunctionalDocTestSuite('Products.listen.content.mailinglist',
                                   setUp=setup_listen_components,
                                   tearDown=tearDown,
                                   test_class=FunctionalTestCase),
            FunctionalDocTestSuite('Products.listen.content.subscriptions',
                                   setUp=setup_utility,
                                   tearDown=tearDown,
                                   test_class=FunctionalTestCase,
                                   optionflags=optionflags),
            FunctionalDocTestSuite('Products.listen.content.membership_handlers',
                                   setUp=setup_utility,
                                   tearDown=tearDown,
                                   test_class=FunctionalTestCase),
            FunctionalDocTestSuite('Products.listen.content.membership_policies',
                                   setUp=setup_utility,
                                   tearDown=tearDown,
                                   test_class=FunctionalTestCase),
            FunctionalDocTestSuite('Products.listen.content.send_mail',
                                   setUp=setup_utility,
                                   tearDown=tearDown,
                                   test_class=FunctionalTestCase),
            FunctionalDocTestSuite('Products.listen.content.post_policies',
                                   setUp=setup_utility,
                                   tearDown=tearDown,
                                   test_class=FunctionalTestCase),
            FunctionalDocFileSuite('mailboxer_list.txt',
                                   package="Products.listen.content.mailboxer_list",
                                   setUp=setup_logging,
                                   tearDown=teardown_logging),
            ))
    return all_tests

def setup_listen_components(self):
    """ register all the components for the listen product """
    setup_utility(self)
    from Products.Five import zcml
    import Products.listen
    import Products.GenericSetup
    zcml.load_config('meta.zcml', Products.GenericSetup)
    zcml.load_config('configure.zcml', Products.GenericSetup)
    zcml.load_config('configure.zcml', Products.listen)

def setup_utility(self):
     """ register the IMemberLookup utility with the portal """
     portal = self.portal
     import Products.Five
     from Products.Five import zcml
     zcml.load_config('meta.zcml', Products.Five)
     zcml.load_config('permissions.zcml', Products.Five)
     zcml.load_config("configure.zcml", Products.Five.site)
     from Products.listen.utilities import tests
     zcml.load_config('configure.zcml', tests)
     from Products.listen.content import tests as content_tests
     zcml.load_config('configure.zcml', content_tests)

     site = portal
     setSite(site)
     sm = site.getSiteManager()
     member_to_email_utility = MemberToEmail()
     sm.registerUtility(member_to_email_utility, IMemberLookup)
     sm.registerUtility(ListLookup('list_lookup'), IListLookup)
     setHooks()
     setup_logging()

def setup_logging(*args, **kw):
    start_log_capture('listen')

def teardown_logging(*args, **kw):
    stop_log_capture('listen')    

def tearDown(*args, **kw):
    stop_log_capture('listen')
    zcTearDown(*args, **kw)


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
