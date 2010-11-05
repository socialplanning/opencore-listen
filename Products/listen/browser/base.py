from zope.formlib import form

import zope.i18nmessageid
_ = zope.i18nmessageid.MessageFactory('plone')

from Products.statusmessages.interfaces import IStatusMessage

class EditForm(form.EditForm):
    """Override EditForm to do sane redirection.
    """
    def update(self):
        form.EditForm.update(self)
        if self.status and not self.errors:
            # Set status message
            status = IStatusMessage(self.request)
            status.addStatusMessage(self.status, type=u'info')
            # Perform conditional redirect to the default view
            next = self.nextURL()
            if next:
                self.request.response.redirect(next)

    def nextURL(self):
        if getattr(self.context, 'absolute_url', None) is not None:
            return self.context.absolute_url()
