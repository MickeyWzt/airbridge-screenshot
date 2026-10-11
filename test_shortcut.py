"""Prevent personal or incorrectly wired Apple templates entering a release."""
import copy
from pathlib import Path
import plistlib

from verify_shortcut import validate


def main():
    source = Path(__file__).parent / 'shortcuts' / 'AirBridgeScreenshot.unsigned.shortcut'
    template = plistlib.loads(source.read_bytes())
    validate(template)

    def rejected(change):
        candidate = copy.deepcopy(template)
        change(candidate)
        try:
            validate(candidate)
        except ValueError:
            return
        raise AssertionError('Unsafe or broken template was accepted')

    def params(value, index):
        return value['WFWorkflowActions'][index]['WFWorkflowActionParameters']

    rejected(lambda v: params(v, 4).update(WFURLActionURL='http://192.168.1.12:8769/clip/' + 'a' * 32))
    rejected(lambda v: v['WFWorkflowActions'].insert(5, copy.deepcopy(v['WFWorkflowActions'][5])))
    rejected(lambda v: params(v, 5).update(WFHTTPMethod='GET'))
    rejected(lambda v: params(v, 5).update(WFHTTPBodyType='JSON'))
    rejected(lambda v: params(v, 5).update(WFURL=params(v, 3)['WFInput']))
    rejected(lambda v: params(v, 5).update(WFRequestVariable=params(v, 3)['WFInput']))
    rejected(lambda v: params(v, 5).update(WFHTTPHeaders={'Authorization': 'personal credential'}))
    rejected(lambda v: v.update(WFWorkflowComment='https://personal.example/lookup/' + 'b' * 64))

    def concat(value):
        params(value, 5)['WFURL']['Value']['string'] = '\ufffc/clip/extra'

    rejected(concat)
    print('PASS: real plist structure; private URL, old lookup, wrong method/body, broken image/URL wiring, extra headers and concatenation rejected')


if __name__ == '__main__':
    main()
