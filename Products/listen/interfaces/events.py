from zope.component.interfaces import ObjectEvent
from zope.interface import Interface
from zope.interface import implements

class INewMsgDeliveredEvent(Interface):
    """ Fired after a new msg has been delivered to the list """


class NewMsgDeliveredEvent(ObjectEvent):
    implements(INewMsgDeliveredEvent)
