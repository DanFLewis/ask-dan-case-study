"""Eval runner (sanitized). Talks straight to a local Ollama; no gateway, no keys.
Usage: python run_tests.example.py [model]
Single-turn cases come from tests.example.json, multi-turn from multi_turn.example.json.
A case passes when every `must` regex matches and no `mustnot` regex matches (case-insensitive).
For multi-turn cases the model's real answers are fed back as history; checks apply to the last answer."""
import json, re, sys, urllib.request
MODEL = sys.argv[1] if len(sys.argv) > 1 else 'gemma4:e4b'
fs = open('../example/factsheet.example.md', encoding='utf-8').read()
sp = open('../example/system_prompt.example.txt', encoding='utf-8').read().replace('<<FACTSHEET>>', fs)

def chat(msgs):
    body = {'model': MODEL, 'stream': False, 'think': False, 'keep_alive': '5m',
            'options': {'num_ctx': 8192, 'temperature': 0.1, 'num_predict': 200},
            'messages': [{'role': 'system', 'content': sp}] + msgs}
    r = urllib.request.Request('http://localhost:11434/api/chat', json.dumps(body).encode(), {'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(r, timeout=180))['message']['content'].strip()

def check(a, c):
    return all(re.search(p, a, re.I) for p in c.get('must', [])) and not any(re.search(p, a, re.I) for p in c.get('mustnot', []))

passed = total = 0
for t in json.load(open('tests.example.json', encoding='utf-8')):
    ok = check(chat([{'role': 'user', 'content': t['q']}]), t); passed += ok; total += 1
    print('PASS' if ok else 'FAIL', t['cat'], '|', t['q'][:70])
for c in json.load(open('multi_turn.example.json', encoding='utf-8')):
    msgs = []
    for u in c['turns']:
        msgs.append({'role': 'user', 'content': u}); a = chat(msgs); msgs.append({'role': 'assistant', 'content': a})
    ok = check(a, c); passed += ok; total += 1
    print('PASS' if ok else 'FAIL', 'multi', '|', c['name'])
print(f'{passed}/{total} passed on {MODEL}')
