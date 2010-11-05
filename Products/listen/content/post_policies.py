import random
import re
from DateTime import DateTime

from zope.component import getAdapter

from Products.listen.lib.common import is_email
from Products.listen.lib.common import send_pending_posts

from persistent.list import PersistentList
from BTrees.OOBTree import OOBTree

from zope.interface import implements
from zope.annotation.interfaces import IAnnotations

from Products.listen.interfaces import IPostPolicy
from Products.listen.interfaces import ISendMail
from Products.listen.interfaces import IWriteMembershipList
from Products.listen.interfaces import IHaveSubscribers
from Products.listen.interfaces import IPostPendingList

from Products.listen.content import PendingList

from Products.listen.config import PROJECTNAME

from Products.listen.config import POST_DENIED
from Products.listen.config import POST_DEFERRED
from Products.listen.config import POST_ALLOWED
from Products.listen.config import POST_ERROR
from Products.listen.config import MODERATION_SUCCESSFUL
from Products.listen.config import MODERATION_FAILED
from Products.listen.lib.common import pin_regex

class BasePostPolicy(object):
    """
    Setup object for testing
    >>> from Products.listen.extras.tests import TestMailingList
    >>> from Products.listen.content import tests
    >>> ml = TestMailingList()
    >>> ml.managers = ['manager@example.com']
    >>> from Products.listen.content.post_policies import BasePostPolicy
    >>> p = BasePostPolicy(ml)
    >>> p.mail_sender.user_subscribe_request('fee@feem.com', 'feemer', '12345676')
    >>> p.mail_sender.user_mod('fee@feem.com', 'feemer')
    >>> p.mail_sender.manager_mod('fee@feem.com', 'feemer')
    >>> ml.message_count
    3

    """

    def __init__(self, context):
        self.context = context
        annot = IAnnotations(context)
        self.listen_annot = annot.setdefault(PROJECTNAME, OOBTree())
        self.mail_sender = ISendMail(context)
        self.mem_list = IWriteMembershipList(context)

    def _check_pin(self, request, pend_list):
        try:
            m = re.search(pin_regex, request['subject'])
            if not m: return False
            pin = m.group(1)
            user_email = request['email']
            expected_pin = pend_list.get_user_pin(user_email)
            return pin == expected_pin
        except KeyError:
            return False

    def _generate_pin(self):
        return str(random.random())[-8:]

    def _is_confirm(self, request):
        subject = request.get('subject', '')
        return bool(re.search(pin_regex, subject))

    def _is_unsubscribe(self, request):
        subject = request.get('subject', '')
        return bool('unsubscribe' in subject)        
       

class PublicEmailPostPolicy(BasePostPolicy):
    """
    Adapter enforces email submissions to a public list.
    If the user is an allowed sender, message is accepted; otherwise, message becomes
    pending and allowed sender confirmation is sent to user, also, managers receive a 
    moderation request for message/stranger; if either of these confirmations are 
    replied-to, the message is accepted and the user becomes an allowed sender

    Setup object for testing
    >>> from Products.listen.extras.tests import TestMailingList
    >>> from Products.listen.content import tests
    >>> ml = TestMailingList()
    >>> from Products.listen.content.post_policies import PublicEmailPostPolicy
    >>> p = PublicEmailPostPolicy(ml)
    >>> mtool = tests.DummyMembershipTool('')
    >>> ml.portal_membership = mtool
    >>> mtool.result = None

    Monkey patch the send mail method to instead trigger a test result
    >>> sent_emails = []
    >>> def patched_send(to, name, pin=''):
    ...     sent_emails.append((to, pin))
    >>> p.mail_sender.user_post_request = patched_send
    >>> p.mail_sender.manager_mod_post_request = patched_send
    >>> p.mail_sender.user_already_pending = patched_send

    try an incomplete request
    >>> from Products.listen.config import POST_ERROR, POST_DEFERRED, POST_ALLOWED, POST_DENIED
    >>> p.enforce({}) == POST_ERROR
    True

    try a new post request
    >>> p.enforce({'email':'foo@bar.com' , 'use_name':'foo', 'post':'hi'}) == POST_DEFERRED
    True
    >>> len(sent_emails)
    2

    make a user an allowed sender and get their post approved
    >>> from Products.listen.interfaces import IWriteMembershipList
    >>> mem_list = IWriteMembershipList(ml)
    >>> mem_list.add_allowed_sender('tam@tammy.com')
    >>> p.enforce({'email':'tam@tammy.com' , 'post':'hi'}) == POST_ALLOWED
    True

    post should be denied for someone who already has a post pending
    >>> p.enforce({'email':'foo@bar.com' , 'use_name':'foo', 'post':'hi'}) == POST_DENIED
    True
    >>> len(sent_emails)
    3

    approve a post simulating a manager moderating
    >>> from Products.listen.config import MODERATION_SUCCESSFUL, MODERATION_FAILED
    >>> p.enforce({'email':'foo@bar.com', 'postid': 0, 'action':'Approve'}) == MODERATION_SUCCESSFUL
    True

    discard a post 
    >>> p.enforce({'email':'ged@bar.com' , 'use_name':'foo', 'post':'hi'}) == POST_DEFERRED
    True
    >>> p.enforce({'email':'ged@bar.com', 'postid': 0, 'action':'Discard'}) == MODERATION_SUCCESSFUL
    True

    """

    implements(IPostPolicy)

    def __init__(self, context):
        BasePostPolicy.__init__(self, context)
        
        # pending list for posts waiting for manager moderation
        self.mod_post_pending_list = getAdapter(context, IPostPendingList, 'pending_mod_post')

        # pending list for strangers waiting to become allowed senders
        self.a_s_pending_list = getAdapter(context, IPostPendingList, 'a_s_pending_sub_email')


    def enforce(self, request):
        user_email = request.get('email')
        user_name = request.get('name')
        post = request.get('post')
        action = request.get('action','').lower()

        if user_email is None:
            return POST_ERROR

        if action:
            postid = request.get('postid')
            if postid is None: return MODERATION_FAILED
            if action=='approve':
                self.mem_list.add_allowed_sender(user_email)
            elif action=='discard':
                self.mod_post_pending_list.remove(user_email)
                self.a_s_pending_list.remove(user_email)
            return MODERATION_SUCCESSFUL

            
        
        if post is None:
            return POST_ERROR

        if self.mem_list.is_allowed_sender(user_email):
            return POST_ALLOWED
        elif self.mod_post_pending_list.is_pending(user_email):
            pin = self.a_s_pending_list.get_user_pin(user_email)
            self.mail_sender.user_already_pending(user_email, user_name, pin)
            return POST_DENIED
        else:
            pin = self._generate_pin()
            self.mod_post_pending_list.add(user_email, user_name=user_name, post=post)
            self.a_s_pending_list.add(user_email, pin=pin)
            self.mail_sender.user_post_request(user_email, user_name, pin)
            self.mail_sender.manager_mod_post_request(user_email, user_name, post)
            return POST_DEFERRED


class PublicTTWPostPolicy(BasePostPolicy):
    """
    Adapter enforces ttw submissions by a logged in user to a public list.
    If user is not an allowed sender, they become one.

    Setup object for testing
    >>> from Products.listen.extras.tests import TestMailingList
    >>> from Products.listen.content import tests
    >>> ml = TestMailingList()
    >>> from Products.listen.content.post_policies import PublicTTWPostPolicy
    >>> p = PublicTTWPostPolicy(ml)
    >>> mtool = tests.DummyMembershipTool('')
    >>> ml.portal_membership = mtool
    >>> mtool.result = None

    try an incomplete request
    >>> from Products.listen.config import POST_ERROR, POST_DENIED, POST_ALLOWED, POST_DEFERRED
    >>> p.enforce({}) == POST_ERROR
    True

    try a new post request
    >>> p.enforce({'email':'foo@bar.com' , 'use_name':'foo', 'post':'hi'}) == POST_ALLOWED
    True

    make a user an allowed sender and get their post approved
    >>> from Products.listen.interfaces import IWriteMembershipList
    >>> mem_list = IWriteMembershipList(ml)
    >>> mem_list.is_allowed_sender('tam@tammy.com')
    False
    >>> p.enforce({'email':'tam@tammy.com' , 'post':'hi'}) == POST_ALLOWED
    True
    >>> mem_list.is_allowed_sender('tam@tammy.com')
    True

    """

    implements(IPostPolicy)

    def __init__(self, context):
        BasePostPolicy.__init__(self, context)

    def enforce(self, request):
        user_email = request.get('email')
        user_name = request.get('name')
        post = request.get('post')
        if user_email is None or post is None:
            return POST_ERROR
        
        if not self.mem_list.is_allowed_sender(user_email):
            self.mem_list.add_allowed_sender(user_email)
        
        return POST_ALLOWED

            


class PostModeratedEmailPostPolicy(BasePostPolicy):
    """
    Adapter enforces email submissions to a post-moderated list.
    The received message becomes pending and the sender is notified of this pending 
    status.  List managers receive a moderation request for the message.

    Setup object for testing
    >>> from Products.listen.extras.tests import TestMailingList
    >>> from Products.listen.content import tests
    >>> ml = TestMailingList()
    >>> from Products.listen.content.post_policies import PostModeratedEmailPostPolicy
    >>> p = PostModeratedEmailPostPolicy(ml)
    >>> mtool = tests.DummyMembershipTool('')
    >>> ml.portal_membership = mtool
    >>> mtool.result = None

    Monkey patch the send mail method to instead trigger a test result
    >>> sent_emails = []
    >>> def patched_send(to, name, pin=''):
    ...     sent_emails.append((to, pin))
    >>> p.mail_sender.user_post_mod_notification = patched_send
    >>> p.mail_sender.user_post_mod_subscribe_notification = patched_send
    >>> p.mail_sender.manager_mod_post_request = patched_send

    try an incomplete request
    >>> from Products.listen.config import POST_ERROR, POST_DEFERRED
    >>> p.enforce({}) == POST_ERROR
    True

    try a new post request
    >>> p.enforce({'email':'foo@bar.com' , 'use_name':'foo', 'post':'hi'}) == POST_DEFERRED
    True
    >>> len(sent_emails)
    2
    >>> p.mod_post_pending_list.get_posts('foo@bar.com')
    [{'body': 'hi', 'header': {}, 'postid': 0}]

    add more posts
    >>> p.enforce({'email':'foo@bar.com' , 'use_name':'foo', 'post':'so hi'}) == POST_DEFERRED
    True
    >>> p.mod_post_pending_list.get_posts('foo@bar.com')
    [{'body': 'hi', 'header': {}, 'postid': 0}, {'body': 'so hi', 'header': {}, 'postid': 1}]

    approve a post simulating a manager moderating
    >>> from Products.listen.config import MODERATION_SUCCESSFUL, MODERATION_FAILED
    >>> p.enforce({'email':'foo@bar.com', 'postid': 0, 'action':'approve'}) == MODERATION_SUCCESSFUL
    True
    >>> p.enforce({'email':'foo@bar.com', 'postid': 0, 'action':'Approve'}) == MODERATION_FAILED
    True

    get a reference to the pending list
    >>> from zope.app.annotation.interfaces import IAnnotations
    >>> from zope.component import getAdapter
    >>> from Products.listen.interfaces import IPostPendingList
    >>> plist = getAdapter(ml, IPostPendingList, 'pending_pmod_post')

    discard a post 
    >>> p.enforce({'email':'ged@bar.com' , 'use_name':'foo', 'post':'hi'}) == POST_DEFERRED
    True
    >>> p.enforce({'email':'ged@bar.com', 'postid': 0, 'action':'disCard'}) == MODERATION_SUCCESSFUL
    True
    >>> plist.get_posts('ged@bar.com')[0]
    Traceback (most recent call last):
    ...
    IndexError: list index out of range

    reject a post simulating a manager moderating
    >>> p.enforce({'email':'foo@bar.com', 'postid': 1, 'action':'Reject', 'reject_reason':'dumb post'}) == MODERATION_SUCCESSFUL
    True
    >>> plist.get_posts('ged@bar.com')[0]
    Traceback (most recent call last):
    ...
    IndexError: list index out of range
    
    """

    implements(IPostPolicy)

    def __init__(self, context):
        BasePostPolicy.__init__(self, context)
        
        # pending list for posts waiting for manager moderation
        self.mod_post_pending_list = getAdapter(context, IPostPendingList, 'pending_pmod_post')


    def enforce(self, request):
        user_email = request.get('email')
        user_name = request.get('name')
        post = request.get('post')
        action = request.get('action','').lower()
        postid = request.get('postid')
        if user_email is None:
            return POST_ERROR

        if action:
            post = self.mod_post_pending_list.pop_post(user_email, postid)
            if post is None:
                return MODERATION_FAILED
            if action == 'approve':
                send_pending_posts(self.context, [post])
            elif action == 'discard':
                pass
            elif action == 'reject':
                self.mail_sender.user_post_rejected(user_email, user_name, request.get('reject_reason'))
            return MODERATION_SUCCESSFUL

        if post is None:
            return POST_ERROR

        self.mod_post_pending_list.add(user_email, user_name=user_name, post=post)

        # notify people
        if self.mem_list.is_subscribed(user_email):
            self.mail_sender.user_post_mod_notification(user_email, user_name)
        else:
            self.mail_sender.user_post_mod_subscribe_notification(user_email, user_name)
            
        self.mail_sender.manager_mod_post_request(user_email, user_name, post)
        return POST_DEFERRED



class PostModeratedTTWPostPolicy(BasePostPolicy):
    """
    Adapter enforces ttw submissions by a logged in user to a post-moderated list.
    The message becomes pending.  Managers receive a moderation request for message.

    Setup object for testing
    >>> from Products.listen.extras.tests import TestMailingList
    >>> from Products.listen.content import tests
    >>> ml = TestMailingList()
    >>> from Products.listen.content.post_policies import PostModeratedTTWPostPolicy
    >>> p = PostModeratedTTWPostPolicy(ml)
    >>> mtool = tests.DummyMembershipTool('')
    >>> ml.portal_membership = mtool
    >>> mtool.result = None

    Monkey patch the send mail method to instead trigger a test result
    >>> sent_emails = []
    >>> def patched_send(to, name, pin=''):
    ...     sent_emails.append((to, pin))
    >>> p.mail_sender.manager_mod_post_request = patched_send

    try an incomplete request
    >>> from Products.listen.config import POST_ERROR, POST_DEFERRED
    >>> p.enforce({}) == POST_ERROR
    True

    try a new post request
    >>> p.enforce({'email':'foo@bar.com' , 'use_name':'foo', 'post':'hi'}) == POST_DEFERRED
    True
    >>> len(sent_emails)
    1
    >>> len(p.mod_post_pending_list.get_posts('foo@bar.com'))
    1

    add more posts
    >>> p.enforce({'email':'foo@bar.com' , 'use_name':'foo', 'post':'so hi'}) == POST_DEFERRED
    True
    >>> len(p.mod_post_pending_list.get_posts('foo@bar.com'))
    2

    """

    implements(IPostPolicy)

    def __init__(self, context):
        BasePostPolicy.__init__(self, context)
        
        # pending list for posts waiting for manager moderation
        self.mod_post_pending_list = getAdapter(context, IPostPendingList, 'pending_pmod_post')


    def enforce(self, request):
        user_email = request.get('email')
        user_name = request.get('name')
        post = request.get('post')
        if user_email is None or post is None:
            return POST_ERROR

        # if user_email already has posts pending, adds new post to list
        # otherwise, add new entry in mod_post_pending_list
        self.mod_post_pending_list.add(user_email, user_name=user_name, post=post)

        # notify managers
        self.mail_sender.manager_mod_post_request(user_email, user_name, post)
        return POST_DEFERRED



class MemModeratedEmailPostPolicy(BasePostPolicy):
    """
    Adapter enforces email submissions to a membership moderated list.
    If the user is an allowed sender, message is accepted; otherwise, the 
    message becomes pending and managers receive a moderation request for 
    message & stranger; user receives a message saying that their message
    is waiting for moderation

    Setup object for testing
    >>> from Products.listen.extras.tests import TestMailingList
    >>> from Products.listen.content import tests
    >>> ml = TestMailingList()
    >>> from Products.listen.content.post_policies import MemModeratedEmailPostPolicy
    >>> p = MemModeratedEmailPostPolicy(ml)
    >>> mtool = tests.DummyMembershipTool('')
    >>> ml.portal_membership = mtool
    >>> mtool.result = None

    Monkey patch the send mail method to instead trigger a test result
    >>> sent_emails = []
    >>> def patched_send(to, name, pin=''):
    ...     sent_emails.append((to, pin))
    >>> p.mail_sender.user_mod = patched_send
    >>> p.mail_sender.manager_mod_post_request = patched_send
    >>> p.mail_sender.user_mem_mod_already_pending = patched_send

    try an incomplete request
    >>> from Products.listen.config import POST_ERROR, POST_DEFERRED, POST_DENIED
    >>> p.enforce({}) == POST_ERROR
    True

    try a new post request
    >>> p.enforce({'email':'foo@bar.com' , 'use_name':'foo', 'post':'hi'}) == POST_DEFERRED
    True
    >>> len(sent_emails)
    2

    make a user an allowed sender and get their post approved
    >>> from Products.listen.interfaces import IWriteMembershipList
    >>> mem_list = IWriteMembershipList(ml)
    >>> mem_list.add_allowed_sender('tam@tammy.com')
    >>> from Products.listen.config import POST_ALLOWED, POST_DENIED
    >>> p.enforce({'email':'tam@tammy.com' , 'post':'hi'}) == POST_ALLOWED
    True

    post should be denied for someone who already has a post pending
    >>> p.enforce({'email':'foo@bar.com' , 'use_name':'foo', 'post':'hi'}) == POST_DENIED
    True
    >>> len(sent_emails)
    3

    approve a post simulating a manager moderating
    >>> from Products.listen.config import MODERATION_SUCCESSFUL
    >>> p.enforce({'email':'foo@bar.com', 'postid': 0, 'action':'aPProve'}) == MODERATION_SUCCESSFUL
    True

    get a reference to the pending list
    >>> from zope.annotation.interfaces import IAnnotations
    >>> plist = IAnnotations(ml)['listen']['pending_mod_post']

    discard a post 
    >>> p.enforce({'email':'newguy@bar.com' , 'use_name':'foo', 'post':'hi'}) == POST_DEFERRED
    True
    >>> p.enforce({'email':'newguy@bar.com', 'postid': 0, 'action':'Discard'}) == MODERATION_SUCCESSFUL
    True
    >>> 'newguy@bar.com' in plist
    False

    reject a post simulating a manager moderating
    >>> p.enforce({'email':'newguy@bar.com' , 'use_name':'foo', 'post':'bye'}) == POST_DEFERRED
    True
    >>> p.enforce({'email':'newguy@bar.com', 'postid': 0, 'action':'Reject', 'reject_reason':'dumb post'}) == MODERATION_SUCCESSFUL
    True
    >>> 'newguy@bar.com' in plist
    False

    """

    implements(IPostPolicy)

    def __init__(self, context):
        BasePostPolicy.__init__(self, context)
        
        # pending list for posts waiting for manager moderation
        self.mod_post_pending_list = getAdapter(context, IPostPendingList, 'pending_mod_post')


    def enforce(self, request):
        user_email = request.get('email')
        user_name = request.get('name')
        post = request.get('post')
        postid = request.get('postid')
        action = request.get('action','').lower()
        
        if user_email is None:
            return POST_ERROR
        
        if action:
            if action == 'approve':
                self.mem_list.add_allowed_sender(user_email)
            elif action == 'discard':
                self.mod_post_pending_list.remove(user_email)
            elif action == 'reject':
                self.mail_sender.user_post_rejected(user_email, user_name, request.get('reject_reason'))
                self.mod_post_pending_list.remove(user_email)
            return MODERATION_SUCCESSFUL

        if post is None:
            return POST_ERROR
        
        if self.mem_list.is_allowed_sender(user_email):
            return POST_ALLOWED
        elif self.mod_post_pending_list.is_pending(user_email):
            self.mail_sender.user_mem_mod_already_pending(user_email, user_name)
            return POST_DENIED
        else:
            self.mod_post_pending_list.add(user_email, post=post, user_name=user_name)
            self.mail_sender.user_mod(user_email, user_name)
            self.mail_sender.manager_mod_post_request(user_email, user_name, post)
            return POST_DEFERRED
            
 

class MemModeratedTTWPostPolicy(BasePostPolicy):
    """
    Adapter enforces ttw submissions by a logged in user to a membership-moderated list.
    If user is not an allowed sender then the message becomes pending and 
    managers receive a moderation request for message & stranger.

    Setup object for testing
    >>> from Products.listen.extras.tests import TestMailingList
    >>> from Products.listen.content import tests
    >>> ml = TestMailingList()
    >>> from Products.listen.content.post_policies import MemModeratedTTWPostPolicy
    >>> p = MemModeratedTTWPostPolicy(ml)
    >>> mtool = tests.DummyMembershipTool('')
    >>> ml.portal_membership = mtool
    >>> mtool.result = None

    Monkey patch the send mail method to instead trigger a test result
    >>> sent_emails = []
    >>> def patched_send(to, name, pin=''):
    ...     sent_emails.append((to, pin))
    >>> p.mail_sender.user_post_request = patched_send
    >>> p.mail_sender.manager_mod_post_request = patched_send
    >>> p.mail_sender.user_already_pending = patched_send

    try an incomplete request
    >>> from Products.listen.config import POST_ERROR, POST_DEFERRED
    >>> p.enforce({}) == POST_ERROR
    True

    try a new post request
    >>> p.enforce({'email':'foo@bar.com' , 'use_name':'foo', 'post':'hi'}) == POST_DEFERRED
    True
    >>> len(sent_emails)
    1

    make a user an allowed sender and get their post approved
    >>> from Products.listen.interfaces import IWriteMembershipList
    >>> mem_list = IWriteMembershipList(ml)
    >>> mem_list.add_allowed_sender('tam@tammy.com')
    >>> from Products.listen.config import POST_ALLOWED, POST_DENIED
    >>> p.enforce({'email':'tam@tammy.com' , 'post':'hi'}) == POST_ALLOWED
    True

    post should be denied for someone who already has a post pending
    >>> p.enforce({'email':'foo@bar.com' , 'use_name':'foo', 'post':'hi'}) == POST_DENIED
    True

    """

    implements(IPostPolicy)

    def __init__(self, context):
        BasePostPolicy.__init__(self, context)
        
        # pending list for posts waiting for manager moderation
        self.mod_post_pending_list = getAdapter(context, IPostPendingList, 'pending_mod_post')


    def enforce(self, request):
        user_email = request.get('email')
        user_name = request.get('name')
        post = request.get('post')
        if user_email is None or post is None:
            return POST_ERROR
        
        if self.mem_list.is_allowed_sender(user_email):
            return POST_ALLOWED
        elif self.mod_post_pending_list.is_pending(user_email):
            return POST_DENIED
        else:
            self.mod_post_pending_list.add(user_email, user_name=user_name, post=post)
            self.mail_sender.manager_mod_post_request(user_email, user_name, post)
            return POST_DEFERRED

