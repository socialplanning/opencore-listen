from Products.listen.lib.common import lookup_member_id
from Products.listen.interfaces import IMembershipList
from Products.listen.interfaces import ISearchableArchive
from Products.listen.interfaces import IWriteMembershipList

from zope.component import getUtility
from Products.CMFCore.utils import getToolByName

from plone.mail import encode_header

from email import message_from_string
from email.Message import Message
from email.MIMEText import MIMEText
from email.MIMEMultipart import MIMEMultipart

from rfc822 import parseaddr

class MailingListMessageImporter(object):
    """ An adapter to import messages in an mbox format to a mailing list archive 

        >>> import Products.Five
        >>> from Products.Five import zcml
        >>> zcml.load_config('meta.zcml', Products.Five)
        >>> zcml.load_config("permissions.zcml", Products.Five)
        >>> zcml.load_config("configure.zcml", Products.Five.site)
        >>> from Products.listen.utilities import tests
        >>> zcml.load_config('configure.zcml', tests)
        >>> ml = tests.install_fake_ml(self.folder)
        
        The value for keepdate is preserved and then set to true to ensure
        the imported messages have the correct dates.
        >>> ml.getValueFor = lambda x: 0
        >>> ml.setValueFor = lambda x,y: None
        >>> from Products.listen.extras.import_export import MailingListMessageImporter
        >>> im = MailingListMessageImporter(ml)
        >>> from Products.listen.interfaces import ISearchableArchive
        >>> from zope.component import getUtility
        >>> sa = getUtility(ISearchableArchive, context=ml)
        >>> ml._msgs # make sure there are no messages
        []
        >>> from cStringIO import StringIO
        >>> mbox_str = '''From bruce.wayne@example.com Sat Jan  3 01:05:34 1996
        ... Message-id: <123456789@example.com>
        ... Date: 3 Jan 1996 01:05:34 -0000
        ... To: alfred@example.com
        ... Subject: It's Bruce
        ... 
        ... Hey, I have some 'work' to do tonight, so I'll probably be home late...
        ... 
        ... 
        ... From robin@example.com Sat Jan  3 01:10:00 1996
        ... Message-id: <12345678910@example.com>
        ... Date: 3 Jan 1996 01:10:00 -0000
        ... To: alfred@example.com
        ... Subject: Laundry...
        ... 
        ... Finished yet? It's been like a week.
        ... '''
        >>> mbox_file = StringIO(mbox_str)
        >>> len(im.import_messages(mbox_file))
        2
    """

    def __init__(self, context):
        self.context = context

    def import_messages(self, mbox_file):
        """ Imports all messages from mbox_file to the mailing list archive """
        keepdate_orig = self.context.getValueFor("keepdate") # save value
        self.context.setValueFor("keepdate", True)
        buf = []
        self.msgids = []
        self.msg_count = 0
        for line in mbox_file:
            if line.startswith("From "):
                if buf:
                    self._add_msg(buf)
                buf = [line]
            buf.append(line)
        if buf:
            self._add_msg(buf)
        self.context.setValueFor("keepdate", keepdate_orig) # restore original value

        # we reindex the new messages because it's possible to import them
        # out of order. This fixes up the threads.
        sa = getUtility(ISearchableArchive, context=self.context)
        for mbrain in sa(getId=self.msgids):
            msg = mbrain.getObject()
            sa.indexNewMessage(msg)

        return self.msgids

    def _add_msg(self, buf):
        msg = self.context.addMail("".join(buf))
        if msg:
            self.msg_count += 1
            self.msgids.append(msg.getId())
        

class MailingListMessageExporter(object):
    """ An adapter to export messages from a mailing list 
    archive to an mbox file
    
        Use a fake mailing list
        >>> import Products.Five
        >>> from Products.Five import zcml
        >>> zcml.load_config('meta.zcml', Products.Five)
        >>> zcml.load_config("permissions.zcml", Products.Five)
        >>> zcml.load_config("configure.zcml", Products.Five.site)
        >>> from Products.listen.utilities import tests
        >>> zcml.load_config('configure.zcml', tests)
        >>> ml = tests.install_fake_ml(self.folder)

        The fake mailing list also needs to provide IMailingList for the adaptation to succeed
        >>> from zope.interface import directlyProvides
        >>> from Products.listen.interfaces import IMailingList
        >>> directlyProvides(ml, IMailingList)

        >>> from Products.listen.utilities.tests import FakeMessage
        >>> from datetime import datetime
        >>> class JamesBondArchive(object):
        ...     def __call__(self, **kwords):
        ...         return [FakeMessage(None, "Dr. No <dr.no@example.com>", "My island",
        ...                             "Could someone come out to fix the plumbing?", 
        ...                             "<12345@example.com>", datetime(1963, 5, 8, 4, 5, 6)),
        ...                 FakeMessage(None, "Q <q@example.com>", "Your car...",
        ...                             "What happened to it?", "<123456@example.com>",
        ...                             datetime(1963, 5, 7, 6, 5, 4), has_attachment=True)]
        >>> from zope.component import provideUtility
        >>> from Products.listen.interfaces import ISearchableArchive
        >>> provideUtility(JamesBondArchive(), ISearchableArchive)

        Instantiate our exporter
        >>> from Products.listen.extras.import_export import MailingListMessageExporter
        >>> exporter = MailingListMessageExporter(ml)
        >>> print exporter.export_messages()
        From dr.no@example.com Wed May  8 04:05:06 1963
        From: Dr. No <dr.no@example.com>
        To: fake_address@example.com
        Subject: My island
        Date: 08 May 1963 04:05:06
        Message-id: <12345@example.com>
        <BLANKLINE>
        Could someone come out to fix the plumbing?
        From q@example.com Tue May  7 06:05:04 1963
        Content-Type: multipart/mixed; boundary="..."
        MIME-Version: 1.0
        From: Q <q@example.com>
        To: fake_address@example.com
        Subject: Your car...
        Date: 07 May 1963 06:05:04
        Message-id: <123456@example.com>
        <BLANKLINE>
        ...
        Content-Type: text/plain; charset="us-ascii"
        MIME-Version: 1.0
        Content-Transfer-Encoding: 7bit
        <BLANKLINE>
        What happened to it?
        ...
        Content-Disposition: attachment; filename="fake.txt"
        Content-Type: text/plain
        <BLANKLINE>
        Do you want to die, Mr. Bond?
        ...
        
    """

    def __init__(self, context):
        self.context = context

    def export_messages_to_tempfile(self):
        sa = getUtility(ISearchableArchive, context=self.context)
        import tempfile, os
        tmpfd, tmpname = tempfile.mkstemp(suffix='.mbox')
        temp_outfile = os.fdopen(tmpfd, 'w')
        msgs = sa(sort_on='modification_date')
        for msg in msgs:
            temp_outfile.write(self._convert_to_mbox_msg(msg.getObject()))
            temp_outfile.write('\n')
        temp_outfile.close()
        return tmpfd, tmpname

    def export_messages(self):
        sa = getUtility(ISearchableArchive, context=self.context)
        msgs = sa(sort_on='modification_date')
        file_data = [self._convert_to_mbox_msg(
                msg.getObject()) for msg in msgs]

        return "\n".join(file_data)

    def _convert_to_mbox_msg(self, msg):
        file_ids = list(msg.objectIds('File'))
        encoding = "utf-8"

        # true only if we have attachments
        if file_ids:
            enc_msg = MIMEMultipart()
            txt = MIMEText(msg.body.encode(encoding))
            enc_msg.attach(txt)
        else:
            enc_msg = Message()
            enc_msg.set_payload(msg.body.encode(encoding))

        enc_msg['From'] = encode_header(msg.from_addr, encoding)
        enc_msg['To'] = encode_header(self.context.mailto, encoding)
        enc_msg['Subject'] = encode_header(msg.subject, encoding)
        enc_msg['Date'] = encode_header(msg.date.strftime("%d %b %Y %T %Z"), encoding)
        enc_msg['Message-id'] = encode_header(msg.message_id, encoding)
        if msg.references:
            enc_msg['References'] = encode_header(" ".join(msg.references), encoding)
        if msg.in_reply_to:
            enc_msg['In-reply-to'] = encode_header(msg.in_reply_to, encoding)
                                    
        ctime = msg.date.strftime("%a %b %e %T %Y")
        enc_msg.set_unixfrom("From %s %s" % (parseaddr(msg.from_addr)[1], ctime))

        for file_id in file_ids:
            file = msg._getOb(file_id)
            data = file.data
            if not isinstance(data, basestring):
                data = str(data)
            content_type = file.getContentType()
            if content_type == 'message/rfc822':
                attachment = message_from_string(data)
            else:
                attachment = Message()
                attachment.add_header('Content-Disposition', 'attachment', filename=file.title)
                attachment.add_header('Content-Type', content_type)
                attachment.set_payload(data)
            enc_msg.attach(attachment)

        try:
            retval = enc_msg.as_string(unixfrom=True)
        except TypeError, e:
            raise

        return retval
        

class MailingListSubscriberExporter(object):
    """ An adapter to export subscribers from a mailing list 
    
        Use a fake mailing list
        >>> import Products.Five
        >>> from Products.Five import zcml
        >>> zcml.load_config('meta.zcml', Products.Five)
        >>> zcml.load_config("permissions.zcml", Products.Five)
        >>> zcml.load_config("configure.zcml", Products.Five.site)
        >>> from Products.listen.utilities import tests
        >>> zcml.load_config('configure.zcml', tests)
        >>> ml = tests.install_fake_ml(self.folder)

        The fake mailing list also needs to provide IMailingList for the adaptation to succeed
        >>> from zope.interface import directlyProvides
        >>> from Products.listen.interfaces import IMailingList
        >>> directlyProvides(ml, IMailingList)

        Instantiate our exporter
        >>> from Products.listen.extras.import_export import MailingListSubscriberExporter
        >>> exporter = MailingListSubscriberExporter(ml)

        We'll use a fake subscriptions adapter
        >>> from Products.listen.content.tests import Subscriptions
        >>> from Products.listen.interfaces import IMembershipList
        >>> from zope.component import provideAdapter
        >>> Subscriptions.subscribers = (u'badguy@example.com',u'cowboy@example.com',u'holly@example.com')
        >>> provideAdapter(Subscriptions, adapts=(IMailingList,), provides=IMembershipList)

        The catalogs and other things need to get stubbed out appropriately too
        >>> class DummyCatalog(object):
        ...     def getMetadataForUID(self, uid):
        ...         if uid.endswith('hanz'):
        ...             return dict(Title='Hans Gruber')
        ...         elif uid.endswith('john'):
        ...             return dict(Title='John McClane')
        >>> ml.portal_catalog = DummyCatalog()
        >>> class DummyPortalMemberdata(object):
        ...     def getPhysicalPath(self):
        ...         return ['', 'portal', 'portal_memberdata']
        >>> ml.portal_memberdata = DummyPortalMemberdata()

        We also need a member lookup utility
        >>> from Products.listen.interfaces import IMemberLookup
        >>> class DummyMemberLookup(object):
        ...     def to_memberid(self, email):
        ...         if email == 'cowboy@example.com':
        ...             return 'john'
        ...         elif email == 'badguy@example.com':
        ...             return 'hanz'
        >>> from zope.component import provideUtility
        >>> provideUtility(DummyMemberLookup(), provides=IMemberLookup)

        And now we can finally export the subscribers
        >>> print exporter.export_subscribers()
        hanz,Hans Gruber,badguy@example.com
        john,John McClane,cowboy@example.com
        ,,holly@example.com

    """
    
    def __init__(self, context):
        self.context = context

    def export_subscribers(self, include_allowed_senders=False):
        """ Returns CSV string of subscriber data """
        ml = IMembershipList(self.context)
        cat = getToolByName(self.context, 'portal_catalog')
        md = getToolByName(self.context, 'portal_memberdata')
        md_path = '/'.join(md.getPhysicalPath())
        file_data = []
            
        for email in ml.subscribers:
            memid = lookup_member_id(email, self.context)
            if memid:
                metadata = cat.getMetadataForUID('%s/%s' % (md_path, memid))
                # title gives the user's full name. It might be a good idea
                # to get the full object so we can directly access the full
                # name, but that'd be more expensive...
                title = metadata['Title']
            else: # e-mail only subscriber 
                memid = title = ""
            file_data.append(','.join([
                        memid, title, email, 'subscribed']))

        if include_allowed_senders:
            for email, info in ml.allowed_senders_data.items():
                if info['subscriber']:
                    continue
                file_data.append(','.join([
                            '', '', email, 'allowed']))

        return "\n".join(file_data)

class MailingListSubscriberImporter(object):
    """ An adapter to import subscribers to a mailing list
    
        Use a fake mailing list
        >>> import Products.Five
        >>> from Products.Five import zcml
        >>> zcml.load_config('meta.zcml', Products.Five)
        >>> zcml.load_config("permissions.zcml", Products.Five)
        >>> zcml.load_config("configure.zcml", Products.Five.site)
        >>> from Products.listen.utilities import tests
        >>> zcml.load_config('configure.zcml', tests)
        >>> ml = tests.install_fake_ml(self.folder)

        The fake mailing list also needs to provide IMailingList for the adaptation to succeed
        >>> from zope.interface import directlyProvides
        >>> from Products.listen.interfaces import IMailingList
        >>> directlyProvides(ml, IMailingList)

        Instantiate our importer
        >>> from Products.listen.extras.import_export import MailingListSubscriberImporter
        >>> importer = MailingListSubscriberImporter(ml)

        We need to register a dummy membership subscription adapter
        >>> test_addresses = []
        >>> class DummySubscriptionAdapter(object):
        ...     def __init__(self, context):
        ...         self.context = context
        ...     def subscribe(self, address, send_notify=True):
        ...         if send_notify:
        ...             raise ValueError('Expecting not to send out '
        ...                              'notifications')
        ...         test_addresses.append(address)

        We'll need to register our dummy subscription adapter
        >>> from zope.component import provideAdapter
        >>> from Products.listen.interfaces import IWriteMembershipList
        >>> provideAdapter(DummySubscriptionAdapter, adapts=(IMailingList,), provides=IWriteMembershipList)

        And now we can import some subscribers
        >>> importer = MailingListSubscriberImporter(ml)
        >>> importer.import_subscribers(['thug1@example.com',
        ...                              'thug2@example.com'])
        >>> print test_addresses
        ['thug1@example.com', 'thug2@example.com']

    """
    
    def __init__(self, context):
        self.context = context

    def import_subscribers(self, subscribers):
        """ Imports the list of subscriber email addresses """
        slist = IWriteMembershipList(self.context)
        for subscriber in subscribers:
            slist.subscribe(subscriber, send_notify=False)
