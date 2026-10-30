# Histórico dos ciclos fechados (RGV 29 a 44) com as mesmas regras do painel: investimento [FF] no Meta,
# lead +100k = envio de form PERPÉTUO no HubSpot vindo do Meta pago (1 por e-mail por dia), SQL pelo histórico de fase.
# Roda à mão (ciclo fechado não muda) e grava ciclos.json, que vai no repositório e o build lê.
import collections, sys
from concurrent.futures import ThreadPoolExecutor
from comum import *
import hs

CICLOS = [c for c in CICLOS if c[0] != ATUAL]


def ciclo_de(d):
    s = d.isoformat()
    return next((c for c, a, b in CICLOS if a <= s <= b), None)


# no nível da conta, o filtro (por nome ou por id) perde as campanhas antigas/excluídas: soma direto do nível de campanha.
# CPM e CTR do ciclo saem das somas (gasto ÷ impressões, cliques ÷ impressões), que é como o Gerenciador agrega.
def midia(c, a, b):
    rs = [x for x in meta_all(f'{ACT}/insights', {'level': 'campaign', 'fields': 'campaign_name,spend,impressions,inline_link_clicks',
                                                    'time_range': json.dumps({'since': a, 'until': b}), 'limit': 500})
          if '[FF]' in x['campaign_name']]
    sp = sum(float(x.get('spend', 0)) for x in rs); im = sum(int(x.get('impressions', 0)) for x in rs)
    ck = sum(int(x.get('inline_link_clicks', 0)) for x in rs)
    return c, {'spend': sp, 'impressions': im, 'inline_link_clicks': ck,
               'cpm': sp / im * 1000 if im else None, 'inline_link_click_ctr': ck / im * 100 if im else None}


INICIO_FORMS = '2025-07-15'   # primeiro envio dos forms PERPÉTUO no HubSpot



def main():
    with ThreadPoolExecutor(4) as ex:
        med = dict(ex.map(lambda x: midia(*x), CICLOS))
    print('mídia ok')

    desde = int(dt.datetime.combine(dt.date.fromisoformat(CICLOS[0][1]), dt.time(), TZ).timestamp() * 1000)
    def envios():
        fs = hs.forms()
        with ThreadPoolExecutor(6) as ex:
            return [s for rs in ex.map(lambda f: hs.envios(f, desde), fs) for s in rs]
    subs = etapa('c_subs.json', envios)
    subs.sort(key=lambda s: s['ts'])
    print(len(subs), 'envios desde', CICLOS[0][1])

    leads, vistos, faixas = [], set(), collections.defaultdict(collections.Counter)
    for s in subs:
        d = dt.datetime.fromtimestamp(s['ts'] / 1000, TZ).date(); c = ciclo_de(d)
        email = (s['v'].get('email') or '').strip().lower()
        if not c or not email or (email, d) in vistos or not hs.pago_meta(s): continue
        vistos.add((email, d))
        fx = s['v'].get('annualrevenue') or s['v'].get('faturamento_anual') or ''
        faixas[c][fx] += 1
        leads.append({'c': c, 'email': email, 'ts': s['ts'], 'q100': hs.q100(s['v'])})
    if '-v' in sys.argv:
        tot = collections.Counter()
        for c in faixas: tot.update(faixas[c])
        for fx, n in tot.most_common(): print(f'  {n:6d}  {fx!r}')

    # SQL: uma vez por pessoa em cada ciclo, contando fase atingida depois do primeiro lead +100k dela no ciclo
    l100 = [l for l in leads if l['q100']]
    primeiro = {}
    for l in l100: primeiro.setdefault((l['c'], l['email']), l['ts'])
    emails = sorted({e for _, e in primeiro})
    def contatos():
        cid = {}
        for b in hs.lotes(emails, 100):
            j = hs.post('https://api.hubapi.com/crm/v3/objects/contacts/batch/read',
                        {'idProperty': 'email', 'inputs': [{'id': e} for e in b], 'properties': ['email']})
            for r in j.get('results', []): cid[(r['properties'].get('email') or '').lower()] = r['id']
        return cid
    cid = etapa('c_cid.json', contatos)
    def assoc():
        out = collections.defaultdict(list)
        for b in hs.lotes(list(cid.values()), 100):
            j = hs.post('https://api.hubapi.com/crm/v4/associations/contacts/deals/batch/read', {'inputs': [{'id': i} for i in b]})
            for r in j.get('results', []): out[r['from']['id']] += [t['toObjectId'] for t in r.get('to', [])]
        return out
    deals_de = etapa('c_assoc.json', assoc)
    def historico():
        todos = sorted({str(d) for l in deals_de.values() for d in l}); h = {}
        for b in hs.lotes(todos, 50):
            j = hs.post('https://api.hubapi.com/crm/v3/objects/deals/batch/read',
                        {'inputs': [{'id': i} for i in b], 'properties': ['pipeline', 'dealstage'], 'propertiesWithHistory': ['dealstage']})
            for r in j.get('results', []):
                h[r['id']] = {'pipeline': r['properties'].get('pipeline'),
                              'h': [(x['value'], x['timestamp']) for x in r.get('propertiesWithHistory', {}).get('dealstage', [])]}
        return h
    hist = etapa('c_hist.json', historico)
    print(len(cid), 'contatos ·', len(hist), 'negócios')

    sql = collections.Counter()
    for (c, e), ts0 in primeiro.items():
        t0 = ts0 - 864e5; ok = False
        for d in deals_de.get(cid.get(e), []):
            h = hist.get(str(d))
            if not h or h['pipeline'] not in hs.SQL_FASES: continue
            if any(st in hs.SQL_FASES[h['pipeline']] and dt.datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp() * 1000 >= t0
                   for st, ts in h['h']):
                ok = True; break
        sql[c] += ok

    nl = collections.Counter(l['c'] for l in l100); ntot = collections.Counter(l['c'] for l in leads)
    out = []
    for c, a, b in CICLOS:
        m = med[c]
        out.append({'nome': c, 'ini': a, 'fim': b, 'spend': round(float(m.get('spend', 0)), 2), 'imp': int(m.get('impressions', 0)),
                    'clk': int(m.get('inline_link_clicks', 0)), 'cpm': float(m['cpm']) if m.get('cpm') else None,
                    'ctr_link': float(m['inline_link_click_ctr']) / 100 if m.get('inline_link_click_ctr') else None,
                    'lead_tot': ntot[c], 'lead': nl[c], 'sql': sql[c],
                    # sem_hs: ciclo inteiro antes dos forms; parcial: forms começaram no meio do ciclo
                    **({'sem_hs': True} if b < INICIO_FORMS else {'parcial': INICIO_FORMS} if a < INICIO_FORMS else {})})
        r = out[-1]
        print(f"{c}  {a}→{b}  R$ {r['spend']:>11,.0f}  leads {r['lead_tot']:5d}  +100k {r['lead']:5d}  SQL {r['sql']:4d}")
    json.dump({'gerado': dt.datetime.now(TZ).strftime('%d/%m/%Y %H:%M'), 'ciclos': out},
              open(os.path.join(AQUI, 'ciclos.json'), 'w'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
