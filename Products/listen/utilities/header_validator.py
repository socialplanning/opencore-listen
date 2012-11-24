from Products.listen.interfaces.utilities import IHeaderValidator
from zope.component import Component
from zope.interface import implements

class DummyHeaderValidator(Component):
    implements(IHeaderValidator)

    def validate_headers(self, headers):
        return False

    def clean_headers(self, headers):
        return headers
