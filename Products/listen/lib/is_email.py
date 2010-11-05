import re

email_regex = re.compile('\s*<?([^@\s]+\@[a-zA-Z0-9-.]+)>?\s*')

def is_email(test_email):
    return email_regex.match(test_email)

