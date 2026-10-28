import json, re, collections, csv
D=json.load(open("crash_f.json"))
P=r"C:/Users/Ale/masters/coursework/MCET063 - Tópicos em Testes Automatizados e Verificação de Software (2026-2)/final-project/experiment/runs/e3/triage/findings.csv"
C={r['key']:r for r in csv.DictReader(open(P,encoding='utf-8'))}
n=0
for o in D:
    r=C[o['key']]
    full_eq = r['shrunk_a'].rstrip('.')==o['a'][:len(r['shrunk_a'].rstrip('.'))] and r['shrunk_b'].rstrip('.')==o['b'][:len(r['shrunk_b'].rstrip('.'))]
    if not full_eq: n+=1
print("csv prefix mismatches", n)
print("csv rows without EMPTY:", sum('EMPTY' not in C[o['key']]['shrunk_a']+C[o['key']]['shrunk_b'] for o in D), "full rows without EMPTY:", sum('EMPTY' not in o['a']+o['b'] for o in D))
# which kind of empty
k=collections.Counter()
for o in D:
    em=re.findall(r'(\w+ EMPTY|\(\s*EMPTY|, EMPTY)', o['a']+' | '+o['b'])
    k[tuple(sorted(set(em)))]+=1
print(k)
print(collections.Counter(o['fa']['emptymember'] or o['fb']['emptymember'] for o in D))
for o in D:
    if o['mag']<1: print(o['key'],o['a'][:200],o['b'][:200]); break
lens=[len(o['a'])+len(o['b']) for o in D]; print(min(lens),max(lens))
