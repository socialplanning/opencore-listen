import re
import os
from Products.CMFCore.utils import ContentInit
from Products.CMFCore.DirectoryView import registerDirectory

from config import PROJECTNAME, GLOBALS

import content
import permissions

# Add builtin mailboxer skin
from Products.MailBoxer.config import SKINS_DIR as MB_SKINS_DIR
from Products.MailBoxer.config import GLOBALS as MB_GLOBALS
registerDirectory(MB_SKINS_DIR, MB_GLOBALS)

# Add local skin
registerDirectory('skins', GLOBALS)

def initialize(context):

    ContentInit(
        PROJECTNAME + ' Content',
        content_types      = (content.MailingList, ),
        permission         = permissions.AddMailingList,
        extra_constructors = (content.addMailingList, ),
        ).initialize(context)

    try:
        fiveVersion = context._ProductContext__app.Control_Panel.Products.Five.version
    except AttributeError:
        import Products.Five
        version_file = open(os.path.join(Products.Five.__path__[0],
                                         'version.txt'))
        fiveVersion = version_file.readline().lower().strip()
        version_file.close()
    m = re.search('([0-9]*\\.[0-9]*)', fiveVersion)
    fiveVersion = m.group(0)

    if float(fiveVersion) >= 1.3:
        config.HAS_CONTAINER_EVENTS = True
