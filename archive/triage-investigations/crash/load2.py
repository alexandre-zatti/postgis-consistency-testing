import json
P=r"C:/Users/Ale/masters/coursework/MCET063 - Tópicos em Testes Automatizados e Verificação de Software (2026-2)/final-project/experiment/runs/e3/triage/findings.json"
d=json.load(open(P,encoding='utf-8'))
print(d.keys())
for k,v in d.items():
    if k!='meta': print(k, type(v), len(v) if hasattr(v,'__len__') else v)
x=[v for v in d.values() if isinstance(v,list)][0][0]
print(json.dumps(x)[:1500])
