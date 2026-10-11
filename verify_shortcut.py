"""Maintainer check for the exact six-action, address-free iPad template.

Apple's public share-record endpoint is not a documented product API. Fail
closed if its format changes; the desktop receiver never calls this endpoint.
The downloaded body stays in memory and errors never echo personal addresses.
This is a structural check, not an Apple-device import or sending test.
"""
import argparse
import json
from pathlib import Path
import plistlib
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from pairing_web import shortcut_link


ACTION_IDS = (
    'com.apple.ShortcutsActions.ShowControlCenterAction',
    'is.workflow.actions.delay',
    'is.workflow.actions.takescreenshot',
    'is.workflow.actions.image.convert',
    'is.workflow.actions.url',
    'is.workflow.actions.downloadurl',
)
PARAMETERS = (
    {'operation', 'AppIntentDescriptor'},
    {'WFDelayTime'},
    {'UUID'},
    {'WFImageFormat', 'WFInput', 'UUID'},
    {'WFURLActionURL', 'UUID'},
    {'WFHTTPBodyType', 'ShowHeaders', 'UUID', 'WFRequestVariable', 'WFURL', 'WFHTTPMethod'},
)
METADATA = {
    'WFWorkflowMinimumClientVersionString', 'WFWorkflowMinimumClientVersion',
    'WFWorkflowIcon', 'WFWorkflowClientVersion', 'WFWorkflowOutputContentItemClasses',
    'WFWorkflowHasOutputFallback', 'WFWorkflowActions', 'WFWorkflowInputContentItemClasses',
    'WFWorkflowTypes', 'WFWorkflowImportQuestions', 'WFQuickActionSurfaces',
    'WFWorkflowHasShortcutInputVariables',
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def references(value, expected_uuid):
    """Accept Apple's direct attachment or a text containing exactly one token."""
    if not isinstance(value, dict) or set(value) != {'Value', 'WFSerializationType'}:
        return False
    attachment = value['Value']
    if value['WFSerializationType'] == 'WFTextTokenString':
        if not isinstance(attachment, dict) or set(attachment) != {'string', 'attachmentsByRange'}:
            return False
        if attachment['string'] != '\ufffc':
            return False
        ranges = attachment['attachmentsByRange']
        if not isinstance(ranges, dict) or set(ranges) != {'{0, 1}'}:
            return False
        attachment = ranges['{0, 1}']
    elif value['WFSerializationType'] != 'WFTextTokenAttachment':
        return False
    return (isinstance(attachment, dict)
            and set(attachment) <= {'Type', 'OutputUUID', 'OutputName'}
            and attachment.get('Type') == 'ActionOutput'
            and attachment.get('OutputUUID') == expected_uuid
            and isinstance(attachment.get('OutputName', ''), str))


def validate(workflow):
    require(isinstance(workflow, dict), 'Shortcut body is not a workflow.')
    require(set(workflow) <= METADATA, 'Unreviewed workflow metadata is present.')
    require(not workflow.get('WFWorkflowImportQuestions'), 'This template uses one editable URL; unexpected import questions are present.')
    actions = workflow.get('WFWorkflowActions', [])
    require(isinstance(actions, list) and len(actions) == 6, 'Expected six actions; remove the old address lookup and URL concatenation.')
    require(all(isinstance(a, dict) for a in actions), 'Malformed actions.')
    require(tuple(a.get('WFWorkflowActionIdentifier') for a in actions) == ACTION_IDS, 'Unexpected action sequence.')
    params = []
    for action, allowed in zip(actions, PARAMETERS):
        require(set(action) == {'WFWorkflowActionIdentifier', 'WFWorkflowActionParameters'}, 'Unreviewed action metadata is present.')
        fields = action['WFWorkflowActionParameters']
        require(isinstance(fields, dict) and set(fields) <= allowed, 'Unexpected action settings are present.')
        params.append(fields)
    hide, wait, capture, convert, url, upload = params
    require(hide.get('operation') == 'hide', 'Control Center must be hidden.')
    require(hide.get('AppIntentDescriptor') == {
        'TeamIdentifier': '0000000000', 'BundleIdentifier': 'com.apple.ShortcutsActions',
        'Name': 'ShortcutsActions', 'AppIntentIdentifier': 'ShowControlCenterAction',
    }, 'Unexpected Control Center app intent.')
    require(wait.get('WFDelayTime') == 1, 'Expected a one-second wait.')
    identifiers = [p.get('UUID') for p in (capture, convert, url, upload)]
    require(all(isinstance(v, str) and re.fullmatch(r'[0-9A-Fa-f-]{36}', v) for v in identifiers)
            and len(set(identifiers)) == 4, 'Missing or duplicate action IDs.')
    require(convert.get('WFImageFormat') == 'PNG'
            and references(convert.get('WFInput'), capture['UUID']), 'PNG conversion must use the screenshot output.')
    require(url.get('WFURLActionURL') == 'SETUP_URL', 'URL must be the plain SETUP_URL placeholder; do not share a personal address.')
    require(upload.get('WFHTTPMethod') == 'POST' and upload.get('WFHTTPBodyType') == 'File', 'Upload must use POST with a File body.')
    require(references(upload.get('WFURL'), url['UUID']), 'Upload URL must reference the only URL action, without extra text.')
    require(references(upload.get('WFRequestVariable'), convert['UUID']), 'Upload File must reference Converted Image.')
    serialized = json.dumps(workflow, ensure_ascii=True)
    require(not re.search(r'https?://|(?:[0-9a-fA-F]{32,})', serialized), 'An embedded address or opaque credential remains.')


def read_url(url, limit):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                body = response.read(limit + 1)
            require(len(body) <= limit, 'Shared template exceeds the expected size limit.')
            return body
        except (urllib.error.URLError, TimeoutError) as error:
            if isinstance(error, urllib.error.HTTPError) and error.code < 500 and error.code not in (408, 429):
                raise
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def fetch_shared(link):
    require(shortcut_link(link) == link, 'Expected an official iCloud Shortcut share link.')
    identifier = link.rsplit('/', 1)[-1]
    record = json.loads(read_url('https://www.icloud.com/shortcuts/api/records/' + identifier, 128 * 1024))
    require(not record.get('deleted'), 'Shared template was deleted.')
    fields = record['fields']
    require(fields['signingStatus']['value'] == 'APPROVED', 'Apple has not approved this shared template.')
    asset = fields['shortcut']['value']['downloadURL']
    parsed = urllib.parse.urlparse(asset)
    require(parsed.scheme == 'https' and parsed.hostname is not None
            and parsed.hostname.endswith('.icloud-content.com'), 'Unexpected Apple download host.')
    return plistlib.loads(read_url(asset, 1024 * 1024))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--file', type=Path, help='Plain workflow source, not an Apple-signed container')
    source.add_argument('--link', help='Public iCloud Shortcut link')
    args = parser.parse_args()
    try:
        workflow = fetch_shared(args.link) if args.link else plistlib.loads(args.file.read_bytes())
        validate(workflow)
    except (OSError, ValueError, KeyError, TypeError, plistlib.InvalidFileException) as error:
        # urllib exception strings may contain URLs. Never echo remote bodies.
        detail = str(error) if type(error) is ValueError else type(error).__name__
        parser.exit(1, 'Template check failed: ' + detail + '\n')
    print('PASS: six actions; PNG output wired to POST File; one SETUP_URL; no embedded address or credential. Apple-device testing is still required.')


if __name__ == '__main__':
    main()
