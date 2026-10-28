import csv, collections, re, json, sys
P=r"C:/Users/Ale/masters/coursework/MCET063 - Tópicos em Testes Automatizados e Verificação de Software (2026-2)/final-project/experiment/runs/e3/triage/findings.csv"
rows=[r for r in csv.DictReader(open(P,encoding='utf-8')) if r['rule']=='crash']
print(len(rows))
print(collections.Counter(r['function'] for r in rows))
print(collections.Counter((r['current'],r['dev'],r['old'],r['shapely'][:40]) for r in rows))
print(collections.Counter(r['sub'] for r in rows).most_common(10))
print(collections.Counter(r['arms'] for r in rows).most_common(10))
def types(w): return tuple(re.findall(r'[A-Z]+(?= ?\(| EMPTY)', w))
c=collections.Counter()
for r in rows:
    e='EMPTY' in r['shrunk_a']+r['shrunk_b']
    c[e]+=1
print(c)
print(any('...' in r['shrunk_a'] or '...' in r['shrunk_b'] for r in rows), sum(r['shrunk_a'].endswith('...') or r['shrunk_b'].endswith('...') for r in rows))
r=rows[0]; print(json.dumps(r,indent=0)[:3000])
