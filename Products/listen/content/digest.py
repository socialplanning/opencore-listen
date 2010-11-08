from Acquisition import aq_inner
from BTrees.OOBTree import OOBTree
from Products.Five.browser.pagetemplatefile import ZopeTwoPageTemplateFile
from Products.MailBoxer.MailBoxerTools import unpackMail
from Products.listen.config import PROJECTNAME
from Products.listen.interfaces import IDigestStorage
from Products.listen.interfaces import IDigestConstructor
from Products.listen.lib.htmlrender import render
from datetime import datetime
from persistent.list import PersistentList
from plone.intelligenttext.transforms import convertWebIntelligentPlainTextToHtml
from rfc822 import parseaddr
from zope.app.annotation.interfaces import IAnnotations
from zope.interface import implements

import email
import urllib

class SimpleDigestStorage(object):
    """
    Create our stubs:
    >>> import email
    >>> from Products.listen.content.tests import DummyAnnotableList
    >>> from Products.listen.content.digest import SimpleDigestStorage
    >>> mlist = DummyAnnotableList()
    >>> digest_store = SimpleDigestStorage(mlist)
    >>> msg1 = email.message_from_string('message one')
    >>> msg2 = email.message_from_string('message two')
    >>> msg3 = email.message_from_string('message three')

    Add the messages to the digest, verify that we can retrieve and
    consume:
    >>> digest_store.add_message_to_digest(msg1)
    >>> len(digest_store.get_digest())
    1
    >>> digest_store.add_message_to_digest(msg2)
    >>> len(digest_store.get_digest())
    2
    >>> digest_store.add_message_to_digest(msg3)
    >>> len(digest_store.get_digest())
    3
    >>> digest = digest_store.consume_digest()
    >>> len(digest_store.get_digest())
    0
    >>> list(digest) == [msg1, msg2, msg3]
    True
    """

    implements(IDigestStorage)

    def __init__(self, context):
        self.context = context
        annot = IAnnotations(context)
        listen_annot = annot.setdefault(PROJECTNAME, OOBTree())
        self.digest = listen_annot.setdefault('digest', PersistentList())

    def add_message_to_digest(self, msg):
        self.digest.append(msg)

    def get_digest(self):
        return self.digest

    def consume_digest(self):
        digest = list(self.digest)
        del self.digest[:]
        return digest


msg_tmpl = """Subject: %(subject)s
From: %(title)s <%(mailto)s>
To: %(mailto)s
X-Mailer: %(xmailer)s
Reply-To: %(mailto)s
Errors-To: %(returnpath)s
List-Subscribe: %(listsub)s
List-Unsubscribe: %(listunsub)s
List-Id: %(mailto)s
Precedence: Bulk
Content-Type: multipart/alternative; boundary="%(boundary)s"
MIME-Version: 1.0

--%(boundary)s
Content-Type: text/plain; charset=utf-8
Content-Transfer-Encoding: quoted-printable
Content-Disposition: inline

%(msgtext)s

--%(boundary)s
Content-Type: text/html; charset=utf-8
Content-Transfer-Encoding: quoted-printable
Content-Disposition: inline

%(msghtml)s
"""



class DigestConstructor(object):
    """
    Constructs a digest message given a sequence of email message
    objects that are to be included in the digest.

    >>> m1 = '''From: vodka@example.com
    ... To: drinkers@example.com
    ... Subject: I like vodka
    ... MIME-Version: 1.0
    ... Content-Type: multipart/mixed; 
    ...   boundary="----=_Part_26204_30744128.1220553085489"
    ... 
    ... 
    ... ------=_Part_26204_30744128.1220553085489
    ... Content-Type: multipart/alternative; 
    ...   boundary="----=_Part_26205_30325303.1220553085489"
    ... 
    ... ------=_Part_26205_30325303.1220553085489
    ... Content-Type: text/plain; charset=ISO-8859-1
    ... Content-Transfer-Encoding: 7bit
    ... Content-Disposition: inline
    ... 
    ... I like vodka!
    ... 
    ... ------=_Part_26205_30325303.1220553085489
    ... Content-Type: text/html; charset=ISO-8859-1
    ... Content-Transfer-Encoding: 7bit
    ... Content-Disposition: inline
    ... 
    ... <div dir="ltr">I like vodka!</div>
    ... 
    ... ------=_Part_26205_30325303.1220553085489--
    ... 
    ... ------=_Part_26204_30744128.1220553085489
    ... Content-Type: text/html; name=bar.html
    ... Content-Transfer-Encoding: base64
    ... X-Attachment-Id: f_fkpps9lu0
    ... Content-Disposition: attachment; filename=bar.html
    ... 
    ... PGh0bWw+CiAgICA8Ym9keT5oZWxsbyE8L2JvZHk+CjwvaHRtbD4K
    ... ------=_Part_26204_30744128.1220553085489
    ... Content-Type: text/plain; name=foo.txt
    ... Content-Transfer-Encoding: base64
    ... X-Attachment-Id: f_fkppsgh61
    ... Content-Disposition: attachment; filename=foo.txt
    ... 
    ... Zm9vCg==
    ... ------=_Part_26204_30744128.1220553085489--'''

    >>> msg = '''Beer before liquor, never been sicker. But, liquor is quicker.
    ...
    ... --
    ...  Wise man
    ... '''
    >>> import quopri
    >>> enc_msg = quopri.encodestring(msg)

    >>> m2='''From: quotedmessage@example.com
    ... To: drinkers@example.com
    ... Subject: My quoted message is
    ... MIME-Version: 1.0
    ... Content-Type: text/plain; charset=us-ascii
    ... Content-Disposition: inline
    ... Content-Transfer-Encoding: quoted-printable
    ... 
    ... %s''' % enc_msg

    >>> import email
    >>> msg1 = email.message_from_string(m1)
    >>> msg2 = email.message_from_string(m2)
    >>> msgs = [msg1, msg2]
    >>> from Products.listen.content.digest import DigestConstructor
    >>> from Products.listen.content.tests import DummyAnnotableAcqList
    >>> mail_list = DummyAnnotableAcqList()
    >>> self.portal._setObject('dummy_list', mail_list)
    'dummy_list'
    >>> mail_list = mail_list.__of__(self.portal)
    >>> cons = DigestConstructor(mail_list.__of__(self.portal))

    Set up some values so that our digest message looks more reasonable
    >>> mail_list.get_value_fors['mailto'] = 'aaa@example.com'

    And stub some additional methods out
    >>> mail_list.Title = lambda: 'Dummy'
    >>> mail_list.mailto = 'aaa@example.com'

    Display the digest for the messages
    >>> digest_message = cons.construct_digest(msgs)
    >>> print digest_message.as_string()  # doctest: +REPORT_NDIFF
    Subject: [Dummy] Digest, ..., ...
    From: Dummy <aaa@example.com>
    To: aaa@example.com...
    Reply-To: aaa@example.com...
    List-Subscribe: <mailto:aaa@example.com?subject=subscribe>
    List-Unsubscribe: <mailto:aaa@example.com?subject=unsubscribe>
    List-Id: aaa@example.com
    Precedence: Bulk
    Content-Type: multipart/alternative; boundary="----=_Part_..."
    MIME-Version: 1.0...
    ------=_Part_...
    Content-Type: text/plain; charset=utf-8
    Content-Transfer-Encoding: quoted-printable
    Content-Disposition: inline...
    ...DUMMY DIGEST FOR ...
    ...Messages in this digest:...
      1) I like vodka <#message_0> — From: vodka@example.com
      2) My quoted message is <#message_1> — From:
      quotedmessage@example.com...
                            Subject: I like vodka...
    From: vodka@example.com (vodka@example.com)...
    Date:...
    Reply to sender...
    <mailto:vodka@example.com?subject=Re:%20I%20like%20vodka>   Reply to
    list <mailto:aaa@example.com?subject=Re:%20I%20like%20vodka>...
    I like vodka!...
    You can view and respond to this message thread here:...
                        Subject: My quoted message is...
    From: quotedmessage@example.com (quotedmessage@example.com)...
    Date:...
    Reply to sender
    <mailto:quotedmessage@example.com?subject=Re:%20My%20quoted%20message%20is>
    Reply to list
    <mailto:aaa@example.com?subject=Re:%20My%20quoted%20message%20is>...
    Beer before liquor, never been sicker. But, liquor is quicker.
    --
    Wise man...
    You can view and respond to this message thread here:...
    You are receiving this message because you have selected to receive a
    daily digest for Dummy. To view previous messages, update your email
    settings, or unsubscribe, visit:...
    ------=_Part_...
    Content-Type: text/html; charset=utf-8
    Content-Transfer-Encoding: quoted-printable
    Content-Disposition: inline...
    <html...
    <body...
    ...Dummy Digest for ...
    ...Messages in this digest:...
    ...<a href="#message_0">I like vodka</a> &mdash; <span>From:</span> vodka@example.com...
    ...<a href="#message_1">My quoted message is</a> &mdash; <span>From:</span> quotedmessage@example.com...
    </html>...
    ------=_Part_...

    """

    implements(IDigestConstructor)

    template = ZopeTwoPageTemplateFile('digest_template.pt')

    def __init__(self, context):
        self.context = context

    def construct_digest(self, messages):
        # render message body
        template = self.template.__of__(aq_inner(self.context))
        template.context = self.context
        now = datetime.now()
        date = now.strftime('%B %d, %Y')
        timestamp = "%d.%d" % (now.toordinal(), now.microsecond)
        extra_context = {'mailinglist': self.context,
                         'messages': messages,
                         'date': date,
                         'constructor': self,
                         }
        msghtml = template.pt_render(extra_context=extra_context)
        #XXX for some reason the template renders an empty string without this
        # hack
        # no idea why ... caching?
        # possible exception the first time through but not the next and the
        # template swalows it and returns an empty string?
        if not msghtml:
            try:
                template()
            except:
                pass
            msghtml = template.pt_render(extra_context=extra_context)

        msgtext = render(msghtml)

        # construct message object
        list_title = self.context.title
        subject = '[%s] Digest, %s' % (list_title, date)
        mailto = self.context.getValueFor('mailto')
        returnpath = self.context.getValueFor('returnpath') \
                     or self.context.manager_email
        listsub = self.context.getValueFor('subscribe')
        listsub = '<mailto:%s?subject=%s>' % (mailto, listsub)
        listunsub = self.context.getValueFor('unsubscribe')
        listunsub = '<mailto:%s?subject=%s>' % (mailto, listunsub)
        boundary = '----=_Part_%s' % timestamp
        msg_map = {'title': list_title,
                   'subject': subject,
                   'mailto': mailto,
                   'xmailer': self.context.getValueFor('xmailer'),
                   'returnpath': returnpath,
                   'listsub': listsub,
                   'listunsub': listunsub,
                   'boundary': boundary,
                   'msghtml': msghtml,
                   'msgtext': msgtext,
                   }
        for key, value in msg_map.items():
            if type(value) is unicode:
                msg_map[key] = value.encode('utf-8')
        msg_str = msg_tmpl % msg_map
        msg = email.message_from_string(msg_str)
        return msg

    def format_message(self, message):
        """returned a dictionary with some fields needed for the template"""
        from_addr = message['from']
        quoted_subject = urllib.quote(message['subject'])
        name, email = parseaddr(from_addr)
        # if there is no name, use the email address in its place
        name = name or email
        archive_url = message.get('X-listen-message-url',
                                  self.context.absolute_url())
        return dict(from_name=name,
                    from_email=email,
                    quoted_subject=quoted_subject,
                    archive_url=archive_url,
                    )

    def unpack_message(self, message):
        msgstr = message.as_string()
        text_body, content_type, html_body, attachments = unpackMail(msgstr)
        if text_body:
            body = convertWebIntelligentPlainTextToHtml(text_body).strip()
        else:
            # we only have an html body; convert it to text and then
            # back to different html rendering
            body = render(html_body)
            body = convertWebIntelligentPlainTextToHtml(body).strip()
        return {'body': body, 'attachments': attachments}
