# Create a thread or two of test messages
from DateTime import DateTime

from Products.listen.content import MailMessage
from Products.listen.content import MailFromString

"""We have a thread that looks like this:

Message1
    Reply 1 (message2)
        Reply 1-1 (message4)
            Reply 1-1-1 (message7)
            Reply 1-1-2 (message10)
                Reply 1-1-2-1 (message11)
        Reply 1-2 (message6)
        Reply 1-3 (message8)
            Reply 1-3-1 (message9)
    Reply 2 (message3)
        Reply 2-1 (message5)

We make this structure available as both a flat list of message objects, and
as by adding a children parameter to each message containing a list of its
child messages.
"""

message1 = {
            'from': 'user1@example.com',
            'to': 'list1@example.com',
            'message_id': '<thread1_message1@example.com>',
            'subject': 'The first message',
            'date': DateTime().rfc822(),
            'in_reply_to': '',
            'references': '',
            'body': "Message 1.",
}

# Defined in the order they were recieved/sent.

# First reply
message2 = message1.copy()
message2['from'] = 'user2@example.com'
message2['message_id'] = '<thread1_reply1@example.com>'
message2['subject'] = 'Re: ' + message1['subject']
message2['in_reply_to'] = message1['message_id']
message2['references'] = message1['references'] +' '+ message1['message_id']
message2['date'] = (DateTime(message1['date']) + .0001).rfc822()
message2['body'] = \
"""> Message 1.
reply 1."""

# Second reply
message3 = message2.copy()
message3['from'] = 'user3@example.com'
message3['message_id'] = '<thread1_reply2@example.com>'
message3['date'] = (DateTime(message2['date']) + .0001).rfc822()
message3['body'] = \
"""> Message 1.
reply 2."""

# Reply 1 to message2
message4 = message2.copy()
message4['from'] = 'user1@example.com'
message4['message_id'] = '<thread1_reply1-1@example.com>'
message4['in_reply_to'] = message2['message_id']
message4['references'] = message2['references'] +' '+ message2['message_id']
message4['date'] = (DateTime(message3['date']) + .0001).rfc822()
message4['body'] = \
"""> > Message 1.
> reply 1.
reply 1."""

# Reply 1 to message3
message5 = message3.copy()
message5['from'] = 'user2@example.com'
message5['message_id'] = '<thread1_reply2-1@example.com>'
message5['in_reply_to'] = message3['message_id']
message5['references'] = message3['references'] +' '+ message3['message_id']
message5['date'] = (DateTime(message4['date']) + .0001).rfc822()
message5['body'] = \
"""> > Message 1.
> reply 2.
reply 1."""

# Reply 2 to message2
message6 = message4.copy()
message6['from'] = 'user3@example.com'
message6['message_id'] = '<thread1_reply1-2@example.com>'
message6['date'] = (DateTime(message5['date']) + .0001).rfc822()
message6['body'] = \
"""> > Message 1.
> reply 1.
reply 2."""

# Reply 1 to message4
message7 = message4.copy()
message7['from'] = 'user2@example.com'
message7['message_id'] = '<thread1_reply1-1-1@example.com>'
message7['in_reply_to'] = message4['message_id']
message7['references'] = message4['references'] +' '+ message4['message_id']
message7['date'] = (DateTime(message6['date']) + .0001).rfc822()
message7['body'] = \
"""> > > Message 1.
> > reply 1.
> reply 1.
reply 1."""

# Reply 3 to message2
message8 = message6.copy()
message8['from'] = 'user2@example.com'
message8['message_id'] = '<thread1_reply1-3@example.com>'
message8['date'] = (DateTime(message7['date']) + .0001).rfc822()
message8['body'] = \
"""> > Message 1.
> reply 1.
reply 3."""

# Reply 1 to message4
message9 = message8.copy()
message9['from'] = 'user1@example.com'
message9['message_id'] = '<thread1_reply1-3-1@example.com>'
message9['in_reply_to'] = message8['message_id']
message9['references'] = message8['references'] +' '+ message8['message_id']
message9['date'] = (DateTime(message8['date']) + .0001).rfc822()
message9['subject'] = 'Changed topic (was Re: The first message)'
message9['body'] = \
"""> > > Message 1.
> > reply 1.
> reply 1.
reply 1."""

# Reply 2 to message4
message10 = message4.copy()
message10['from'] = 'user3@example.com'
message10['message_id'] = '<thread1_reply1-1-2@example.com>'
message10['in_reply_to'] = message4['message_id']
message10['references'] = message4['references'] +' '+ message4['message_id']
message10['date'] = (DateTime(message9['date']) + .0001).rfc822()
message10['body'] = \
"""> > > Message 1.
> > reply 1.
> reply 1.
reply 2."""

# Reply 1 to message10
message11 = message10.copy()
message11['from'] = 'user2@example.com'
message11['message_id'] = '<thread1_reply1-1-2-1@example.com>'
message11['in_reply_to'] = message10['message_id']
message11['references'] = message10['references'] +' '+ message10['message_id']
message11['date'] = (DateTime(message10['date']) + .0001).rfc822()
message11['body'] = \
"""> > > > Message 1.
> > > reply 1.
> > reply 1.
> reply 2.
reply 1."""

body_template = \
"""To: %(to)s
From: %(from)s
Subject: %(subject)s
Message-ID: %(message_id)s
In-Reply-To: %(in_reply_to)s
References: %(references)s
Date: %(date)s

%(body)s
"""

def createMessages(*args):
    msg_list = []
    i = 0
    for msg in args:
        message = MailMessage('msg_%s'%i, msg['from'], msg['subject'],
                              msg['date'])
        message_str = body_template%msg
        MailFromString(message).createMailFromMessage(message_str)
        msg_list.append(message)
        i += 1
    return msg_list

def makeMailStructure():
    messages = createMessages(message1, message2, message3, message4,
                              message5, message6, message7, message8,
                              message9, message10, message11)
    messages[0].children = [messages[1], messages[2]]
    messages[1].children = [messages[3], messages[5], messages[7]]
    messages[2].children = [messages[4]]
    messages[3].children = [messages[6], messages[9]]
    messages[4].children = []
    messages[5].children = []
    messages[6].children = []
    messages[7].children = [messages[8]]
    messages[8].children = []
    messages[9].children = [messages[10]]
    messages[10].children = []
    return messages