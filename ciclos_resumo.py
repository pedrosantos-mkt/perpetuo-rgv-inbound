# Remonta ciclos.json (tabela "Ciclos anteriores") a partir dos ciclos encerrados em site/c/: investimento Meta (+ Google),
# leads e MQL do HubSpot (todas as origens) e SQL. Rodar depois de refazer os ciclos encerrados.
import json, os
from comum import AQUI, CICLOS, ATUAL, slug

INICIO_FORMS = '2025-07-15'   # primeiro envio dos forms PERPÉTUO no HubSpot
out = []
for nome, ini, fim in CICLOS:
    if nome == ATUAL: continue
    p = os.path.join(AQUI, 'site', 'c', slug(nome) + '.json')
    d = json.load(open(p))
    if nome != 'RGV 45' and not d['ciclo'].get('somado'):   # 29–44 foram coletados com a mídia somada por campanha
        d['ciclo']['somado'] = True
        json.dump(d, open(p, 'w'), ensure_ascii=False, separators=(',', ':'))
    k, g = d['k'], d.get('google') or {}
    out.append({'nome': nome, 'ini': ini, 'fim': fim, 'spend': round(k['spend'], 2), 'imp': k['imp'], 'clk': k['clk'],
                'cpm': d['bm'].get('cpm'), 'ctr_link': d['bm'].get('ctr_link'),
                'lead': k['lead'], 'lead_tot': k['lead'], 'mql': k['mql'], 'sql': k['sql'], 'hubspot': True,
                **({'g_spend': g['spend']} if g.get('spend') and not g.get('sem_gasto') else {}),
                **({'sem_hs': True} if fim < INICIO_FORMS else {'parcial': INICIO_FORMS} if ini < INICIO_FORMS else {})})
    print(nome, round(k['spend']), 'leads', k['lead'], 'MQL', k['mql'], 'SQL', k['sql'])
json.dump({'ciclos': out}, open(os.path.join(AQUI, 'ciclos.json'), 'w'), ensure_ascii=False, indent=1)
