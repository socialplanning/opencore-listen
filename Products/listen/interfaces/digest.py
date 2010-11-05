from zope.interface import Interface

class IDigestStorage(Interface):
    """
    For storing and retrieving digested messages for delivery to
    digest subscribers.
    """
    def add_message_to_digest(msg):
        """
        Adds a message to the digest, to be delivered next time digest
        delivery occurs.
        """

    def get_digest():
        """
        Retrieves the current digest message.
        """

    def consume_digest():
        """
        Retrieves the current digest message and clears the digest so
        add'l messages will be added to a new digest.
        """

class IDigestConstructor(Interface):
    """
    For constructing digest messages.
    """
    def construct_digest(messages):
        """
        Constructs a digest message given a sequence of email message
        objects that are to be included in the digest.
        """
