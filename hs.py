# HubSpot: envios dos forms PERPÉTUO vindos do Meta pago, 1 lead por e-mail por dia; SQL pelo histórico de fase do negócio
import collections
from concurrent.futures import ThreadPoolExecutor
from comum import *

H = HS_HEAD()
# fases que contam como SQL (contato efetivo / em qualificação em diante, até Ganho)
SQL_FASES = {
    '749390743': {'1089186215', '1320560225', '1089186216', '1089186217', '1089186218', '1089131958', '1089131959',
                  '1089131960', '1089131961', '1089132032', '1089132033', '1121488310', '1089132034', '1089131937'},
    'default': {'64323906', '996296754', 'presentationscheduled', 'decisionmakerboughtin', '65469583', 'contractsent',
                '56883564', '211946083', '69507725', '1029506917', 'closedwon'},
}


def forms():
    out, after = [], None
    while True:
        j = req('GET', 'https://api.hubapi.com/marketing/v3/forms', headers=H, params={'limit': 100, **({'after': after} if after else {})})
        out += j['results']; after = j.get('paging', {}).get('next', {}).get('after')
        if not after: break
    return [f for f in out if 'RGV' in f['name'] and 'PERPETUO' in f['name'].upper()]


def envios(f, desde_ms):
    rows, after = [], None
    while True:
        j = req('GET', f"https://api.hubapi.com/form-integrations/v1/submissions/forms/{f['id']}", headers=H,
                params={'limit': 50, **({'after': after} if after else {})})
        res = j.get('results', [])
        for s in res:
            if s['submittedAt'] < desde_ms: return rows
            rows.append({'form': f['name'], 'ts': s['submittedAt'], 'page': s.get('pageUrl') or '',
                         'v': {x['name']: x['value'] for x in s['values']}})
        after = j.get('paging', {}).get('next', {}).get('after')
        if not after or not res: return rows


def pago_meta(s):
    """Mesma regra do painel de frentes: Lead Ads ou UTM de mídia paga do Facebook/Instagram."""
    v = s['v']
    src = (v.get('utm_source') or '').lower(); med = (v.get('utm_medium') or '').lower(); camp = (v.get('utm_campaign') or '').lower()
    if 'teste-claude' in src: return False
    if 'LEAD ADS' in s['form']: return True
    if 'youtube' in src or '[yt]' in camp or 'linkedin' in src or '[linkedin]' in camp or 'google' in src or '[search]' in camp:
        return False
    return med in ('cpc', 'paid', 'paid_social') or src.startswith('meta_') or (src in ('facebook', 'fb') and med != 'organico')


def mais_100k(fx):
    fx = (fx or '').strip()
    if not fx: return False
    if fx.replace('.', '').isdigit(): return float(fx) >= 100000
    return not (fx.startswith('Menor que 100') or fx.startswith('<'))


# até o RGV 35 o form perguntava o faturamento por ano: conta a partir de R$ 1 milhão/ano (faixa mais próxima de 100 mil/mês)
ANUAL_100K = {'1 a 6 milhões por ano', '6 a 12 milhões por ano', '12 a 36 milhões por ano', '36 a 50 milhões por ano', 'Acima de 50 milhões'}


def q100(v):
    return mais_100k(v.get('annualrevenue')) if v.get('annualrevenue') else v.get('faturamento_anual') in ANUAL_100K


def lotes(l, n):
    for i in range(0, len(l), n): yield l[i:i + n]


def post(url, body):
    return req('POST', url, headers={**H, 'Content-Type': 'application/json'}, json=body)


def main():
    desde = int(dt.datetime.combine(CICLO['ini'], dt.time(), TZ).timestamp() * 1000)
    fim = ate()
    cache = os.path.join(RAW_ATUAL, 'c_subs.json')   # todos os envios desde o RGV 29, baixados por ciclos.py
    if FECHADO and os.path.exists(cache):
        subs = [s for s in json.load(open(cache)) if s['ts'] >= desde]
    else:
        fs = forms()
        with ThreadPoolExecutor(6) as ex:
            subs = [s for rs in ex.map(lambda f: envios(f, desde), fs) for s in rs]
    subs.sort(key=lambda s: s['ts'])
    print(len(subs), 'envios nos forms PERPÉTUO desde', CICLO['ini'])

    leads, vistos = [], set()
    for s in subs:
        d = dt.datetime.fromtimestamp(s['ts'] / 1000, TZ).date()
        if d > fim or d < CICLO['ini']: continue
        email = (s['v'].get('email') or '').strip().lower()
        if not email or (email, d) in vistos or not pago_meta(s): continue
        vistos.add((email, d))
        v = s['v']
        leads.append({'email': email, 'ts': s['ts'], 'dia': d.isoformat(), 'q100': q100(v),
                      'faixa': v.get('annualrevenue') or v.get('faturamento_anual') or '', 'form': s['form'], 'page': s['page'],
                      'camp': v.get('utm_campaign') or '', 'term': v.get('utm_term') or '', 'content': v.get('utm_content') or '',
                      'cargo': v.get('ti__form____cargo') or ''})
    l100 = [l for l in leads if l['q100']]
    print(len(leads), 'leads pagos do Meta ·', len(l100), '+100k')

    # SQL: contato → negócios → histórico de fase
    emails = sorted({l['email'] for l in l100})
    primeiro = {}
    for l in l100: primeiro.setdefault(l['email'], l['ts'])
    cid = {}
    for b in lotes(emails, 100):
        j = post('https://api.hubapi.com/crm/v3/objects/contacts/batch/read',
                 {'idProperty': 'email', 'inputs': [{'id': e} for e in b], 'properties': ['email']})
        for r in j.get('results', []):
            cid[(r['properties'].get('email') or '').lower()] = r['id']
    print(len(cid), 'de', len(emails), 'contatos encontrados')
    deals_de = collections.defaultdict(list)
    ids = list(cid.values())
    for b in lotes(ids, 100):
        j = post('https://api.hubapi.com/crm/v4/associations/contacts/deals/batch/read', {'inputs': [{'id': i} for i in b]})
        for r in j.get('results', []):
            deals_de[r['from']['id']] += [t['toObjectId'] for t in r.get('to', [])]
    todos = sorted({str(d) for l in deals_de.values() for d in l})
    print(len(todos), 'negócios associados')
    hist = {}
    for b in lotes(todos, 50):
        j = post('https://api.hubapi.com/crm/v3/objects/deals/batch/read',
                 {'inputs': [{'id': i} for i in b], 'properties': ['pipeline', 'dealstage', 'createdate'],
                  'propertiesWithHistory': ['dealstage']})
        for r in j.get('results', []):
            hist[r['id']] = {'pipeline': r['properties'].get('pipeline'),
                             'h': [(x['value'], x['timestamp']) for x in r.get('propertiesWithHistory', {}).get('dealstage', [])]}
    sql = set()
    for e, c in cid.items():
        if e not in primeiro: continue   # o HubSpot achou o contato por um e-mail secundário e devolveu o principal
        t0 = primeiro[e] - 864e5
        for d in deals_de.get(c, []):
            h = hist.get(str(d))
            if not h or h['pipeline'] not in SQL_FASES: continue
            for st, ts in h['h']:
                ms = dt.datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp() * 1000
                if st in SQL_FASES[h['pipeline']] and ms >= t0:
                    sql.add(e); break
    print(len(sql), 'SQL entre', len(emails), 'contatos +100k')
    salva('hs.json', {'leads': leads, 'sql': sorted(sql), 'gerado': dt.datetime.now(TZ).strftime('%d/%m/%Y %H:%M')})


if __name__ == '__main__':
    main()
