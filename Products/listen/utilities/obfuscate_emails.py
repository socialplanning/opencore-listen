import re
from zope.interface import implements

from OFS.SimpleItem import SimpleItem

from Products.listen.interfaces import IObfuscateEmails

class ObfuscateEmails(SimpleItem):
    """
    this class is registered as a local utility
    It provides a means for obfuscating emails from a given value with an option
    of having a javascript method of deobfuscation (revealing the email)

    Some framework setup:
        >>> import Products.Five
        >>> from Products.Five import zcml
        >>> zcml.load_config('meta.zcml', Products.Five)
        >>> zcml.load_config('permissions.zcml', Products.Five)
        >>> zcml.load_config("configure.zcml", Products.Five.site)
        >>> from Products.listen.utilities import tests
        >>> zcml.load_config('configure.zcml', tests)

    Create our utility:
        >>> from Products.listen.utilities.obfuscate_emails import ObfuscateEmails
        >>> oe = ObfuscateEmails()


    Now Obfuscate some strings:
        >>> test1 = "Spam this email@example.com and while you're at it, this@example.com too."
        >>> oe.obfuscate(test1)
        'Spam this <a href="#" onmouseover="javascript:this.href=deObfct(\\'example.com\\', \\'email\\');"\\n            onfocus="javascript:this.href=deObfct(\\'example.com\\', \\'email\\');"\\n            title="email">email@...</a> and while you\\'re at it, <a href="#" onmouseover="javascript:this.href=deObfct(\\'example.com\\', \\'this\\');"\\n            onfocus="javascript:this.href=deObfct(\\'example.com\\', \\'this\\');"\\n            title="this">this@...</a> too.'
        >>> oe.obfuscate(test1, False)
        "Spam this email@... and while you're at it, this@... too."

    """
    
    implements(IObfuscateEmails)

    def __init__(self):
        self.ob_email_regex = re.compile(r'''(\s*
          (?:<|&lt;)?)
            ([^@\s\<]+)\@([-a-zA-Z0-9_.]+\.[-a-zA-Z0-9_]+)
          ((?:>|&gt;)?
          \s*)''', re.VERBOSE)    

    def obfuscate(self, value, deobfuscate=True):
        if not deobfuscate:
            return self.ob_email_regex.sub('''\\1\\2@...\\4''', value)

        return self.ob_email_regex.sub('''\\1<a href="#" onmouseover="javascript:this.href=deObfct('\\3', '\\2');"
            onfocus="javascript:this.href=deObfct('\\3', '\\2');"
            title="\\2">\\2@...</a>\\4''', value)


    
