# Junta data.json no template e gera index.html (Artifact) e site/index.html (Vercel)
import json, os
from comum import AQUI

d = json.load(open(os.path.join(AQUI, 'data.json')))
# ciclos fechados com arquivo em site/c/ entram no seletor (a página lê c/<ciclo>.json ao trocar)
pasta = os.path.join(AQUI, 'site', 'c')
lista = sorted(({'nome': f[:-5].replace('-', ' ')} for f in os.listdir(pasta) if f.endswith('.json')), key=lambda c: c['nome']) if os.path.isdir(pasta) else []
lista_site = json.dumps(lista, ensure_ascii=False)
# metas de leads por ciclo (metas.json), embutidas para valer em qualquer ciclo sem refazer os arquivos dos ciclos
mj = os.path.join(AQUI, 'metas.json')
metas = json.load(open(mj))['ciclos'] if os.path.exists(mj) else {}
t = open(os.path.join(AQUI, 'template.html')).read().replace('__DATA__', json.dumps(d, ensure_ascii=False)).replace('__METAS__', json.dumps(metas, ensure_ascii=False))
open(os.path.join(AQUI, 'index.html'), 'w').write(t.replace('__LISTA__', '[]'))   # Artifact: só o ciclo atual
t = t.replace('__LISTA__', lista_site)
os.makedirs(os.path.join(AQUI, 'site'), exist_ok=True)
open(os.path.join(AQUI, 'site', 'index.html'), 'w').write(
    '<!doctype html><html lang="pt-BR" data-theme="dark"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
    + t.replace('<div class="wrap">', '</head><body><div class="wrap">', 1) + '</body></html>')
print(len(t), 'bytes')
