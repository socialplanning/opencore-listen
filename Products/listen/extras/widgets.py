# Specialized Zope 3 widgets for listen
import itertools
from zope.component import getMultiAdapter
from zope.component.interfaces import ComponentLookupError
from zope.interface import Interface
from zope.app.form.browser.widget import SimpleInputWidget
from zope.app.form.browser.widget import DisplayWidget
from zope.app.form.interfaces import IInputWidget
from zope.app.pagetemplate.viewpagetemplatefile import ViewPageTemplateFile
from Products.CMFCore.utils import getToolByName
from Products.CMFPlone.utils import getSiteEncoding
from Products.listen.lib.common import email_regex

class MemberBaseWidget(object):
    """A mixin class for widgets that need to deal with Plone member objects"""
    def getMemberInfoFromId(self, mid):
        mtool = getToolByName(self.context.context, 'portal_membership')
        portal_url = getToolByName(mtool, 'portal_url')()
        portal_url = portal_url.endswith('/') and portal_url or portal_url + '/'
        author_url = portal_url + 'author/'
        # Plone 2.5 does not like the id to be unicode
        encoding = getSiteEncoding(self.context.context)
        mid = mid.encode(encoding)
        m = mtool.getMemberById(mid)
        name = m.getUserName()
        return {'id': m.getId(),
                'name': name,
                'fullname': m.getProperty('fullname', ''),
                'url': author_url+name}

class MemberRemovalWidget(SimpleInputWidget, MemberBaseWidget):
    """A simple widget that displays a list of current members and allows
    removing them (but not adding them).  This is useful as a base for the
    search widget, and also in an invitation based list, where members are
    invited using a search widget, and current members can only be removed,
    not added directly.

    We need to setup a Tuple field and use this widget for it, as well as some
    members::

        >>> from Products.listen.extras.tests import setupBasicFieldRequestAndMembers
        >>> field, request = setupBasicFieldRequestAndMembers(self.portal)
        >>> from Products.listen.extras.widgets import MemberRemovalWidget
        >>> widget = MemberRemovalWidget(field, field.value_type, request)
        >>> widget.name
        'field.foo'

    Let's examine our currently empty field::
        >>> widget.getData()
        []
        >>> widget.hidden()
        ''

    Data about current users will be available to the browser as a
    mapping with user data::
        >>> widget.setRenderedValue((u'test1',))
        >>> widget.getData()
        [{'url': 'http://nohost/plone/author/test1', 'fullname': 'Test User 1', 'id': 'test1', 'name': 'test1'}]

    The hidden widget should be hidden, we need to load the standard
    form zcml for this to work::
        >>> from Products.Five import zcml
        >>> from zope.app.form import browser
        >>> zcml.load_config('configure.zcml', package=browser)
        >>> print widget.hidden()
        <input class="hiddenType" id="field.foo" name="field.foo" type="hidden" value="test1"  />

   Data returned from the form to the widget will be in the expected
   form (in this case a list of strigs should become a tuple of
   unicode strings)::
        >>> widget.request.form[widget.name] = ['test1']
        >>> widget.getInputValue()
        (u'test1',)

   There's a sneaky little trick, where a marker value is set as the first value
   in the list to ensure that an empty list still appears in the request::
        >>> widget.request.form[widget.name] = [widget.marker, 'test1']
        >>> widget.getInputValue()
        (u'test1',)
        >>> widget.request.form[widget.name] = [widget.marker]
        >>> widget.getInputValue()
        ()

   Another sneaky trick is that we silently enforce the rule that no entries
   may be added, only removed with this widget by filtering the values::

        >>> widget.request.form[widget.name] = [widget.marker, 'test1', 'test2']
        >>> widget.getInputValue()
        (u'test1',)

   Should perform postback from the request if no data is available, but enforce
   the restrictions on the postback.  If the widget data is unset the
   widget consults the field context to get a value, so we must set an
   appropriate attribute on the field:

        >>> widget.setRenderedValue(widget._data_marker)
        >>> widget.getData()
        []
        >>> request.form[widget.name] = [widget.marker, 'test1', 'test2']
        >>> widget.getData()
        []
        >>> setattr(self.portal, field.__name__, (u'test1',))
        >>> widget.getData()
        [{'url': 'http://nohost/plone/author/test1', 'fullname': 'Test User 1', 'id': 'test1', 'name': 'test1'}]

"""

    template = ViewPageTemplateFile('member_removal.pt')
    marker = '__marker'

    def __init__(self, context, value_type, request):
        """Initialize the widget."""
        # only allow this to happen for a bound field
        assert context.context is not None
        self._type = context._type
        self._sub_type = value_type._type
        super(MemberRemovalWidget, self).__init__(context, request)

    def __call__(self):
        self.request.debug = 0
        return self.template()

    def getData(self):
        if not self._renderedValueSet():
            # Pull the values from the request if available, e.g. on resubmit
            data = self._toFieldValue(self.request.get(self.name, []))
        else:
            data = self._data
        return [self.getMemberInfoFromId(m) for m in data]

    def _toFieldValue(self, input_vals):
        """Coerce the input value to the expected sequence type for
        getInputValue"""
        # In we have a hidden field in the form that ensures that the list
        # is always submitted, even when empty.  We must remove that value.
        if input_vals and self.marker == input_vals[0]:
            input_vals.pop(0)
        input_vals = super(MemberRemovalWidget, self)._toFieldValue(input_vals)
        input_vals = [self._sub_type(i) for i in input_vals]
        # Perform any filtering:
        input_vals = self._restrictInputValues(input_vals)
        return self._type(input_vals)

    def _restrictInputValues(self, input_vals):
        """This widget has a contract that it will not allow for adding new
        entries, only removing existing ones, we must enforce this."""
        if not self._renderedValueSet():
            # Get the current values of the field from the adapted bound context
            # as self._data may not have been set yet.
            try:
                # Get the value directly from the context of the field
                context = self.context.context
                if self.context.interface is not None:
                    # if the field has an associated inteface/schema attempt to
                    # adapt the context to it
                    try:
                        context = self.context.interface(context)
                    except ComponentLookupError:
                        pass
                cur_vals = self.context.get(context)
            except AttributeError:
                return []
        else:
            cur_vals = self._data
        cur_vals = dict(itertools.izip(cur_vals,
                                       itertools.repeat(None)))
        return [val for val in input_vals if val in cur_vals]

    def hidden(self):
        """Render the widget as hidden fields"""
        fields = []
        data = self._renderedValueSet() and self._data or []
        for value in data:
            widget = getMultiAdapter((self.context.value_type, self.request),
                                     IInputWidget)
            widget.name = self.name
            widget.setRenderedValue(value)
            fields.append(widget.hidden())
        return '\n'.join(fields)

class MemberSearchWidget(MemberRemovalWidget):
    """An input widget for searching for members and adding them to a
    list.  Let's setup a widget for a Tuple field, and a portal with
    some members::

        >>> from Products.listen.extras.tests import setupBasicFieldRequestAndMembers
        >>> field, request = setupBasicFieldRequestAndMembers(self.portal)
        >>> from Products.listen.extras.widgets import MemberSearchWidget
        >>> widget = MemberSearchWidget(field, field.value_type, request)
        >>> widget.name
        'field.foo'

    Let's examine our currently empty field::
        >>> widget.getData()
        []
        >>> widget.hidden()
        ''

    And the search method of the widget (for when Ajax is not
    available).  In order to use the search results, we must register a 'view'::
        >>> from zope.component import provideAdapter
        >>> from zope.interface import Interface
        >>> from Products.listen.extras.member_search import MemberSearchView
        >>> provideAdapter(MemberSearchView, (Interface, Interface),
        ...                name='member_search.html')
        >>> widget.request.form['field.foo.search_term'] = 'test1'
        >>> widget.request.form['field.foo.search_param'] = 'name'
        >>> widget.getSearchResults()
        [{'url': 'http://nohost/plone/author/test1', 'fullname': 'Test User 1', 'id': 'test1', 'name': 'test1'}]

    However, if the field has values already those values will not be
    shown in the search results::
        >>> widget.setRenderedValue((u'test1',))
        >>> widget.getSearchResults()
        []
        >>> widget.request.form['field.foo.search_term'] = 'test2'
        >>> widget.getSearchResults()
        [{'url': 'http://nohost/plone/author/test2', 'fullname': 'Test User 2', 'id': 'test2', 'name': 'test2'}]

   This widget needs to allow adding new values, unlike its parent widget::

        >>> widget.request.form[widget.name] = [widget.marker, 'test1', 'test2']
        >>> widget.getInputValue()
        (u'test1', u'test2')
    """

    template = ViewPageTemplateFile('member_search.pt')
    marker = '__marker'

    def getSearchResults(self):
        """Use the member search view to get member search results directly"""
        portal = getToolByName(self.context.context,
                               'portal_url').getPortalObject()
        view = getMultiAdapter((portal, self.request),
                               name='member_search.html')
        self.request.form['search_term'] = \
                         self.request.get(self.name+'.search_term', '')
        self.request.form['search_type'] = \
                         self.request.get(self.name+'.search_param', 'name')
        # Don't return results we already have
        cur_vals = [m['id'] for m in self.getData()]
        return [self.getMemberInfoFromId(i.getId()) for
                i in  view.searchForMembers() if i.getId() not in cur_vals]

    def _restrictInputValues(self, input):
        """This widget allows adding entries, so no filtering"""
        return input

class SubscriberRemovalWidget(MemberRemovalWidget):
    """A version of the removal widget that will accept entries that may be
      simple email addresses and not exclusively member ids.

    We again setup a Tuple field and use this widget for it, as well as some
    members::

        >>> from Products.listen.extras.tests import setupBasicFieldRequestAndMembers
        >>> field, request = setupBasicFieldRequestAndMembers(self.portal)
        >>> from Products.listen.extras.widgets import SubscriberRemovalWidget
        >>> widget = SubscriberRemovalWidget(field, field.value_type, request)
        >>> widget.name
        'field.foo'

    Data about members should work as before::
        >>> widget.setRenderedValue((u'test1',))
        >>> widget.getData()
        [{'url': 'http://nohost/plone/author/test1', 'fullname': 'Test User 1', 'id': 'test1', 'name': 'test1'}]

    But, if we add a simple email address::
        >>> widget.setRenderedValue((u'test1','tester@example.com'))
        >>> widget.getData()
        [{'url': 'http://nohost/plone/author/test1', 'fullname': 'Test User 1', 'id': 'test1', 'name': 'test1'}, {'url': 'mailto:tester@example.com', 'fullname': '', 'id': 'tester@example.com', 'name': 'tester@example.com'}]    
    """

    def getData(self):
        if not self._renderedValueSet():
            # Pull the values from the request if available, e.g. on resubmit
            data = self._toFieldValue(self.request.get(self.name, []))
        else:
            data = self._data
        entries = []
        for entry in data:
            try:
                info = self.getMemberInfoFromId(entry)
                entries.append(info)
            except AttributeError:
                info = None
            if info is None and email_regex.match(entry):
                info = {'id': entry, 'name': entry, 'fullname': '',
                        'url': 'mailto:'+entry}
                entries.append(info)
        return entries

class MemberListDisplayWidget(DisplayWidget, MemberBaseWidget):
    """A display widget for showing lists of Plone member objects."""

    item_str = '<li><a href="%(url)s">%(fullname)s (%(name)s)</a></li>'

    def __call__(self):
        view_items = ['<ul>']
        if self._renderedValueSet():
            value = self._data
        else:
            value = self.context.default
        if value == self.context.missing_value:
            return ""
        for item in value:
            view_items.append(self.item_str%self.getMemberInfoFromId(item))
        view_items.append['</ul>']
        return '\n'.join(view_items)
