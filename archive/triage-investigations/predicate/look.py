import csv,collections,sys
rows=list(csv.DictReader(open(sys.argv[1],encoding='utf-8')))
print(len(rows))
c=collections.Counter((r['rule'],r['sub'],r['function']) for r in rows if r['rule'] in('R2','R3','R4'))
for k,v in sorted(c.items()): print(k,v)
c2=collections.Counter((r['rule'],r['current'],r['dev'],r['old'],r['shapely'],r['draft_class']) for r in rows if r['rule'] in('R2','R3','R4'))
for k,v in sorted(c2.items()): print(k,v)
