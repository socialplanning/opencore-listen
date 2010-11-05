# Some utilities for views
import re
from StringIO import StringIO

from Products.CMFPlone.utils import base_hasattr
from Products.CMFCore.utils import getToolByName
from Products.listen.lib.common import lookup_member_id
from zope.component import getUtility
from Products.listen.interfaces import IObfuscateEmails

from rfc822 import parseaddr
import logging
logger=logging.getLogger("listen")


def format_date(date, aq_context):
    tool = getToolByName(aq_context, 'translation_service', None)
    if tool is not None:
        return tool.ulocalized_time(date, long_format=True, context=aq_context)
    else:
        return date


def messageStructure(obj, aq_context=None, sub_mgr=None, full_message=False):
    """A mapping defining the data we want from brain objects for views"""
    if base_hasattr(obj, 'getURL'):
        url = obj.getURL()
        id = obj.getId
    else:
        url = obj.absolute_url()
        id= obj.getId()
    if aq_context is None:
        aq_context = obj

    from_id, from_addr = getAddressInfo(obj, sub_mgr)
    subject = escape(obj.subject) or '(No Subject)'
    struct = {'subject': obfct_de(subject),
              'brief_subject': obfct(subject[:40]) + \
                                     (len(subject) > 40 and ' ...' or ''),
              'mail_from': from_id and from_id or obfct(from_addr),
              'from_id': from_id,
              'date': format_date(obj.date, aq_context),
              'message_id': obj.message_id,
              'in_reply_to': obj.in_reply_to,
              'id': id,
              'url': url}
    if full_message:
        msg_obj = obj
        if not base_hasattr(msg_obj, 'body'):
            msg_obj = obj.getObject()
        struct['body'] = obfct_de(escape(msg_obj.body))
        struct['attachments'] = getAttachmentsForMessage(msg_obj)
    return struct


def getAddressInfo(obj, subscription_manager):
    if subscription_manager is not None:
        from_name, from_addr = parseaddr(obj.from_addr)
        user = lookup_member_id(from_addr, obj)
        if user is not None:
            return user, obj.from_addr
    return None, obj.from_addr


# Should we use a generator here? Doing so would ensure we only do one loop,
# but makes caching and batching difficult.
def catalogMessageIterator(brains, sub_mgr=None):
    """Returns simple dicts for each catalog brain input"""
    return [messageStructure(b, sub_mgr=sub_mgr) for b in brains]


# This may be a bit inefficient, as it potentially performs many (simple)
# catalog queries. This will, however be more accurate in cases where mail
# clients properly fill in the in-reply-to header but do not completely fill
# out their references (Outlook doesn't even create it apparently, and kmail
# and others keep only a limited set of references, not the whole thread).
def createReplyStructure(message, search_interface,
                               sub_mgr=None, full_message=False):
    return recursiveCreateReplyStructure(message, search_interface,
         sub_mgr=sub_mgr, full_message=full_message)

def recursiveCreateReplyStructure(message, search_interface,
                                          sub_mgr, full_message):
    """Creates a nested structure of all replies to the passed object.
       Optionally includes bodies, using getObject unfortunately."""
    msg_struct = messageStructure(message, sub_mgr=sub_mgr,
                                                    full_message=full_message)
    msg_struct['children'] = []

    children = search_interface.getMessageReplies(message.message_id)
    for child in children:
        # Chain together the generators for each of the child objects
        msg_struct['children'] = msg_struct['children'] + \
            [recursiveCreateReplyStructure(child, search_interface,
                                                       sub_mgr, full_message)]

    return msg_struct


# This should be faster, but uses the references header which mailers set
# inconsistently.  It will certainly break when starting from a message that
# is not the true top of the thread, but may be sufficient for getting an
# entire thread (assuming all mailers which set the header include the
# initial message).
def createReplyStructureFromReferrers(message, search_interface,
           sub_mgr=None, full_message=False, newest_first=False):
    """Should return a structure identical to the previous method (except
       with lists in place of generators) using a different technique"""
    origin_id = message.message_id
    proxy = messageStructure(message, sub_mgr=sub_mgr,
                             full_message=full_message)
    proxy['children'] = []
    result = {origin_id: proxy}
    tree = search_interface.getMessageReferrers(message.message_id)
    result = generateThreadedMessageStructure(result, tree, sub_mgr=sub_mgr,
                                              full_message=full_message)
    if newest_first:
        result[origin_id]['children'].reverse()
    return result[origin_id]

def generateThreadedMessageStructure(struct, tree,
                               sub_mgr=None, full_message=False):
    """Takes an initial structure consisting of a mapping with one
       entry, which is a message structure representing object at the root of
       the message tread, and a list of messages in the thread (catalog brains
       or message objects).  If you want to generate a threaded structure
       without a fixed root message (i.e. a number of distinct threads), then
       the initial structure should contain a mapping called 'base_level'
       containing a key 'children' which points to a list.  All parentless,
       messages will end up in struct['base_level']['children'].  This method
       Modifies the 'struct' in place, and also returns it."""
    for brain in tree:
        item = messageStructure(brain, sub_mgr=sub_mgr,
                                full_message=full_message)
        item['children'] = []
        parent = item['in_reply_to']
        msg_id = item['message_id']
        is_start_of_thread = getattr(brain, 'isInitialMessage', None)
        if is_start_of_thread or not parent:
            # If there is no parent, add the item to the 'base_level' list
            # of children.
            struct['base_level']['children'].append(item)
        elif struct.has_key(parent):
            struct[parent]['children'].append(item)
        else:
            struct[parent] = {'children':[item]}
        # If we have processed a child already, make sure we register it
        # as a child
        if struct.has_key(msg_id):
            item['children'] = struct[msg_id]['children']
        struct[msg_id] = item
    return struct


def getAttachmentsForMessage(message):
    attachments = message.objectValues('File')
    attach_list = []
    if attachments:
        mime_reg = getToolByName(message, 'mimetypes_registry')
        portal_url = getToolByName(message, 'portal_url')()
        for attachment in attachments:
            title = attachment.title
            mimetype = attachment.getContentType()
            try:
                mime_obj = mime_reg.classify(attachment,
                            mimetype=mimetype,
                            filename=title)
            except:
                logger.warn("Attachment skipped due to mime reg error (type=%s, name=%s)"%(mimetype, title))
                continue
            # XXX: Using a python script here is increidbly lame, but
            # reimplementing the size stuff is worse.
            size = message.getObjSize(size=attachment.get_size())
            attach_list.append({'title': title,
                            'type': mimetype,
                            'icon_url': portal_url + '/' + mime_obj.icon_path,
                            'url': attachment.absolute_url(),
                            'size': size})
    return attach_list


# match opening quotes in mails
quote_regex = re.compile('^((?:> ?)+)')
MAX_MAIL_WIDTH = 78

def rewrapMessage(body, add_quote=False):
    """Rewraps an email message at 78 chars preserving quote characters, and
       optionally adding an extra level of quoting

        >>> str1 = 'A message that needs wrapping because it is over 80 chars wide, and it should have a line break somewhere.'
        >>> print rewrapMessage(str1)
        A message that needs wrapping because it is over 80 chars wide, and it should\r
        have a line break somewhere.

       We need to preserve quotes as well:
        >>> str2 = '> > A message that needs wrapping because it is over 80 chars wide, and it should have a line break somewhere.'
        >>> print rewrapMessage(str2)
        > > A message that needs wrapping because it is over 80 chars wide, and it\r
        > > should have a line break somewhere.

       If we have a single word longer than 80 char we leave it be:
        >>> str3 = 'https://areallylongurl.that.has.no.spaces.com/this/is/getting/ridiculous?with_a=query&string=even'
        >>> print rewrapMessage(str3)
        https://areallylongurl.that.has.no.spaces.com/this/is/getting/ridiculous?with_a=query&string=even

       We don't break on the space in the quote chars even:
        >>> str4 = '> > > https://areallylongurl.that.has.no.spaces.com/this/is/getting/ridiculous?with_a=query&string=even'
        >>> print rewrapMessage(str4)
        > > > https://areallylongurl.that.has.no.spaces.com/this/is/getting/ridiculous?with_a=query&string=even

       But we need to break a line that starts with a long string and has
       whitespace separated strings after it:
        >>> str5 = '> > > https://areallylongurl.that.has.no.spaces.com/this/is/getting/ridiculous?with_a=query&string=even Wow, that was some url'
        >>> print rewrapMessage(str5)
        > > > https://areallylongurl.that.has.no.spaces.com/this/is/getting/ridiculous?with_a=query&string=even\r
        > > > Wow, that was some url

       And we need to break a line that containd a long string and has
       whitespace separated strings before and after:
        >>> str6 = '> > > Here it goes, https://areallylongurl.that.has.no.spaces.com/this/is/getting/ridiculous?with_a=query&string=even Wow, that was some url'
        >>> print rewrapMessage(str6)
        > > > Here it goes,\r
        > > > https://areallylongurl.that.has.no.spaces.com/this/is/getting/ridiculous?with_a=query&string=even\r
        > > > Wow, that was some url

       We also optionally add quotes before reflowing:
        >>> str7 = '> > A quoted string that is a little bit too long when another quote is added'
        >>> rewrapMessage(str7)
        '> > A quoted string that is a little bit too long when another quote is added'
        >>> print rewrapMessage(str7, add_quote=True)
        > > > A quoted string that is a little bit too long when another quote is\r
        > > > added

       And test it with a combination of the above:
        >>> msg = 'A long string that should get split into three lines because it is absurdly long, and has no breaks in it; really, it is far far longer than it should be and someone should consider stopping it as soon as possible.\\r\\n> > > A quoted line that needs a break because it is also a bit long, especially when the extra quote is added a the front.\\r\\n> > A really long url like: https://areallylongurl.that.has.no.spaces.com/this/is/getting/ridiculous?with_a=query which needs to be split twice.'
        >>> print rewrapMessage(msg, add_quote=True)
        > A long string that should get split into three lines because it is absurdly\r
        > long, and has no breaks in it; really, it is far far longer than it should\r
        > be and someone should consider stopping it as soon as possible.\r
        > > > > A quoted line that needs a break because it is also a bit long,\r
        > > > > especially when the extra quote is added a the front.\r
        > > > A really long url like:\r
        > > > https://areallylongurl.that.has.no.spaces.com/this/is/getting/ridiculous?with_a=query\r
        > > > which needs to be split twice.

       Finally test that it preserves existing newlines:
        >>> msg = '> > > A line that got badly\\r\\n> > > broken somehow. But should not be reflowed.\\r\\nWith another quote level as\\r\\nwell.'
        >>> print rewrapMessage(msg, add_quote=True)
        > > > > A line that got badly\r
        > > > > broken somehow. But should not be reflowed.\r
        > With another quote level as\r
        > well.

       But that it reflows broken lines:
        >>> msg = '> > > A line that will break when a quote is added and get flowed to the next\\r\\n> > > line. Which will itself be broken and flowed into the following line.\\r\\n> > > Which will be broken itself, but not be reflowed because the next line\\r\\n> is at a different quote level.'
        >>> print rewrapMessage(msg, add_quote=True)
        > > > > A line that will break when a quote is added and get flowed to the\r
        > > > > next line. Which will itself be broken and flowed into the following\r
        > > > > line. Which will be broken itself, but not be reflowed because the\r
        > > > > next line\r
        > > is at a different quote level.

       Should work for unicode too:
        >>> msg = u'> > > A line that will break when a quote is added and get flowed to the next\\r\\n> > > line. Which will itself be broken and flowed into the following line.\\r\\n> > > Which will be broken itself, but not be reflowed because the next line\\r\\n> is at a different quote level.'
        >>> print rewrapMessage(msg, add_quote=True)
        > > > > A line that will break when a quote is added and get flowed to the\r
        > > > > next line. Which will itself be broken and flowed into the following\r
        > > > > line. Which will be broken itself, but not be reflowed because the\r
        > > > > next line\r
        > > is at a different quote level.

       Multiple line breaks should not get truncated
        >>> msg = 'The quick brown fox jumped over the lazy dog. The quick brown fox jumped over the lazy dog. The quick brown fox jumped over the lazy dog.\\r\\n\\r\\nThe quick brown fox jumped over the lazy dog.'
        >>> print rewrapMessage(msg)
        The quick brown fox jumped over the lazy dog. The quick brown fox jumped over\r
        the lazy dog. The quick brown fox jumped over the lazy dog.\r
        \r
        The quick brown fox jumped over the lazy dog.
       """
    new_body = ''
    body_iter = StringIO(body)
    combine = False
    combine_line = ''
    for line in body_iter:
        # Optionally, add a '> ' for quoting:
        if add_quote:
            line = '> %s'%line
        # Find the quote chars:
        quotes = quote_regex.match(line)
        if quotes:
            quotes = quotes.group(1)
        else:
            quotes = ''
        if combine:
            # Only reflow with the next line if they are at the same quote
            # level
            old_quotes = quote_regex.match(combine_line)
            old_quotes = old_quotes and old_quotes.group(1) or ''
            if quotes and old_quotes == quotes:
                # Combine the two lines, removing the quotes from the second
                line = '\r\n' + combine_line.replace('\r\n',' ') + \
                                                     quote_regex.sub('', line)
            else:
                new_body += '\r\n' + combine_line
        new_lines = splitOnSpace(line, quotes)
        if len(new_lines) > 1:
            # If we split the line into multiple lines, we want to reflow the
            # last split line with the next line
            combine = True
            combine_line = new_lines[-1]
            new_text = '\r\n'.join(new_lines[:-1])
        else:
            combine = False
            new_text = new_lines[0]
        new_body += new_text
    # We may have missed a split line
    if combine:
        new_body += '\r\n' + combine_line
    return new_body

def splitOnSpace(line, quote_chars):
    # XXX: rewrap poorly by breaking at the earliest word and using
    # that as the next line.
    # The length of the line minus any trailing whitespace
    line_len = len(line.rstrip())
    # Return if the line is acceptable as is
    if line_len <= MAX_MAIL_WIDTH:
        return (line,)
    # find the next space, start at the character before the
    # newline, and quit at the quotes:
    for space_index in range(MAX_MAIL_WIDTH, len(quote_chars)-1, -1):
        if line[space_index] in [' ','\t']:
            break
    # If we didn't find a space then we have a long string with no
    # spaces, we need to ensure that there are no spaces after this
    # string to break on
    if space_index <= len(quote_chars):
        for space_index in range(MAX_MAIL_WIDTH+1, line_len):
            if line[space_index] in [' ','\t']:
                break
    if space_index >= line_len-1:
        return (line,)
    else:
        first_line = line[:space_index]
        next_line = quote_chars + line[space_index+1:]
        # Split the newly split line if necessary
        next_lines = splitOnSpace(next_line, quote_chars)
    return (first_line ,) + next_lines


def stripSignature(body, max_sig_lines=10):
    """Removes the signature from an email message body by looking for a line
       statring with '--':

        >>> message='A message:\\n --Item one\\n --Item two\\n\\n--\\nsig'
        >>> print stripSignature(message)
        A message:
         --Item one
         --Item two
        <BLANKLINE>
        <BLANKLINE>

       Make sure we don't fail when there's no signature:
        >>> message='A message:\\nwith no signature\\nat all.'
        >>> print stripSignature(message)
        A message:
        with no signature
        at all.
    """
    body_list = body.splitlines(True)
    body_end = len(body_list) - 1
    sig_end = body_end - max_sig_lines
    if sig_end < 0:
        sig_end = 0
    sig_index = None
    # Search from the bottom of the message up, recording the index at which
    # the signature line is found
    for i in range(body_end, sig_end, -1):
        line = body_list[i]
        if line.startswith('--'):
            sig_index = i
            break
    if sig_index:
        return ''.join(body_list[:sig_index])
    return body

# Get the default site encoding
def getSiteEncoding(context):
    encoding = 'utf-8'
    putils = getToolByName(context, 'plone_utils', None)
    if putils is not None:
        encoding = putils.getSiteEncoding()
    return encoding

# Encode a string to the site encoding or UTF-8
def encode(value, context):
    """ensure value is an encoded string"""
    if isinstance(value, unicode):
        value = value.encode(getSiteEncoding(context))
    return value

# Decode a string from the site encoding or UTF-8
def decode(value, context):
    """ensure a value is unicode"""
    if isinstance(value, str):
        value = value.decode(getSiteEncoding(context))
    return value

def escape(value):
    import cgi
    return cgi.escape(value)

def obfct(value):
     #obfuscates email addresses
    obfct_utility = getUtility(IObfuscateEmails)
    return obfct_utility.obfuscate(value, deobfuscate=False)

def obfct_de(value):
     #obfuscates email addresses with a javascript deobfuscation link
    obfct_utility = getUtility(IObfuscateEmails)
    return obfct_utility.obfuscate(value, deobfuscate=True)
