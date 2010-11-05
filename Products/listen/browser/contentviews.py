from Acquisition import aq_chain
from Acquisition import aq_inner
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from Products.Five.viewlet.viewlet import ViewletBase
from Products.listen.interfaces import IMailingList
from zope.component import getMultiAdapter
import pkg_resources

class ListenContentViewsViewlet(ViewletBase):
    """if there is a mailing list in the aq_chain, then show its content views
       otherwise show the default"""

    def render(self):
        # set up a reference to the original template
        filename = pkg_resources.resource_filename(pkg_resources.Requirement.parse('plone.app.layout'), 'plone/app/layout/viewlets/contentviews.pt')
        self.template_file = ViewPageTemplateFile(filename)

        # if we're looking at a mailing list, then show that immediately
        if IMailingList.providedBy(self.context):
            # Remove the disable border setting if it's set
            # or we won't get the proper content views on archives or posts
            try:
                del self.request.other['disable_border']
            except KeyError:
                pass
            # and always enable it
            self.request.other['enable_border'] = True
            return self.template_file()

        # otherwise, check if we have a mailing list in the parents
        for obj in aq_chain(aq_inner(self.context)):
            if IMailingList.providedBy(obj):
                # show the content views in the mailing list's context
                viewlet = getMultiAdapter((obj,
                                           self.request,
                                           self.__parent__,
                                           self.manager),
                                          name='plone.contentviews')
                viewlet.update()
                return viewlet.render()

        # we didn't have a mailing list in our chain, so return the default
        return self.template_file()
