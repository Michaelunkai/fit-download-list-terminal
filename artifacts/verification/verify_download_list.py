
import json, sqlite3, re, os
list_path=r'C:\Users\micha\AppData\Roaming\com.fitlauncher.carrotrub\library\collections\games_to_download.json'
with open(list_path,encoding='utf-8') as f: data=json.load(f)
queries=['pathfinder','Hell is Us','until then','goodnight universe','keeper','Legacy of Kain']
for q in queries:
    hits=[g.get('title','') for g in data if q.lower() in g.get('title','').lower()]
    print(q, len(hits), ' | '.join(hits[:20]))
print('total', len(data))
