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
# MQL = negócio do relatório "[CICLO] MQL - PERPÉTUO": pipelines padrão, Boletos e Vendas Principal (RGV), criado no ciclo,
# fora estas origens do negócio (eventos, indicações, outbound...); mesmo filtro do relatório do HubSpot
ORIGENS_FORA = ['Indicação - Aluno RGV', 'Palestras', 'Indicação - Clube R1', 'Networking - Nunes', 'Convocação Nacional', 'Instagram - Stories',
                'Indicação - Lead', 'Indicação - Ricardo Nunes', 'Outbound', 'Membro Clube R1', 'Funcionários - Clube R1', 'Café com Ricardo - MG',
                'MSA - Cimed', 'Resgate Convocação', 'CNE On-line', 'Café com Ricardo - SP']
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
                                                    {'propertyName': 'pipeline', 'operator': 'IN', 'values': [PRINCIPAL, BOLETO, PADRAO]},
                                                    {'propertyName': 'origem_dos_negocios', 'operator': 'NOT_IN', 'values': ORIGENS_FORA}]}],
                      'properties': PROPS, 'limit': 200, **({'after': after} if after else {})})
        out += j.get('results', [])
        after = j.get('paging', {}).get('next', {}).get('after')
        if not after: return out
        time.sleep(.15)


def main():
    if os.environ.get('SO_VENDAS'):   # ciclo congelado: mantém os MQL salvos e só acrescenta as vendas
        out = le('crm.json')['deals']
    else:
        ms = lambda d: int(dt.datetime.combine(d, dt.time(), TZ).timestamp() * 1000)
        fim = ate()
        dias = [CICLO['ini'] + dt.timedelta(i) for i in range((fim - CICLO['ini']).days + 1)]
        janelas = [(ms(d), ms(d + dt.timedelta(1))) for d in dias]   # um dia por consulta (fica longe do limite de 10 mil)
        with ThreadPoolExecutor(2) as ex:   # mais que isso estoura o limite por segundo do HubSpot
            deals = [d for r in ex.map(lambda w: busca(*w), janelas) for d in r]
        # e-mails dos contatos de cada negócio, para ligar o MQL ao formulário (origem e anúncio)
        ass = {}
        ids = [d['id'] for d in deals]
        for k in range(0, len(ids), 100):
            j = req('POST', 'https://api.hubapi.com/crm/v4/associations/deals/contacts/batch/read', headers={**H, 'Content-Type': 'application/json'},
                    json={'inputs': [{'id': x} for x in ids[k:k + 100]]})
            for r in j.get('results', []): ass[r['from']['id']] = [str(t['toObjectId']) for t in r.get('to', [])]
        cids = sorted({c for v in ass.values() for c in v}); em = {}
        for k in range(0, len(cids), 100):
            j = req('POST', 'https://api.hubapi.com/crm/v3/objects/contacts/batch/read', headers={**H, 'Content-Type': 'application/json'},
                    json={'inputs': [{'id': x} for x in cids[k:k + 100]], 'properties': ['email']})
            for r in j.get('results', []): em[r['id']] = (r['properties'].get('email') or '').strip().lower()
        out = []
        for d in deals:
            p = d['properties']; pipe = p['pipeline']
            if pipe == BOLETO:   # o Boletos é a continuação depois da reunião: chegou até o realizado; venda só no Ganho de lá
                ch = {e: e != 'venda' or p['dealstage'] == GANHO_BOLETO for e in ETAPAS}
            else:
                f = FASES[pipe]
                ch = {e: p['dealstage'] in f[e] or any(p.get(f'hs_v2_date_entered_{s}') for s in f[e]) for e in ETAPAS}
            cria = dt.datetime.fromisoformat(p['createdate'].replace('Z', '+00:00'))
            out.append({'id': d['id'], 'dia': cria.astimezone(TZ).date().isoformat(), 'ts': int(cria.timestamp() * 1000), 'pipe': pipe,
                        'emails': [em[c] for c in ass.get(d['id'], []) if em.get(c)], 'utm_camp': p.get('utm_camp') or '', 'mql': True,
                        **{e: bool(v) for e, v in ch.items()}})
        print(len(out), 'MQL (negócios do relatório [CICLO] MQL - PERPÉTUO) ·', ' · '.join(f"{e} {sum(x[e] for x in out)}" for e in ETAPAS))
    # vendas do ciclo (Planilha Comercial, canal Perpétuo + produto RGV, em vendas_rgv.json): data de criação e e-mails
    # de cada negócio vendido, para ligar a venda à origem/anúncio do formulário da pessoa
    vj = os.path.join(AQUI, 'vendas_rgv.json')
    vendas = [v for v in json.load(open(vj))['vendas'] if v['ciclo'] == CICLO['nome']] if os.path.exists(vj) else []
    ja = {d['id']: d for d in out}
    falta = sorted({v['id'] for v in vendas if v['id'] and v['id'] not in ja})
    info = {}
    for k in range(0, len(falta), 100):
        j = req('POST', 'https://api.hubapi.com/crm/v3/objects/deals/batch/read', headers={**H, 'Content-Type': 'application/json'},
                json={'inputs': [{'id': x} for x in falta[k:k + 100]], 'properties': ['createdate']})
        for r in j.get('results', []):
            info[r['id']] = {'ts': int(dt.datetime.fromisoformat(r['properties']['createdate'].replace('Z', '+00:00')).timestamp() * 1000), 'emails': []}
        j = req('POST', 'https://api.hubapi.com/crm/v4/associations/deals/contacts/batch/read', headers={**H, 'Content-Type': 'application/json'},
                json={'inputs': [{'id': x} for x in falta[k:k + 100]]})
        cs = {r['from']['id']: [str(t['toObjectId']) for t in r.get('to', [])] for r in j.get('results', [])}
        todos = sorted({c for l in cs.values() for c in l}); em = {}
        for q in range(0, len(todos), 100):
            jj = req('POST', 'https://api.hubapi.com/crm/v3/objects/contacts/batch/read', headers={**H, 'Content-Type': 'application/json'},
                     json={'inputs': [{'id': x} for x in todos[q:q + 100]], 'properties': ['email']})
            for r in jj.get('results', []): em[r['id']] = (r['properties'].get('email') or '').strip().lower()
        for did, l in cs.items():
            info.setdefault(did, {'ts': 0, 'emails': []})['emails'] = [em[c] for c in l if em.get(c)]
    vout = []
    for v in vendas:
        d = ja.get(v['id']) or info.get(v['id']) or {}
        vout.append({**v, 'ts': d.get('ts', 0), 'emails': d.get('emails', []), 'mql': v['id'] in ja})
    print(len(vout), 'linhas de venda ·', sum(v['vendas'] for v in vout), 'vendas ·', sum(v['mql'] for v in vout), 'linhas com negócio no relatório de MQL')
    salva('crm.json', {'deals': out, 'vendas': vout, 'gerado': dt.datetime.now(TZ).strftime('%d/%m/%Y %H:%M')})


if __name__ == '__main__':
    main()
