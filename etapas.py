# Gasto da conta Perpétuo RGV por etapa do funil (topo, meio e fundo), por dia, em todos os ciclos.
# Classificação pelo nome da campanha:
#   fundo = [FF] · meio = [MF] ou AQUECIMENTO · topo = [TF], ATRAÇÃO ou post impulsionado do Instagram
#   fora  = ações de outros projetos/eventos ([C2G], [MDV], CNE, cadastro de live/evento, venda de rota, live)
# Ciclos fechados ficam guardados em etapas.json; só o ciclo atual é lido de novo a cada rodada.
import collections
from comum import *

FORA = ('[C2G]', '[MDV]', '[CNE]', 'CNE]', '[CADASTRO]', '[VENDA]', '[LIVE]', '[ROTA', 'ROTA_')


def etapa(n):
    u = n.upper()
    if '[FF]' in u: return 2
    if any(x in u for x in FORA): return None
    if '[MF]' in u or 'AQUECIMENTO' in u: return 1
    if '[TF]' in u or 'ATRAÇÃO' in u or 'ATRACAO' in u or re.match(r'(POST DO INSTAGRAM|PUBLICAÇÃO DO INSTAGRAM|INSTAGRAM POST)', u):
        return 0
    return None


def ler(a, b):
    dias = collections.defaultdict(lambda: [0.0, 0.0, 0.0])
    for x in meta_all(f'{ACT}/insights', {'level': 'campaign', 'fields': 'campaign_name,spend', 'time_increment': 1,
                                           'time_range': json.dumps({'since': a, 'until': b}), 'limit': 500}):
        e = etapa(x['campaign_name'])
        if e is not None and float(x.get('spend', 0)):
            dias[x['date_start']][e] += float(x['spend'])
    return {d: [round(v, 2) for v in dias[d]] for d in sorted(dias)}


arq = os.path.join(AQUI, 'etapas.json')
out = json.load(open(arq)) if os.path.exists(arq) else {}
for c, a, b in CICLOS:
    if c == ATUAL or c not in out:
        out[c] = ler(a, min(b, hoje().isoformat()))
        t = [sum(v[i] for v in out[c].values()) for i in range(3)]
        print(c, 'topo', round(t[0]), '· meio', round(t[1]), '· fundo', round(t[2]))
json.dump(out, open(arq, 'w'), ensure_ascii=False, separators=(',', ':'))
