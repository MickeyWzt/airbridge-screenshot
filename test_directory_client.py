import json
from directory_client import AddressPublisher


def main():
    requests = []
    now = [1000]
    fail = [False]
    def send(request):
        requests.append(request)
        if fail[0]:
            raise OSError('offline')
    config={'service_url':'https://directory.example', 'read_key':'a'*64, 'write_key':'b'*64}
    publisher=AddressPublisher(config, clock=lambda:now[0], sender=send)
    assert publisher.update('10.1.2.3',8769)
    assert json.loads(requests[-1].data)=={'host':'10.1.2.3','port':8769}
    assert requests[-1].get_header('Authorization')=='Bearer '+'b'*64
    assert requests[-1].get_header('User-agent')=='AirBridgeScreenshot/1.0'
    now[0]+=10
    assert publisher.update('10.1.2.3',8769) and len(requests)==1
    assert publisher.update('192.168.0.105',8769) and len(requests)==2
    now[0]+=60
    assert publisher.update('192.168.0.105',8769) and len(requests)==3
    fail[0]=True
    assert not publisher.update('10.1.2.4',8769)
    count=len(requests)
    assert not publisher.update('10.1.2.4',8769) and len(requests)==count
    now[0]+=16
    fail[0]=False
    assert publisher.update('10.1.2.4',8769)
    assert publisher.update(None,8769)
    assert json.loads(requests[-1].data)['host'] is None
    assert not publisher.update('8.8.8.8',8769)
    assert 'a'*64 in publisher.lookup_url and 'b'*64 not in publisher.lookup_url
    print('PASS: address-only publication; heartbeat; immediate IP updates; offline expiry support; retry backoff; distinct keys')


if __name__=='__main__':
    main()
