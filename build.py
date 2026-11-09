# Junta Meta (raw/meta.json) + HubSpot (raw/hs.json) + base das metas em data.json
import collections, re, unicodedata
from comum import *

M, HS = le('meta.json'), le('hs.json')
B = json.load(open(os.path.join(RAW_ATUAL, 'base.json')))   # metas da mídia: sempre as do ciclo atual
SQL = set(HS['sql'])
NATIVO = 'Formulário nativo (Lead Ads)'

# meta diária de leads +100k do Instagram/Facebook: rampa "Operação 3.000 leads" a partir de 15/10;
# antes disso, o primeiro degrau da rampa (51/dia)
RAMPA_INI = dt.date(2026, 10, 15)
RAMPA = [51, 52, 51, 52, 51, 52, 51, 58, 58, 58, 57, 58, 58, 58, 64, 63, 64, 63, 64, 63, 64, 69, 70, 69, 69, 69, 70, 69, 73, 74, 73]


RAMPA_CICLO = 'RGV 45'   # a rampa "Operação 3.000 leads" é do ciclo 45; ciclo sem rampa fica sem meta de volume


def meta_do_dia(d):
    if FECHADO or CICLO['nome'] != RAMPA_CICLO: return None
    i = (d - RAMPA_INI).days
    return RAMPA[0] if i < 0 else RAMPA[min(i, len(RAMPA) - 1)]


def A(row, t):
    return sum(float(a['value']) for a in row.get('actions') or [] if a['action_type'] == t)


def f(x, k, d=1):
    v = (x or {}).get(k)
    return round(float(v) / d, 6) if v not in (None, '') else None


def bm(x):
    return {'cpm': f(x, 'cpm'), 'ctr_link': f(x, 'inline_link_click_ctr', 100), 'ctr_all': f(x, 'ctr', 100),
            'cpc': f(x, 'cost_per_inline_link_click')}


def midia(x):
    return collections.Counter({'spend': float(x.get('spend', 0)), 'imp': int(x.get('impressions', 0)),
                                'clk': int(x.get('inline_link_clicks', 0)), 'lpv': A(x, 'landing_page_view'),
                                'pix': A(x, 'lead')})


# ---------- anúncios: URL de destino, post do Instagram, miniatura ----------
camp_nome = {c['campaign_id']: c['campaign_name'] for c in M['camps']}
info_ad = {}
for a in M['ads']:
    cr = a.get('creative') or {}
    urls = [u.get('website_url') for u in (cr.get('asset_feed_spec') or {}).get('link_urls', []) if u.get('website_url')]
    oss = cr.get('object_story_spec') or {}
    ld = oss.get('link_data') or {}; vd = oss.get('video_data') or {}
    urls += [ld.get('link'), ((vd.get('call_to_action') or {}).get('value') or {}).get('link')]
    urls = [u for u in urls if u and 'fb.me' not in u and 'facebook.com' not in u]
    nativo = 'FORMS_NATIVO' in camp_nome.get(a['campaign_id'], '') or any(
        ((x.get('call_to_action') or {}).get('value') or {}).get('lead_gen_form_id') for x in (ld, vd))
    info_ad[a['id']] = {'page': NATIVO if nativo else (norm_page(urls[0]) if urls else '(sem URL)'),
                        'prev': cr.get('instagram_permalink_url') or a.get('preview_shareable_link'),
                        'thumb': cr.get('thumbnail_url')}

adset_tag = {a['adset_id']: janela(a['adset_name']) for a in M['adsets']}
# nomes comparados só por letras e números (UTMs chegam com traço, espaço ou colchete diferente)
N = lambda s: re.sub(r'[^0-9A-Z]', '', unicodedata.normalize('NFD', s or '').upper())
nome_ad = {N(n): n for n in [a['name'] for a in M['ads']] + [a['ad_name'] for a in M['ads_ins']]}
nome_adset = {N(a['adset_name']): a['adset_name'] for a in M['adsets']}
nome_camp = {N(c['campaign_name']): c['campaign_name'] for c in M['camps']}
# (campanha, anúncio) → peso de cada público, para a UTM que não traz o conjunto (Lead Ads):
# leads do formulário nativo que o Meta contou em cada conjunto; sem lead no Meta, o gasto
pesos = collections.defaultdict(collections.Counter)
for a in M['ads_ins']:
    pesos[(camp_nome.get(a['campaign_id']), a['ad_name'])][adset_tag.get(a['adset_id'], 'Outros')] += A(a, 'lead') or float(a['spend']) / 1e6

# ---------- mídia por público, página, criativo e campanha ----------
pub, pag, cre, cmp = (collections.defaultdict(collections.Counter) for _ in range(4))
prev = {}
for a in M['ads_ins']:
    m = midia(a); i = info_ad.get(a['ad_id'], {})
    m['clkp'] = m['clk'] if i.get('page') != NATIVO else 0   # cliques que levam à página (base do connect)
    pub[adset_tag.get(a['adset_id'], 'Outros')] += m
    pag[i.get('page', '(sem URL)')] += m
    cre[a['ad_name']] += m
    if a['ad_name'] not in prev and i.get('prev'): prev[a['ad_name']] = {'prev': i['prev'], 'thumb': i.get('thumb')}
for c in M['camps']:
    m = midia(c); m['clkp'] = 0 if 'FORMS_NATIVO' in c['campaign_name'] else m['clk']
    cmp[c['campaign_name']] += m


# ---------- leads do HubSpot ligados a público, página, criativo e campanha ----------
def atribui(l):
    t, c = l['term'].strip(), l['content'].strip()
    ad = next((nome_ad[N(x)] for x in (t, c) if N(x) in nome_ad), None) or next((x for x in (t, c) if x.startswith('[RGV]')), None)
    st = next((nome_adset[N(x)] for x in (t, c) if N(x) in nome_adset), None)
    camp = nome_camp.get(N(l['camp']), l['camp'].strip())
    if st: tags = {janela(st): 1.0}
    else:
        w = pesos.get((camp, ad)) or {}
        tot = sum(w.values())
        tags = {g: v / tot for g, v in w.items()} if tot else {'Sem conjunto na UTM': 1.0}
    page = NATIVO if 'LEAD ADS' in l['form'] else norm_page(l['page'])
    return {'tags': tags, 'page': page, 'ad': ad, 'camp': camp}


faixas = collections.Counter()
dia_leads = collections.defaultdict(collections.Counter)
sql_ja = set()
# Google Ads (Search e YouTube): gasto lido à mão no google.json; leads e SQL pela UTM do HubSpot, fora dos quadros do Meta
G_CAMP = {}
_gj = json.load(open(os.path.join(AQUI, 'google.json'))) if os.path.exists(os.path.join(AQUI, 'google.json')) else {}
_gc = _gj.get('ciclos', {}).get(CICLO['nome'])
sem_rgv = lambda n: N((n or '').replace('[RGV]', ''))   # a UTM do Google vem sem o [RGV] do nome da campanha
if _gc:
    for c in _gc['campanhas']: G_CAMP[sem_rgv(c['nome'])] = collections.Counter({'spend': c['spend'], 'imp': c['imp'], 'clk': c['clk']})
G, G_NOME = collections.Counter(), {}
ORIG = collections.defaultdict(collections.Counter)   # origem do lead → leads (todas as faixas), +100k e SQL
for l in HS['leads']:
    if l.get('canal') == 'organico': continue   # demais origens: segunda passada, depois da mídia paga
    if l.get('canal') == 'google':
        if 'teste' in l['camp'].lower() or 'teste' in l['email']: continue
        s = 1 if (l['q100'] and l['email'] in SQL and l['email'] not in sql_ja) else 0
        if s: sql_ja.add(l['email'])
        alvo = G_CAMP.setdefault(sem_rgv(l['camp']) or 'SEMCAMPANHA', collections.Counter())
        G_NOME.setdefault(sem_rgv(l['camp']) or 'SEMCAMPANHA', l['camp'].strip())
        for c in (G, alvo, ORIG['Google Ads']):
            c['lead_tot'] += 1; c['lead'] += l['q100']; c['sql'] += s
        continue
    o = ORIG['Meta · Lead Ads' if 'LEAD ADS' in l['form'] else 'Meta · página']
    o['lead_tot'] += 1
    dia_leads[l['dia']]['tot'] += 1
    if 'LEAD ADS' not in l['form']: dia_leads[l['dia']]['tot_pag'] += 1   # base da conversão da página (todas as faixas)
    faixas[l['faixa'] or '(sem resposta)'] += 1
    if not l['q100']: continue
    a = atribui(l)
    # SQL conta uma vez por contato, no primeiro lead +100k do ciclo
    s = 1 if (l['email'] in SQL and l['email'] not in sql_ja) else 0
    if s: sql_ja.add(l['email'])
    o['lead'] += 1; o['sql'] += s
    dia_leads[l['dia']]['lead'] += 1; dia_leads[l['dia']]['sql'] += s
    dia_leads[l['dia']]['lead_nativo' if a['page'] == NATIVO else 'lead_pag'] += 1
    for g, w in a['tags'].items():
        pub[g]['lead'] += w; pub[g]['sql'] += s * w
    for bucket, key in ((pag, a['page']), (cre, a['ad'] or '(sem anúncio na UTM)'),
                        (cmp, a['camp'] if a['camp'] in cmp else ('·' + a['camp'] if a['camp'] else '·'))):
        bucket[key]['lead'] += 1; bucket[key]['sql'] += s

for l in HS['leads']:
    if l.get('canal') != 'organico': continue
    o = ORIG[l.get('origem') or 'Outras origens']
    s = 1 if (l['q100'] and l['email'] in SQL and l['email'] not in sql_ja) else 0
    if s: sql_ja.add(l['email'])
    o['lead_tot'] += 1; o['lead'] += l['q100']; o['sql'] += s

# ---------- totais e dia a dia ----------
T = M['total']; k = midia(T)
fim = dt.date.fromisoformat(M['fim'])
dias = [(CICLO['ini'] + dt.timedelta(i)) for i in range((fim - CICLO['ini']).days + 1)]
dm = {r['date_start']: r for r in M['dia']}
daily = []
for d in dias:
    r = dm.get(d.isoformat(), {}); m = midia(r); L = dia_leads.get(d.isoformat(), {})
    daily.append([d.isoformat(), round(m['spend'], 2), m['imp'], m['clk'], m['lpv'], L.get('lead', 0), L.get('sql', 0),
                  f(r, 'cpm'), f(r, 'inline_link_click_ctr', 100), f(r, 'ctr', 100), L.get('tot', 0), meta_do_dia(d)])

# connect e conversão de página só nas campanhas de página (Lead Ads não passa pela página)
pg_m = sum((v for n, v in pag.items() if n != NATIVO), collections.Counter())
nat_m = pag.get(NATIVO, collections.Counter())

limpa = lambda c: {kk: round(vv, 2) for kk, vv in c.items()}
camps_out = []
st = {c['campaign_name']: c.get('status') for c in M['camps']}
for n, v in sorted(cmp.items(), key=lambda x: (-x[1].get('spend', 0), -x[1].get('lead', 0))):
    if n.startswith('·'):
        camps_out.append({'name': n[1:] or None, 'extra': True, **limpa(v)})
    else:
        camps_out.append({'name': n, 'status': st.get(n), **limpa(v)})
tot_meta_ciclo = None if meta_do_dia(CICLO['ini']) is None else sum(meta_do_dia(CICLO['ini'] + dt.timedelta(i)) for i in range((CICLO['fim'] - CICLO['ini']).days + 1))
data = {
    'gerado': dt.datetime.now(TZ).strftime('%d/%m/%Y %H:%M'),
    'ciclo': {'nome': CICLO['nome'], 'fechado': FECHADO, 'somado': bool(M.get('somado')),   # somado: mídia somada por campanha (meta.py em ciclo fechado)
              # forms PERPÉTUO só existem no HubSpot desde 15/07/2025
              'hs_desde': None if CICLO['ini'].isoformat() >= '2025-07-15' else '2025-07-15', 'ini': CICLO['ini'].isoformat(), 'fim': CICLO['fim'].isoformat(),
              'dias': (CICLO['fim'] - CICLO['ini']).days + 1, 'meta_leads': tot_meta_ciclo,
              'meta_dias': [meta_do_dia(CICLO['ini'] + dt.timedelta(i)) for i in range((CICLO['fim'] - CICLO['ini']).days + 1)]},
    'ate': M['fim'],
    'k': {**limpa(k), 'lead': sum(r[5] for r in daily), 'sql': sum(r[6] for r in daily), 'lead_tot': sum(r[10] for r in daily),
          'lead_pag': sum(L.get('lead_pag', 0) for L in dia_leads.values()), 'lead_tot_pag': sum(L.get('tot_pag', 0) for L in dia_leads.values()), 'lead_nativo': sum(L.get('lead_nativo', 0) for L in dia_leads.values()),
          'pg': limpa(pg_m), 'nat': limpa(nat_m), 'ativas': sum(1 for c in M['camps'] if c.get('status') == 'ACTIVE')},
    'bm': bm(T),
    'base': B,
    'daily': daily,
    'publicos': [{'nome': n, **limpa(pub[n]), 'bm': bm(M['pub_bm'].get(n))} for n in ORDEM_PUBLICO if n in pub],
    'paginas': sorted([{'nome': n, **limpa(v)} for n, v in pag.items()], key=lambda r: (-r.get('spend', 0), -r.get('lead', 0))),
    'criativos': [{'nome': n, **limpa(v), **prev.get(n, {}), 'bm': bm(M['cre_bm'].get(n)) if n in M['cre_bm'] else None}
                  for n, v in cre.items() if v.get('spend', 0) > 0 or v.get('lead', 0) > 0],
    'camps': camps_out,
    'faixas': faixas.most_common(),
    # origem de todos os leads dos forms PERPÉTUO (pago e orgânico); investimento só nas pagas
    'origens': [{'nome': n, 'pago': n.startswith('Meta') or n == 'Google Ads',
                 'spend': round(pg_m['spend'] if n == 'Meta · página' else nat_m['spend'] if n == 'Meta · Lead Ads'
                                else sum(c['spend'] for c in _gc['campanhas']) if n == 'Google Ads' and _gc else 0, 2), **v}
                for n, v in sorted(ORIG.items(), key=lambda x: (['Meta · página', 'Meta · Lead Ads', 'Google Ads'] + [x[0]]).index(x[0]) * 1e6 - x[1]['lead_tot'])]
                if any(l.get('canal') == 'organico' for l in HS['leads']) else None,
    # sem gasto lido no google.json (sem_gasto), os leads do Google entram mesmo assim, para o topo fechar com as origens
    'google': (_gc or G['lead_tot']) and {'fonte': _gj.get('fonte'), 'sem_gasto': not _gc,
                       'spend': round(sum(c['spend'] for c in _gc['campanhas']), 2) if _gc else 0,
                       'imp': sum(c['imp'] for c in _gc['campanhas']) if _gc else 0, 'clk': sum(c['clk'] for c in _gc['campanhas']) if _gc else 0, **G,
                       'campanhas': sorted(({'nome': next((c['nome'] for c in (_gc or {}).get('campanhas', []) if sem_rgv(c['nome']) == kk), G_NOME.get(kk, kk) if kk != 'SEMCAMPANHA' else 'Sem campanha na UTM'),
                                             'tipo': next((c['tipo'] for c in (_gc or {}).get('campanhas', []) if sem_rgv(c['nome']) == kk), ''), **v}
                                            for kk, v in G_CAMP.items() if v.get('spend') or v.get('lead_tot')), key=lambda r: -r.get('spend', 0))} or None,
    # funil comercial (crm.py): MQL e etapas pelos negócios [FF] criados no ciclo; lead no CRM = leads pagos de todas as faixas
    # antes dos forms PERPÉTUO (até o RGV 33) o lead no CRM é o negócio [FF] de qualquer faixa
    'crm': (lambda c: c and {'lead_crm': len(c['deals']) if CICLO['ini'].isoformat() < '2025-07-15' else sum(r[10] for r in daily) + G['lead_tot'],
                             'lead_fonte': 'negocios' if CICLO['ini'].isoformat() < '2025-07-15' else 'forms',
                             'leads_meta': round(k['pix']), 'gerado': c['gerado'],
                             **{e: sum(1 for x in c['deals'] if x['mql'] and (e == 'mql' or x[e]))
                                for e in ('mql', 'contato', 'sql', 'marcado', 'realizado', 'venda')}})(
        json.load(open(os.path.join(RAW, 'crm.json'))) if os.path.exists(os.path.join(RAW, 'crm.json')) else None),
    # vendas da Planilha Comercial com tráfego × orgânico pela UTM (vendas.json, gerado à mão no debriefing-ciclo45/exporta_vendas.py)
    'vendas': (lambda v: v if v and v.get('ciclo') == CICLO['nome'] else None)(
        json.load(open(os.path.join(AQUI, 'vendas.json'))) if os.path.exists(os.path.join(AQUI, 'vendas.json')) else None),
    # ciclos fechados (ciclos.json, gerado à mão por ciclos.py) + o ciclo atual até ontem
    'historico': [] if FECHADO else (json.load(open(os.path.join(AQUI, 'ciclos.json')))['ciclos'] if os.path.exists(os.path.join(AQUI, 'ciclos.json')) else [])
                 + [{'nome': CICLO['nome'], 'ini': CICLO['ini'].isoformat(), 'fim': CICLO['fim'].isoformat(), 'atual': True, 'ate': M['fim'],
                     'spend': round(k['spend'], 2), 'imp': k['imp'], 'clk': k['clk'], 'cpm': bm(T)['cpm'], 'ctr_link': bm(T)['ctr_link'],
                     'lead_tot': sum(r[10] for r in daily), 'lead': sum(r[5] for r in daily), 'sql': sum(r[6] for r in daily),
                     **({'g_spend': round(sum(c['spend'] for c in _gc['campanhas']), 2) if _gc else 0, 'g_lead': G['lead'], 'g_sql': G['sql']} if (_gc or G['lead_tot']) else {})}],
}
saida = os.path.join(AQUI, 'site', 'c', slug(CICLO['nome']) + '.json') if FECHADO else os.path.join(AQUI, 'data.json')
os.makedirs(os.path.dirname(saida), exist_ok=True)
json.dump(data, open(saida, 'w'), ensure_ascii=False, separators=(',', ':'))
print('investimento', round(k['spend']), '· leads +100k', data['k']['lead'], '· SQL', data['k']['sql'],
      '· meta ciclo', tot_meta_ciclo, '· até', M['fim'])
for p in data['publicos']: print('  ', p['nome'], round(p.get('spend', 0)), p.get('lead', 0), p.get('sql', 0))
for p in data['paginas'][:8]: print('  ', p['nome'], round(p.get('spend', 0)), p.get('lead', 0))
