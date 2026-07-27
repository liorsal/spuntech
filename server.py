#!/usr/bin/env python3
"""שרת האתר של בקרת גליל + צ'אט מעבדה.

הרצה:  python3 server.py [port]
הצ'אט וההערות נשמרים בקובץ chat.json ליד הסקריפט.
כל כתובת IP מקבלת שם חיה אקראי וקבוע. עריכת הערות דורשת סיסמה.
"""
import json
import random
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'chat.json'
LOCK = threading.Lock()

ANIMALS = [
    'אריה', 'נמר', 'פנדה', 'קואלה', 'דולפין', 'ינשוף', 'איילה', 'צבי',
    'ברבור', 'תוכי', 'סנאי', 'ארנב', 'לווייתן', 'פינגווין', "ג'ירפה",
    'זברה', 'יעל', 'דוב', 'בז', 'עיט', 'טווס', 'פלמינגו', 'לביא', 'אלפקה',
    'שועל', 'נשר', 'חתול בר', 'קיפוד', 'חמוס', 'למור', 'טוקן', 'שנונית',
]

NOTES_PASS = '1111'


def load():
    try:
        data = json.loads(DATA.read_text(encoding='utf-8'))
    except Exception:
        data = {}
    data.setdefault('names', {})
    data.setdefault('messages', [])
    data.setdefault('notes', {'text': '', 'by': '', 'time': ''})
    return data


def save(data):
    DATA.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')


def name_for(data, ip):
    if ip in data['names']:
        return data['names'][ip]
    used = set(data['names'].values())
    free = [a for a in ANIMALS if a not in used]
    if free:
        name = random.choice(free)
    else:
        suffix = 2
        while True:
            free = [f'{a} {suffix}' for a in ANIMALS if f'{a} {suffix}' not in used]
            if free:
                name = random.choice(free)
                break
            suffix += 1
    data['names'][ip] = name
    return name


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        if self.path.startswith(('/api/state', '/api/chat')):
            with LOCK:
                data = load()
                me = name_for(data, self.client_address[0])
                save(data)
                messages = data['messages'][-100:]
                notes = data['notes']
            self.send_json({'you': me, 'messages': messages, 'notes': notes})
            return
        if self.path in ('/', '/index.html'):
            self.path = '/main.html'
        super().do_GET()

    def do_POST(self):
        length = int(self.headers.get('Content-Length') or 0)
        try:
            body = json.loads(self.rfile.read(length).decode('utf-8'))
        except Exception:
            body = {}

        if self.path.startswith('/api/notes'):
            if str(body.get('pass', '')) != NOTES_PASS:
                self.send_json({'ok': False, 'error': 'bad password'}, code=403)
                return
            with LOCK:
                data = load()
                me = name_for(data, self.client_address[0])
                data['notes'] = {
                    'text': str(body.get('text', ''))[:4000],
                    'by': me,
                    'time': time.strftime('%H:%M'),
                }
                save(data)
            self.send_json({'ok': True})
            return

        if not self.path.startswith('/api/chat'):
            self.send_error(404)
            return
        text = str(body.get('text', '')).strip()[:500]
        if not text:
            self.send_json({'ok': False}, code=400)
            return
        with LOCK:
            data = load()
            me = name_for(data, self.client_address[0])
            data['messages'].append({
                'name': me,
                'text': text,
                'time': time.strftime('%H:%M'),
            })
            data['messages'] = data['messages'][-200:]
            save(data)
        self.send_json({'ok': True, 'you': me})

    def send_json(self, obj, code=200):
        payload = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(payload)


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f'serving on 0.0.0.0:{port} from {ROOT}')
    ThreadingHTTPServer(('0.0.0.0', port), Handler).serve_forever()
