"""Read-only command probes: measure the deployed webhook, then verify its exact inbox receipt."""
from __future__ import annotations

import json
import os
import secrets
import time

import requests

from . import db
from .telegram_bot import INBOX, LINK, webhook_secret


def measure(store, token, base_url, command, *, http=None, timer=time.perf_counter):
    if command not in ('/menu', '/status', '/jadual', '/robot', '/bil', '/kesihatan'):
        raise ValueError('Only read-only command probes are allowed')
    rows = store.table(LINK).select('telegram_user_id,chat_id').eq('id', 1).execute().data or []
    if not rows:
        raise ValueError('No linked Telegram owner')
    link = rows[0]
    update_id = -(secrets.randbits(50) + 1)
    update = {'update_id': update_id, 'message': {'message_id': 0, 'date': int(time.time()),
              'chat': {'id': int(link['chat_id']), 'type': 'private'},
              'from': {'id': int(link['telegram_user_id']), 'is_bot': False, 'first_name': 'Semasa probe'},
              'text': command}}
    started = timer()
    response = (http or requests).post(base_url.rstrip('/') + '/functions/v1/semasa-telegram',
        json=update, headers={'X-Telegram-Bot-Api-Secret-Token': webhook_secret(token), 'X-Semasa-Probe': 'latency-v1'},
        timeout=35, allow_redirects=False)
    elapsed_ms = round((timer() - started) * 1000)
    body = response.json()
    saved = store.table(INBOX).select('status,note').eq('update_id', update_id).execute().data or []
    status = saved[0].get('status') if saved else None
    note = saved[0].get('note') if saved else None
    inline = (response.status_code == 200 and body.get('method') == 'sendMessage'
              and body.get('chat_id') == int(link['chat_id']) and status == 'done'
              and note == f"answered (command: {command[1:]})")
    return {'command': command, 'update_id': update_id, 'http_status': response.status_code,
            'elapsed_ms': elapsed_ms, 'response_method': body.get('method'), 'inbox_status': status,
            'inline': inline}


def main():
    try:
        store = db.client()
        results = [measure(store, os.environ['TELEGRAM_BOT_TOKEN'], os.environ['SUPABASE_URL'], command)
                   for command in ('/menu', '/status', '/jadual', '/kesihatan')]
        print('Telegram latency probes: ' + json.dumps(results))
        return 0 if all(row['inline'] for row in results) else 1
    except Exception as exc:
        print('Telegram latency probe failed: ' + type(exc).__name__)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
