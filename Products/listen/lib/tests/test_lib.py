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
from Testing.ZopeTestCase import Zope2

# Get our monkeys lined up
import Products.Five

def test_suite():
    from zope.testing.doctestunit import DocTestSuite
    from doctest import ELLIPSIS
    return unittest.TestSuite((
        DocTestSuite('Products.listen.lib.browser_utils'),
        DocTestSuite('Products.listen.lib.common', optionflags=ELLIPSIS),
        ))

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
