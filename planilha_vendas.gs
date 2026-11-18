// Apps Script da Planilha Comercial (Extensões > Apps Script), publicado como App da Web.
// Versão com a saída do Perpétuo RGV (?p=perpetuo); sem parâmetro, devolve o mesmo resumo de antes (painel da turnê).
// Devolve só o resumo das vendas da turnê por cidade e dia — sem nome, e-mail, telefone ou HubSpot.
// Formato de cada grupo: CIDADE|E ou D|DD/MM/AAAA|vendas|cadeiras|receita em centenas de R$ ; ...
//   E = canal MDV (venda no evento) · D = resgate / indicação / outras ações
// Aba Vendas: A = data, D = cadeiras (VENDA), E = valor (TICKET), I = canal, L = Obs (cidade).
function doGet(e) {
  if (e && e.parameter && e.parameter.p === 'perpetuo') return perpetuoRGV();   // painel do Perpétuo RGV
  const linhas = SpreadsheetApp.getActive().getSheetByName('Vendas').getDataRange().getValues().slice(1);
  const N = s => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase();
  const valor = v => typeof v === 'number' ? v : Number(String(v || '').replace(/[^\d,]/g, '').replace(',', '.')) || 0;
  const grupos = {};
  linhas.forEach(x => {
    const obs = N(x[11]), cad = Number(x[3]) || 0;
    const texto = String(x[0] || '').match(/^(\d{2}\/\d{2}\/\d{4})/);
    if (!/CNE|MDV/.test(obs) || !cad || !(x[0] instanceof Date || texto)) return;
    const cidade = obs.replace(/RESGATE|INDICACAO|CNE|MDV|VAI CANCELAR\?|CONTRATO NAO ASSINADO|[-\/]/g, ' ').replace(/\s+/g, ' ').trim();
    const dia = x[0] instanceof Date ? Utilities.formatDate(x[0], 'America/Sao_Paulo', 'dd/MM/yyyy') : texto[1];
    const k = [cidade, x[8] === 'MDV' ? 'E' : 'D', dia].join('|');
    const g = grupos[k] = grupos[k] || { n: 0, d: 0, e: 0 };
    g.n++; g.d += cad; g.e += valor(x[4]);
  });
  const txt = Object.keys(grupos).map(k => [k, grupos[k].n, grupos[k].d, Math.round(grupos[k].e / 100)].join('|')).join(';');
  return ContentService.createTextOutput(txt).setMimeType(ContentService.MimeType.TEXT);
}

// ?p=perpetuo — vendas do Perpétuo RGV (canal Perpétuo, produto RGV), uma linha por venda, sem nomes:
// NEGÓCIO HUBSPOT|vendas|valor em centavos|CICLO|DD/MM/AAAA|OBS ; ...   (C = HubSpot, D = vendas, E = valor, I = canal, J = produto, K = ciclo, L = Obs)
function perpetuoRGV() {
  const linhas = SpreadsheetApp.getActive().getSheetByName('Vendas').getDataRange().getValues().slice(1);
  const N = s => String(s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase().trim();
  const valor = v => typeof v === 'number' ? v : Number(String(v || '').replace(/[^\d,]/g, '').replace(',', '.')) || 0;
  const out = [];
  linhas.forEach(x => {
    if (!/PERPETUO/.test(N(x[8])) || N(x[9]) !== 'RGV') return;
    const texto = String(x[0] || '').match(/^(\d{2}\/\d{2}\/\d{4})/);
    const dia = x[0] instanceof Date ? Utilities.formatDate(x[0], 'America/Sao_Paulo', 'dd/MM/yyyy') : (texto ? texto[1] : '');
    out.push([String(x[2] || '').trim(), Number(x[3]) || 0, Math.round(valor(x[4]) * 100), String(x[10] || '').trim(), dia,
              String(x[11] || '').replace(/[|;\n]/g, ' ').trim()].join('|'));
  });
  return ContentService.createTextOutput(out.join(';')).setMimeType(ContentService.MimeType.TEXT);
}
