from email import Utils as utils

import zope.event
from zope.event import notify
from zope.component import adapter
from zope.component import getAdapter

from DateTime import DateTime
from zope.interface import implements
from zope.annotation.interfaces import IAnnotations

from Products.CMFCore.utils import getToolByName

from AccessControl import Unauthorized
from BTrees.OOBTree import OOBTree
from BTrees.IOBTree import IOBTree

from Products.listen.lib.common import is_email
from Products.listen.lib.common import lookup_email
from Products.listen.lib.common import lookup_emails
from Products.listen.lib.common import lookup_member_id
from Products.listen.lib.common import send_pending_posts

from Products.listen.interfaces import ISubscriptionList
from Products.listen.interfaces import IWriteSubscriptionList
from Products.listen.interfaces import IPendingList
from Products.listen.interfaces import IMembershipList
from Products.listen.interfaces import IWriteMembershipList
from Products.listen.interfaces import IMembershipDigestList
from Products.listen.interfaces import IWriteMembershipDigestList
from Products.listen.interfaces import IBecameAnAllowedSender
from Products.listen.interfaces import IBecameASubscriber
from Products.listen.interfaces import ISubscriberRemoved
from Products.listen.interfaces import IAllowedSenderRemoved
from Products.listen.interfaces import IPostPendingList
from Products.listen.interfaces import IMembershipPendingList
from Products.listen.interfaces import IUserEmailMembershipPolicy
from Products.listen.interfaces import IEmailPostPolicy
from Products.listen.interfaces import IBaseList
from Products.listen.interfaces import ISendMail

from Products.listen.config import PROJECTNAME


class PendingList(object):
    """ Implementation of IPendingList

    Set up the pending list
    >>> from Products.listen.content import PendingList
    >>> plist = PendingList()
    
    Add a few pending members
    >>> plist.add('tom')
    >>> plist.add('heart@cone.org')
    >>> plist.add('mikey', time='2006-05-09', pin='4532123')
    >>> sorted(plist.get_user_emails())
    ['heart@cone.org', 'mikey', 'tom']

    The time that we set on mikey should be used instead of the default time
    >>> plist.get_pending_time('mikey')
    '2006-05-09'
    >>> plist.get_user_pin('mikey')
    '4532123'

    Try and add mikey a second time and make sure data is not lost but time is updated
    >>> plist.add('mikey')
    >>> plist.get_user_pin('mikey')
    '4532123'
    >>> plist.get_pending_time('mikey') != '2006-05-09'
    True

    Now let's remove them
    >>> plist.remove('tom')
    >>> plist.remove('heart@cone.org')
    >>> plist.remove('mikey')
    >>> plist.get_user_emails()
    []

    Let's create an item with a post
    >>> plist.add('timmy', post='a new post')
    >>> post = plist.get_posts('timmy')[0]
    >>> post['header']
    {}
    >>> post['body']
    'a new post'

    Verify the id of the post
    >>> post['postid']
    0
    
    Let's add a new post, and verify its id too
    >>> plist.add('timmy', post='hi there')
    >>> newpost = plist.get_posts('timmy')[1]
    >>> newpost['postid']
    1

    Remove the first one
    >>> plist.pop_post('timmy', 0) is not None
    True
    >>> p = plist.get_posts('timmy')[0]
    >>> p['body']
    'hi there'
    >>> p['postid']
    1

    Trying to pop a fake post returns None
    >>> plist.pop_post('timmy', 0) is None
    True
    >>> plist.pop_post('timmy', 17) is None
    True

    """
    implements(IPendingList)

    def __init__(self):
        self.pend = OOBTree()
        
    def add(self, item, **values):
        self.pend.setdefault(item, OOBTree())
        if 'time' not in values:
            values['time'] = DateTime().ISO()
        if 'post' in values:
            post_list = self.pend[item].setdefault('post', IOBTree())
            new_post = values['post']
            if isinstance(new_post, basestring):
                new_post = dict(header={}, body=new_post)

            try:
                nextid = post_list.maxKey() + 1
            except ValueError:
                nextid = 0
                
            new_post['postid'] = nextid
            post_list[nextid] = new_post
            values.pop('post')
        self.pend[item].update(values)

    def remove(self, item):
        if item in self.pend:
            self.pend.pop(item)

    def pop_post(self, item, postid):
        posts = self.pend[item]['post']
        try:
            return posts.pop(postid)
        except KeyError:
            return None

    def get_posts(self, user_email):
        return list(self.pend.get(user_email, {}).get('post', {}).values())

    def is_pending(self, item):
        return item in self.pend

    def get_user_pin(self, user_email):
        return self.pend.get(user_email, {}).get('pin')

    def get_pending_time(self, user_email):
        return self.pend.get(user_email, {}).get('time')

    def get_user_emails(self):
        return list(self.pend.keys())

    def get_user_name(self, user_email):
        return self.pend.get(user_email, {}).get('user_name')

    def clear(self):
        for email, item in self.pend.items():
            if 'post' in item:
                for post in item['post'].values():
                    for k, v in item.items():
                        if k == 'post': continue
                        post[k] = v
                    post['email'] = email
                    yield post
            else:
                item['email'] = email
                yield item
        self.pend.clear()

def create_pending_list_for(pendinglist_annotation):
    class New_Pending_List(PendingList):
        def __init__(self, context):
            self.context = context
            annot = IAnnotations(context)
            listen_annot = annot.setdefault(PROJECTNAME, OOBTree())
            self.pend = listen_annot.setdefault(pendinglist_annotation,
                                                OOBTree())
    return New_Pending_List

# membership pending lists
PendingAllowedSenderModeration = create_pending_list_for('pending_a_s_mod_email')
PendingSubscriptionEmail = create_pending_list_for('pending_sub_email')
PendingSubscriptionModerationEmail = create_pending_list_for('pending_sub_mod_email')
PendingUnsubscriptionEmail = create_pending_list_for('pending_unsub_email')

# post pending lists
PendingAllowedSenderSubscriptionEmail = create_pending_list_for('a_s_pending_sub_email')
PendingModerationPost = create_pending_list_for('pending_mod_post')
PendingPostModerationPost = create_pending_list_for('pending_pmod_post')

class SubscriptionList(object):
    implements(ISubscriptionList)

    def __init__(self, context):
        self.context = context
        annot = IAnnotations(self.context)
        self.listen_annot = listen_annot = annot.setdefault(PROJECTNAME,
                                                            OOBTree())
        self.emails = listen_annot.setdefault('emails', OOBTree())
        self.members = listen_annot.setdefault('members', OOBTree())

    @property
    def subscribers(self):
        emails = [x for x in self.emails.keys()]
        members = [x for x in self.members.keys()]
        member_emails = lookup_emails(members)
        return emails + member_emails

    def is_subscribed(self, subscriber):
        if is_email(subscriber):
            user_id = lookup_member_id(subscriber, self.context)
            if user_id:
                return user_id in self.members or subscriber in self.emails
            else:
                return subscriber in self.emails
        else:
            email = lookup_email(subscriber, self.context)
            return subscriber in self.members or email in self.emails


class WriteSubscriptionList(SubscriptionList):
    """ 
    Create our subscription list and stubs
    >>> from Products.listen.content.tests import DummyAnnotableList
    >>> from Products.listen.content.tests import DummyMembershipTool
    >>> from Products.listen.content.tests import DummyMember
    >>> mail_list = DummyAnnotableList()
    >>> dtool = DummyMembershipTool('foo')
    >>> dtool.result = None
    >>> mail_list.portal_membership = dtool
    >>> from Products.listen.content import WriteSubscriptionList
    >>> slist = WriteSubscriptionList(mail_list)    

    Add an allowed sender with an email address
    >>> slist.subscribers
    []
    >>> slist.subscribe('a@foo.com')
    >>> slist.subscribers
    ['a@foo.com']
    >>> slist.is_subscribed('a@foo.com')
    True

    Now remove his subscription
    >>> slist.unsubscribe('a@foo.com')
    >>> slist.subscribers
    []
    >>> slist.is_subscribed('a@foo.com')
    False

    Let's try adding a member id now
    >>> mem = DummyMember('foomem', 'quux', 'foomem@bar.com')
    >>> dtool.foomem = mem
    >>> dtool.result = (mem,)
    >>> from Products.listen.interfaces import IMemberLookup
    >>> from zope.component import getUtility
    >>> email_utility = getUtility(IMemberLookup)
    >>> email_utility.mtool = dtool
    >>> slist.is_subscribed('foomem')
    False
    >>> slist.subscribe('foomem')
    >>> slist.subscribers
    ['foomem@bar.com']

    Flexes is_* functions
    >>> slist.is_subscribed('foomem')
    True
    >>> slist.is_subscribed('foomem@bar.com')
    True


    Try to remove the email address. The member object should get removed
    >>> slist.unsubscribe('foomem@bar.com')
    >>> slist.is_subscribed('foomem')
    False
    >>> slist.subscribers
    []


    Now let's try something orthogonal: add an email and remove the member
    >>> slist.subscribe('foomem@bar.com')
    >>> slist.unsubscribe('foomem')
    >>> slist.subscribers
    []

    Edge case test
    >>> slist.subscribe('feek@fleem.com')
    >>> slist.is_subscribed('feek@fleem.com')
    True
    >>> mem = DummyMember('feek', 'fuux', 'feek@fleem.com')
    >>> dtool.feek = mem
    >>> dtool.result = (mem,)
    >>> slist.unsubscribe('feek@fleem.com')
    >>> slist.is_subscribed('feek@fleem.com')
    False

    """

    implements(IWriteSubscriptionList)

    def subscribe(self, subscriber):
        if is_email(subscriber):
            user_id = lookup_member_id(subscriber, self.context)
            if user_id:
                self._add_member(user_id)
            else:
                if subscriber not in self.emails:
                    self.emails[subscriber] = OOBTree()
        else:
            self._add_member(subscriber)

    def _add_member(self, member_id):
        if member_id in self.members: return
        email = lookup_email(member_id, self.context)
        if email in self.emails:
            self.members[member_id] = self.emails[email]
            self.emails.pop(email)
        else:
            self.members[member_id] = OOBTree()

    def unsubscribe(self, subscriber):
        if is_email(subscriber):
            user_id = lookup_member_id(subscriber, self.context)
            if user_id:
                if user_id in self.members:
                    self.members.pop(user_id)
            if subscriber in self.emails:
                self.emails.pop(subscriber)
        else:
            email = lookup_email(subscriber, self.context)
            if email in self.emails:
                self.email.pop(email)
            if subscriber in self.members:
                self.members.pop(subscriber)


class MembershipList(SubscriptionList):
    implements(IMembershipList)

    @property
    def allowed_senders(self):
        members = [lookup_email(x, self.context) for x in self.members.keys()]
        members = filter(None, members)
        # XXX for some reason list(self.emails.keys()) does not work
        return [x for x in self.emails.keys()] + members

    @property
    def subscribers(self):
        emails = [k for k,v in self.emails.items() if v.get('subscriber')]
        member_ids = [k for k,v in self.members.items() if v.get('subscriber')]
        member_emails = lookup_emails(member_ids)
        return emails + member_emails

    @property
    def allowed_senders_data(self):
        return dict(dict(self.emails), **dict(self.members))

    def is_subscribed(self, subscriber):
        if is_email(subscriber):
            user_id = lookup_member_id(subscriber, self.context)
            if user_id:
                return self.members.get(user_id, {}).get('subscriber', False) or self.emails.get(subscriber, {}).get('subscriber', False)
            else:
                return self.emails.get(subscriber, {}).get('subscriber', False)
        else:
            email = lookup_email(subscriber, self.context)
            return self.members.get(subscriber, {}).get('subscriber', False) or self.emails.get(email, {}).get('subscriber', False)


    def is_allowed_sender(self, allowed_sender):
        if is_email(allowed_sender):
            user_id = lookup_member_id(allowed_sender, self.context)
            if user_id:
                return user_id in self.members or allowed_sender in self.emails
            else:
                return allowed_sender in self.emails
        else:
            email = lookup_email(allowed_sender, self.context)
            return allowed_sender in self.members or email in self.emails


class WriteMembershipList(MembershipList):
    """ 
    Create our subscription list and stubs
    >>> from Products.listen.content.tests import DummyAnnotableList
    >>> from Products.listen.content.tests import DummyMembershipTool
    >>> from Products.listen.content.tests import DummyMember
    >>> mail_list = DummyAnnotableList()
    >>> dtool = DummyMembershipTool('foo')
    >>> dtool.result = None
    >>> mail_list.portal_membership = dtool
    >>> from Products.listen.content import WriteMembershipList
    >>> slist = WriteMembershipList(mail_list)

    Add an allowed sender with an email address
    >>> slist.subscribers
    []
    >>> slist.allowed_senders
    []
    >>> slist.add_allowed_sender('a@foo.com')
    >>> slist.allowed_senders
    ['a@foo.com']
    >>> slist.subscribers
    []

    And make him a subscriber
    >>> slist.subscribe('a@foo.com')
    >>> slist.allowed_senders
    ['a@foo.com']
    >>> slist.subscribers
    ['a@foo.com']

    Now remove his subscription
    >>> slist.unsubscribe('a@foo.com')
    >>> slist.allowed_senders
    ['a@foo.com']
    >>> slist.subscribers
    []

    And remove him from the allowed senders list
    >>> slist.remove_allowed_sender('a@foo.com')
    >>> slist.allowed_senders
    []
    >>> slist.subscribers
    []

    Let's try adding a member id now
    >>> mem = DummyMember('foomem', 'quux', 'foomem@bar.com')
    >>> dtool.foomem = mem
    >>> dtool.result = (mem,)
    >>> from Products.listen.interfaces import IMemberLookup
    >>> from zope.component import getUtility
    >>> email_utility = getUtility(IMemberLookup)
    >>> email_utility.mtool = dtool

    >>> slist.add_allowed_sender('foomem')
    >>> slist.subscribers
    []
    >>> slist.allowed_senders
    ['foomem@bar.com']

    Flexes is_* functions
    >>> slist.is_allowed_sender('foomem')
    True
    >>> slist.is_subscribed('foomem')
    False
    >>> slist.is_allowed_sender('foomem@bar.com')
    True
    >>> slist.is_subscribed('foomem@bar.com')
    False

    Upgrade the member to a subscriber by subscribing the id
    >>> slist.subscribe('foomem')
    >>> slist.subscribers
    ['foomem@bar.com']
    >>> slist.allowed_senders
    ['foomem@bar.com']

    Flexes is_* functions
    >>> slist.is_allowed_sender('foomem')
    True
    >>> slist.is_subscribed('foomem')
    True
    >>> slist.is_allowed_sender('foomem@bar.com')
    True
    >>> slist.is_subscribed('foomem@bar.com')
    True

    Unsubscribe the member
    >>> slist.unsubscribe('foomem')
    >>> slist.subscribers
    []
    >>> slist.allowed_senders
    ['foomem@bar.com']

    Remove the allowed sender
    >>> slist.remove_allowed_sender('foomem')
    >>> slist.subscribers
    []
    >>> slist.allowed_senders
    []

    Flexes is_* functions
    >>> slist.is_allowed_sender('foomem')
    False
    >>> slist.is_subscribed('foomem')
    False
    >>> slist.is_allowed_sender('foomem@bar.com')
    False
    >>> slist.is_subscribed('foomem@bar.com')
    False

    Add an allowed sender as a member, then try to remove the email address.
    The member object should get removed
    >>> slist.add_allowed_sender('foomem')
    >>> slist.subscribers
    []
    >>> slist.allowed_senders
    ['foomem@bar.com']
    >>> dtool.result = [mem]
    >>> slist.remove_allowed_sender('foomem@bar.com')
    >>> slist.subscribers
    []
    >>> slist.allowed_senders
    []

    Now let's try something orthogonal: add an email and remove the member
    >>> slist.add_allowed_sender('foomem@bar.com')
    >>> slist.subscribers
    []
    >>> slist.allowed_senders
    ['foomem@bar.com']
    >>> slist.remove_allowed_sender('foomem')
    >>> slist.subscribers
    []
    >>> slist.allowed_senders
    []

    Add an email address as an allowed sender, and then try to add the member id
    corresponding to that email address
    >>> slist.add_allowed_sender('foomem@bar.com')
    >>> slist.subscribe('foomem')
    >>> slist.subscribers
    ['foomem@bar.com']
    >>> slist.allowed_senders
    ['foomem@bar.com']

    Now remove that email address through the member
    >>> slist.remove_allowed_sender('foomem')
    >>> slist.subscribers
    []
    >>> slist.allowed_senders
    []

    Edge case test
    >>> slist.subscribe('feek@fleem.com')
    >>> slist.is_subscribed('feek@fleem.com')
    True
    >>> mem = DummyMember('feek', 'fuux', 'feek@fleem.com')
    >>> dtool.feek = mem
    >>> dtool.result = (mem,)
    >>> slist.unsubscribe('feek@fleem.com')
    >>> slist.is_subscribed('feek@fleem.com')
    False

    Tests allowed_senders_data
    >>> dtool.result = None
    >>> slist.subscribe('foomem')
    >>> slist.subscribe('feek@fleem.com')
    >>> slist.subscribe('tammy@talk.loud')
    >>> len(slist.allowed_senders_data)
    3

    Set up a sample event handler for becoming an allowed sender
    >>> allowed_sender_list = []
    >>> from zope.component import adapter
    >>> from Products.listen.interfaces import IBecameAnAllowedSender
    >>> @adapter(IBecameAnAllowedSender)
    ... def stub_became_allowed_sender(event):
    ...     try: allowed_sender_list.append(event.email)
    ...     except NameError: pass
    >>> from zope.component import provideHandler
    >>> provideHandler(stub_became_allowed_sender)
    
    Now verify that adding an allowed sender triggers our new method
    >>> slist.add_allowed_sender('quux_gurgle@foobarbaz.woot')
    >>> allowed_sender_list
    ['quux_gurgle@foobarbaz.woot']
    >>> allowed_sender_list = []

    Trying to add them again should not fire the event
    >>> slist.add_allowed_sender('quux_gurgle@foobarbaz.woot')
    >>> allowed_sender_list
    []

    Adding a member should also trigger the event
    >>> mem = DummyMember('zool', 'zul', 'zool@ghosts.com')
    >>> dtool.result = 'zool@ghosts.com'
    >>> dtool.zool = mem
    >>> slist.add_allowed_sender('zool')
    >>> allowed_sender_list
    ['zool@ghosts.com']
    >>> allowed_sender_list = []

    Again, trying to add a member that's already allowed should not
    trigger the event
    >>> slist.add_allowed_sender('zool')
    >>> allowed_sender_list
    []

    Subscribing a new email address should also trigger the event
    >>> dtool.result = None
    >>> slist.subscribe('fakename@example.com')
    >>> allowed_sender_list
    ['fakename@example.com']
    >>> allowed_sender_list = []

    Trying to subscribe the email again should not trigger the event
    >>> slist.subscribe('fakename@example.com')
    >>> allowed_sender_list
    []

    Now try subscribing a member id to trigger the event
    >>> mem = DummyMember('puff', 'stay', 'puff@ghosts.com')
    >>> dtool.puff = mem
    >>> slist.subscribe('puff')
    >>> allowed_sender_list
    ['puff@ghosts.com']
    >>> allowed_sender_list = []

    Trying to subscribe the id again should not trigger the event
    >>> slist.subscribe('puff')
    >>> allowed_sender_list
    []

    Try an edge case for subscribing the email address associated
    with the member
    >>> dtool.result = [mem]
    >>> slist.subscribe('puff@ghosts.com')
    >>> allowed_sender_list
    []

    And if we tried to make the same email address an allowed sender,
    we should also not get the event
    >>> slist.add_allowed_sender('puff@ghosts.com')
    >>> allowed_sender_list
    []

    We can also subscribe members without sending the event
    >>> slist.subscribe('slimer@example.com', send_notify=False)
    >>> allowed_sender_list
    []

"""
    implements(IWriteMembershipList)

    def _notify_added_a_s(self, user):
        email = is_email(user) and user or lookup_email(user, self.context)
        if email:
            notify(AllowedSenderPromotion(self.context, email))
            
    def _notify_added_subscriber(self, user):
        email = is_email(user) and user or lookup_email(user, self.context)
        if email:
            notify(SubscriberPromotion(self.context, email))

    def _notify_removed_subscriber(self, user):
        email = is_email(user) and user or lookup_email(user, self.context)
        if email:
            notify(SubscriberRemoved(self.context, email))

    def _notify_removed_allowed_sender(self, user):
        email = is_email(user) and user or lookup_email(user, self.context)
        if email:
            notify(AllowedSenderRemoved(self.context, email))

    def subscribe(self, subscriber, send_notify=True):
        if is_email(subscriber):
            user_id = lookup_member_id(subscriber, self.context)
            if user_id:
                if user_id not in self.members and send_notify:
                    self._notify_added_a_s(user_id)
                self.members[user_id] = {'subscriber':True}
                if subscriber in self.emails:
                    self.emails.pop(subscriber)
            else:
                if subscriber not in self.emails and send_notify:
                    self._notify_added_a_s(subscriber)
                self.emails[subscriber] = {'subscriber':True}
        else:
            if subscriber not in self.members and send_notify:
                self._notify_added_a_s(subscriber)
            self.members[subscriber] = {'subscriber':True}
            email = lookup_email(subscriber, self.context)
            if email in self.emails:
                self.emails.pop(email)
        if send_notify:
            self._notify_added_subscriber(subscriber)

    def unsubscribe(self, subscriber, send_notify=True):
        if is_email(subscriber):
            user_id = lookup_member_id(subscriber, self.context)
            if user_id:
                if user_id in self.members:
                    self.members[user_id] = {'subscriber':False}
            if subscriber in self.emails:
                self.emails[subscriber] = {'subscriber':False}
        else:
            if subscriber in self.members:
                self.members[subscriber] = {'subscriber':False}
        if send_notify:
            self._notify_removed_subscriber(subscriber)

    def add_allowed_sender(self, allowed_sender, send_notify=True):
        if is_email(allowed_sender):
            user_id = lookup_member_id(allowed_sender, self.context)
            if user_id:
                self._add_member(user_id, send_notify)
            else:
                if allowed_sender not in self.emails:
                    self.emails[allowed_sender] = {'subscriber':False}
                    if send_notify:
                        self._notify_added_a_s(allowed_sender)
        else:
            self._add_member(allowed_sender, send_notify)

    def _add_member(self, member_id, send_notify):
        if member_id in self.members: return
        email = lookup_email(member_id, self.context)
        if email in self.emails:
            self.members[member_id] = self.emails[email]
            self.emails.pop(email)
        else:
            if member_id not in self.members:
                self.members[member_id] = {'subscriber':False}
                if send_notify:
                    self._notify_added_a_s(member_id)

    def remove_allowed_sender(self, allowed_sender, send_notify=True):
        was_subscribed = False
        if is_email(allowed_sender):
            user_id = lookup_member_id(allowed_sender, self.context)
            if user_id:
                if user_id in self.members:
                    record = self.members.pop(user_id)
                    if record.get("subscriber") == True:
                        was_subscribed = True
            if allowed_sender in self.emails:
                record = self.emails.pop(allowed_sender)
                if record.get("subscriber") == True:
                    was_subscribed = True
        else:
            email = lookup_email(allowed_sender, self.context)
            if email in self.emails:
                record = self.email.pop(email)
                if record.get("subscriber") == True:
                    was_subscribed = True
            if allowed_sender in self.members:
                record = self.members.pop(allowed_sender)
                if record.get("subscriber") == True:
                    was_subscribed = True
        if send_notify:
            if was_subscribed:
                self._notify_removed_subscriber(allowed_sender)
            self._notify_removed_allowed_sender(allowed_sender)

class MembershipDigestList(MembershipList):
    implements(IMembershipDigestList)

    def __init__(self, context):
        MembershipList.__init__(self, context)
        listen_annot = self.listen_annot
        self.digest_emails = listen_annot.setdefault('digest_emails',
                                                     OOBTree())
        self.digest_members = listen_annot.setdefault('digest_members',
                                                      OOBTree())

    @property
    def digest_subscribers(self):
        emails = [x for x in self.digest_emails.keys()]
        members = [x for x in self.digest_members.keys()]
        member_emails = lookup_emails(members)
        return emails + member_emails

    @property
    def nondigest_subscribers(self):
        emails = [x for x in self.emails.keys()
                  if self.emails[x].get('subscriber')
                  and x not in self.digest_emails]
        members = [x for x in self.members.keys()
                   if self.members[x].get('subscriber')
                   and x not in self.digest_members]
        member_emails = lookup_emails(members)
        return emails + member_emails

    def has_digest_subscribers(self):
        return self.digest_emails or self.digest_members

    def is_digest_subscriber(self, subscriber):
        if is_email(subscriber):
            user_id = lookup_member_id(subscriber, self.context)
            if user_id:
                return (user_id in self.digest_members or
                        subscriber in self.digest_emails)
            return subscriber in self.digest_emails
        email = lookup_email(subscriber, self.context)
        return (subscriber in self.digest_members or
                email in self.digest_emails)

    
class WriteMembershipDigestList(MembershipDigestList, WriteMembershipList):
    """
    Create our membership list and stubs
    >>> from Products.listen.content.tests import DummyAnnotableList
    >>> from Products.listen.content.tests import DummyMembershipTool
    >>> from Products.listen.content.tests import DummyMember
    >>> mail_list = DummyAnnotableList()
    >>> dtool = DummyMembershipTool('foo')
    >>> dtool.result = None
    >>> mail_list.portal_membership = dtool
    >>> from Products.listen.content import WriteMembershipDigestList
    >>> from Products.listen.content import WriteMembershipList
    >>> dlist = WriteMembershipDigestList(mail_list)

    Fail when trying to digest address that's not already a subscriber:
    >>> dlist.subscribers
    []
    >>> dlist.digest_subscribers
    []
    >>> dlist.is_digest_subscriber('a@foo.com')
    False
    >>> self.assertRaises(ValueError, dlist.make_digest_subscriber,
    ...                   ('a@foo.com'))
    >>> dlist.digest_subscribers
    []

    Add subscriber, convert to digest:
    >>> mlist = WriteMembershipList(mail_list)
    >>> mlist.subscribe('a@foo.com')
    >>> dlist.make_digest_subscriber('a@foo.com')
    >>> dlist.digest_subscribers
    ['a@foo.com']
    >>> dlist.is_digest_subscriber('a@foo.com')
    True

    Verify re-digesting doesn't cause any problems:
    >>> dlist.make_digest_subscriber('a@foo.com')
    >>> dlist.digest_subscribers
    ['a@foo.com']

    Convert back to regular subscriber:
    >>> dlist.unmake_digest_subscriber('a@foo.com')
    >>> dlist.is_digest_subscriber('a@foo.com')
    False
    >>> dlist.digest_subscribers
    []
    >>> dlist.subscribers
    ['a@foo.com']

    Fail when undigesting someone who's not on digest:
    >>> self.assertRaises(ValueError, dlist.unmake_digest_subscriber,
    ...                   ('a@foo.com'))

    Now add a member and handle some mock stuff:
    >>> mem = DummyMember('foomem', 'quux', 'foomem@bar.com')
    >>> dtool.foomem = mem
    >>> dtool.result = (mem,)
    >>> from Products.listen.interfaces import IMemberLookup
    >>> from zope.component import getUtility
    >>> email_utility = getUtility(IMemberLookup)
    >>> email_utility.mtool = dtool

    Subscribe and digest the member:
    >>> mlist.subscribe('foomem')
    >>> dlist.make_digest_subscriber('foomem')
    >>> dlist.is_digest_subscriber('foomem')
    True
    >>> dlist.is_digest_subscriber('foomem@bar.com')
    True
    >>> dlist.digest_subscribers
    ['foomem@bar.com']

    Un-digest by member id:
    >>> dlist.unmake_digest_subscriber('foomem')
    >>> dlist.is_digest_subscriber('foomem')
    False
    >>> dlist.is_digest_subscriber('foomem@bar.com')
    False
    >>> dlist.digest_subscribers
    []

    Try adding by email address, verify that the member is
    what is actually added:
    >>> dlist.make_digest_subscriber('foomem@bar.com')
    >>> list(dlist.digest_members.keys())
    ['foomem']

    Now remove via email address:
    >>> dlist.unmake_digest_subscriber('foomem@bar.com')
    >>> list(dlist.digest_members.keys())
    []
    >>> dlist.digest_subscribers
    []
    """
    implements(IWriteMembershipDigestList)

    def make_digest_subscriber(self, subscriber):
        if is_email(subscriber):
            user_id = lookup_member_id(subscriber, self.context)
            if user_id:
                # submitted email address, is connected to a user
                if user_id not in self.members:
                    raise ValueError('%s (username: %s) is not a subscriber'
                                     % (subscriber, user_id))
                if subscriber in self.digest_emails:
                    # clean up lingering email digest sub
                    del(self.digest_emails[subscriber])
                if user_id not in self.digest_members:
                    self.digest_members[user_id] = None
            else:
                # submitted email address, no connected user
                if subscriber not in self.emails:
                    raise ValueError('%s is not a subscriber' % subscriber)
                if subscriber not in self.digest_emails:
                    self.digest_emails[subscriber] = None
        else:
            # submitted user id
            email = lookup_email(subscriber, self.context)
            if subscriber not in self.members:
                raise ValueError('%s is not a subscriber' % subscriber)
            if email in self.digest_emails:
                # clean up lingering email digest sub
                del(self.digest_emails[email])
            if subscriber not in self.digest_members:
                self.digest_members[subscriber] = None

    def unmake_digest_subscriber(self, subscriber):
        if is_email(subscriber):
            user_id = lookup_member_id(subscriber, self.context)
            if user_id:
                # submitted email, but has user; check and clear both
                # digest_members and digest_emails to be safe
                if (user_id not in self.digest_members and
                    subscriber not in self.digest_emails):
                    raise ValueError('%s (username: %s) is not a digest'
                                     ' subscriber' % (subscriber, user_id))
                if user_id in self.digest_members:
                    del(self.digest_members[user_id])
                if subscriber in self.digest_emails:
                    del(self.digest_emails[subscriber])
            else:
                # submitted email, no user
                if subscriber not in self.digest_emails:
                    raise ValueError('%s is not a digest subscriber'
                                     % subscriber)
                del(self.digest_emails[subscriber])
        else:
            # submitted user id; check and clear both digest_members
            # and digest_emails to be safe
            email = lookup_email(subscriber, self.context)
            if (subscriber not in self.digest_members and
                email not in self.digest_emails):
                raise ValueError('%s is not a digest subscriber'
                                 % subscriber)
            if subscriber in self.digest_members:
                del(self.digest_members[subscriber])
            if email in self.digest_emails:
                del(self.digest_emails[email])


class AllowedSenderPromotion(object):
    implements(IBecameAnAllowedSender)

    def __init__(self, context, email):
        self.context = context
        self.email = email


@adapter(IBecameAnAllowedSender)
def became_allowed_sender(event):
    """
    This function should ensure that all other pending allowed sender
    lists that the other policy adapters depend on are in sync.

    set up the phony mailing list and policies
    >>> from Products.listen.content.tests import DummyAnnotableList
    >>> from Products.listen.content.tests import DummyMembershipTool
    >>> from Products.listen.extras.tests import TestMailingList
    >>> from Products.listen.content.tests import DummyMember
    >>> from Products.listen.config import POST_DEFERRED, MEMBERSHIP_DEFERRED
    >>> ml = TestMailingList()
    >>> from zope.interface import alsoProvides
    >>> from Products.listen.interfaces import IPublicList
    >>> alsoProvides(ml, IPublicList)
    >>> mails_to_list = []
    >>> def listMail(post):
    ...     mails_to_list.append(post)
    >>> ml.listMail = listMail
    >>> from Products.listen.interfaces import IMailingList
    >>> dtool = DummyMembershipTool('foo')
    >>> dtool.result = None
    >>> ml.portal_membership = dtool
    >>> from Products.listen.content import WriteMembershipList
    >>> mlist = WriteMembershipList(ml)
    >>> from zope.component import getAdapter
    >>> from zope.component import provideAdapter
    >>> from Products.listen.interfaces import IEmailPostPolicy
    >>> from Products.listen.interfaces import IUserEmailMembershipPolicy
    >>> from Products.listen.content import PublicEmailPostPolicy
    >>> from Products.listen.content import UserMembershipPolicy
    >>> postpolicy = getAdapter(ml, IEmailPostPolicy)
    >>> mempolicy = getAdapter(ml, IUserEmailMembershipPolicy)

    send a subscribe email to get on the pending list
    >>> request = dict(email='zul@bar.com',
    ...                subject='subscribe')
    >>> mempolicy.enforce(request) == MEMBERSHIP_DEFERRED
    True

    now submit a post to get on that pending list
    >>> request = dict(email='zul@bar.com',
    ...                post=dict(header={}, body='there is only zul!'))
    >>> postpolicy.enforce(request) == POST_DEFERRED
    True

    now add the email as an allowed sender
    >>> mlist.add_allowed_sender('zul@bar.com')

    make sure he's not on the allowed sender pending list
    >>> from zope.annotation.interfaces import IAnnotations
    >>> annot = IAnnotations(ml)
    >>> listen_annot = annot['listen']
    >>> a_s_list = listen_annot['a_s_pending_sub_email']
    >>> 'zul@bar.com' in a_s_list
    False

    verify that the post is no longer pending and has been sent out
    >>> post_list = listen_annot['pending_mod_post']
    >>> 'zul@bar.com' in post_list
    False
    >>> 'there is only zul!' in mails_to_list[0]['Mail']
    True

    try with a mem-moderated list policy
    >>> from zope.interface import directlyProvides
    >>> from Products.listen.interfaces import IMembershipModeratedList
    >>> directlyProvides(ml, IMembershipModeratedList)
    >>> postpolicy = getAdapter(ml, IEmailPostPolicy)
    >>> request = dict(email='zui@bar.com',
    ...                post=dict(header={}, body='there is only zui!'))
    >>> postpolicy.enforce(request) == POST_DEFERRED
    True
    >>> mlist.add_allowed_sender('zui@bar.com')
    >>> 'zui@bar.com' in post_list
    False
    >>> 'there is only zui!' in mails_to_list[1]['Mail']
    True

    make someone who is pending subscription moderation an allowed sender
    and make sure they get automatically subscribed
    >>> from Products.listen.interfaces import IMembershipPendingList
    >>> sub_mod_pending_list = getAdapter(ml, IMembershipPendingList, 'pending_sub_mod_email')
    >>> sub_mod_pending_list.add('waiting@moderation.com')
    >>> mlist.add_allowed_sender('waiting@moderation.com')
    >>> mlist.is_subscribed('waiting@moderation.com')
    True

    now try subscribing a member who is pending subscription moderation
    >>> sub_mod_pending_list.add('subwaiting@moderation.com')
    >>> mlist.subscribe('subwaiting@moderation.com')
    >>> mlist.is_subscribed('subwaiting@moderation.com')
    True

    """
    
    email = event.email
    context = event.context

    # clean up pending subscription
    pend_list = getAdapter(context, IPostPendingList, 'a_s_pending_sub_email')
    pend_list.remove(email)

    # if member is waiting for moderation to become a subscriber
    # then subscribe member
    sub_pending_list = getAdapter(context, IMembershipPendingList, 'pending_sub_mod_email')
    if sub_pending_list.is_pending(email):
        mlist = IWriteMembershipList(context)
        mail_sender = ISendMail(context)
        sub_pending_list.remove(email)
        mlist.subscribe(email)
        mail_sender.user_welcome(email, email)

    # clean up pending posts
    post_mod_list = getAdapter(context, IPostPendingList, 'pending_mod_post')
    # XXX currently expecting one post,
    # this is not the case for Post Moderated Lists
    # send the post for the user to the list
    posts = post_mod_list.get_posts(email)
    # uniquify posts
    post_dict = {}
    for p in posts:
        post_dict[p['body']] = p['header']
    posts = [dict(header=v, body=k) for k,v in post_dict.iteritems()]
    send_pending_posts(context, posts)
    post_mod_list.remove(email)


class SubscriberRemoved(object):
    implements(ISubscriberRemoved)

    def __init__(self, context, email):
        self.context = context
        self.email = email

class AllowedSenderRemoved(object):
    implements(IAllowedSenderRemoved)

    def __init__(self, context, email):
        self.context = context
        self.email = email

class SubscriberPromotion(object):
    implements(IBecameASubscriber)

    def __init__(self, context, email):
        self.context = context
        self.email = email


@adapter(IBecameASubscriber)
def became_subscriber(event):
    """
    This function should ensure that all other pending membership
    lists that the other policy adapters depend on are in sync.

    set up the phony mailing list and policies
    >>> from Products.listen.content.tests import DummyAnnotableList
    >>> from Products.listen.content.tests import DummyMembershipTool
    >>> from Products.listen.extras.tests import TestMailingList
    >>> from Products.listen.content.tests import DummyMember
    >>> from Products.listen.config import POST_DEFERRED, MEMBERSHIP_DEFERRED
    >>> ml = TestMailingList()
    >>> from zope.interface import alsoProvides
    >>> from Products.listen.interfaces import IPublicList
    >>> alsoProvides(ml, IPublicList)
    >>> mails_to_list = []
    >>> def listMail(post):
    ...     mails_to_list.append(post)
    >>> ml.listMail = listMail
    >>> from Products.listen.interfaces import IMailingList
    >>> dtool = DummyMembershipTool('foo')
    >>> dtool.result = None
    >>> ml.portal_membership = dtool
    >>> from Products.listen.content import WriteMembershipList
    >>> mlist = WriteMembershipList(ml)
    >>> from zope.component import getAdapter
    >>> from zope.component import provideAdapter
    >>> from Products.listen.interfaces import IEmailPostPolicy
    >>> from Products.listen.interfaces import IManagerTTWMembershipPolicy
    >>> postpolicy = getAdapter(ml, IEmailPostPolicy)
    >>> mempolicy = getAdapter(ml, IManagerTTWMembershipPolicy)

    test the case when an allowed sender is sent a subscription request
    by a manager and the allowed sender subscribes independently, ttw
    make sure the subscription request is no longer pending
    >>> mlist.add_allowed_sender('fame@fortune.com')
    >>> mempolicy.enforce({'action':'subscribe', 'email':'fame@fortune.com'}) == MEMBERSHIP_DEFERRED
    True

    make sure he's on the pending_sub_email list
    >>> from zope.annotation.interfaces import IAnnotations
    >>> annot = IAnnotations(ml)
    >>> listen_annot = annot['listen']
    >>> pend_list = listen_annot['pending_sub_email']
    >>> 'fame@fortune.com' in pend_list
    True

    after subscribing, he should no longer be on the pending list
    >>> mlist.subscribe('fame@fortune.com')
    >>> 'fame@fortune.com' in pend_list
    False


    """
    
    email = event.email
    context = event.context

    # clean up pending subscription
    pend_list = getAdapter(context, IMembershipPendingList, 'pending_sub_email')
    pend_list.remove(email)
