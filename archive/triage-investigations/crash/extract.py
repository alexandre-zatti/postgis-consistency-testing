import json, re, collections, os
B=r"C:/Users/Ale/masters/coursework/MCET063 - Tópicos em Testes Automatizados e Verificação de Software (2026-2)/final-project/experiment/runs/e3/triage/"
d=json.load(open(B+"findings.json",encoding='utf-8'))
out=[]
for f in d['findings']:
    if f['rule']!='crash': continue
    k=f['key_id']
    rr=json.load(open(B+f"reruns/{k}.json",encoding='utf-8'))
    cur=[p['probe'] for p in rr['images']['current']['probes'] if p['error']=='crash']
    dev=[p['probe'] for p in rr['images']['dev']['probes'] if p['error']=='crash']
    shp=[i for i,c in enumerate(rr['shapely']['calls']) if 'crashed' in c['result']] if rr.get('shapely') else None
    out.append(dict(key=k,fn=f['function'],types=f['types_sig'],a=f['a'],b=f['b'],coord=f['coord'],cur=cur,dev=dev,shp=shp,
                    shpfns=[c['fn'] for c in rr['shapely']['calls']] if rr.get('shapely') else None))
json.dump(out,open("crash.json","w"),indent=1)
print(len(out))
print(collections.Counter(tuple(sorted(set(re.sub(r'ST_\w+\(','F(',p) for p in o['cur']))) for o in out).most_common())
print(collections.Counter(o['types'] for o in out).most_common())
print(collections.Counter(tuple(o['shp'] or []) for o in out).most_common())
