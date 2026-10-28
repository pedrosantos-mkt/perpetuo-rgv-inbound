# Meta Ads: campanhas [FF] do ciclo, métricas do Gerenciador (total, por dia, por público e por criativo), anúncios
import json, collections
from comum import *

INI, FIM = CICLO['ini'].isoformat(), ate().isoformat()
TR = json.dumps({'since': INI, 'until': FIM})
BM = 'spend,impressions,inline_link_clicks,cpm,ctr,inline_link_click_ctr,cost_per_inline_link_click,actions'
filtro = lambda campo, ids: json.dumps([{'field': campo, 'operator': 'IN', 'value': ids}])

# 1. campanhas [FF] com gasto no ciclo
def _camps():
    cs = [c for c in meta_all(f'{ACT}/insights', {'level': 'campaign', 'fields': 'campaign_id,campaign_name,' + BM,
                                                  'time_range': TR, 'limit': 500})
          if '[FF]' in c['campaign_name'] and float(c['spend']) > 0]
    st = meta_all(f'{ACT}/campaigns', {'fields': 'id,effective_status', 'filtering': filtro('id', [c['campaign_id'] for c in cs]), 'limit': 500})
    st = {x['id']: x['effective_status'] for x in st}
    for c in cs: c['status'] = st.get(c['campaign_id'], '')
    return cs
camps = etapa('m_camps.json', _camps)
ids = [c['campaign_id'] for c in camps]
print(len(camps), 'campanhas [FF]', round(sum(float(c['spend']) for c in camps)), 'R$')
fc = filtro('campaign.id', ids)

# 2. conta inteira filtrada pelas campanhas: total e por dia (números do Gerenciador)
total = etapa('m_total.json', lambda: meta_all(f'{ACT}/insights', {'level': 'account', 'fields': BM, 'time_range': TR, 'filtering': fc}))
dia = etapa('m_dia.json', lambda: meta_all(f'{ACT}/insights', {'level': 'account', 'fields': BM, 'time_range': TR, 'filtering': fc,
                                                               'time_increment': 1, 'limit': 500}))

# 3. conjuntos e métricas por público (janela de envolvimento)
adsets = etapa('m_adsets.json', lambda: meta_all(f'{ACT}/insights', {'level': 'adset', 'fields': 'campaign_id,campaign_name,adset_id,adset_name,' + BM,
                                                                    'time_range': TR, 'filtering': fc, 'limit': 500}))
grupos = collections.defaultdict(list)
for a in adsets: grupos[janela(a['adset_name'])].append(a['adset_id'])
def _pub():
    out = {}
    for g, l in grupos.items():
        r = meta_all(f'{ACT}/insights', {'level': 'account', 'fields': BM, 'time_range': TR, 'filtering': filtro('adset.id', l)})
        out[g] = r[0] if r else {}
    return out
pub_bm = etapa('m_pub.json', _pub)
print(len(adsets), 'conjuntos', {g: len(l) for g, l in grupos.items()})

# 4. anúncios com gasto: métricas e dados do criativo (URL, post do Instagram, miniatura), em lotes de 50
ads_ins = etapa('m_ads_ins.json', lambda: meta_all(f'{ACT}/insights', {'level': 'ad', 'fields': 'campaign_id,adset_id,adset_name,ad_id,ad_name,' + BM,
                                                                      'time_range': TR, 'filtering': fc, 'limit': 500}))
def _ads():
    out, l = [], sorted({a['ad_id'] for a in ads_ins})
    for i in range(0, len(l), 50):
        out += meta_all(f'{ACT}/ads', {'fields': 'id,name,adset_id,campaign_id,preview_shareable_link,'
                                                 'creative{instagram_permalink_url,thumbnail_url,object_type,asset_feed_spec{link_urls},'
                                                 'object_story_spec{link_data{link,call_to_action},video_data{call_to_action}}}',
                                       'filtering': filtro('id', l[i:i + 50]), 'limit': 50})
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
        if len(l) == 1:
            out[n] = next(a for a in ads_ins if a['ad_id'] == l[0])
        else:
            r = meta_all(f'{ACT}/insights', {'level': 'account', 'fields': BM, 'time_range': TR, 'filtering': filtro('ad.id', l)})
            out[n] = r[0] if r else {}
    return out
cre_bm = etapa('m_cre.json', _cre)
print(len(cre_bm), 'criativos com métricas do Gerenciador')

salva('meta.json', {'ini': INI, 'fim': FIM, 'camps': camps, 'total': total[0] if total else {}, 'dia': dia,
                    'adsets': adsets, 'pub_bm': pub_bm, 'ads_ins': ads_ins, 'ads': ads, 'cre_bm': cre_bm})
