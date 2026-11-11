# Puxa a mídia por anúncio × dia de um ciclo encerrado (base do filtro De/Até) e guarda em raw/RGV-xx/meta.json.
# Uso: CICLO="RGV 38" python3 ad_dia_fechado.py   (depois: build.py e retencao_fechado.py do mesmo ciclo)
from comum import *

assert FECHADO, 'use para ciclo fechado (CICLO="RGV xx")'
VID = 'video_p25_watched_actions,video_p50_watched_actions,video_p75_watched_actions,video_p95_watched_actions,video_p100_watched_actions'
M = le('meta.json')


def _linhas():
    # sem filtro (o do Meta descarta campanhas excluídas) e em janelas de 10 dias (o ciclo inteiro estoura o tempo da consulta)
    out, d0 = [], CICLO['ini']
    while d0 <= CICLO['fim']:
        d1 = min(d0 + dt.timedelta(9), CICLO['fim'])
        out += [r for r in meta_all(f'{ACT}/insights', {
            'level': 'ad', 'fields': 'ad_id,campaign_name,spend,impressions,inline_link_clicks,clicks,actions,' + VID,
            'time_range': json.dumps({'since': d0.isoformat(), 'until': d1.isoformat()}), 'time_increment': 1, 'limit': 500})
            if '[FF]' in r['campaign_name']]
        d0 = d1 + dt.timedelta(1)
    return out


M['ad_dia'] = etapa('m_ad_dia.json', _linhas)
salva('meta.json', M)
gasto = sum(float(r['spend']) for r in M['ad_dia']); total = float(M['total'].get('spend', 0))
print(CICLO['nome'], len(M['ad_dia']), 'linhas · gasto por dia', round(gasto), '· investimento do ciclo', round(total),
      'OK' if abs(gasto - total) < 2 else 'DIFERENTE')
