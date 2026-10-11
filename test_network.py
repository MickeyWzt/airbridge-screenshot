"""Exercise real listener transitions without changing the user's Wi-Fi."""
import json
from pathlib import Path
import tempfile
import urllib.request

from receiver import NetworkBinding, ReceiverServer


class Advertisement:
    def __init__(self, host, port, name):
        self.host = host
        self.closed = False

    def close(self):
        self.closed = True


def main():
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    server = ReceiverServer(('127.0.0.1', 0), 'test-token')
    with tempfile.TemporaryDirectory() as folder:
        config = Path(folder) / 'connection.json'
        now = [1000]
        binding = NetworkBinding(server, 'test-device.local', advertiser=Advertisement,
                                 config_path=config, clock=lambda: now[0])
        def health(host):
            with client.open(f'http://{host}:{binding.port}/health', timeout=2) as response:
                return json.load(response)
        try:
            binding.switch('127.0.0.1')
            assert health('127.0.0.1')['ready']
            first_ad = binding.advertisement
            now[0] += 30
            binding.switch('127.0.0.1')
            assert binding.advertisement is first_ad
            now[0] += 3600  # Resume with the same IP after sleeping.
            binding.switch('127.0.0.1')
            assert first_ad.closed and binding.advertisement is not first_ad
            assert binding.server is server and health('127.0.0.1')['ready']
            old_ad = binding.advertisement
            original_queue = server.pending
            server.accepting = False
            binding.switch('127.0.0.2')
            assert old_ad.closed
            assert not health('127.0.0.2')['ready'], 'Pause lost on network change'
            assert binding.server.pending is original_queue, 'Clipboard queue replaced'
            assert json.loads(config.read_text())['host'] == '127.0.0.2'
            assert 'test-device.local' in json.loads(config.read_text())['url']
            try:
                health('127.0.0.1')
                raise AssertionError('Old interface still listening')
            except urllib.error.URLError:
                pass
            binding.switch(None)
            assert binding.server is None and binding.advertisement is None
            server.accepting = True
            binding.switch('127.0.0.1')
            assert health('127.0.0.1')['ready'], 'Did not recover after disconnection'
            assert binding.server.state is server.state
            print('PASS: same-IP discovery rebuilt after resume without restarting HTTP; changed IP; offline/reconnect; pause/queue preserved; stable URL')
        finally:
            binding.unpublish()
            if binding.server:
                binding.server.shutdown()
                binding.server.server_close()


if __name__ == '__main__':
    main()
