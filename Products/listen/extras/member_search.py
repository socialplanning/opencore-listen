import urllib
from Products.CMFCore.utils import getToolByName
from Acquisition import Explicit

class MemberSearchView(Explicit):
    """A simple browser view for doing a member search and returning ajax
       parseable results.  Let's take a look::

         >>> portal = self.portal
         >>> mtool = portal.portal_membership
         >>> req = self.app.REQUEST
         >>> res = req.RESPONSE

       We apply our view, it shouldn't fail if the search paramters are omitted
       from the request::

         >>> from Products.listen.extras.member_search import MemberSearchView
         >>> view = MemberSearchView(portal, req)
         >>> view.searchForMembers()
         []
         >>> print view.getAjaxResults()
         <members>
         </members>
         >>> print view()
         <members>
         </members>
         >>> res['content-type']
         'text/xml'

       Now we set some real query parameters (for a member who doesn't exist),
       and perform our search::

         >>> res.setHeader('content-type', 'text/html')
         >>> req.set('search_type', 'name')
         >>> req.set('search_term', 'my_user')
         >>> view.searchForMembers()
         []
         >>> print view.getAjaxResults()
         <members>
         </members>
         >>> print view()
         <members>
         </members>
         >>> res['content-type']
         'text/xml'
         >>> res.setHeader('content-type', 'text/html')

       Now we add the expected member object and perform the search again::

         >>> mtool.addMember('my_user', 'secret',
         ... ('Member',), (),
         ... properties={'fullname': 'Test User', 'email': 'test@example.com'})
         >>> len(view.searchForMembers())
         1
         >>> print view.getAjaxResults()
         <members>
         <member>
           <id>my_user</id>
           <name>my_user</name>
           <fullname>Test User</fullname>
           <url>http://nohost/plone/author/my_user</url>
         </member>
         </members>
         >>> print  view()
         <members>
         <member>
           <id>my_user</id>
           <name>my_user</name>
           <fullname>Test User</fullname>
           <url>http://nohost/plone/author/my_user</url>
         </member>
         </members>
         >>> res['content-type']
         'text/xml'

    """

    ajax_format = """<member>
  <id>%s</id>
  <name>%s</name>
  <fullname>%s</fullname>
  <url>%s</url>
</member>"""

    def __init__(self, context, request):
        self.context = context
        self.request = request

    def searchForMembers(self):
        """
        This is horribly inefficient, and shouldn't really be used in
        any site w/ a large number of users.
        """
        request = self.request
        search_type = request.get('search_type', 'name')
        search_term = request.get('search_term', '')
        if not search_term:
            # Don't return all users when the search is empty as this could
            # create performance issues
            return []
        uf = getToolByName(self.context, 'acl_users', None)
        if uf is None:
            raise AttributeError, "No acl_users"
        # "name" generates both "login" and "fullname" searches
        if search_type == 'name':
            login_result = uf.searchUsers(login=search_term)
            fullname_result = uf.searchUsers(fullname=search_term)
            if login_result: # can only be one login match
                already = login_result[0].get('login')
                fullname_result = [res for res in fullname_result
                                   if res.get('login') != already]
            results = login_result + tuple(fullname_result)
        else:
            results = uf.searchUsers(**{search_type: search_term})
        mtool = getToolByName(self.context, 'portal_membership', None)
        if mtool is None:
            raise AttributeError, "No portal_membership"
        return [mtool.getMemberById(result['login']) for result in results]

    def getAjaxResults(self):
        portal_url = getToolByName(self.context, 'portal_url')()
        portal_url = portal_url.endswith('/') and portal_url or portal_url + '/'
        author_url = portal_url + 'author/'
        members = self.searchForMembers()
        member_xml_list = ['<members>']
        # Iterate over the members to generate xml entries of the format defined
        # by the ajax_format, and merge those into a single string
        for member in members:
            name = member.getUserName()
            member_xml_list.append(self.ajax_format%(
                                            member.getId(),
                                            name,
                                            member.getProperty('fullname', ''),
                                            author_url+urllib.quote(name)
                                            ))
        member_xml_list.append('</members>')
        member_xml = '\n'.join(member_xml_list)
        return member_xml

    def __call__(self):
        self.request.RESPONSE.setHeader('content-type', 'text/xml')
        return self.getAjaxResults()
