#!/usr/bin/python
'''
Script to test race condition on web apps.

Just build request on Burp and use "save item" option to generate a request file.

$ python oportuno request.file

'''

from threading import Condition
from threading import Thread
from base64 import b64decode
from urlparse import urlparse
from xml.dom import minidom
import traceback
import httplib
#httplib.HTTPConnection.debuglevel = 1
import time
import sys
import os
from StringIO import StringIO

console = Condition()

class MyRequest:

    def __init__(self):
        self.raw = None
        self.url = None
        self.parsed = None
        self.method = None
        self.headers = []
        self.body = None

    def __str__(self):
        return str(self.raw)

class MyResponse:

    def __init__(self):
        self.status = None
        self.headers = []
        self.content = None

    def __str__(self):
        return str(self.raw)

class BurpImporter():

    def parse(self, burp_file):
        reqs = []
        xmldom = minidom.parse(burp_file)
        items = xmldom.getElementsByTagName('item')
        for item in items:
            try:
                new_req = MyRequest()
                new_req.raw = b64decode(item.getElementsByTagName('request')[0].childNodes[0].data)
                new_req.url = item.getElementsByTagName('url')[0].childNodes[0].data
                new_req.parsed = urlparse(new_req.url)
                new_req.method = item.getElementsByTagName('method')[0].childNodes[0].data
                new_req.headers, new_req.body = self._parse_raw(new_req.raw)
                
                reqs.append(new_req)

            except:
                print traceback.format_exc()
                continue

        return reqs

    def _parse_raw(self, rawdata):
        headers = []
        body = None
        lines = rawdata.splitlines(True)
        bodyindex = 0
        current = 0
        for line in lines[1:]:
            if line.strip() == '':
                if current + 2 < len(lines):
                    bodyindex = current + 2
                break
            split = line.split(':')
            if len(split) > 2:
                header = split[0]
                value = ':'.join(split[1:])
            else:
                header, value = split
            headers.append([header, value.strip()])
            current += 1
        
        if bodyindex > 0:
            body = ''.join(lines[bodyindex:])

        return headers, body

def do_request(args):

        req = args[0]
        condition = args[1]

        if req.parsed.scheme == 'https':
            c = httplib.HTTPSConnection(req.parsed.hostname, req.parsed.port, timeout=300)
        else:
            c = httplib.HTTPConnection(req.parsed.hostname, req.parsed.port, timeout=300)

        path = '%s?%s' % (req.parsed.path, req.parsed.query)
        c.putrequest(req.method, path, skip_host=True, skip_accept_encoding=True)
        for header, value in req.headers:
            c.putheader(header, value)
        if req.method.lower() == 'get':
            with condition:
                # Wait for notify before sending last request line
                condition.wait()
        # send blank line and body if its a POST
        '''
        From https://github.com/python-git/python/blob/master/Lib/httplib.py#L754
        # If msg and message_body are sent in a single send() call,
        # it will avoid performance problems caused by the interaction
        # between delayed ack and the Nagle algorithim.
        if isinstance(message_body, str):
            msg += message_body
            message_body = None
        self.send(msg)
        if message_body is not None:
            #message_body was not a string (i.e. it is a file) and
            #we must run the risk of Nagle
            self.send(message_body)        
        '''
        c.endheaders()
        if req.body:
            body = StringIO(req.body)
            assert not isinstance(body, str)
            body.seek(0, os.SEEK_END)
            length = body.tell()
            body.seek(0)
            c.send(body.read(length - 3))
            
            body.seek(-3, os.SEEK_END)
            with console:
                print "waiting for go"
            with condition:
                condition.wait()
            c.send(body.read())
            with console:
                print "last byte sent!"
            
        #c.endheaders(body)

        httpresp = c.getresponse()
        resp = MyResponse()
        resp.status = httpresp.status
        resp.headers = dict(httpresp.getheaders())
        resp.content = httpresp.read()

        # process response

        with condition:
            print "%i %s" % (resp.status, resp.headers['date'])


if __name__ == '__main__':

    # import requests
    reqs = BurpImporter().parse(sys.argv[1])
    threads = []
    condition = Condition()
    # create one thread per request
    for req in reqs:
        threads.append(Thread(target=do_request, args=((req, condition),)))
    # start threads
    [thread.start() for thread in threads]
    # wait for threads to send first lines
    print "Waiting for threads..."
    time.sleep(10)
    # finish requests all at once
    print "Notify threads!!"
    with condition:
        condition.notify_all()
    [thread.join() for thread in threads]
    
