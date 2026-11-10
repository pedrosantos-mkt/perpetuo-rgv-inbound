# Acrescenta a retenção do vídeo (3 s e 25/50/75/95/100%) e "onde rodou" aos criativos de um ciclo já congelado
# (site/c/RGV-xx.json), sem mexer em nenhum outro número. Uso: CICLO="RGV 45" python3 retencao_fechado.py
import collections
from comum import *

assert FECHADO, 'use para ciclo fechado (CICLO="RGV xx")'
VID = ['video_p25_watched_actions', 'video_p50_watched_actions', 'video_p75_watched_actions', 'video_p95_watched_actions', 'video_p100_watched_actions']
arq = os.path.join(AQUI, 'site', 'c', slug(CICLO['nome']) + '.json')
d = json.load(open(arq))

# sem filtro: o filtro do Meta descarta campanhas excluídas (as [FF] saem pelo nome)
def _rows():
    # em janelas de 10 dias: o ciclo inteiro de uma vez estoura o tempo da consulta do Meta (RGV 33)
    out, d0 = [], CICLO['ini']
    while d0 <= CICLO['fim']:
        d1 = min(d0 + dt.timedelta(9), CICLO['fim'])
        out += [r for r in meta_all(f'{ACT}/insights', {
            'level': 'ad', 'fields': 'campaign_name,adset_name,ad_name,spend,actions,' + ','.join(VID),
            'time_range': json.dumps({'since': d0.isoformat(), 'until': d1.isoformat()}), 'limit': 500})
            if '[FF]' in r['campaign_name']]
        d0 = d1 + dt.timedelta(1)
    return out
rows = etapa('m_ret.json', _rows)

ret = collections.defaultdict(collections.Counter); onde = collections.defaultdict(collections.Counter)
for r in rows:
    n = r['ad_name']
    ret[n]['v3s'] += sum(float(a['value']) for a in r.get('actions') or [] if a['action_type'] == 'video_view')
    for q, campo in zip((25, 50, 75, 95, 100), VID):
        ret[n][f'p{q}'] += sum(float(a['value']) for a in r.get(campo) or [])
    onde[n][f"{r['campaign_name']} · {r.get('adset_name', '')}"] += float(r['spend'])

achados = 0
for c in d['criativos']:
    if c['nome'] in ret:
        c.update({k: round(v, 2) for k, v in ret[c['nome']].items()})
        c['onde'] = [x for x, _ in onde[c['nome']].most_common(3)]
        achados += 1
json.dump(d, open(arq, 'w'), ensure_ascii=False, separators=(',', ':'))
print(CICLO['nome'], len(rows), 'anúncios [FF] ·', achados, 'de', len(d['criativos']), 'criativos com retenção ·',
      int(sum(c.get('v3s', 0) for c in d['criativos'])), 'views de 3 s')
