from zope.component import getUtility
from zope.interface import implements

from Products.CMFCore.utils import getToolByName
from Products.CMFCore.interfaces import ISiteRoot
from OFS.SimpleItem import SimpleItem

from AccessControl import Unauthorized

from Products.listen.interfaces import IMemberLookup
try:
    from Products.membrane.config import TOOLNAME as MBTOOLNAME
except ImportError: # membrane is optional
    MBTOOLNAME = ''


class MemberToEmail(SimpleItem):
    """
    Implementation to convert from plone member ids to email addresses

    set up our implementation
    >>> from tests import app
    >>> from Products.listen.content.tests import DummyMembershipTool
    >>> from Products.listen.content.tests import DummyMember
    >>> mtool = DummyMembershipTool('whatever')
    >>> app.portal_membership = mtool
    >>> from zope.component import provideUtility
    >>> provideUtility(app, ISiteRoot)
    >>> me = MemberToEmail(app)

    create some fake members on our fake tool
    >>> mtool.foo = DummyMember('foo', 'foo', 'foo@example.com')
    >>> mtool.bar = DummyMember('bar', 'bar', 'bar@example.com')
    >>> mtool.baz = DummyMember('baz', 'baz', 'baz@example.com')

    try converting an empty list of members
    >>> me.to_email_address([])
    []

    now try converting one member
    >>> me.to_email_address(['foo'])
    ['foo@example.com']

    and now try 3 at a time
    >>> me.to_email_address('foo bar baz'.split())
    ['foo@example.com', 'bar@example.com', 'baz@example.com']

    try going the other way: email --> memberid
    >>> me.to_memberid('foo@example.com')
    'foo'

    """
    
    implements(IMemberLookup)

    def __init__(self, id='listen_member_lookup'):
        self.id = id
        site = self.site = getUtility(ISiteRoot)
        self.mtool = getToolByName(site, 'portal_membership')

    def _lookup_memberid(self, member_id):
        member_obj = self.mtool.getMemberById(member_id)

        if member_obj is None: return None
        try:
            return member_obj.getProperty('email', None)
        except Unauthorized, e:
            try:
                # Maybe we have CMFMember/remember, if not reraise
                return member_obj.getEmail()
            except AttributeError:
                raise e

    def to_email_address(self, tokens):
        return filter(None, map(self._lookup_memberid, tokens))

    def to_memberid(self, email):
        mems = self.mtool.searchForMembers(email=email)
        if mems:
            # is this the best way of getting the member id from a search?
            mem = mems[0]
            return mem.getId()
        else:
            return None


class MembraneMemberToEmail(MemberToEmail):
    """ override searches to use the membrane tool """

    def __init__(self, id_index='getId', email_index='getEmail'):
        super(MembraneMemberToEmail, self).__init__(self)
        # provide configurability hooks for id and email index names
        self.id_index = id_index
        self.email_index = email_index
        self.mbtool = getToolByName(self.site, MBTOOLNAME)

    def _search(self, query_dict, prop):
        """ generic search method """
        brains = self.mbtool(**query_dict)
        if brains:
            # assert we only got one result?
            brain = brains[0]
            return getattr(brain, prop)
        else:
            return None

    # these override the superclass methods
    def _lookup_memberid(self, member_id):
        query = {self.id_index: member_id}
        return self._search(query, self.email_index)

    def to_memberid(self, email):
        query = {self.email_index: email}
        return self._search(query, self.id_index)
