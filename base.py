# Base das metas de mídia: CPM, CTR e connect das campanhas [FF] nos 30 dias antes do ciclo (números do Gerenciador)
import json
from comum import *

ini, fim = CICLO['ini'] - dt.timedelta(30), CICLO['ini'] - dt.timedelta(1)
TR = json.dumps({'since': ini.isoformat(), 'until': fim.isoformat()})
todas = [c for c in meta_all(f'{ACT}/insights', {'level': 'campaign', 'fields': 'campaign_id,campaign_name,spend,inline_link_clicks,actions',
                                                  'time_range': TR, 'limit': 500})
         if '[FF]' in c['campaign_name'] and float(c['spend']) > 0]
camps = [c['campaign_id'] for c in todas]
# connect só nas campanhas de página (no Lead Ads o clique abre o formulário, não a página)
pag = [c for c in todas if 'FORMS_NATIVO' not in c['campaign_name']]
lpv_p = sum(float(a['value']) for c in pag for a in c.get('actions', []) if a['action_type'] == 'landing_page_view')
clk_p = sum(int(c.get('inline_link_clicks', 0)) for c in pag)
r = meta_all(f'{ACT}/insights', {'level': 'account', 'time_range': TR,
                                  'fields': 'spend,impressions,inline_link_clicks,cpm,ctr,inline_link_click_ctr,actions',
                                  'filtering': json.dumps([{'field': 'campaign.id', 'operator': 'IN', 'value': camps}])})[0]
lpv = sum(float(a['value']) for a in r.get('actions', []) if a['action_type'] == 'landing_page_view')
base = {'ini': ini.isoformat(), 'fim': fim.isoformat(), 'spend': float(r['spend']), 'cpm': float(r['cpm']),
        'ctr_link': float(r['inline_link_click_ctr']) / 100, 'ctr_all': float(r['ctr']) / 100,
        'connect': lpv_p / clk_p}
salva('base.json', base)
print(base)
