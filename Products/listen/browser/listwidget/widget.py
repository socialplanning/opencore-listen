from zope.component import getMultiAdapter
from zope.app.form.interfaces import IInputWidget
from zope.app.form.browser.widget import SimpleInputWidget
from zope.app.pagetemplate.viewpagetemplatefile import ViewPageTemplateFile

class DynamicListWidget(SimpleInputWidget):

    template = ViewPageTemplateFile('widget.pt')

    def __call__(self):
        self.request.debug = 0
        return self.template()

    def _getFormInput(self):
        value = super(DynamicListWidget, self)._getFormInput()
        # Make sure that we always retrieve a list object from the
        # request, even if only a single item or nothing has been
        # entered.  Also make sure we decode all the values to unicode
        # since the widget validation demands this.
        if value is None:
            seq = ()
        elif isinstance(value, tuple) or isinstance(value, list):
            seq = value
        else:
            seq = (value,)
        seq = [v.decode('utf8', 'replace') for v in seq]
        return tuple(seq)

    def hasInput(self):
        return (self.name + '.marker') in self.request.form

    def hidden(self):
        s = ''
        for value in self._getFormValue():
            widget = getMultiAdapter(
                (self.context.value_type, self.request), IInputWidget)
            widget.name = self.name
            widget.setRenderedValue(value)
            s += widget.hidden()
        return s

    def resource_url(self):
        return '/'.join((self.context.context.absolute_url(),
                         '++resource++listoperations.js'))



