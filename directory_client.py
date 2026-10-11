"""Publish a short-lived LAN address only. Never accepts or uploads an image."""
import ipaddress
import json
import logging
import re
import time
import urllib.request
from urllib.parse import urlsplit

DIRECTORY_USER_AGENT = 'AirBridgeScreenshot/1.0'
EVENTS = logging.getLogger('screenshot_receiver')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class AddressPublisher:
    def __init__(self, config, clock=time.time, sender=None):
        base = config['service_url'].rstrip('/')
        parsed = urlsplit(base)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment or parsed.path):
            raise ValueError('Directory must use an HTTPS origin')
        for key in ('read_key', 'write_key'):
            if not re.fullmatch(r'[0-9a-f]{64}', config[key]):
                raise ValueError('Invalid directory key')
        self.base = base
        self.write_key = config['write_key']
        self.lookup_url = base + '/lookup/' + config['read_key']
        self.clock = clock
        self.sender = sender or self.send
        self.last_record = None
        self.last_success = 0
        self.next_attempt = 0
        self.last_attempt_record = None
        self.ready = False
        self.last_error = None

    @staticmethod
    def send(request):
        opener = urllib.request.build_opener(NoRedirect())
        with opener.open(request, timeout=8) as response:
            if response.status != 200 or response.read(16) != b'ok':
                raise OSError('Directory rejected update')

    def update(self, host, port):
        if host is not None:
            address = ipaddress.IPv4Address(host)
            if not any(address in ipaddress.IPv4Network(net) for net in
                       ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')):
                self.ready = False
                return False
        if port != 8769:
            raise ValueError('Unexpected receiver port')
        record = {'host': host, 'port': port}
        now = self.clock()
        if self.ready and record == self.last_record and 0 <= now-self.last_success < 60:
            return True
        if record == self.last_attempt_record and now < self.next_attempt:
            return False
        self.last_attempt_record = record
        request = urllib.request.Request(self.base + '/address', method='PUT',
            data=json.dumps(record).encode('utf-8'),
            headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + self.write_key,
                     'User-Agent': DIRECTORY_USER_AGENT, 'Accept': 'text/plain'})
        try:
            self.sender(request)
        except Exception as exc:
            # Never log the request URL, keys, or arbitrary exception messages.
            error = (type(exc).__name__, getattr(exc, 'code', None))
            if error != self.last_error:
                EVENTS.warning('Address update failed; error=%s status=%s; retrying', *error)
            self.last_error = error
            self.ready = False
            self.next_attempt = now + 15
            return False
        if not self.ready or record != self.last_record:
            EVENTS.info('Address update succeeded; connected=%s', host is not None)
        self.last_error = None
        self.ready = True
        self.last_record = record
        self.last_success = now
        self.next_attempt = 0
        return True


def load_publisher(path):
    if not path.exists():
        return None
    return AddressPublisher(json.loads(path.read_text(encoding='utf-8')))
