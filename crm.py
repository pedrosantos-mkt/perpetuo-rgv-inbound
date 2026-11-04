# Funil comercial do ciclo pelo pipeline de vendas do HubSpot: negócios criados no ciclo vindos de campanha [FF],
# do lead no CRM à venda. Cada etapa conta o negócio que chegou nela ou passou dela (mesmo perdido depois).
from concurrent.futures import ThreadPoolExecutor
from comum import *

H = HS_HEAD()
PRINCIPAL, BOLETO, PADRAO = '749390743', '746355509', 'default'
# etapa do funil → fases (em ordem) que contam como "chegou"; a primeira de cada lista é a própria fase
ETAPAS = ['contato', 'sql', 'marcado', 'realizado', 'venda']
FASES = {
    PRINCIPAL: {
        'contato': ['1089186215', '1320560225', '1089186216', '1089186217', '1089186218', '1089131958', '1089131959', '1089131960',
                    '1089131961', '1089132032', '1089132033', '1121488310', '1089132034', '1089131937'],   # Em Qualificação →
        'sql': ['1320560225', '1089186216', '1089186217', '1089186218', '1089131958', '1089131959', '1089131960', '1089131961',
                '1089132032', '1089132033', '1121488310', '1089132034', '1089131937'],                        # Em Agendamento →
        'marcado': ['1089186216', '1089186217', '1089186218', '1089131958', '1089131959', '1089131960', '1089131961', '1089132032',
                    '1089132033', '1121488310', '1089132034', '1089131937'],                                   # DIAG. Agendado (NoShow e Reagendado inclusos) →
        'realizado': ['1089131958', '1089131959', '1089131960', '1089131961', '1089132032', '1089132033', '1121488310', '1089132034',
                      '1089131937'],                                                                           # DIAG. Realizado →
        'venda': ['1089131937'],                                                                               # Ganho
    },
    PADRAO: {
        'contato': ['64323906', '996296754', 'presentationscheduled', 'decisionmakerboughtin', '65469583', 'contractsent', '56883564',
                    '211946083', '69507725', '1029506917', 'closedwon'],
        'sql': ['996296754', 'presentationscheduled', 'decisionmakerboughtin', '65469583', 'contractsent', '56883564', '211946083',
                '69507725', '1029506917', 'closedwon'],
        'marcado': ['presentationscheduled', 'decisionmakerboughtin', '65469583', 'contractsent', '56883564', '211946083', '69507725',
                    '1029506917', 'closedwon'],
        'realizado': ['decisionmakerboughtin', '65469583', 'contractsent', '56883564', '211946083', '69507725', '1029506917', 'closedwon'],
        'venda': ['closedwon'],
    },
}
GANHO_BOLETO = '1086562155'
MENSAL_100K = lambda fx: bool(fx) and not (fx.startswith('Menor que 100') or fx.startswith('<'))
ANUAL_100K = {'1 a 6 milhões por ano', '6 a 12 milhões por ano', '12 a 36 milhões por ano', '36 a 50 milhões por ano', 'Acima de 50 milhões'}
STAGES = sorted({s for p in FASES.values() for l in p.values() for s in l})
PROPS = ['dealname', 'pipeline', 'dealstage', 'createdate', 'utm_camp', 'faturamento_mensal_oficial', 'faturamento_anual', 'produto'] + \
        [f'hs_v2_date_entered_{s}' for s in STAGES]


def busca(a, b):
    """Negócios criados entre a e b (ms), nos pipelines de venda; a busca do HubSpot para em 10 mil por consulta."""
    out, after = [], None
    while True:
        j = req('POST', 'https://api.hubapi.com/crm/v3/objects/deals/search', headers={**H, 'Content-Type': 'application/json'},
                json={'filterGroups': [{'filters': [{'propertyName': 'createdate', 'operator': 'BETWEEN', 'value': str(a), 'highValue': str(b - 1)},
                                                    {'propertyName': 'pipeline', 'operator': 'IN', 'values': [PRINCIPAL, BOLETO, PADRAO]}]}],
                      'properties': PROPS, 'limit': 200, **({'after': after} if after else {})})
        out += j.get('results', [])
        after = j.get('paging', {}).get('next', {}).get('after')
        if not after: return out
        time.sleep(.15)


def main():
    ms = lambda d: int(dt.datetime.combine(d, dt.time(), TZ).timestamp() * 1000)
    fim = ate()
    dias = [CICLO['ini'] + dt.timedelta(i) for i in range((fim - CICLO['ini']).days + 1)]
    janelas = [(ms(d), ms(d + dt.timedelta(1))) for d in dias]   # um dia por consulta (fica longe do limite de 10 mil)
    with ThreadPoolExecutor(2) as ex:   # mais que isso estoura o limite por segundo do HubSpot
        deals = [d for r in ex.map(lambda w: busca(*w), janelas) for d in r]
    out = []
    for d in deals:
        p = d['properties']
        uc = (p.get('utm_camp') or '').upper()
        # [FF] do Meta ou campanha do Google Ads do Perpétuo ([C2G] ... [PERPETUO] [SEARCH]/[YT])
        if '[FF]' not in uc and not ('[PERPETUO]' in uc and ('[SEARCH]' in uc or '[YT]' in uc)): continue
        if 'PROCESSOS' in (p.get('produto') or '').upper() or 'PROCESSOS' in (p.get('dealname') or '').upper(): continue
        pipe = p['pipeline']
        fx = p.get('faturamento_mensal_oficial')
        mql = MENSAL_100K(fx) if fx else p.get('faturamento_anual') in ANUAL_100K
        if pipe == BOLETO:   # o Boletos é a continuação depois da reunião: chegou até o realizado; venda só no Ganho de lá
            ch = {e: e != 'venda' or p['dealstage'] == GANHO_BOLETO for e in ETAPAS}
        else:
            f = FASES[pipe]
            ch = {e: p['dealstage'] in f[e] or any(p.get(f'hs_v2_date_entered_{s}') for s in f[e]) for e in ETAPAS}
        dia = (dt.datetime.fromisoformat(p['createdate'].replace('Z', '+00:00')).astimezone(TZ)).date().isoformat()
        out.append({'id': d['id'], 'dia': dia, 'pipe': pipe, 'mql': mql, **{e: bool(v) for e, v in ch.items()}})
    n = lambda k: sum(1 for x in out if x['mql'] and x[k])
    print(len(deals), 'negócios nos pipelines ·', len(out), '[FF] ·', sum(x['mql'] for x in out), 'MQL ·',
          ' · '.join(f'{e} {n(e)}' for e in ETAPAS))
    salva('crm.json', {'deals': out, 'gerado': dt.datetime.now(TZ).strftime('%d/%m/%Y %H:%M')})


if __name__ == '__main__':
    main()
