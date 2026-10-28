import sys,json,collections
j=json.load(open(sys.argv[1]+'/findings.json',encoding='utf-8'))
c=collections.Counter()
for e in j['findings']:
    if e['rule'] not in ('R2','R3','R4'): continue
    fam=e['rule']+('-empty' if (e['rule']=='R3' and ('EMPTY' in e['a'] or 'EMPTY' in e['b'])) else '')
    o=e['rerun']['images']['old']
    c[(fam,o['present'],tuple(sorted(o['outcomes'].keys())))]+=1
for k,v in sorted(c.items(),key=str): print(v,k)
