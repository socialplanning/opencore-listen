"""
A collection of common functions used throughout listen

"""

from email.Message import Message
from email import Header
from email.MIMEText import MIMEText
from email.quopriMIME import body_encode

from plone.mail import encode_header

import re
import random

from zope.app.component.hooks import getSite
from zope.app.component.hooks import setSite
from zope.app.component.interfaces import ISite
from zope.component import getUtility

from Acquisition import aq_chain

from Products.listen.interfaces import IMemberLookup
from Products.listen.lib.is_email import is_email
from Products.listen.lib.is_email import email_regex

pin_regex = '\[([0-9]{8})\]\)?$'

def lookup_email(member_id, context):
    results = lookup_emails([member_id])
    return results and results[0] or ''

def lookup_emails(member_ids):
    email_translator = getUtility(IMemberLookup)
    return email_translator.to_email_address(member_ids)

def lookup_member_id(email, context):
    memberid_translator = getUtility(IMemberLookup)
    return memberid_translator.to_memberid(email)

def check_pin(request, pend_list):
    try:
        m = re.search(pin_regex, request['subject'])
        if not m: return False
        pin = m.group(1)
        user_email = request['email']
        expected_pin = pend_list.get_user_pin(user_email)
        return pin == expected_pin
    except KeyError:
        return False

def generate_pin():
    return str(random.random())[-8:]

def is_confirm(request):
    subject = request.get('subject', '')
    return bool(re.search(pin_regex, subject))

def is_unsubscribe(request):
    subject = request.get('subject', '')
    return bool('unsubscribe' in subject)

def headers_to_string(header):
    return '\n'.join('%s: %s' % (k, v) for k,v in header.iteritems())

def create_request_from(post):
    # XXX may need to add additional information to post as necessary
    try:
        header = headers_to_string(post['header'])
        body = post['body']
    except TypeError:
        header = ''
        body = post
    mail_string = '%s\r\n\r\n%s' % (header, body)
    return dict(Mail=mail_string)

def send_pending_posts(context, posts):
    if not posts: return
    # XXX listMail is not in the interface
    for p in posts:
        post = create_request_from(p)
        context.listMail(post)

# copied from plone.mail since we need to modify to change content type header
def construct_simple_encoded_message(from_addr, to_addr, subject, body,
                                  other_headers={}, encoding='utf-8'):
    """The python email package makes it very difficult to send quoted-printable
    messages for charsets other than ascii and selected others.  As a result we
    need to do a few things manually here.  All inputs to this method are
    expected to be unicode or ascii.

    We should be able to pass in some arbitrary unicode stuff and get back
    a sensible encoded message:

        >>> m = construct_simple_encoded_message(u'test@example.com',
        ...     u'test@example.com',
        ...     u'Un Subj\xc3\xa9t',
        ...     u'A simple body with some non ascii t\xc3\xa9xt',
        ...     other_headers = {'X-Test': u't\xc3\xa9st'})
        >>> print m.as_string()
        From: test@example.com
        To: test@example.com
        Subject: Un =?utf-8?b?U3ViasODwql0?=
        Content-Transfer-Encoding: quoted-printable
        Content-Type: text/plain; charset="utf-8"
        X-Test: =?utf-8?b?dMODwqlzdA==?=
        <BLANKLINE>
        A simple body with some non ascii ...
    """

    m = Message()
    m['From'] = encode_header(from_addr, encoding)
    m['To'] = encode_header(to_addr, encoding)
    m['Subject'] = encode_header(subject, encoding)
    # Normally we wouldn't try to set these manually, but the email module
    # tries to be a little too smart here.
    m['Content-Transfer-Encoding'] = 'quoted-printable'
    if 'Content-Type' not in other_headers:
        m['Content-Type'] = 'text/plain; charset="%s"'%encoding
    for key, val in other_headers.items():
        m[key] = encode_header(val, encoding)
    body = body.encode(encoding)
#    body = body_encode(body, eol="\r\n")
    m.set_payload(body)
    return m

def assign_local_role(roleid, userids, role_manager):
    """ assign a local role to a particular user
        this is useful when giving a user the owner role when becoming a
        list manager

        Set up the mock object
        >>> class MockRoleManager(object):
        ...     def __init__(self):
        ...         self.userids = {}
        ...     def users_with_local_role(self, roleid):
        ...         roles = []
        ...         for userid, user_roles in self.userids.items():
        ...             if roleid in user_roles:
        ...                 roles.append(userid)
        ...         return tuple(roles)
        ...     def get_local_roles_for_userid(self, userid):
        ...         return self.userids.get(userid, ())
        ...     def manage_setLocalRoles(self, userid, new_roles):
        ...         self.userids[userid] = new_roles
        ...     def manage_delLocalRoles(self, userids):
        ...         for userid in userids:
        ...             self.manage_setLocalRoles(userid, ())

        >>> rm = MockRoleManager()
        >>> rm.userids
        {}

        Assign one role to one user
        >>> assign_local_role('foo_role', ['bar_user'], rm)
        >>> rm.userids
        {'bar_user': ('foo_role',)}

        Assign a separate role to multiple users
        >>> assign_local_role('quux_role', ['bar_user', 'foo_user'], rm)
        >>> rm.userids['bar_user']
        ('foo_role', 'quux_role')
        >>> rm.userids['foo_user']
        ('quux_role',)

        Reassign the same role to the same users should not effect anything
        >>> assign_local_role('quux_role', ['bar_user', 'foo_user'], rm)
        >>> rm.userids['bar_user']
        ('foo_role', 'quux_role')
        >>> rm.userids['foo_user']
        ('quux_role',)

        Assigning a bogus role to no users should not add anything
        >>> assign_local_role('baz_role', [], rm)
        >>> rm.userids.keys()
        ['bar_user', 'foo_user']

        Assigning a previously assigned role to no users should remove all users
        from that role
        >>> assign_local_role('quux_role', [], rm)
        >>> rm.userids['foo_user']
        ()
        >>> rm.userids['bar_user']
        ('foo_role',)
    """
    old_users_with_role = role_manager.users_with_local_role(roleid)
    new_users_with_role = userids
    set_new_users = set(new_users_with_role)
    set_old_users = set(old_users_with_role)
    users_to_add = set_new_users - set_old_users
    users_to_del = set_old_users - set_new_users
    remove = lambda xs,ys:tuple(set(xs) - set(ys))
    def change_roles_for(userid, op):
        cur_roles = role_manager.get_local_roles_for_userid(userid)
        new_roles = op(cur_roles, (roleid,))
	if new_roles:
	    role_manager.manage_setLocalRoles(userid, new_roles)
        else:
            role_manager.manage_delLocalRoles([userid])
    for userid in users_to_del:
        change_roles_for(userid, remove)
    from operator import add
    for userid in users_to_add:
        change_roles_for(userid, add)

def get_utility_for_context(iface, name=u'', context=None):
    """
    Does a getSite / setSite dance to workaround a
    five.localsitemanager bug.
    """
    orig_site = getSite()
    for context in aq_chain(context):
        if ISite.providedBy(context):
            setSite(context)
            break
    utility = getUtility(iface, name=name, context=context)
    setSite(orig_site)
    return utility
