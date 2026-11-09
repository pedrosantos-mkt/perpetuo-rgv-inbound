# Acrescenta o quadro "Origem dos leads" a um ciclo já congelado (site/c/RGV-xx.json) sem mexer nos números dele:
# as linhas pagas saem do próprio arquivo congelado; só as demais origens (orgânico, live, sem UTM) são puxadas agora.
# Uso: CICLO="RGV 45" python3 origens_fechado.py
import collections
from concurrent.futures import ThreadPoolExecutor
from comum import *
import hs

assert FECHADO, 'use para ciclo fechado (CICLO="RGV xx")'
arq = os.path.join(AQUI, 'site', 'c', slug(CICLO['nome']) + '.json')
d = json.load(open(arq)); k = d['k']; g = d.get('google')
pagos = le('hs.json')   # leads pagos congelados (raw/RGV-xx/hs.json)
vistos = {(l['email'], l['dia']) for l in pagos['leads']}
sql_ja = {l['email'] for l in pagos['leads'] if l['q100'] and l['email'] in set(pagos['sql'])}

desde = int(dt.datetime.combine(CICLO['ini'], dt.time(), TZ).timestamp() * 1000)
with ThreadPoolExecutor(6) as ex:
    subs = sorted((s for rs in ex.map(lambda f: hs.envios(f, desde), hs.forms()) for s in rs), key=lambda s: s['ts'])
org = []
for s in subs:
    dd = dt.datetime.fromtimestamp(s['ts'] / 1000, TZ).date()
    if dd > CICLO['fim']: continue
    email = (s['v'].get('email') or '').strip().lower()
    if not email or hs.pago_meta(s) or hs.pago_google(s) or hs.teste(s, email) or (email, dd.isoformat()) in vistos: continue
    vistos.add((email, dd.isoformat()))
    org.append(hs.lead(s, email, dd, 'organico', hs.origem_organica(s)))
sql = hs.sql_de([l for l in org if l['q100']])

ORIG = collections.defaultdict(collections.Counter)
for l in org:
    o = ORIG[l['origem']]
    s = 1 if (l['q100'] and l['email'] in sql and l['email'] not in sql_ja) else 0
    if s: sql_ja.add(l['email'])
    o['lead_tot'] += 1; o['lead'] += l['q100']; o['sql'] += s

nat = next((p for p in d['paginas'] if p['nome'] == 'Formulário nativo (Lead Ads)'), {})
pagas = [{'nome': 'Meta · página', 'pago': True, 'spend': k['pg'].get('spend', 0), 'lead_tot': k['lead_tot_pag'], 'lead': k['lead_pag'],
          'sql': k['sql'] - nat.get('sql', 0)},
         {'nome': 'Meta · Lead Ads', 'pago': True, 'spend': k['nat'].get('spend', 0), 'lead_tot': k['lead_tot'] - k['lead_tot_pag'],
          'lead': k['lead_nativo'], 'sql': nat.get('sql', 0)}]
if g:
    pagas.append({'nome': 'Google Ads', 'pago': True, 'spend': g['spend'], 'lead_tot': g['lead_tot'], 'lead': g['lead'], 'sql': g['sql']})
d['origens'] = pagas + [{'nome': n, 'pago': False, 'spend': 0, **v} for n, v in sorted(ORIG.items(), key=lambda x: -x[1]['lead_tot'])]
d['origens_obs'] = f'outras origens puxadas em {dt.datetime.now(TZ).strftime("%d/%m/%Y")}; mídia paga = números congelados do ciclo'
json.dump(d, open(arq, 'w'), ensure_ascii=False, separators=(',', ':'))
for o in d['origens']: print(o['nome'], o['lead_tot'], o['lead'], o['sql'], round(o['spend']))
