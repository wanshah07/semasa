import importlib.util
from types import SimpleNamespace

from fakestore import FakeStore

from semasa.telegram_bot import INBOX, LINK, webhook_secret


def test_probe_checks_inline_reply_and_reads_back_exact_inbox_row(monkeypatch):
    assert importlib.util.find_spec('semasa.telegram_latency_probe'), 'Missing live latency probe'
    from semasa import telegram_latency_probe as probe
    store = FakeStore(**{LINK:[{'id':1,'telegram_user_id':111,'chat_id':111,'user_id':'u1'}],INBOX:[]})
    calls=[]
    class HTTP:
        def post(self,url,**kw):
            calls.append((url,kw))
            row={**kw['json'],'status':'done','note':'answered (command: menu)'}
            store.tables[INBOX].append(row)
            return SimpleNamespace(status_code=200,json=lambda:{'method':'sendMessage','chat_id':111,'text':'Menu'})
    times=iter([10.0,10.25])
    result=probe.measure(store,'123:private-test-token','https://x.supabase.co','/menu',http=HTTP(),timer=lambda:next(times))
    assert result['inline'] is True
    assert result['elapsed_ms']==250
    assert result['inbox_status']=='done'
    assert result['update_id'] < 0
    assert calls[0][1]['headers']['X-Telegram-Bot-Api-Secret-Token']==webhook_secret('123:private-test-token')
    assert calls[0][1]['headers']['X-Semasa-Probe']=='latency-v1'
    assert 'private-test-token' not in str(result)
