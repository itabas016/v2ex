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
from google.appengine.api import urlfetch
from google.appengine.api.labs import taskqueue
from google.appengine.ext import db
from google.appengine.ext.webapp import util
from google.appengine.ext.webapp import template

from v2ex.babel import Member
from v2ex.babel import Counter
from v2ex.babel import Section
from v2ex.babel import Node
from v2ex.babel import Topic
from v2ex.babel import Reply

from v2ex.babel import SYSTEM_VERSION

from v2ex.babel.security import *
from v2ex.babel.ua import *
from v2ex.babel.da import *
from v2ex.babel.ext.cookies import Cookies
from v2ex.babel.ext.sessions import Session

from django.utils import simplejson as json

from twitter.oauthtwitter import OAuthApi
from twitter.oauth import OAuthToken

from consumer import CONSUMER_KEY, CONSUMER_SECRET

template.register_template_library('v2ex.templatetags.filters')

class NewTopicHandler(webapp.RequestHandler):
    def get(self, node_name):
        browser = detect(self.request)
        template_values = {}
        template_values['page_title'] = 'V2EX › 创建新主题'
        template_values['system_version'] = SYSTEM_VERSION
        member = CheckAuth(self)
        if (member):
            template_values['member'] = member
            node = GetKindByName('Node', node_name)
            template_values['node'] = node
            section = False
            if node:
                q2 = db.GqlQuery("SELECT * FROM Section WHERE num = :1", node.section_num)
                if (q2.count() == 1):
                    section = q2[0]
            template_values['section'] = section
            if browser['ios']:
                path = os.path.join(os.path.dirname(__file__), 'tpl', 'mobile', 'new_topic.html')
            else:
                path = os.path.join(os.path.dirname(__file__), 'tpl', 'desktop', 'new_topic.html')
            output = template.render(path, template_values)
            self.response.out.write(output)
        else:
            self.redirect('/signin')

    def post(self, node_name):
        browser = detect(self.request)
        template_values = {}
        template_values['page_title'] = 'V2EX › 创建新主题'
        template_values['system_version'] = SYSTEM_VERSION
        member = CheckAuth(self)
        if (member):
            template_values['member'] = member
            q = db.GqlQuery("SELECT * FROM Node WHERE name = :1", node_name)
            node = False
            if (q.count() == 1):
                node = q[0]
            template_values['node'] = node
            section = False
            if node:
                q2 = db.GqlQuery("SELECT * FROM Section WHERE num = :1", node.section_num)
                if (q2.count() == 1):
                    section = q2[0]
            template_values['section'] = section
            errors = 0
            # Verification: title
            topic_title_error = 0
            topic_title_error_messages = ['',
                u'请输入主题标题',
                u'主题标题长度不能超过 120 个字符'
                ]
            topic_title = self.request.get('title').strip()
            if (len(topic_title) == 0):
                errors = errors + 1
                topic_title_error = 1
            else:
                if (len(topic_title) > 120):
                    errors = errors + 1
                    topic_title_error = 2
            template_values['topic_title'] = topic_title
            template_values['topic_title_error'] = topic_title_error
            template_values['topic_title_error_message'] = topic_title_error_messages[topic_title_error]
            # Verification: content
            topic_content_error = 0
            topic_content_error_messages = ['',
                u'请输入主题内容',
                u'主题内容长度不能超过 2000 个字符'
            ]
            topic_content = self.request.get('content').strip()
            if (len(topic_content) == 0):
                errors = errors + 1
                topic_content_error = 1
            else:
                if (len(topic_content) > 2000):
                    errors = errors + 1
                    topic_content_error = 2
            template_values['topic_content'] = topic_content
            template_values['topic_content_error'] = topic_content_error
            template_values['topic_content_error_message'] = topic_content_error_messages[topic_content_error]
            template_values['errors'] = errors
            if (errors == 0):
                topic = Topic()
                q = db.GqlQuery('SELECT * FROM Counter WHERE name = :1', 'topic.max')
                if (q.count() == 1):
                    counter = q[0]
                    counter.value = counter.value + 1
                else:
                    counter = Counter()
                    counter.name = 'topic.max'
                    counter.value = 1
                q2 = db.GqlQuery('SELECT * FROM Counter WHERE name = :1', 'topic.total')
                if (q2.count() == 1):
                    counter2 = q2[0]
                    counter2.value = counter2.value + 1
                else:
                    counter2 = Counter()
                    counter2.name = 'topic.total'
                    counter2.value = 1
                topic.num = counter.value
                topic.title = topic_title
                topic.content = topic_content
                topic.node = node
                topic.node_num = node.num
                topic.node_name = node.name
                topic.node_title = node.title
                topic.created_by = member.username
                topic.member = member
                topic.member_num = member.num
                topic.last_touched = datetime.datetime.now()
                ua = self.request.headers['User-Agent']
                if (re.findall('Mozilla\/5.0 \(iPhone;', ua)):
                    topic.source = 'iPhone'
                if (re.findall('Mozilla\/5.0 \(iPod;', ua)):
                    topic.source = 'iPod'
                if (re.findall('Mozilla\/5.0 \(iPad;', ua)):
                    topic.source = 'iPad'
                if (re.findall('Android', ua)):
                    topic.source = 'Android'
                if (re.findall('Mozilla\/5.0 \(PLAYSTATION 3;', ua)):
                    topic.source = 'PS3'            
                node.topics = node.topics + 1
                node.put()
                topic.put()
                counter.put()
                counter2.put()
                memcache.delete('Node_' + str(topic.node_num))
                memcache.delete('Node::' + str(node.name))
                taskqueue.add(url='/index/topic/' + str(topic.num))
                # Twitter Sync
                if member.twitter_oauth == 1 and member.twitter_sync == 1:
                    access_token = OAuthToken.from_string(member.twitter_oauth_string)
                    twitter = OAuthApi(CONSUMER_KEY, CONSUMER_SECRET, access_token)
                    status = topic.title + ' http://' + self.request.headers['Host'] + '/t/' + str(topic.num)
                    try:
                        twitter.PostUpdate(status.encode('utf-8'))
                    except:
                        logging.error("Failed to sync to Twitter for Topic #" + str(topic.num))
                self.redirect('/t/' + str(topic.num) + '#reply0')
            else:    
                if browser['ios']:
                    path = os.path.join(os.path.dirname(__file__), 'tpl', 'mobile', 'new_topic.html')
                else:
                    path = os.path.join(os.path.dirname(__file__), 'tpl', 'desktop', 'new_topic.html')
                output = template.render(path, template_values)
                self.response.out.write(output)
        else:
            self.redirect('/signin')

class TopicHandler(webapp.RequestHandler):
    def get(self, topic_num):
        browser = detect(self.request)
        self.session = Session()
        template_values = {}
        template_values['rnd'] = random.randrange(1, 100)
        reply_reversed = self.request.get('r')
        if reply_reversed == '1':
            reply_reversed = True
        else:
            reply_reversed = False
        filter_mode = self.request.get('f')
        if filter_mode == '1':
            filter_mode = True
        else:
            filter_mode = False
        template_values['reply_reversed'] = reply_reversed
        template_values['filter_mode'] = filter_mode
        template_values['system_version'] = SYSTEM_VERSION
        errors = 0
        template_values['errors'] = errors
        member = CheckAuth(self)
        template_values['member'] = member
        topic = False
        topic = memcache.get('topic_' + str(topic_num))
        if topic is None:
            q = db.GqlQuery("SELECT * FROM Topic WHERE num = :1", int(topic_num))
            if (q.count() == 1):
                topic = q[0]
                memcache.set('topic_' + str(topic_num), topic, 86400)
        if topic:
            taskqueue.add(url='/hit/topic/' + str(topic.key()))
        template_values['page_title'] = u'V2EX › ' + topic.title
        template_values['topic'] = topic
        if (topic):
            node = False
            section = False
            node = GetKindByNum('Node', topic.node_num)
            if (node):
                if 'recent_nodes' in self.session:
                    recent_nodes = json.loads(self.session['recent_nodes'])
                else:
                    recent_nodes = {}
                recent_nodes[node.name] = node.title
                template_values['recent_nodes'] = recent_nodes
                self.session['recent_nodes'] = json.dumps(recent_nodes)
                section = GetKindByNum('Section', node.section_num)
            template_values['node'] = node
            template_values['section'] = section
            replies = False
            if filter_mode:
                replies = memcache.get('topic_' + str(topic_num) + '_replies_filtered')
                if replies is None:
                    q5 = db.GqlQuery("SELECT * FROM Reply WHERE topic_num = :1 AND member_num = :2 ORDER BY created ASC", topic.num, topic.member.num)
                    replies = q5
                    memcache.set('topic_' + str(topic_num) + '_replies_filtered', replies, 7200)
            else:    
                if reply_reversed:
                    replies = memcache.get('topic_' + str(topic_num) + '_replies_desc')
                    if replies is None:
                        q4 = db.GqlQuery("SELECT * FROM Reply WHERE topic_num = :1 ORDER BY created DESC", topic.num)
                        replies = q4
                        memcache.set('topic_' + str(topic_num) + '_replies_desc', q4, 86400)
                else:
                    replies = memcache.get('topic_' + str(topic_num) + '_replies_asc')
                    if replies is None:
                        q4 = db.GqlQuery("SELECT * FROM Reply WHERE topic_num = :1 ORDER BY created ASC", topic.num)
                        replies = q4
                        memcache.set('topic_' + str(topic_num) + '_replies_asc', q4, 86400)
            template_values['replies'] = replies
            if browser['ios']:
                path = os.path.join(os.path.dirname(__file__), 'tpl', 'mobile', 'topic.html')
            else:
                path = os.path.join(os.path.dirname(__file__), 'tpl', 'desktop', 'topic.html')
        else:
            if browser['ios']:
                path = os.path.join(os.path.dirname(__file__), 'tpl', 'mobile', 'topic_not_found.html')
            else:
                path = os.path.join(os.path.dirname(__file__), 'tpl', 'desktop', 'topic_not_found.html')
        output = template.render(path, template_values)
        self.response.out.write(output)
        
    def post(self, topic_num):
        browser = detect(self.request)
        template_values = {}
        template_values['system_version'] = SYSTEM_VERSION
        member = CheckAuth(self)
        template_values['member'] = member
        if (member):
            topic = False
            q = db.GqlQuery("SELECT * FROM Topic WHERE num = :1", int(topic_num))
            if (q.count() == 1):
                topic = q[0]
                try:
                    topic.hits = topic.hits + 1
                    topic.put()
                except:
                    topic.hits = topic.hits - 1
            template_values['topic'] = topic
            errors = 0
            # Verification: content
            reply_content_error = 0
            reply_content_error_messages = ['',
                u'请输入回复内容',
                u'回复内容长度不能超过 2000 个字符'
            ]
            reply_content = self.request.get('content').strip()
            if (len(reply_content) == 0):
                errors = errors + 1
                reply_content_error = 1
            else:
                if (len(reply_content) > 2000):
                    errors = errors + 1
                    reply_content_error = 2
            template_values['reply_content'] = reply_content
            template_values['reply_content_error'] = reply_content_error
            template_values['reply_content_error_message'] = reply_content_error_messages[reply_content_error]
            template_values['errors'] = errors
            if (topic and (errors == 0)):
                reply = Reply()
                q = db.GqlQuery('SELECT * FROM Counter WHERE name = :1', 'reply.max')
                if (q.count() == 1):
                    counter = q[0]
                    counter.value = counter.value + 1
                else:
                    counter = Counter()
                    counter.name = 'reply.max'
                    counter.value = 1
                q2 = db.GqlQuery('SELECT * FROM Counter WHERE name = :1', 'reply.total')
                if (q2.count() == 1):
                    counter2 = q2[0]
                    counter2.value = counter2.value + 1
                else:
                    counter2 = Counter()
                    counter2.name = 'reply.total'
                    counter2.value = 1
                node = False
                section = False
                if topic:
                    q3 = db.GqlQuery("SELECT * FROM Node WHERE num = :1", topic.node_num)
                    node = q3[0]
                    q4 = db.GqlQuery("SELECT * FROM Section WHERE num = :1", node.section_num)
                    section = q4[0]
                reply.num = counter.value
                reply.content = reply_content
                reply.topic = topic
                reply.topic_num = topic.num
                reply.member = member
                reply.member_num = member.num
                reply.created_by = member.username
                topic.replies = topic.replies + 1
                topic.node_name = node.name
                topic.node_title = node.title
                topic.last_reply_by = member.username
                topic.last_touched = datetime.datetime.now()
                ua = self.request.headers['User-Agent']
                if (re.findall('Mozilla\/5.0 \(iPhone', ua)):
                    reply.source = 'iPhone'
                if (re.findall('Mozilla\/5.0 \(iPod', ua)):
                    reply.source = 'iPod'
                if (re.findall('Mozilla\/5.0 \(iPad', ua)):
                    reply.source = 'iPad'
                if (re.findall('Android', ua)):
                    reply.source = 'Android'
                if (re.findall('Mozilla\/5.0 \(PLAYSTATION 3;', ua)):
                    reply.source = 'PS3'
                reply.put()
                topic.put()
                counter.put()
                counter2.put()
                memcache.set('topic_' + str(topic.num), topic, 86400)
                memcache.delete('topic_' + str(topic.num) + '_replies_desc')
                memcache.delete('topic_' + str(topic.num) + '_replies_asc')
                memcache.delete('topic_' + str(topic_num) + '_replies_filtered')
                taskqueue.add(url='/index/topic/' + str(topic.num))
                # Twitter Sync
                if member.twitter_oauth == 1 and member.twitter_sync == 1:
                    access_token = OAuthToken.from_string(member.twitter_oauth_string)
                    twitter = OAuthApi(CONSUMER_KEY, CONSUMER_SECRET, access_token)
                    link = 'http://' + self.request.headers['Host'] + '/t/' + str(topic.num)
                    link_length = len(link)
                    reply_content_length = len(reply.content)
                    available = 140 - link_length - 1
                    if available > reply_content_length:
                        status = reply.content + ' ' + link
                    else:
                        status = reply.content[0:(available - 4)] + '... ' + link
                    self.response.out.write('Status: ' + status)
                    logging.error('Status: ' + status)
                    try:
                        twitter.PostUpdate(status.encode('utf-8'))
                    except:
                        logging.error("Failed to sync to Twitter for Reply #" + str(reply.num))
                self.redirect('/t/' + str(topic.num) + '#reply' + str(topic.replies))
            else:
                node = False
                section = False
                if topic:
                    q2 = db.GqlQuery("SELECT * FROM Node WHERE num = :1", topic.node_num)
                    node = q2[0]
                    q3 = db.GqlQuery("SELECT * FROM Section WHERE num = :1", node.section_num)
                    section = q3[0]
                template_values['node'] = node
                template_values['section'] = section
                if browser['ios']:
                    path = os.path.join(os.path.dirname(__file__), 'tpl', 'mobile', 'topic.html')
                else:
                    path = os.path.join(os.path.dirname(__file__), 'tpl', 'desktop', 'topic.html')
                output = template.render(path, template_values)
                self.response.out.write(output)
        else:
            self.redirect('/signin')


class TopicEditHandler(webapp.RequestHandler):
    def get(self, topic_num):
        browser = detect(self.request)
        template_values = {}
        template_values['system_version'] = SYSTEM_VERSION
        errors = 0
        template_values['errors'] = errors
        member = CheckAuth(self)
        if (member):
            if (member.num == 1):
                template_values['member'] = member
                topic = False
                q = db.GqlQuery("SELECT * FROM Topic WHERE num = :1", int(topic_num))
                if (q.count() == 1):
                    topic = q[0]
                    try:
                        topic.hits = topic.hits + 1
                        topic.put()
                    except:
                        topic.hits = topic.hits - 1
                template_values['topic'] = topic
                if (topic):
                    template_values['topic_title'] = topic.title
                    template_values['topic_content'] = topic.content
                    node = False
                    section = False
                    if topic:
                        q2 = db.GqlQuery("SELECT * FROM Node WHERE num = :1", topic.node_num)
                        node = q2[0]
                        q3 = db.GqlQuery("SELECT * FROM Section WHERE num = :1", node.section_num)
                        section = q3[0]
                    template_values['node'] = node
                    template_values['section'] = section
                    q4 = db.GqlQuery("SELECT * FROM Reply WHERE topic_num = :1 ORDER BY created ASC", topic.num)
                    template_values['replies'] = q4
                    path = os.path.join(os.path.dirname(__file__), 'tpl', 'mobile', 'edit_topic.html')
                else:
                    path = os.path.join(os.path.dirname(__file__), 'tpl', 'mobile', 'topic_not_found.html')
                output = template.render(path, template_values)
                self.response.out.write(output)
            else:
                self.redirect('/t/' + str(topic_num))
        else:
            self.redirect('/signin')
    
    def post(self, topic_num):
        template_values = {}
        browser = detect(self.request)
        template_values['system_version'] = SYSTEM_VERSION
        member = CheckAuth(self)
        if (member):
            if (member.num == 1):
                template_values['member'] = member
                topic = False
                q = db.GqlQuery("SELECT * FROM Topic WHERE num = :1", int(topic_num))
                if (q.count() == 1):
                    topic = q[0]
                    template_values['topic'] = topic
                if (topic):
                    q2 = db.GqlQuery("SELECT * FROM Node WHERE num = :1", topic.node_num)
                    node = False
                    if (q2.count() == 1):
                        node = q2[0]
                    template_values['node'] = node
                    section = False
                    if node:
                        q3 = db.GqlQuery("SELECT * FROM Section WHERE num = :1", node.section_num)
                        if (q3.count() == 1):
                            section = q3[0]
                    template_values['section'] = section
                    errors = 0
                    # Verification: title
                    topic_title_error = 0
                    topic_title_error_messages = ['',
                        u'请输入主题标题',
                        u'主题标题长度不能超过 120 个字符'
                        ]
                    topic_title = self.request.get('title').strip()
                    if (len(topic_title) == 0):
                        errors = errors + 1
                        topic_title_error = 1
                    else:
                        if (len(topic_title) > 120):
                            errors = errors + 1
                            topic_title_error = 2
                    template_values['topic_title'] = topic_title
                    template_values['topic_title_error'] = topic_title_error
                    template_values['topic_title_error_message'] = topic_title_error_messages[topic_title_error]
                    # Verification: content
                    topic_content_error = 0
                    topic_content_error_messages = ['',
                        u'请输入主题内容',
                        u'主题内容长度不能超过 5000 个字符'
                    ]
                    topic_content = self.request.get('content').strip()
                    if (len(topic_content) == 0):
                        errors = errors + 1
                        topic_content_error = 1
                    else:
                        if (len(topic_content) > 5000):
                            errors = errors + 1
                            topic_content_error = 2
                    template_values['topic_content'] = topic_content
                    template_values['topic_content_error'] = topic_content_error
                    template_values['topic_content_error_message'] = topic_content_error_messages[topic_content_error]
                    template_values['errors'] = errors
                    if (errors == 0):
                        topic.title = topic_title
                        topic.content = topic_content
                        topic.last_touched = datetime.datetime.now()
                        topic.put()
                        self.redirect('/t/' + str(topic.num))
                    else:    
                        path = os.path.join(os.path.dirname(__file__), 'tpl', 'mobile', 'edit_topic.html')
                        output = template.render(path, template_values)
                        self.response.out.write(output)
                else:
                    path = os.path.join(os.path.dirname(__file__), 'tpl', 'mobile', 'topic_not_found.html')
                    output = template.render(path, template_values)
                    self.response.out.write(output)
            else:
                self.redirect('/t/' + str(topic_num))
        else:
            self.redirect('/signin')

class TopicDeleteHandler(webapp.RequestHandler):
    def get(self, topic_num):
        member = CheckAuth(self)
        if member:
            if member.num == 1:
                q = db.GqlQuery("SELECT * FROM Topic WHERE num = :1", int(topic_num))
                if q.count() == 1:
                    topic = q[0]
                    # Take care of Node                
                    node = topic.node
                    node.topics = node.topics - 1
                    node.put()
                    # Take care of Replies
                    q2 = db.GqlQuery("SELECT * FROM Reply WHERE topic_num = :1", int(topic_num))
                    replies_count = q2.count()
                    if replies_count > 0:
                        for reply in q2:
                            reply.delete()
                        q3 = db.GqlQuery('SELECT * FROM Counter WHERE name = :1', 'reply.total')
                        if q3.count() == 1:
                            counter = q3[0]
                            counter.value = counter.value - replies_count
                            counter.put()
                    topic.delete()
                    q4 = db.GqlQuery('SELECT * FROM Counter WHERE name = :1', 'topic.total')
                    if q4.count() == 1:
                        counter2 = q4[0]
                        counter2.value = counter2.value - 1
                        counter2.put()
        self.redirect('/')
                    

class TopicPlainTextHandler(webapp.RequestHandler):
    def get(self, topic_num):
        topic = GetKindByNum('topic', topic_num)
        if topic:
            template_values = {}
            template_values['topic'] = topic
            replies = memcache.get('topic_' + str(topic_num) + '_replies_asc')
            if replies is None:
                q = db.GqlQuery("SELECT * FROM Reply WHERE topic_num = :1 ORDER BY created ASC", topic.num)
                replies = q
                memcache.set('topic_' + str(topic_num) + '_replies_asc', q, 86400)
            if replies:
                template_values['replies'] = replies
            path = os.path.join(os.path.dirname(__file__), 'tpl', 'api', 'topic.txt')
            output = template.render(path, template_values)
            self.response.headers['Content-type'] = 'text/plain;charset=UTF-8'
            self.response.out.write(output)
        else:
            self.error(404)


class TopicIndexHandler(webapp.RequestHandler):
    def post(self, topic_num):
        try:
            if int(os.environ['SERVER_PORT']) == 10000:
                urlfetch.fetch('http://127.0.0.1:20000/index/' + str(topic_num))
            else:
                urlfetch.fetch('http://fts.v2ex.com/index/' + str(topic_num))
        except:
            logging.info('Topic #' + str(topic_num) + ' indexed with minor problem')


class ReplyEditHandler(webapp.RequestHandler):
    def get(self, reply_num):
        member = CheckAuth(self)
        if member:
            if member.num == 1:
                template_values = {}
                template_values['page_title'] = u'V2EX › 编辑回复'
                template_values['member'] = member
                q = db.GqlQuery("SELECT * FROM Reply WHERE num = :1", int(reply_num))
                if q[0]:
                    reply = q[0]
                    topic = reply.topic
                    node = topic.node
                    template_values['reply'] = reply
                    template_values['topic'] = topic
                    template_values['node'] = node
                    template_values['reply_content'] = reply.content
                    path = os.path.join(os.path.dirname(__file__), 'tpl', 'desktop', 'edit_reply.html')
                    output = template.render(path, template_values)
                    self.response.out.write(output)
                else:
                    self.redirect('/')
            else:
                self.redirect('/')
        else:
            self.redirect('/signin')
    
    def post(self, reply_num):
        member = CheckAuth(self)
        if member:
            if member.num == 1:
                template_values = {}
                template_values['page_title'] = u'V2EX › 编辑回复'
                template_values['member'] = member
                q = db.GqlQuery("SELECT * FROM Reply WHERE num = :1", int(reply_num))
                if q[0]:
                    reply = q[0]
                    topic = reply.topic
                    node = topic.node
                    template_values['reply'] = reply
                    template_values['topic'] = topic
                    template_values['node'] = node
                    # Verification: content
                    errors = 0
                    reply_content_error = 0
                    reply_content_error_messages = ['',
                        u'请输入回复内容',
                        u'回复内容长度不能超过 2000 个字符'
                    ]
                    reply_content = self.request.get('content').strip()
                    if (len(reply_content) == 0):
                        errors = errors + 1
                        reply_content_error = 1
                    else:
                        if (len(reply_content) > 2000):
                            errors = errors + 1
                            reply_content_error = 2
                    template_values['reply_content'] = reply_content
                    template_values['reply_content_error'] = reply_content_error
                    template_values['reply_content_error_message'] = reply_content_error_messages[reply_content_error]
                    template_values['errors'] = errors
                    if (errors == 0):
                        reply.content = reply_content
                        reply.put()
                        memcache.delete('topic_' + str(topic.num) + '_replies_asc')
                        memcache.delete('topic_' + str(topic.num) + '_replies_desc')
                        memcache.delete('topic_' + str(topic_num) + '_replies_filtered')
                        self.redirect('/t/' + str(topic.num) + '#reply' + str(topic.replies))
                    else:
                        path = os.path.join(os.path.dirname(__file__), 'tpl', 'desktop', 'edit_reply.html')
                        output = template.render(path, template_values)
                        self.response.out.write(output)
                else:
                    self.redirect('/')
            else:
                self.redirect('/')
        else:
            self.redirect('/signin')
        

class TopicHitHandler(webapp.RequestHandler):
    def post(self, topic_key):
        topic = db.get(db.Key(topic_key))
        if topic:
            topic.hits = topic.hits + 1
            topic.put()

def main():
    application = webapp.WSGIApplication([
    ('/new/(.*)', NewTopicHandler),
    ('/t/([0-9]+)', TopicHandler),
    ('/t/([0-9]+).txt', TopicPlainTextHandler),
    ('/edit/topic/([0-9]+)', TopicEditHandler),
    ('/delete/topic/([0-9]+)', TopicDeleteHandler),
    ('/index/topic/([0-9]+)', TopicIndexHandler),
    ('/edit/reply/([0-9]+)', ReplyEditHandler),
    ('/hit/topic/(.*)', TopicHitHandler)
    ],
                                         debug=True)
    util.run_wsgi_app(application)


if __name__ == '__main__':
    main()