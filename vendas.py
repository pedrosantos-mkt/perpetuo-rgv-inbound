# Vendas do Perpétuo RGV (Planilha Comercial, aba Vendas: canal Perpétuo + produto RGV, ciclo da coluna K) pelo
# Apps Script da planilha (planilha_vendas.gs, ?p=perpetuo; link no segredo VENDAS_URL). Regrava vendas_rgv.json;
# sem o segredo ou se o script não responder, fica o vendas_rgv.json do repositório (última leitura à mão).
import json, os, datetime as dt, requests
from comum import AQUI

def so_perpetuo(obs):
    """Coluna L (Obs): vale só venda sem observação ou marcada PERPETUO; resgate, De Frente, outras ações, live, MQL,
    cancelado e "verificar" ficam fora (são de outras ações ou não confirmadas)."""
    import unicodedata
    o = unicodedata.normalize('NFD', obs).encode('ascii', 'ignore').decode().upper().strip()
    return not o or o.startswith('PERPETUO')


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
    if not ciclo.startswith('RGV') or not so_perpetuo(obs[0] if obs else ''): continue
    data = dt.date(int(dia[6:10]), int(dia[3:5]), int(dia[:2])).isoformat() if len(dia) >= 10 else ''
    vendas.append({'id': i, 'vendas': int(float(n or 0)), 'valor': int(cent) / 100, 'ciclo': ciclo, 'data': data})
p = os.path.join(AQUI, 'vendas_rgv.json')
fonte = 'Planilha Comercial (1GPPqdff…, aba Vendas): CANAL Perpétuo + PRODUTO RGV, pela coluna CICLO; lida pelo Apps Script da planilha em ' + \
        dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).strftime('%d/%m/%Y %H:%M')
json.dump({'fonte': fonte, 'vendas': vendas}, open(p, 'w'), ensure_ascii=False, indent=1)
por = {}
for v in vendas: por[v['ciclo']] = por.get(v['ciclo'], 0) + v['vendas']
print(len(vendas), 'linhas de venda do Perpétuo RGV ·', ' · '.join(f'{c} {n}' for c, n in sorted(por.items())))
