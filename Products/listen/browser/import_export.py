from AccessControl import Unauthorized
from BTrees.OOBTree import OOBTree
from Products.CMFCore.utils import getToolByName
from Products.Five import BrowserView
from Products.listen.config import PROJECTNAME
from Products.listen.i18n import _
from Products.listen.interfaces import IMailingListMessageExport
from Products.listen.interfaces import IMailingListMessageImport
from Products.listen.interfaces import IMailingListSubscriberImport
from Products.listen.interfaces import IMailingListSubscriberExport
from Products.listen.interfaces import IMembershipList
from Products.listen.interfaces import ISearchableArchive
from Products.listen.permissions import ExportMailingListArchives
from Products.listen.permissions import ExportMailingListSubscribers
from Products.listen.permissions import ImportMailingListArchives
from Products.listen.permissions import ImportMailingListSubscribers
from time import strftime
from zope.app.annotation.interfaces import IAnnotations
from zope.component import getAdapter
from zope.component import getUtility
import time

class ImportExportView(BrowserView):
    def __call__(self):

        plone_utils = getToolByName(self.context, 'plone_utils')

        # handle export actions
        export_messages = self.request.form.get('export_messages')
        export_addresses = self.request.form.get('export_addresses')

        if export_messages or export_addresses:
            filename = file_data = ""
            if export_addresses:
                if not self.can(ExportMailingListSubscribers):
                    raise Unauthorized(_(u'Cannot export mailing list subscribers'))
                filename = "%s-subscribers.csv" % self.context.getId()
                es = getAdapter(self.context, IMailingListSubscriberExport, name='csv')
                file_data = es.export_subscribers()
            elif export_messages:
                if not self.can(ExportMailingListArchives):
                    raise Unauthorized(_(u'Cannot export mailing list archives'))
                filename = "%s.mbox" % self.context.getId()
                em = getAdapter(self.context, IMailingListMessageExport, name='mbox')
                file_data = em.export_messages()

            # both export actions result in a file to download
            self.request.response.setHeader("Content-type", "text/plain")
            self.request.response.setHeader("Content-disposition", "attachment; filename=%s" % filename)
            
            # XXX don't know why i have to do this
            import transaction
            transaction.abort()

            return file_data

        # import actions
        psm_text = psm_type = None
        # This should be moved elsewhere
        self.UNDO_SUBMIT = UNDO_SUBMIT = "undu_"
        for key in self.request.form:
            if key.startswith(UNDO_SUBMIT):
                # reuse the import permission here
                if not self.can(ImportMailingListArchives):
                    raise Unauthorized(_(u'Cannot import mailing list archives'))
                key = key[len(UNDO_SUBMIT):]
                msg_count = self.undo_import(key)
                if msg_count:
                    txt = (_(u"Removed %s message%s from the list archive.")
                           % (msg_count, self._plural(msg_count)))
                    plone_utils.addPortalMessage(txt, type='info')
                    self.request.response.redirect(self.nextURL())
                    return

        if self.request.form.get("import_messages"):
            if not self.can(ImportMailingListArchives):
                raise Unauthorized(_(u'Cannot import mailing list archives'))
            file = self.request.form.get("import_file")
            if file:
                im = getAdapter(self.context, IMailingListMessageImport, name='mbox')
                self.msgids = im.import_messages(file)
                self.filename = file.filename
                self.save_import_history()
                msg_count = len(self.msgids)
                psm_text = (_(u'Imported %s message%s from \'%s\'')
                    % (msg_count, self._plural(msg_count), file.filename))
                psm_type = 'info'
            else:
                psm_text = _(u"No file selected. Please select an mbox file before importing.")
                psm_type = 'error'

            plone_utils.addPortalMessage(psm_text, type=psm_type)
            self.request.response.redirect(self.nextURL())
            return

        if self.request.form.get('import_subscribers'):
            if not self.can(ImportMailingListSubscribers):
                raise Unauthorized(_(u'Cannot import mailing list subscribers'))
            file = self.request.form.get("import_subscribers_file")
            if file:
                emails = [s.strip().split(',')[-1] for s in file]
                # quick sanity check
                emails = [e for e in emails if '@' in e]
                subscriber_importer = IMailingListSubscriberImport(self.context)
                if emails:
                    subscriber_importer.import_subscribers(emails)
                    n_emails = len(emails)
                    if n_emails != 1:
                        psm_text = _(u'%s email addresses imported') % n_emails
                    else:
                        psm_text = _(u'1 email address imported')
                    psm_type = 'info'
                else:
                    psm_text = _(u'No emails found')
                    psm_type = 'error'
            else:
                psm_text = _(u"No file selected. Please select a csv file before importing.")
                psm_type = 'error'
            plone_utils.addPortalMessage(psm_text, type=psm_type)
            self.request.response.redirect(self.nextURL())
            return

        return self.index()

    def nextURL(self):
        return '%s/%s' % (self.context.absolute_url(), self.__name__)

    def has_subscribers(self):
        ml = IMembershipList(self.context)
        return ml.subscribers

    def has_messages(self):
        sa = getUtility(ISearchableArchive, context=self.context)
        return len(sa())

    def is_archived(self):
        return self.context._is_archived()

    def undo_import(self, key):
        import_annot = self.get_import_annot()
        if import_annot:
            msgids = import_annot[key]['msgids']
            num_removed = len(msgids)
            sa = getUtility(ISearchableArchive, context=self.context)
            msg_map = {}
            for brain in sa(getId=msgids):
                # This is almost certainly suboptimal, as there must be a way
                # to get the parent folder from just the metadata, i.e., 
                # without calling getObject()
                msg_map.setdefault(brain.getObject().aq_parent, []).append(brain.getId)
                # Not sure why I have to specifically uncatalog the objects,
                # but if I don't they still show up in the archive -- even 
                # after they've been deleted below.
                sa.uncatalog_object(brain.getPath())
            for folder, msgids in msg_map.items():
                folder.manage_delObjects(msgids)
                if not len(folder):
                    parent = folder.aq_parent
                    parent.manage_delObjects([folder.getId()])
                    # Delete the folder's parent if it's empty
                    if len(parent.aq_parent.objectIds()) == 0:
                        parent.aq_parent.manage_delObjects([parent.getId()])
            del import_annot[key]
            return num_removed

    def get_import_annot(self):
        annot = IAnnotations(self.context)
        listen_annot = annot.get(PROJECTNAME)
        if listen_annot:
            return listen_annot.get('import')
        
    def save_import_history(self):
        annot = IAnnotations(self.context)
        listen_annot = annot.get(PROJECTNAME)
        if listen_annot is None:
            annot[PROJECTNAME] = listen_annot = OOBTree()
        import_annot = listen_annot.get('import')
        if import_annot is None:
            listen_annot['import'] = import_annot = OOBTree()
            
        now = str(time.time())
        data = dict(msgids=self.msgids,
                    filename=self.filename)
        import_annot[now] = OOBTree(data)

    def import_history(self):
        import_annot = self.get_import_annot()
        if import_annot:
            results = []
            keys = [k for k in import_annot.keys()]
            keys.sort(reverse=True)
            for timekey in keys:
                values = import_annot[timekey]
                import_time = strftime("%a, %b %d %Y at %I:%M %p", 
                                       time.localtime(float(timekey)))
                msg_count = len(values['msgids'])
                results.append(dict(
                        import_time=import_time,
                        import_id=timekey,
                        filename=values['filename'],
                        msg_count=msg_count,
                        plural=(msg_count != 1)))
            return results
        return []

    def _plural(self, count):
        if count != 1:
            return "s"
        else:
            return ""

    def can_import(self):
        return (self.can(ImportMailingListArchives) or
                self.can(ImportMailingListSubscribers))

    def can_export(self):
        return (self.can(ExportMailingListArchives) or
                self.can(ExportMailingListSubscribers))

    def can(self, permission):
        mstool = getToolByName(self.context, 'portal_membership')
        return mstool.checkPermission(permission, self.context)
