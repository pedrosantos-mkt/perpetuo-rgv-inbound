# Meta Ads: campanhas [FF] do ciclo, métricas do Gerenciador (total, por dia, por público e por criativo), anúncios
import json, collections
from comum import *

INI, FIM = CICLO['ini'].isoformat(), ate().isoformat()
TR = json.dumps({'since': INI, 'until': FIM})
BM = 'spend,impressions,inline_link_clicks,clicks,cpm,ctr,inline_link_click_ctr,cost_per_inline_link_click,actions'
filtro = lambda campo, ids: json.dumps([{'field': campo, 'operator': 'IN', 'value': ids}])


# Ciclo fechado: o filtro por campanha/conjunto/anúncio do Meta descarta as campanhas excluídas (no RGV 33, R$ 929 mil de
# R$ 1,35 mi). Nesse caso tudo vem sem filtro, no nível de campanha/conjunto/anúncio, e as métricas do grupo saem das somas.
def soma(rows):
    """Agrega linhas de insights como o Gerenciador: soma gasto, impressões, cliques e ações; taxas pelas somas."""
    sp = sum(float(r.get('spend', 0)) for r in rows); im = sum(int(r.get('impressions', 0)) for r in rows)
    lk = sum(int(r.get('inline_link_clicks', 0)) for r in rows); ck = sum(int(r.get('clicks', 0)) for r in rows)
    ac = collections.Counter()
    for r in rows:
        for x in r.get('actions') or []: ac[x['action_type']] += float(x['value'])
    q = lambda a, b, m=1: str(a / b * m) if b else None
    return {'spend': str(sp), 'impressions': str(im), 'inline_link_clicks': str(lk), 'clicks': str(ck),
            'cpm': q(sp, im, 1000), 'ctr': q(ck, im, 100), 'inline_link_click_ctr': q(lk, im, 100),
            'cost_per_inline_link_click': q(sp, lk), 'actions': [{'action_type': k, 'value': str(v)} for k, v in ac.items()]}


def sem_filtro(level, campos, **extra):
    return [r for r in meta_all(f'{ACT}/insights', {'level': level, 'fields': campos + ',campaign_name,' + BM, 'time_range': TR,
                                                    'limit': 500, **extra})
            if '[FF]' in r['campaign_name']]

# 1. campanhas [FF] com gasto no ciclo
def _camps():
    cs = [c for c in meta_all(f'{ACT}/insights', {'level': 'campaign', 'fields': 'campaign_id,campaign_name,' + BM,
                                                  'time_range': TR, 'limit': 500})
          if '[FF]' in c['campaign_name'] and float(c['spend']) > 0]
    st = {} if FECHADO else {x['id']: x['effective_status'] for x in meta_all(
        f'{ACT}/campaigns', {'fields': 'id,effective_status', 'filtering': filtro('id', [c['campaign_id'] for c in cs]), 'limit': 500})}
    for c in cs: c['status'] = st.get(c['campaign_id'], '')
    return cs
camps = etapa('m_camps.json', _camps)
ids = [c['campaign_id'] for c in camps]
print(len(camps), 'campanhas [FF]', round(sum(float(c['spend']) for c in camps)), 'R$')
fc = filtro('campaign.id', ids)

# 2. conta inteira filtrada pelas campanhas: total e por dia (números do Gerenciador)
def _dia_somado():
    g = collections.defaultdict(list)
    for r in sem_filtro('campaign', 'campaign_id', time_increment=1): g[r['date_start']].append(r)
    return [{**soma(v), 'date_start': d, 'date_stop': d} for d, v in sorted(g.items())]
if FECHADO:
    total = etapa('m_total.json', lambda: [soma(camps)])
    dia = etapa('m_dia.json', _dia_somado)
else:
    total = etapa('m_total.json', lambda: meta_all(f'{ACT}/insights', {'level': 'account', 'fields': BM, 'time_range': TR, 'filtering': fc}))
    dia = etapa('m_dia.json', lambda: meta_all(f'{ACT}/insights', {'level': 'account', 'fields': BM, 'time_range': TR, 'filtering': fc,
                                                                   'time_increment': 1, 'limit': 500}))

# 3. conjuntos e métricas por público (janela de envolvimento)
adsets = etapa('m_adsets.json', lambda: sem_filtro('adset', 'campaign_id,adset_id,adset_name') if FECHADO else meta_all(
    f'{ACT}/insights', {'level': 'adset', 'fields': 'campaign_id,campaign_name,adset_id,adset_name,' + BM, 'time_range': TR, 'filtering': fc, 'limit': 500}))
grupos = collections.defaultdict(list)
for a in adsets: grupos[janela(a['adset_name'])].append(a['adset_id'])
def _pub():
    out = {}
    if FECHADO:
        return {g: soma([a for a in adsets if a['adset_id'] in set(l)]) for g, l in grupos.items()}
    for g, l in grupos.items():
        r = meta_all(f'{ACT}/insights', {'level': 'account', 'fields': BM, 'time_range': TR, 'filtering': filtro('adset.id', l)})
        out[g] = r[0] if r else {}
    return out
pub_bm = etapa('m_pub.json', _pub)
print(len(adsets), 'conjuntos', {g: len(l) for g, l in grupos.items()})

# 4. anúncios com gasto: métricas e dados do criativo (URL, post do Instagram, miniatura), em lotes de 50
ads_ins = etapa('m_ads_ins.json', lambda: sem_filtro('ad', 'campaign_id,adset_id,adset_name,ad_id,ad_name') if FECHADO else meta_all(
    f'{ACT}/insights', {'level': 'ad', 'fields': 'campaign_id,adset_id,adset_name,ad_id,ad_name,' + BM, 'time_range': TR, 'filtering': fc, 'limit': 500}))
def _ads():
    out, l = [], sorted({a['ad_id'] for a in ads_ins})
    campos = ('id,name,adset_id,campaign_id,preview_shareable_link,creative{instagram_permalink_url,thumbnail_url,object_type,'
              'asset_feed_spec{link_urls},object_story_spec{link_data{link,call_to_action},video_data{call_to_action}}}')
    n = 10 if FECHADO else 50   # por id, lotes de 50 com o criativo junto dão erro 500
    for i in range(0, len(l), n):
        if FECHADO:   # anúncios excluídos não saem no filtro do /ads; lidos direto pelo id
            try:
                j = req('GET', 'https://graph.facebook.com/v21.0/', tries=3, params={'ids': ','.join(l[i:i + n]), 'fields': campos, 'access_token': META_TOKEN()})
                out += list(j.values())
            except RuntimeError:   # um id inválido derruba o lote: tenta um a um
                for x in l[i:i + n]:
                    try: out.append(req('GET', f'https://graph.facebook.com/v21.0/{x}', tries=2, params={'fields': campos, 'access_token': META_TOKEN()}))
                    except RuntimeError: pass
        else:
            out += meta_all(f'{ACT}/ads', {'fields': campos, 'filtering': filtro('id', l[i:i + n]), 'limit': 50})
    return out
ads = etapa('m_ads.json', _ads)
print(len(ads_ins), 'anúncios com gasto ·', len(ads), 'com dados do criativo')

# 5. métricas do Gerenciador por criativo (mesmo nome em vários conjuntos = uma linha)
por_nome = collections.defaultdict(list); gasto_nome = collections.Counter()
for a in ads_ins:
    por_nome[a['ad_name']].append(a['ad_id']); gasto_nome[a['ad_name']] += float(a['spend'])
def _cre():
    out = {}
    for n, l in por_nome.items():
        if gasto_nome[n] < 150: continue
        if FECHADO:
            out[n] = soma([a for a in ads_ins if a['ad_id'] in set(l)])
        elif len(l) == 1:
            out[n] = next(a for a in ads_ins if a['ad_id'] == l[0])
        else:
            r = meta_all(f'{ACT}/insights', {'level': 'account', 'fields': BM, 'time_range': TR, 'filtering': filtro('ad.id', l)})
            out[n] = r[0] if r else {}
    return out
cre_bm = etapa('m_cre.json', _cre)
print(len(cre_bm), 'criativos com métricas do Gerenciador')

salva('meta.json', {'ini': INI, 'fim': FIM, 'somado': FECHADO, 'camps': camps, 'total': total[0] if total else {}, 'dia': dia,
                    'adsets': adsets, 'pub_bm': pub_bm, 'ads_ins': ads_ins, 'ads': ads, 'cre_bm': cre_bm})
