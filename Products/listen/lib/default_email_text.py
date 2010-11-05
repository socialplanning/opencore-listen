from Products.listen.i18n import _


user_pin_mismatch = _(u'user_pin_mismatch_body',u'''
Hello ${fullname},

Your request to join the ${listname} mailing list has been denied
because the pin you provided does not match the one initially sent.
Any questions regarding this should be sent to ${listmanager}.

Yours,
List Manager
''')

user_denied = _(u'user_denied_body',u'''
Hello ${fullname},

Your request to join the ${listname} mailing list has been denied
because there was no record of a request.
Any questions regarding this should be sent to ${listmanager}.

Yours,
List Manager
''')


user_mod = _(u'user_mod_body',u'''
Hello ${fullname},

We have received a message from you to the ${listname} mailing 
list. Permission for you to post messages to this list is 
awaiting approval.  Once you are approved, your message will 
be processed.

Please send questions to ${listmanager}.

Yours, 
List Manager
''')

user_sub_mod = _(u'user_sub_mod_body',u'''
Hello ${fullname},

Your request to join the ${listname} mailing list is awaiting approval.
Any questions regarding this invitation should be sent to ${listmanager}.

Yours, 
List Manager
''')

user_mem_mod_already_pending = _(u'user_mem_mod_already_pending_body',u'''
Hello ${fullname},

We have already received a message from you to the 
${listname} mailing list. Permission for you to post messages 
to this list is awaiting approval.  Once you are approved, 
your initial message will be processed. You should then
resend all subsequent messages.

Please send questions to ${listmanager}.

Yours, 
List Manager
''')

manager_mod = _(u'user_manager_body',u'''
Hello List Manager,

${fullname} is awaiting approval for membership on the ${listname} mailing list.
${mod_url}

''')


user_subscribe_request = _(u'user_subscribe_request_body',u'''
Hello ${fullname},

We have received a subscription request for your email address to the
${listname} mailing list. To confirm the request, simply reply to this 
message leaving the subject line unchanged.

If you do not wish to subscribe to this list, please disregard this
message. Send questions to ${listmanager}. 

Yours, 
List Manager
''')


user_welcome = _(u'user_welcome_body',u'''
Hello ${fullname},

You are now subscribed to ${listname}.

Send your messages to ${listaddress}

If you want to unsubscribe from ${listname}, send a message to 
${listaddress} with subject: unsubscribe.

Yours, 
List Manager
''')

user_unsubscribe_confirm = _(u'unsubscribe_confirm_body',u'''
Hello ${fullname},

You have been unsubscribed from ${listname}.

Farewell!

Yours, 
List Manager
''')

user_unsubscribe_request = _(u'user_unsubscribe_request_body',u'''
Hello ${fullname},

We have received a request to unsubscribe your email address from the
${listname} mailing list.

To confirm the request, simply reply to this message, leaving the 
subject line unchanged.

If you do not wish to cancel your subscription, please disregard this
message. Send questions to ${listmanager}.

Yours, 
List Manager
''')

user_already_pending = _(u'user_already_pending_body',u'''
Hello ${fullname},

We have received more than one message from you to the ${listname} 
mailing list.  In order to be able to send a message to this list,
please reply to this message leaving the subject line unchanged.  
After you have confirmed your email address, you may resend your
message.

Please send questions to ${listmanager}.

Yours, 
List Manager
''')

user_post_request = _(u'user_post_request_body',u'''
Hello ${fullname},

We have received a message from you to the ${listname} mailing 
list.  In order to be able to send a message to this list,
please reply to this message leaving the subject line unchanged.  
After you have confirmed your email address, your message will
be processed.

To subscribe to this list, send a message to ${listaddress}
with the subject: subscribe.

Please send questions to ${listmanager}.

Yours, 
List Manager
''')

manager_mod_post_request = _(u'manager_mod_post_request_body',u'''
--${boundary}
Content-Type: text/plain
Context-Transfer-Encoding: 8bit

Hello List Manager,

${fullname} has sent a message to the ${listname} mailing list 
and it is waiting for your approval.
${mod_url}

--${boundary}
Content-Type: message/rfc822
Content-Description: ${fullname}

${post}
''')

user_post_mod_notification = _(u'user_post_mod_notification',u'''
Hello ${fullname},

We have received a message from you to the ${listname} mailing 
list.  The message is waiting for approval from a list manager.

Please send questions to ${listmanager}.

Yours,
List Manager
''')

user_post_mod_subscribe_notification = _(u'user_post_mod_subscribe_notification',u'''
Hello ${fullname},

We have received a message from you to the ${listname} mailing 
list.  The message is waiting for approval from a list manager.

To subscribe to this list, send a message to ${listaddress}
with the subject: subscribe.

Please send questions to ${listmanager}.

Yours,
List Manager
''')

user_post_rejected = _(u'user_post_rejected',u'''
Hello ${fullname},

The message you have sent to ${listname} mailing list has been
rejected for the following reason:
${reject_reason}

Please send questions to ${listmanager}.

Yours, 
List Manager
''')

user_sub_rejected = _(u'user_sub_rejected',u'''
Hello ${fullname},

Your request to subscribe to ${listname} mailing list has been
rejected for the following reason:
${reject_reason}

Please send questions to ${listmanager}.

Yours, 
List Manager
''')

mail_footer_archived = _(u'mail_footer_archived',u'''
--
Archive: ${archive_url}
To unsubscribe send an email with subject "unsubscribe" to ${mailto}.  Please contact ${manager_email} for questions.
''')

mail_footer_unarchived = _(u'mail_footer_unarchived',u'''
--
To unsubscribe send an email with subject "unsubscribe" to ${mailto}.  Please contact ${manager_email} for questions.
''')

mail_header = _(u'mail_header',u'''
Content-type: ${content-type}
Subject: ${subject}
Message-id: ${message_id}
X-Mailer: ${xmailer}
Reply-To: ${mailto}
Errors-To: ${returnpath}
List-Post: <mailto:${mailto}>
List-Subscribe: <mailto:${mailto}?subject=${subscribe}>
List-Unsubscribe: <mailto:${mailto}?subject=${unsubscribe}>
List-Id: ${title}
Precedence: Bulk
''')
