from zope.interface import Interface

class IMailingListSubscriberExport(Interface):
    def export_subscribers():
        """ Export mailing list subscribers """

class IMailingListSubscriberImport(Interface):
    def import_subscribers(subscribers):
        """ Import mailing list subscribers """


class IMailingListMessageExport(Interface):
    def export_messages():
        """ Export mailing list message archive """


class IMailingListMessageImport(Interface):
    def import_messages(file):
        """ Import messages into mailing list archive """

