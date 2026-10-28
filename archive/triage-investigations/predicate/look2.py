import csv,sys
rows=list(csv.DictReader(open(sys.argv[1],encoding='utf-8')))
for r in rows:
    if r['rule'] in('R2','R4') or (r['rule']=='R3'):
        a=r['shrunk_a']; b=r['shrunk_b']
        emp = 'EMPTY' in a or 'EMPTY' in b
        if r['rule']=='R3' and emp: continue
        print(r['key'],r['rule'],r['sub'],r['function'],'|',a[:300],'|',b[:300])
