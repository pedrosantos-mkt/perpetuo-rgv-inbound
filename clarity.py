# Clarity (projeto Método RGV, z18rb8ktfq): sessões, rolagem, tempo ativo e cliques de raiva/mortos/volta rápida por página.
# A API só devolve as últimas 24 h–3 dias e aceita 10 chamadas por dia por projeto (a Central do Grupo R1 usa o mesmo
# projeto), então lê UMA vez por dia as últimas 24 h e guarda no clarity.json do repositório, dia a dia; o painel soma os
# dias do ciclo. As 24 h lidas na 1ª rodada do dia (6h17) entram como o dia anterior.
import json, os, re, datetime as dt, collections, requests
from comum import AQUI, TZ, norm_page

P = os.path.join(AQUI, 'clarity.json')
hist = json.load(open(P)) if os.path.exists(P) else {'obs': 'Clarity por dia (dia = as 24 h lidas na manhã seguinte), por página', 'dias': {}}
dia = (dt.datetime.now(TZ) - dt.timedelta(days=1)).date().isoformat()
tok = os.environ.get('CLARITY_TOKEN') or (open(os.path.expanduser('~/.config/clarity/z18rb8ktfq')).read().strip()
                                          if os.path.exists(os.path.expanduser('~/.config/clarity/z18rb8ktfq')) else '')
if not tok:
    print('sem CLARITY_TOKEN: Clarity fica com os dias já guardados'); raise SystemExit(0)
if dia in hist['dias']:
    print('Clarity de', dia, 'já guardado'); raise SystemExit(0)
r = requests.get('https://www.clarity.ms/export-data/api/v1/project-live-insights', params={'numOfDays': 1, 'dimension1': 'URL'},
                 headers={'Authorization': 'Bearer ' + tok}, timeout=60)
if r.status_code != 200:
    print('Clarity respondeu', r.status_code, r.text[:120]); raise SystemExit(0)
j = {m['metricName']: m['information'] for m in r.json()}
pg = lambda u: norm_page(u)
out = collections.defaultdict(lambda: collections.Counter())
for i in j.get('Traffic', []):
    out[pg(i['Url'])]['sess'] += int(i.get('totalSessionCount') or 0)
# as outras métricas vêm por URL completa (com UTM): ponderadas pelas sessões da própria URL
ses = {i['Url']: int(i.get('totalSessionCount') or 0) for i in j.get('Traffic', [])}
for i in j.get('ScrollDepth', []):
    out[pg(i['Url'])]['rol'] += float(i.get('averageScrollDepth') or 0) * ses.get(i['Url'], 0)
for i in j.get('EngagementTime', []):
    out[pg(i['Url'])]['ativo'] += float(i.get('activeTime') or 0) * ses.get(i['Url'], 0)
for m, k in (('RageClickCount', 'raiva'), ('DeadClickCount', 'morto'), ('QuickbackClick', 'volta')):
    for i in j.get(m, []):
        out[pg(i['Url'])][k] += float(i.get('sessionsWithMetricPercentage') or 0) / 100 * ses.get(i['Url'], 0)
hist['dias'][dia] = {p: {k: round(v, 2) for k, v in c.items()} for p, c in out.items() if c['sess']}
json.dump(hist, open(P, 'w'), ensure_ascii=False, indent=1)
print('Clarity de', dia, '·', len(hist['dias'][dia]), 'páginas ·', sum(c['sess'] for c in hist['dias'][dia].values()), 'sessões')
