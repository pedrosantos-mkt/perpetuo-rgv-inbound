# Configuração e utilitários compartilhados pela coleta do painel Perpétuo RGV — funil inbound
import os, json, re, time, datetime as dt, requests

AQUI = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(AQUI, 'raw')
os.makedirs(RAW, exist_ok=True)
TZ = dt.timezone(dt.timedelta(hours=-3))
ACT = 'act_696363384474339'
CICLO = {'nome': 'RGV 45', 'ini': dt.date(2026, 9, 29), 'fim': dt.date(2026, 11, 3)}


def hoje():
    return dt.datetime.now(TZ).date()


def ate():
    """Último dia fechado (ontem), limitado ao fim do ciclo."""
    return min(hoje() - dt.timedelta(1), CICLO['fim'])


def tok(env, arq):
    return (os.environ.get(env) or open(os.path.expanduser(arq)).read()).strip()


META_TOKEN = lambda: tok('META_TOKEN', '~/.config/meta/token')
HS_HEAD = lambda: {'Authorization': 'Bearer ' + tok('HUBSPOT_TOKEN', '~/.config/hubspot/token')}


def req(method, url, tries=7, **kw):
    for i in range(tries):
        try:
            r = requests.request(method, url, timeout=(10, 120), **kw)
            if r.status_code in (429, 500, 502, 503, 504):
                print('  HTTP', r.status_code, r.text[:160]); time.sleep(min(300, 5 * 2 ** i)); continue
            j = r.json()
            if isinstance(j, dict) and 'error' in j and isinstance(j['error'], dict):
                e = j['error']
                if e.get('code') in (4, 17, 32, 613, 80000, 80004) or e.get('is_transient'):
                    print('  limite Meta, aguardando', e.get('message', '')[:80]); time.sleep(min(300, 15 * 2 ** i)); continue
                raise RuntimeError(e)
            return j
        except requests.RequestException as ex:
            print('  rede:', ex); time.sleep(5 * (i + 1))
    raise RuntimeError('falhou: ' + url.split('?')[0])   # sem a query, que leva o token


def meta_all(path, params):
    """GET paginado na Graph API (params=, nunca data=)."""
    url = f'https://graph.facebook.com/v21.0/{path}'
    p = {**params, 'access_token': META_TOKEN()}
    out = []
    while url:
        j = req('GET', url, params=p)
        out += j.get('data', [])
        url = j.get('paging', {}).get('next'); p = None
    return out


def etapa(nome, f):
    """Roda f() e guarda em raw/; se o arquivo já existe nesta rodada (CACHE=1), reaproveita."""
    p = os.path.join(RAW, nome)
    if os.environ.get('CACHE') and os.path.exists(p): return json.load(open(p))
    r = f(); json.dump(r, open(p, 'w'), ensure_ascii=False); return r


def salva(nome, obj):
    json.dump(obj, open(os.path.join(RAW, nome), 'w'), ensure_ascii=False)


def le(nome):
    return json.load(open(os.path.join(RAW, nome)))


def janela(nome):
    """Público pela janela de envolvimento no nome do conjunto."""
    n = (nome or '').upper()
    if 'MIX VALIDADOS' in n or 'QUENTES-AMPLOS' in n:
        return 'Mix validados'
    dias = [int(x) for x in re.findall(r'(\d+)\s*D\b', n)]
    m = max(dias) if dias else None
    if m is None:
        return 'Outros'
    if m <= 30:
        return 'Quente · até 30 dias + listas'
    if m <= 180:
        return 'Morno · 60 a 180 dias'
    return 'Base ampla · 365 a 730 dias'


ORDEM_PUBLICO = ['Quente · até 30 dias + listas', 'Morno · 60 a 180 dias', 'Base ampla · 365 a 730 dias',
                 'Mix validados', 'Outros', 'Sem conjunto na UTM']


def norm_page(u):
    u = (u or '').split('?')[0].split('#')[0].strip().lower()
    u = re.sub(r'^https?://(www\.)?', '', u).rstrip('/')
    return u or '(sem URL)'
