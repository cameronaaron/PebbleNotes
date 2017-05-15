import webapp2
from urllib import urlencode
import json
import urllib2
import random
from google.appengine.api import memcache

from secret import client_id, client_secret
import config


WORDS = (
    'red green blue white brown violet purple black yellow orange '
    'dog cat cow unicorn animal hedgehog chicken '
    'task computer phone watch android robot apple '
    'rambler rogue warrior king '
    'jeans muffin cake bake cookie oven bread '
).split()


def query_json(url, data):
    """
    Query JSON data from Google server using POST request.
    Returns only data and ignores result code.
    """
    if not isinstance(data, str):
        data = urlencode(data)
    try:
        return json.loads(urllib2.urlopen(url, data).read())
    except urllib2.HTTPError as e:  # exception is a file-like object
        return json.loads(e.read())


class AuthRedirect(webapp2.RequestHandler):
    def get(self):
        url = 'https://accounts.google.com/o/oauth2/auth?' + urlencode(dict(
            client_id=client_id,
            redirect_uri=config.auth_redir_uri,
            response_type='code',
            scope='https://www.googleapis.com/auth/tasks',
            state='',
            access_type='offline',
            approval_prompt='force',
            include_granted_scopes='true',
        ))
        self.response.location = url
        self.response.status_int = 302


class AuthCheck(webapp2.RequestHandler):
    def post(self):
        passcode = self.request.POST.get('passcode', '')
        # normalize case and spaces
        passcode = ' '.join(passcode.lower().split())
        tokendata = memcache.get(passcode, namespace='passcode')
        if tokendata:
            memcache.delete(passcode, namespace='passcode')

        self.response.headers['Content-Type'] = \
            "application/json; charset=UTF-8"
        self.response.write(tokendata or '{"error": "Incorrect token"}')


class AuthPoller(webapp2.RequestHandler):
    def get(self):
        args = self.request.GET
        args["client_id"] = client_id
        args["redirect_uri"] = config.auth_redir_uri
        url = "https://accounts.google.com/o/oauth2/auth?"+urlencode(args)
        self.response.location = url
        self.response.status_int = 302


def json_compactify(data):
    return json.dumps(data, separators=(',', ':'))  # compact encoding


class AuthCallback(webapp2.RequestHandler):
    """
    This page is called by Google when user finished auth process.
    It receives state (currently unused), code (if success)
    or error (if failure).
    Then it queries Google for access and refresh tokens
    and passes them in urlencode form
    to intermediate static page, which will show status
    and pass data to js code.
    """
    def get(self):
        #state = self.request.get("state")
        code = self.request.get("code")
        #error = self.request.get("error")
        q = {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": config.auth_redir_uri,
            "grant_type": "authorization_code",
        }
        result = query_json("https://accounts.google.com/o/oauth2/token", q)
        if 'access_token' not in result:
            self.response.write('ERROR: %s' % result)
            return

        passcode = ' '.join(random.sample(WORDS, 4))
        passcode2 = random.randrange(10**4, 10**5)
        data = json_compactify(result)
        for code in (passcode, passcode2):
            memcache.add(code, data, namespace='passcode',
                         time=10*60)  # store for 10 minutes
        self.response.headers['Content-Type'] = 'text/html';
        self.response.write('<h1>Passcode: <tt>{}</tt></h1>'.format(passcode))


class AuthRefresh(webapp2.RequestHandler):
    """
    This page is used by client to refresh their access tokens.
    An access token has lifetime of 1 hour, after that it becomes invalid and
    needs to be refreshed.
    So we receive refresh_token as a parameter
    and return a new access_token with its lifetime as a json result.
    """
    def get(self):
        refresh_token = self.request.get("refresh_token")
        if not refresh_token:
            self.response.status_int = 400
            return
        q = {
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
        }
        result = query_json("https://accounts.google.com/o/oauth2/token", q)
        self.response.headers['Content-Type'] = \
            "application/json; charset=UTF-8"
        self.response.write(json_compactify(result))
        # return result as JSON


application = webapp2.WSGIApplication([
    ('/auth', AuthRedirect),
    ('/auth/check', AuthCheck),
    ('/auth/result', AuthCallback),
    ('/auth/refresh', AuthRefresh),
], debug=True)
