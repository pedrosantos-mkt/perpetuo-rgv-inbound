# Vendas do Perpétuo RGV (Planilha Comercial, aba Vendas: canal Perpétuo + produto RGV, ciclo da coluna K) pelo
# Apps Script da planilha (planilha_vendas.gs, ?p=perpetuo; link no segredo VENDAS_URL). Regrava vendas_rgv.json;
# sem o segredo ou se o script não responder, fica o vendas_rgv.json do repositório (última leitura à mão).
import json, os, datetime as dt, requests
from comum import AQUI, HS_HEAD, req

def so_perpetuo(obs):
    """Coluna L (Obs): vale venda sem observação ou marcada PERPETUO, MQL ou "Verificar" (contam como Perpétuo);
    De Frente e live devolvem 'live' (decide o HubSpot, ver perpetuo_ativo); resgate, outras ações e cancelado ficam fora."""
    import unicodedata
    o = unicodedata.normalize('NFD', obs).encode('ascii', 'ignore').decode().upper().strip()
    if o.startswith('DE FRENTE') or o.startswith('LIVE'): return 'live'
    return not o or o.startswith('PERPETUO') or o.startswith('VERIFICAR') or o == 'MQL'


def perpetuo_ativo(deal_id, dia):
    """Venda de live conta como Perpétuo se a pessoa já tinha oportunidade do Perpétuo ativa, com reunião agendada, ao fechar:
    algum negócio dela (o próprio ou outro) nos pipelines do relatório de MQL, de origem que não seja Live nem as de fora,
    que entrou em DIAG. Agendado (ou depois) até o dia da venda e não estava perdido antes disso.
    Quem se inscreveu na live e fechou sem outra oportunidade ativa é conversão da live."""
    import crm
    H = {**HS_HEAD(), 'Content-Type': 'application/json'}
    rd = lambda ii: req('POST', 'https://api.hubapi.com/crm/v3/objects/deals/batch/read', headers=H, json={
        'inputs': [{'id': i} for i in ii], 'properties': crm.PROPS + ['origem_dos_negocios', 'hs_is_closed_lost', 'closedate']}).get('results', [])
    a = req('POST', 'https://api.hubapi.com/crm/v4/associations/deals/contacts/batch/read', headers=H, json={'inputs': [{'id': deal_id}]})
    cs = [str(t['toObjectId']) for r in a.get('results', []) for t in r['to']]
    ids = {deal_id}
    if cs:
        b = req('POST', 'https://api.hubapi.com/crm/v4/associations/contacts/deals/batch/read', headers=H, json={'inputs': [{'id': c} for c in cs]})
        ids |= {str(t['toObjectId']) for r in b.get('results', []) for t in r['to']}
    for d in rd(sorted(ids)):
        p = d['properties']
        if p['pipeline'] not in (crm.PRINCIPAL, crm.PADRAO, crm.BOLETO): continue
        if (p.get('origem_dos_negocios') or '') in crm.ORIGENS_FORA + ['Live']: continue
        m = crm.datas(p).get('marcado')
        perdido = p.get('hs_is_closed_lost') == 'true' and (p.get('closedate') or '9')[:10] < dia
        if m and m <= dia and not perdido: return True
    return False


url = os.environ.get('VENDAS_URL')
if not url:
    print('sem VENDAS_URL: vendas do vendas_rgv.json do repositório'); raise SystemExit(0)
txt = None
for t in range(3):
    try:
        r = requests.get(url, params={'p': 'perpetuo'}, timeout=60)
        if r.status_code == 200 and '|' in r.text and '<html' not in r.text[:200].lower() and 'RGV' in r.text: txt = r.text; break
        print('planilha respondeu', r.status_code, r.text[:80].replace('\n', ' '))
    except Exception as e: print('planilha:', e)
if not txt:
    print('Apps Script sem a saída do Perpétuo: mantém o vendas_rgv.json do repositório'); raise SystemExit(0)
if txt.split(';')[0].count('|') < 5:   # versão antiga do script, sem a coluna L: não dá para tirar as outras ações
    print('Apps Script sem a coluna L (Obs): mantém o vendas_rgv.json do repositório'); raise SystemExit(0)
vendas = []
for g in filter(None, (x.strip() for x in txt.split(';'))):
    i, n, cent, ciclo, dia, *obs = g.split('|')
    if not ciclo.startswith('RGV'): continue
    data = dt.date(int(dia[6:10]), int(dia[3:5]), int(dia[:2])).isoformat() if len(dia) >= 10 else ''
    ok = so_perpetuo(obs[0] if obs else '')
    if ok == 'live':
        try: ok = bool(i.strip()) and perpetuo_ativo(i.strip(), data or '9999')
        except Exception as e: print('HubSpot', i, e); ok = False
        if ok: print('  live com oportunidade Perpétuo ativa → Perpétuo:', i, n)
    if not ok: continue
    vendas.append({'id': i, 'vendas': int(float(n or 0)), 'valor': int(cent) / 100, 'ciclo': ciclo, 'data': data})
p = os.path.join(AQUI, 'vendas_rgv.json')
fonte = 'Planilha Comercial (1GPPqdff…, aba Vendas): CANAL Perpétuo + PRODUTO RGV, pela coluna CICLO; lida pelo Apps Script da planilha em ' + \
        dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).strftime('%d/%m/%Y %H:%M')
json.dump({'fonte': fonte, 'vendas': vendas}, open(p, 'w'), ensure_ascii=False, indent=1)
por = {}
for v in vendas: por[v['ciclo']] = por.get(v['ciclo'], 0) + v['vendas']
print(len(vendas), 'linhas de venda do Perpétuo RGV ·', ' · '.join(f'{c} {n}' for c, n in sorted(por.items())))
