# Junta Meta (raw/meta.json) + HubSpot (raw/hs.json) + base das metas em data.json
import collections, re, unicodedata
from comum import *

M, HS = le('meta.json'), le('hs.json')
CRM = le('crm.json') if os.path.exists(os.path.join(RAW, 'crm.json')) else {'deals': []}
B = json.load(open(os.path.join(RAW_ATUAL, 'base.json')))   # metas da mídia: sempre as do ciclo atual
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
pub, pag, cre, cmp, onde = (collections.defaultdict(collections.Counter) for _ in range(5))
prev = {}
for a in M['ads_ins']:
    m = midia(a); i = info_ad.get(a['ad_id'], {})
    m['clkp'] = m['clk'] if i.get('page') != NATIVO else 0   # cliques que levam à página (base do connect)
    pub[adset_tag.get(a['adset_id'], 'Outros')] += m
    pag[i.get('page', '(sem URL)')] += m
    cre[a['ad_name']] += m
    # retenção do vídeo (3 s e 25/50/75/95/100%) e onde o criativo rodou (campanha · conjunto), para o detalhe do criativo
    cre[a['ad_name']]['v3s'] += A(a, 'video_view')
    for q in (25, 50, 75, 95, 100):
        cre[a['ad_name']][f'p{q}'] += sum(float(x['value']) for x in a.get(f'video_p{q}_watched_actions') or [])
    onde[a['ad_name']][f"{camp_nome.get(a['campaign_id'], '')} · {a.get('adset_name', '')}"] += float(a['spend'])
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


# Leads e MQL só do HubSpot, de todas as origens:
#   lead = pessoa única que preencheu formulário PERPÉTUO no ciclo (hs.py)
#   MQL  = negócio do relatório "[CICLO] MQL - PERPÉTUO" criado no ciclo; SQL = MQL que chegou em Em Agendamento ou depois (crm.py)
# Cada lead e cada MQL vai para público/página/criativo/campanha pela UTM do formulário; o que não veio de anúncio fica em "sem anúncio".
SEM = 'Sem anúncio (orgânico e outras origens)'
faixas = collections.Counter()
dia_leads = collections.defaultdict(collections.Counter)
# Google Ads (Search e YouTube): gasto lido à mão no google.json; leads e MQL pela UTM do HubSpot
G_CAMP = {}
_gj = json.load(open(os.path.join(AQUI, 'google.json'))) if os.path.exists(os.path.join(AQUI, 'google.json')) else {}
_gc = _gj.get('ciclos', {}).get(CICLO['nome'])
sem_rgv = lambda n: N((n or '').replace('[RGV]', ''))   # a UTM do Google vem sem o [RGV] do nome da campanha
if _gc:
    for c in _gc['campanhas']: G_CAMP[sem_rgv(c['nome'])] = collections.Counter({'spend': c['spend'], 'imp': c['imp'], 'clk': c['clk']})
G, G_NOME = collections.Counter(), {}
ORIG = collections.defaultdict(collections.Counter)   # origem → leads, MQL e SQL


def origem_de(l):
    if l is None: return 'Sem formulário PERPÉTUO'
    if l['canal'] == 'meta': return 'Meta · Lead Ads' if 'LEAD ADS' in l['form'] else 'Meta · página'
    if l['canal'] == 'google': return 'Google Ads'
    return l.get('origem') or 'Outras origens'


def frente(l):
    """Frente e canal (aba MQL diários frentes) de quem não veio de mídia paga, pela UTM do formulário; None = fora das frentes."""
    if l is None or l['canal'] != 'organico' or 'src' not in l: return None
    s, m, c, k, tm = (l.get(x, '').strip().lower() for x in ('src', 'med', 'content', 'camp', 'term'))
    tem = lambda *ws: any(w in x for w in ws for x in (s, m, c))
    if not s and not m: return None
    if 'manychat' in tm or 'manychat' in s or 'manychat' in m: return 'Instagram orgânico|Comentários ManyChat'   # link da DM do ManyChat: utm_term manychat_comentarios
    if 'youtube' in s or s == 'yt':
        return 'YouTube orgânico|' + ('Shorts' if tem('short') else 'Podcast / vlogs' if tem('podcast', 'vlog') else 'Outros do YouTube')
    if tem('whats', 'wpp', 'zap'):
        return 'Bases|' + ('Grupos de WhatsApp' if tem('grupo', 'group', 'comunidade') else 'WhatsApp 1x1')
    if tem('email', 'e-mail', 'hs_automation', 'hubspot', 'newsletter', 'rdstation'): return 'Bases|E-mail'
    if tem('crm', 'disparo', 'sms', 'base'): return 'Bases|Outras bases'
    if tem('manychat'): return 'Instagram orgânico|Comentários ManyChat'
    if s == 'live' or tem('live'): return 'Instagram orgânico|Live'
    if 'lancamento' in k or 'lançamento' in k or tem('lancamento', 'lançamento'): return 'Instagram orgânico|Lançamento'
    if tem('canal', 'transmiss'): return 'Instagram orgânico|Canal de transmissão'
    if tem('grupo_r1', 'grupor1', 'grupo r1'): return 'Instagram orgânico|Grupo R1'
    if s == 'direct' or tem('direct'): return 'Instagram orgânico|Direct'
    if s == 'stories' or tem('stories', 'story'): return 'Instagram orgânico|Stories'
    if s == 'bio' or tem('bio', 'link_in_bio'): return 'Instagram orgânico|Bio'
    if s in ('instagram', 'ig', 'reels', 'feed') or tem('feed', 'reels', 'ricardo', 'instagram'): return 'Instagram orgânico|Feed / Reels'
    return None


def atrib(l):
    """Para onde vai 1 lead ou 1 MQL: origem, públicos (com peso), página, criativo, campanha e campanha do Google."""
    o = origem_de(l)
    if l is None or l['canal'] == 'organico':
        return {'o': o, 't': {SEM: 1.0}, 'p': '(orgânico e outras origens)', 'c': None, 'm': '·' + SEM, 'g': None, **({'f': frente(l)} if frente(l) else {})}
    if l['canal'] == 'google':
        k = sem_rgv(l['camp']) or 'SEMCAMPANHA'
        G_NOME.setdefault(k, l['camp'].strip())
        return {'o': o, 't': {'Google Ads (Search e YouTube)': 1.0}, 'p': 'Google Ads (Search e YouTube)', 'c': None, 'm': None, 'g': k}
    a = atribui(l)
    return {'o': o, 't': {g: round(w, 6) for g, w in a['tags'].items()}, 'p': a['page'], 'c': a['ad'] or '(sem anúncio na UTM)',
            'm': a['camp'] if a['camp'] in cmp else ('·' + a['camp'] if a['camp'] else '·'), 'g': None}


ATTR, ATTR_IX = [], {}   # atribuições únicas: o filtro de datas no navegador refaz os quadros a partir delas
def ix(a):
    k = json.dumps(a, sort_keys=True, ensure_ascii=False)
    if k not in ATTR_IX: ATTR_IX[k] = len(ATTR); ATTR.append(a)
    return ATTR_IX[k]


def soma(a, chave, v=1):
    """Põe 1 lead ou 1 MQL (chave) em todos os quadros, pela atribuição a."""
    ORIG[a['o']][chave] += v
    for g, w in a['t'].items(): pub[g][chave] += v * w
    pag[a['p']][chave] += v
    if a['c']: cre[a['c']][chave] += v
    if a['m']: cmp[a['m']][chave] += v
    if a['g']: G[chave] += v; G_CAMP.setdefault(a['g'], collections.Counter())[chave] += v


DIA_IX = {(CICLO['ini'] + dt.timedelta(i)).isoformat(): i for i in range((CICLO['fim'] - CICLO['ini']).days + 1)}
FAIXAS_IX = {}
GL, GQ = [], []   # granular: [dia, atribuição, faixa, tipo] por lead; [dia, atribuição, sql, contato, marcado, realizado, venda] por MQL
for l in HS['leads']:
    faixas[l['faixa'] or '(sem resposta)'] += 1
    dia_leads[l['dia']]['lead'] += 1
    tipo = 0
    if l['canal'] == 'meta':
        tipo = 2 if 'LEAD ADS' in l['form'] else 1
        dia_leads[l['dia']]['lead_nativo' if tipo == 2 else 'lead_pag'] += 1
    a = atrib(l); soma(a, 'lead')
    GL.append([DIA_IX.get(l['dia'], 0), ix(a), FAIXAS_IX.setdefault(l['faixa'] or '(sem resposta)', len(FAIXAS_IX)), tipo])

# MQL → formulário da pessoa: o último envio até 10 min depois de o negócio nascer (ou o primeiro do ciclo)
env_de = collections.defaultdict(list)
for e in HS.get('envios', HS['leads']): env_de[e['email']].append(e)
for d in CRM['deals']:
    ev = sorted((e for m in d.get('emails', []) for e in env_de.get(m, [])), key=lambda e: e['ts'])
    antes = [e for e in ev if e['ts'] <= d.get('ts', 0) + 600000]
    l = antes[-1] if antes else (ev[0] if ev else None)
    a = atrib(l); soma(a, 'mql')
    if d.get('sql'): soma(a, 'sql')
    dia_leads[d['dia']]['mql'] += 1; dia_leads[d['dia']]['sql'] += bool(d.get('sql'))
    GQ.append([DIA_IX.get(d['dia'], 0), ix(a)] + [int(bool(d.get(e))) for e in ('sql', 'contato', 'marcado', 'realizado', 'venda')])

# vendas (Planilha Comercial, canal Perpétuo + produto RGV): origem pelo formulário da pessoa, como o MQL; dia = data da venda
# (venda com data fora do ciclo entra no dia mais próximo, para o dia a dia fechar no total)
GV = []
ult = max(DIA_IX.values()) if DIA_IX else 0
# venda de ticket alto demora: se o comprador não preencheu formulário no ciclo, procura o formulário PERPÉTUO em todo o
# histórico baixado (raw/c_subs.json desde o RGV 29 + raw/subs_mql.json do último mês)
_hist = None
def hist_de(email):
    global _hist
    if _hist is None:
        import hs
        _hist = collections.defaultdict(list)
        for arq in ('c_subs.json', 'subs_mql.json'):
            p_ = os.path.join(RAW_ATUAL, arq)
            if not os.path.exists(p_): continue
            for s_ in json.load(open(p_)):
                em_ = (s_['v'].get('email') or '').strip().lower()
                if not em_ or hs.teste(s_, em_): continue
                d_ = dt.datetime.fromtimestamp(s_['ts'] / 1000, TZ).date()
                canal = 'meta' if hs.pago_meta(s_) else 'google' if hs.pago_google(s_) else 'organico'
                _hist[em_].append(hs.lead(s_, em_, d_, canal, None if canal != 'organico' else hs.origem_organica(s_)))
    return _hist.get(email, [])
for v in CRM.get('vendas', []):
    ev = sorted((e for m in v.get('emails', []) for e in (env_de.get(m) or hist_de(m))), key=lambda e: e['ts'])
    antes = [e for e in ev if e['ts'] <= (v.get('ts') or 9e15) + 600000]
    l = antes[-1] if antes else (ev[0] if ev else None)
    a = atrib(l); soma(a, 'venda', v['vendas']); soma(a, 'receita', v['valor'])
    di = DIA_IX.get(v['data'], 0 if v['data'] < CICLO['ini'].isoformat() else ult)
    dia_leads[next(k for k, i in DIA_IX.items() if i == di)]['venda'] += v['vendas']
    GV.append([di, ix(a), v['vendas'], v['valor']])

# Google em linha própria nos quadros de público e página, com o gasto lido no google.json
if _gc:
    gs = {'spend': sum(c['spend'] for c in _gc['campanhas']), 'imp': sum(c['imp'] for c in _gc['campanhas']), 'clk': sum(c['clk'] for c in _gc['campanhas'])}
    for q in (pub['Google Ads (Search e YouTube)'], pag['Google Ads (Search e YouTube)']): q.update(gs)

# ---------- totais e dia a dia ----------
T = M['total']; k = midia(T)
fim = dt.date.fromisoformat(M['fim'])
dias = [(CICLO['ini'] + dt.timedelta(i)) for i in range((fim - CICLO['ini']).days + 1)]
dm = {r['date_start']: r for r in M['dia']}
daily = []
for d in dias:
    r = dm.get(d.isoformat(), {}); m = midia(r); L = dia_leads.get(d.isoformat(), {})
    # [dia, investimento, impressões, cliques, visitas, leads, SQL, CPM, CTR link, CTR todos, leads, meta do dia, MQL, vendas]
    daily.append([d.isoformat(), round(m['spend'], 2), m['imp'], m['clk'], m['lpv'], L.get('lead', 0), L.get('sql', 0),
                  f(r, 'cpm'), f(r, 'inline_link_click_ctr', 100), f(r, 'ctr', 100), L.get('lead', 0), meta_do_dia(d), L.get('mql', 0), L.get('venda', 0)])

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
    # o dia de hoje entra parcial: frac = parte do dia já passada na coleta (médias por dia e meta de hoje usam essa fração)
    'parcial': (not FECHADO) and M['fim'] == hoje().isoformat(),
    'hora': dt.datetime.now(TZ).strftime('%Hh%M'),
    'frac': round((dt.datetime.now(TZ).hour * 60 + dt.datetime.now(TZ).minute) / 1440, 4),
    'k': {**limpa(k), 'venda': sum(x[2] for x in GV), 'receita': sum(x[3] for x in GV), 'lead': len(HS['leads']), 'mql': len(CRM['deals']), 'sql': sum(1 for d in CRM['deals'] if d.get('sql')), 'lead_tot': len(HS['leads']),
          'lead_pag': sum(L.get('lead_pag', 0) for L in dia_leads.values()), 'lead_tot_pag': sum(L.get('lead_pag', 0) for L in dia_leads.values()), 'lead_nativo': sum(L.get('lead_nativo', 0) for L in dia_leads.values()),
          'pg': limpa(pg_m), 'nat': limpa(nat_m), 'ativas': sum(1 for c in M['camps'] if c.get('status') == 'ACTIVE')},
    'bm': bm(T),
    'base': B,
    'daily': daily,
    'publicos': [{'nome': n, **limpa(pub[n]), 'bm': bm(M['pub_bm'].get(n))} for n in ORDEM_PUBLICO if n in pub],
    'paginas': sorted([{'nome': n, **limpa(v)} for n, v in pag.items()], key=lambda r: (-r.get('spend', 0), -r.get('lead', 0))),
    'criativos': [{'nome': n, **limpa(v), **prev.get(n, {}), 'bm': bm(M['cre_bm'].get(n)) if n in M['cre_bm'] else None,
                   'onde': [x for x, _ in onde[n].most_common(3)] if n in onde else []}
                  for n, v in cre.items() if v.get('spend', 0) > 0 or v.get('lead', 0) > 0],
    'camps': camps_out,
    'faixas': faixas.most_common(),
    # origem de todos os leads dos forms PERPÉTUO (pago e orgânico); investimento só nas pagas
    'origens': [{'nome': n, 'pago': n.startswith('Meta') or n == 'Google Ads',
                 'spend': round(pg_m['spend'] if n == 'Meta · página' else nat_m['spend'] if n == 'Meta · Lead Ads'
                                else sum(c['spend'] for c in _gc['campanhas']) if n == 'Google Ads' and _gc else 0, 2), **v}
                for n, v in sorted(ORIG.items(), key=lambda x: (['Meta · página', 'Meta · Lead Ads', 'Google Ads'] + [x[0]]).index(x[0]) * 1e6 - x[1]['lead'] - x[1]['mql'])],
    # sem gasto lido no google.json (sem_gasto), os leads do Google entram mesmo assim, para o topo fechar com as origens
    'google': (_gc or G['lead'] or G['mql']) and {'fonte': _gj.get('fonte'), 'sem_gasto': not _gc,
                       'spend': round(sum(c['spend'] for c in _gc['campanhas']), 2) if _gc else 0,
                       'imp': sum(c['imp'] for c in _gc['campanhas']) if _gc else 0, 'clk': sum(c['clk'] for c in _gc['campanhas']) if _gc else 0, **G,
                       'campanhas': sorted(({'nome': next((c['nome'] for c in (_gc or {}).get('campanhas', []) if sem_rgv(c['nome']) == kk), G_NOME.get(kk, kk) if kk != 'SEMCAMPANHA' else 'Sem campanha na UTM'),
                                             'tipo': next((c['tipo'] for c in (_gc or {}).get('campanhas', []) if sem_rgv(c['nome']) == kk), ''), **v}
                                            for kk, v in G_CAMP.items() if v.get('spend') or v.get('lead') or v.get('mql')), key=lambda r: -r.get('spend', 0))} or None,
    # funil comercial (crm.py): MQL e etapas pelos negócios [FF] criados no ciclo; lead no CRM = leads pagos de todas as faixas
    # antes dos forms PERPÉTUO (até o RGV 33) o lead no CRM é o negócio [FF] de qualquer faixa
    'crm': CRM.get('gerado') and {'lead_crm': len(HS['leads']), 'lead_fonte': 'forms', 'gerado': CRM['gerado'],
                                  **{e: sum(1 for x in CRM['deals'] if e == 'mql' or x.get(e)) for e in ('mql', 'contato', 'sql', 'marcado', 'realizado')},
                                  'venda': sum(x[2] for x in GV) if 'vendas' in CRM else sum(1 for x in CRM['deals'] if x.get('venda'))},   # venda = Planilha Comercial
    # vendas da Planilha Comercial com tráfego × orgânico pela UTM (vendas.json, gerado à mão no debriefing-ciclo45/exporta_vendas.py)
    'vendas': (lambda v: v if v and v.get('ciclo') == CICLO['nome'] else None)(
        json.load(open(os.path.join(AQUI, 'vendas.json'))) if os.path.exists(os.path.join(AQUI, 'vendas.json')) else None),
    # ciclos fechados (ciclos.json, gerado à mão por ciclos.py) + o ciclo atual até ontem
    'historico': [] if FECHADO else (json.load(open(os.path.join(AQUI, 'ciclos.json')))['ciclos'] if os.path.exists(os.path.join(AQUI, 'ciclos.json')) else [])
                 + [{'nome': CICLO['nome'], 'ini': CICLO['ini'].isoformat(), 'fim': CICLO['fim'].isoformat(), 'atual': True, 'ate': M['fim'],
                     'spend': round(k['spend'], 2), 'imp': k['imp'], 'clk': k['clk'], 'cpm': bm(T)['cpm'], 'ctr_link': bm(T)['ctr_link'],
                     'lead_tot': len(HS['leads']), 'lead': len(HS['leads']), 'mql': len(CRM['deals']), 'sql': sum(1 for d in CRM['deals'] if d.get('sql')),
                     'hubspot': True, 'venda': sum(x[2] for x in GV), 'receita': sum(x[3] for x in GV), **({'g_spend': round(sum(c['spend'] for c in _gc['campanhas']), 2)} if _gc else {})}],
}
# ---------- dados granulares para o filtro de datas dentro do ciclo ----------
ad_info = {}
for a in M['ads_ins']:
    i = info_ad.get(a['ad_id'], {})
    ad_info.setdefault(a['ad_id'], {'c': a['ad_name'], 't': adset_tag.get(a['adset_id'], 'Outros'), 'p': i.get('page', '(sem URL)'),
                                    'm': camp_nome.get(a['campaign_id'], ''), 'n': int(i.get('page') == NATIVO)})
ADS = sorted(ad_info); AD_IX = {x: n for n, x in enumerate(ADS)}
vid = lambda r, q: sum(float(x['value']) for x in r.get(f'video_p{q}_watched_actions') or [])
MD = [[DIA_IX[r['date_start']], AD_IX[r['ad_id']], round(float(r.get('spend', 0)), 2), int(r.get('impressions', 0)), int(r.get('inline_link_clicks', 0)),
       int(r.get('clicks', 0)), int(A(r, 'landing_page_view')), int(A(r, 'video_view'))] + [int(vid(r, q)) for q in (25, 50, 75, 95, 100)]
      for r in M.get('ad_dia', []) if r.get('ad_id') in AD_IX and r['date_start'] in DIA_IX]
data['gran'] = M.get('ad_dia') and {
    'ads': [ad_info[x] for x in ADS],   # c = criativo, t = público, p = página, m = campanha, n = Lead Ads
    'md': MD,                           # [dia, anúncio, gasto, impressões, cliques no link, cliques, visitas, 3 s, 25, 50, 75, 95, 100%]
    'attr': ATTR, 'leads': GL, 'mql': GQ, 'vendas': GV, 'faixas': list(FAIXAS_IX)}

saida = os.path.join(AQUI, 'site', 'c', slug(CICLO['nome']) + '.json') if FECHADO else os.path.join(AQUI, 'data.json')
os.makedirs(os.path.dirname(saida), exist_ok=True)
json.dump(data, open(saida, 'w'), ensure_ascii=False, separators=(',', ':'))
print('investimento', round(k['spend']), '· leads', data['k']['lead'], '· MQL', data['k']['mql'], '· SQL', data['k']['sql'],
      '· meta ciclo', tot_meta_ciclo, '· até', M['fim'])
for p in data['publicos']: print('  ', p['nome'], round(p.get('spend', 0)), p.get('lead', 0), p.get('mql', 0), p.get('sql', 0))
for p in data['paginas'][:8]: print('  ', p['nome'], round(p.get('spend', 0)), p.get('lead', 0))
