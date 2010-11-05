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
"""Test forms

$Id: test_forms.py 14595 2005-07-12 21:26:12Z philikon $
"""

import unittest
from zope.component.testing import tearDown as zcTearDown

# Get our monkeys lined up
import Products.Five
# activate the event handler infrastructure
import zope.component.event

# A bogus plone tool for the normalize method
from OFS.SimpleItem import SimpleItem
class FakePloneTool(SimpleItem):
    def normalizeString(self, string):
        return string.replace(' ','-').lower()


# Stop log spew during tests
from Products.listen.content.tests import start_log_capture, stop_log_capture

def setUp(*args, **kw):
    start_log_capture('listen')
    
def tearDown(*args, **kw):
    stop_log_capture('listen')
    zcTearDown(*args, **kw)


def test_suite():
    import unittest
    from Testing.ZopeTestCase import ZopeDocFileSuite
    from Testing.ZopeTestCase import ZopeDocTestSuite
    from zope.testing.doctestunit import DocTestSuite
    return unittest.TestSuite((
            ZopeDocTestSuite('Products.listen.utilities.archive_search'),
            ZopeDocFileSuite('search.txt',package='Products.listen.utilities.tests'),
            ZopeDocTestSuite('Products.listen.utilities.list_lookup',
                             setUp=setUp, tearDown=tearDown),
            ZopeDocTestSuite('Products.listen.utilities.obfuscate_emails'),
            DocTestSuite('Products.listen.utilities.rename'),
            DocTestSuite('Products.listen.utilities.token_to_email'),),)

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
