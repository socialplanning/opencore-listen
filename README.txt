Listen
-------

Listen is a mailing list management application that integrates into the Plone
Content Management System.  It is based on the venerable MailBoxer Zope
Product by Maik Jablonski, and offers most of the features of that product.
Key features include:

- Easily create mailing lists through the Plone interface.

- Lists may be moderated or unmoderated, open to all or restricted to
  subscribers only.

- Optional archiving of mail with or without attachments.

- Fully threaded archive display, including a forum-like view.

- Portal members and visitors can easily subscribe/unsubscribe themselves
  through the Plone interface.

- Each list maintains its own catalog featuring a full text index of messages.

- Members can make responses with quotation to archived messages through the
  Plone interface.

- Automatic masking of member email addresses with links to author pages.

- Provides a registry of lists on a Zope instance allowing lists to be added
  without any additional SMTP server configuration.

- Performs well due to use of simple Zope types and z3/Five techniques.
  Capable of higher mail volume that MailBoxer itself, and much greater
  volume than Archetypes-based mailing list systems.

This product makes heavy use of Zope3 features within Plone via Five; it uses
views, adapters, Zope3 schemas (add and edit views), local utilities,
factories, and events.  It is not an ideally componentized application because
of its dependence on MailBoxer, which is used as the base class for the
primary content type, and provides more logic/functionality than an
ideal content class would.  Hopefully, those parts which make heavy use of
Five technologies can serve as a helpful example for those intending to use
Five in their own products.

Requirements
------------

Plone 2.1+ (and all that entails)
Zope 2.8.4+
Five 1.4
plone.app.form
MailBoxer (svn version from
https://svn.plone.org/svn/collective/MailBoxerTempDev/trunk)
ManagableIndex 1.1
(also OFolder http://www.dieter.handshake.de/pyprojects/zope/index.html#ManagableIndex)
plone.mail (https://svn.plone.org/svn/plone/plone.mail/trunk)

Highly Recommended
-------------------

MaildropHost 1.13+ (http://www.dataflake.org/software/maildrophost/)
    Any site that expects a reasonable amount of mail traffic (incoming and
    especially outgoing) needs to use this.  It well not send duplicate mails
    when a conflict error forces a retry, and it increases potential incoming
    mail volume tremendously by not blocking on sending mail.


Installation and setup
-----------------------

Place this product folder in your Zope instance's Products folder and restart
Zope.  Go to the portal_quickinstaller in the ZMI and install the product. Now
you may create mailing lists by using the add menu in any container in Plone,
or (preferably) using the add view for the Mailing List class which can be
accessed with a url of the following form:

http://mysite.example.com/my_portal/path/+/listen.add_mailinglist

Hopefully, Five add forms will be integrated into the Plone ui in the near
future so that the more correct way is also the easy way to add a list.

Your SMTP server must be configured to route mail to the mailing list(s).  For
a simple single list instance the easiest way to do this is the standard
MailBoxer way:

1) Copy the smtp2zope.py script from your MailBoxer folder to the relevant
SMTP server (if you are using sendmail with smrsh, then you need to place/link
it in a folder accessible to smrsh; for postfix place/link it in /etc/postfix).

2) Add an alias for the mailing list of the form:
my_list@lists.mydomain.com    "|/etc/smrsh/smtp2zope.py http://my_site.example.com/path/to/list/manage_mailboxer 200000"

for postfix:
my_list:      "|/etc/postfix/smtp2zope.py http://my_site.example.com/path/to/list/manage_mailboxer 200000"

Where the number at the end restricts the maximum size of a message intended
for the list, this is optional, but highly recommended.

If you would like to be able to setup arbitrary lists on your server and have
them automatically handled by your SMTP server the setup is slightly more
involved and dependent on the particulars of your SMTP server.  The end result
is that you need to map a catch-all domain to a similar command which uses a
tool in your Zope instance to decide where to route the mail.  In sendmail the
process is as follows:

1) same as step 1 above.

2) Add an entry to your virtusertable to create the catch-all domain:

@lists.my_domain.com      my_zope_lists

3) Add an alias pointing to the script with the URL for the global list lookup
utility:

my_zope_lists   "|/etc/smrsh/smtp2zope.py http://my_site.example.com/send_listen_mail 200000"

That should be about it.  Site members and anonymous users can subscribe
themselves to the list, the list creator and/or site manager can choose
whether the list is moderated or closed and how it is archived.

Qmail
=====
If you are using Qmail instead of postfix or sendmail, setting up the aliases
is slightly different. You need to create a file .qmail-mylist,
where mylist is the name of the list (i.e. mylist@example.com).

So on my system (which serves multiple domains), I had to create the file in
this directory: /var/qmail/mailnames/example.com
Depending on your setup, it might go somewhere else (i.e. /var/qmail/alias)

The contents of the file look like this:

/etc/smrsh/smtp2zope.py http://my_site.example.com/send_listen_mail 200000

Unlike with postfix/sendmail, you don't need to run a command 'newaliases'.
The new alias should be active immediately after you create the file.

Migration
=========

The following applies to listen lists created using instances of listen older
than 3/21/2006:

Due to issues with unicode/ASCII and message thread handling a migration
method was introduced for listen lists which will rebuild the archive
catalog and fix improperly stored strings in archived mail.  There are two
steps involved in migrating your lists and fixing these issues, first go to
the url for your search catalog
``http://site/path/to/list/utilities/ISearchableArchive/manage_main``, and delete
the existing 'mail_lexicon' and add a new ZCTextIndex Lexicon with::

 id: mail_lexicon
 Case Normalizer: True
 Stop Words: Don't remove stop words
 Word Splitter: Unicode Whitespace splitter

Then go to the following URL to reindex your archive
``http://site/path/to/list/fixupMessages``


Enjoy!

Alec Mitchell <apm13@columbia.edu>
