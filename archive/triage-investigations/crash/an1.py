import json, collections
R=json.load(open("run1.json")); D={o['key']:o for o in json.load(open("crash_f.json"))}
c=collections.Counter(); per=collections.Counter()
def k(v): return 'CRASH' if str(v).startswith('CRASH') else ('EXC' if str(v).startswith('EXC') else 'ok')
for key,rs in R.items():
    anyb=any(k(r['base'])=='CRASH' for r in rs)
    anyn=any(k(r['noempty'])=='CRASH' for r in rs)
    anyr=any(k(r.get('relate'))=='CRASH' for r in rs)
    per[(D[key]['fn'] in ('ST_Covers','ST_Relate(pattern)'), anyb, anyn, anyr)]+=1
    for r in rs: c[(k(r['base']),k(r['noempty']),k(r.get('relate')) if 'relate' in r else '-')]+=1
print(per); print(c)
print(set(r['base'] for rs in R.values() for r in rs if k(r['base'])!='ok'))
print([ (key,r) for key,rs in R.items() for r in rs if k(r['noempty'])!='ok'][:5])
