
#!/usr/bin/env python
# coding=utf-8

import os
import re
import time
import datetime
import hashlib
import string
import random

from google.appengine.ext import webapp
from google.appengine.api import memcache
from google.appengine.ext import db
from google.appengine.ext.webapp import util
from google.appengine.ext.webapp import template

from v2yh.babel import Member
from v2yh.babel import Counter
from v2yh.babel import Section
from v2yh.babel import Node
from v2yh.babel import Topic
from v2yh.babel import Reply
from v2yh.babel import Note

from v2yh.babel import SYSTEM_VERSION

from v2yh.babel.security import *
from v2yh.babel.ua import *
from v2yh.babel.da import *
from v2yh.babel.l10n import *
from v2yh.babel.ext.cookies import Cookies

template.register_template_library('v2yh.templatetags.filters')

class MyNodesHandler(webapp.RequestHandler):
    def get(self):
        member = CheckAuth(self)
        if member:
            site = GetSite()
            l10n = GetMessages(self, member, site)
            template_values = {}
            template_values['site'] = site
            template_values['member'] = member
            template_values['l10n'] = l10n
            template_values['page_title'] = site.title + u' › 我收藏的节点'
            template_values['rnd'] = random.randrange(1, 100)
            path = os.path.join(os.path.dirname(__file__), 'tpl', 'desktop', 'my_nodes.html')
            output = template.render(path, template_values)
            self.response.out.write(output)
        else:
            self.redirect('/')

def main():
    application = webapp.WSGIApplication([
    ('/my/nodes', MyNodesHandler)
    ],
                                         debug=True)
    util.run_wsgi_app(application)


if __name__ == '__main__':
    main()