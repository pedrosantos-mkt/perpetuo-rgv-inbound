# Junta data.json no template e gera index.html (Artifact) e site/index.html (Vercel)
import json, os
from comum import AQUI

d = json.load(open(os.path.join(AQUI, 'data.json')))
t = open(os.path.join(AQUI, 'template.html')).read().replace('__DATA__', json.dumps(d, ensure_ascii=False))
open(os.path.join(AQUI, 'index.html'), 'w').write(t)
os.makedirs(os.path.join(AQUI, 'site'), exist_ok=True)
open(os.path.join(AQUI, 'site', 'index.html'), 'w').write(
    '<!doctype html><html lang="pt-BR" data-theme="dark"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
    + t.replace('<div class="wrap">', '</head><body><div class="wrap">', 1) + '</body></html>')
print(len(t), 'bytes')
