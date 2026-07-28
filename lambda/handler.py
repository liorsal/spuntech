"""Chat + notes backend for the Spuntech roll-control app (API Gateway HTTP API)."""
import json
import os
import random
import time

import boto3
from botocore.exceptions import ClientError

TABLE = boto3.resource('dynamodb').Table(os.environ.get('TABLE_NAME', 'spuntech-chat'))
KEY = {'pk': 'state'}
NOTES_PASS = os.environ.get('NOTES_PASS', '1111')
MAX_KEEP = 200

ANIMALS = [
    'אריה', 'נמר', 'פנדה', 'קואלה', 'דולפין', 'ינשוף', 'איילה', 'צבי',
    'ברבור', 'תוכי', 'סנאי', 'ארנב', 'לווייתן', 'פינגווין', "ג'ירפה",
    'זברה', 'יעל', 'דוב', 'בז', 'עיט', 'טווס', 'פלמינגו', 'לביא', 'אלפקה',
    'שועל', 'נשר', 'חתול בר', 'קיפוד', 'חמוס', 'למור', 'טוקן', 'שנונית',
]


def load():
    item = TABLE.get_item(Key=KEY).get('Item') or {}
    return {
        'names': item.get('names') or {},
        'messages': item.get('messages') or [],
        'notes': item.get('notes') or {'text': '', 'by': '', 'time': ''},
        'alert': item.get('alert') or {},
    }


def name_for(data, cid):
    if cid in data['names']:
        return data['names'][cid]
    used = set(data['names'].values())
    pool = [a for a in ANIMALS if a not in used]
    suffix = 2
    while not pool:
        pool = [f'{a} {suffix}' for a in ANIMALS if f'{a} {suffix}' not in used]
        suffix += 1
    name = random.choice(pool)
    try:
        TABLE.update_item(
            Key=KEY,
            UpdateExpression='SET #n.#c = :name',
            ConditionExpression='attribute_not_exists(#n.#c)',
            ExpressionAttributeNames={'#n': 'names', '#c': cid},
            ExpressionAttributeValues={':name': name},
        )
    except ClientError:
        # map missing, or another request claimed this cid first
        TABLE.update_item(
            Key=KEY,
            UpdateExpression='SET #n = if_not_exists(#n, :empty)',
            ExpressionAttributeNames={'#n': 'names'},
            ExpressionAttributeValues={':empty': {}},
        )
        try:
            TABLE.update_item(
                Key=KEY,
                UpdateExpression='SET #n.#c = :name',
                ConditionExpression='attribute_not_exists(#n.#c)',
                ExpressionAttributeNames={'#n': 'names', '#c': cid},
                ExpressionAttributeValues={':name': name},
            )
        except ClientError:
            return load()['names'].get(cid, name)
    data['names'][cid] = name
    return name


def now():
    return time.strftime('%H:%M', time.localtime())


def client_id(event, body):
    cid = (body.get('cid') or '').strip()
    if not cid:
        params = event.get('queryStringParameters') or {}
        cid = (params.get('cid') or '').strip()
    if not cid:
        cid = event.get('requestContext', {}).get('http', {}).get('sourceIp', 'unknown')
    return cid[:64]


def reply(obj, code=200):
    return {
        'statusCode': code,
        'headers': {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'},
        'body': json.dumps(obj, ensure_ascii=False),
    }


def handler(event, context):
    http = event.get('requestContext', {}).get('http', {})
    method = http.get('method', 'GET')
    path = (http.get('path') or '').rstrip('/')
    # the $default route hands CORS preflight to us; API Gateway adds the headers
    if method == 'OPTIONS':
        return {'statusCode': 204, 'body': ''}
    try:
        body = json.loads(event.get('body') or '{}')
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}

    cid = client_id(event, body)
    data = load()
    me = name_for(data, cid)

    if method == 'GET':
        return reply({
            'you': me,
            'messages': data['messages'][-100:],
            'notes': data['notes'],
            'alert': data['alert'],
        })

    if path.endswith('/alert'):
        text = str(body.get('text', '')).strip()[:200]
        if not text:
            return reply({'ok': False}, 400)
        alert = {'id': str(int(time.time() * 1000)), 'text': text, 'by': me, 'time': now(), 'cid': cid}
        TABLE.update_item(
            Key=KEY,
            UpdateExpression='SET #a = :a',
            ExpressionAttributeNames={'#a': 'alert'},
            ExpressionAttributeValues={':a': alert},
        )
        return reply({'ok': True, 'alert': alert})

    if path.endswith('/notes'):
        if str(body.get('pass', '')) != NOTES_PASS:
            return reply({'ok': False, 'error': 'bad password'}, 403)
        notes = {'text': str(body.get('text', ''))[:4000], 'by': me, 'time': now()}
        TABLE.update_item(
            Key=KEY,
            UpdateExpression='SET notes = :n',
            ExpressionAttributeValues={':n': notes},
        )
        return reply({'ok': True})

    text = str(body.get('text', '')).strip()[:500]
    if not text:
        return reply({'ok': False}, 400)
    msg = {'name': me, 'text': text, 'time': now()}
    TABLE.update_item(
        Key=KEY,
        UpdateExpression='SET messages = list_append(if_not_exists(messages, :empty), :m)',
        ExpressionAttributeValues={':empty': [], ':m': [msg]},
    )
    if len(data['messages']) > MAX_KEEP + 50:
        TABLE.update_item(
            Key=KEY,
            UpdateExpression='SET messages = :trim',
            ExpressionAttributeValues={':trim': (data['messages'] + [msg])[-MAX_KEEP:]},
        )
    return reply({'ok': True, 'you': me})
