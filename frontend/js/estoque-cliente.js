/* PRATIC — Estoque do cliente (copo personalizado guardado para o cliente).
   Usado no portal do vendedor (/comercial, aba "Estoque dos meus clientes") e no painel (Estoque → Estoque de clientes).
   - Entra: pedido marcado "para o estoque do cliente" ao terminar a produção.
   - Sai: "Entregar" cria um pedido de entrega (EST-xxxx) já pronto, que segue embalagem → frete → NF.
   - Gestor/Estoque: baixa ou entrada manual (saldo inicial, perda, entrega por fora). */
(function () {
  const API_EC = window.location.origin + '/api';
  let ecDados = { linhas: [], a_caminho: [], pode_mexer: false };
  let ecContainer = null;
  let ecEntregaCliente = null;

  const e = v => String(v == null ? '' : v).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const n = (v, c) => Number(v || 0).toLocaleString('pt-BR', { maximumFractionDigits: c == null ? 0 : c });
  const dt = s => { if (!s) return '—'; const [y, m, d] = String(s).slice(0, 10).split('-'); return `${d}/${m}/${y}`; };

  async function chamar(path, method, body) {
    const opts = { method: method || 'GET', headers: { 'Content-Type': 'application/json' }, cache: 'no-store' };
    if (body) opts.body = JSON.stringify(body);
    const r = await fetch(API_EC + path, opts);
    if (r.status === 401) { window.location.href = '/login'; return null; }
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || 'Erro');
    return d;
  }
  function aviso(msg, tipo) {
    if (typeof window.showAlert === 'function') window.showAlert(msg, tipo || 'success');
    else alert(msg);
  }

  function garantirModais() {
    if (!document.getElementById('ec-estilos')) {
      const st = document.createElement('style');
      st.id = 'ec-estilos';
      st.textContent = `
        .ec-vend{display:inline-block;font-size:14px;font-weight:700;border-radius:14px;padding:4px 12px;margin-left:8px;
          background:rgba(59,130,246,.16);color:#93c5fd;border:1px solid rgba(59,130,246,.45);vertical-align:middle}
        .ec-vend.sem{background:rgba(239,68,68,.14);color:#fca5a5;border-color:rgba(239,68,68,.45)}
        [data-theme="light"] .ec-vend{background:#dbeafe;color:#1d4ed8;border-color:#93c5fd}
        [data-theme="light"] .ec-vend.sem{background:#fee2e2;color:#b91c1c;border-color:#fca5a5}`;
      document.head.appendChild(st);
    }
    if (document.getElementById('modal-ec-entrega')) return;
    const wrap = document.createElement('div');
    wrap.innerHTML = `
    <div class="modal-overlay" id="modal-ec-entrega">
      <div class="modal" style="max-width:760px;width:96vw">
        <div class="modal-title">🚚 Entregar do estoque do cliente</div>
        <div id="ec-ent-cab" style="font-size:14px;margin-bottom:12px;background:var(--surface2);padding:10px 12px;border-radius:8px;border-left:4px solid var(--accent)"></div>
        <div style="overflow-x:auto"><table style="width:100%">
          <thead><tr><th>Produto</th><th style="text-align:right">Saldo</th><th style="width:160px">Entregar agora</th></tr></thead>
          <tbody id="ec-ent-itens"></tbody>
        </table></div>
        <div class="form-group" style="margin-top:10px"><label>Observação <span style="color:var(--muted);font-weight:400">(opcional)</span></label><textarea id="ec-ent-obs" rows="2" placeholder="Ex.: cliente pediu para a próxima semana"></textarea></div>
        <div style="font-size:12px;color:var(--muted);margin-top:6px">Cria um pedido de entrega já pronto (EST-xxxx). Ele segue o fluxo normal: embalagem → frete ou retirada → NF pela Expedição. O saldo do cliente baixa na hora; se a entrega for excluída, o saldo volta.</div>
        <div class="modal-footer">
          <button class="btn btn-secondary" onclick="document.getElementById('modal-ec-entrega').classList.remove('open')">Cancelar</button>
          <button class="btn btn-primary" onclick="ecConfirmarEntrega()">Criar entrega</button>
        </div>
      </div>
    </div>
    <div class="modal-overlay" id="modal-ec-ajuste">
      <div class="modal" style="max-width:520px">
        <div class="modal-title">✏️ Baixa / ajuste no estoque do cliente</div>
        <div id="ec-aj-cab" style="font-size:14px;margin-bottom:12px"></div>
        <div class="form-grid">
          <div class="form-group"><label>Tipo</label><select id="ec-aj-tipo"><option value="baixa">➖ Baixa (sai do estoque)</option><option value="entrada">➕ Entrada (saldo inicial / acerto)</option></select></div>
          <div class="form-group"><label>Quantidade</label><input type="number" id="ec-aj-qtd" min="0" step="1"></div>
          <div class="form-group" style="grid-column:1/-1"><label>Motivo *</label><input id="ec-aj-obs" placeholder="Ex.: saldo inicial, perda, entregue sem pedido..."></div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" onclick="document.getElementById('modal-ec-ajuste').classList.remove('open')">Cancelar</button>
          <button class="btn btn-primary" onclick="ecConfirmarAjuste()">Salvar</button>
        </div>
      </div>
    </div>
    <div class="modal-overlay" id="modal-ec-novo">
      <div class="modal" style="max-width:640px;max-height:92vh;overflow-y:auto">
        <div class="modal-title">➕ Saldo inicial no estoque de um cliente</div>
        <div class="form-grid">
          <div class="form-group" style="grid-column:1/-1"><label for="ec-novo-cli-busca">Cliente</label>
            <div id="ec-novo-cli-sel" style="display:none;align-items:center;gap:8px;justify-content:space-between;padding:8px 12px;border:1px solid var(--success);border-radius:8px;background:rgba(34,197,94,.08);font-weight:600"></div>
            <div id="ec-novo-cli-escolha"><input id="ec-novo-cli-busca" placeholder="Digite o nome, fantasia ou CNPJ e clique no cliente" oninput="ecFiltrarClientesNovo()" autocomplete="off">
            <div id="ec-novo-cli-lista" role="listbox" style="margin-top:6px;max-height:170px;overflow-y:auto;border:1px solid var(--border);border-radius:8px"></div></div>
            <input type="hidden" id="ec-novo-cli"></div>
          <div class="form-group" style="grid-column:1/-1"><label for="ec-novo-vend">Vendedor (quem vê este estoque no portal Comercial)</label>
            <select id="ec-novo-vend"><option value="">— escolha o vendedor —</option></select></div>
          <div id="ec-novo-ja" style="grid-column:1/-1;display:none;font-size:12.5px;color:var(--muted);background:var(--surface2);border-radius:8px;padding:8px 10px"></div>
          <div class="form-group" style="grid-column:1/-1;margin-bottom:0"><label>Produtos e quantidades</label>
            <div id="ec-novo-itens"></div><datalist id="ec-novo-prods"></datalist>
            <button type="button" class="btn btn-secondary" style="width:100%;margin-top:6px" onclick="ecNovoLinha(true)">+ Adicionar produto</button>
            <div id="ec-novo-total" style="text-align:right;font-size:12.5px;color:var(--muted);margin-top:6px"></div></div>
          <div class="form-group" style="grid-column:1/-1"><label for="ec-novo-obs">Motivo *</label><input id="ec-novo-obs" value="Saldo inicial"></div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" onclick="document.getElementById('modal-ec-novo').classList.remove('open')">Cancelar</button>
          <button class="btn btn-primary" onclick="ecConfirmarNovo()">Salvar</button>
        </div>
      </div>
    </div>
    <div class="modal-overlay" id="modal-ec-hist">
      <div class="modal" style="max-width:820px;width:96vw">
        <div class="modal-title">📜 Movimentações <span id="ec-hist-tit" style="color:var(--muted);font-weight:400"></span></div>
        <div style="overflow-x:auto;max-height:60vh"><table style="width:100%">
          <thead><tr><th>Data</th><th>Tipo</th><th style="text-align:right">Qtd.</th><th>Pedido</th><th>Por</th><th>Obs.</th></tr></thead>
          <tbody id="ec-hist-tbody"></tbody>
        </table></div>
        <div class="modal-footer"><button class="btn btn-secondary" onclick="document.getElementById('modal-ec-hist').classList.remove('open')">Fechar</button></div>
      </div>
    </div>`;
    while (wrap.firstElementChild) {
      const m = wrap.firstElementChild;
      document.body.appendChild(m);
      m.addEventListener('click', ev => { if (ev.target === m) m.classList.remove('open'); });
    }
  }

  const SIT = {
    acabando: ['rgba(240,180,41,.15)', 'var(--accent)', 'Acabando (≤30 dias)'],
    parado: ['rgba(156,163,175,.15)', 'var(--muted)', 'Parado 60+ dias'],
    zerado: ['rgba(239,68,68,.15)', 'var(--danger)', 'Zerado'],
    ok: ['rgba(16,185,129,.15)', 'var(--success)', 'Ok'],
  };

  function render() {
    if (!ecContainer) return;
    const busca = (document.getElementById('ec-busca')?.value || '').toLowerCase().trim();
    let linhas = ecDados.linhas || [];
    const vpc = ecDados.vendedor_por_cliente || {};
    const fv = document.getElementById('ec-filtro-vend')?.value || '';
    const passaVend = cid => !fv || (fv === 'sem' ? !vpc[cid] : String((vpc[cid] || {}).id) === fv);
    linhas = linhas.filter(l => passaVend(l.cliente_id));
    if (busca) linhas = linhas.filter(l => (l.cliente_nome + ' ' + (l.nome_fantasia || '') + ' ' + l.descricao + ' ' + (l.produto_nome || '')).toLowerCase().includes(busca));
    const porCliente = {};
    linhas.forEach(l => { (porCliente[l.cliente_id] = porCliente[l.cliente_id] || { nome: l.cliente_nome, fantasia: l.nome_fantasia, linhas: [] }).linhas.push(l); });
    const caminho = {};
    (ecDados.a_caminho || []).filter(p => passaVend(p.cliente_id)).forEach(p => { (caminho[p.cliente_id] = caminho[p.cliente_id] || { nome: p.cliente_nome, pedidos: [] }).pedidos.push(p); });
    Object.keys(caminho).forEach(cid => { if (!porCliente[cid] && !busca) porCliente[cid] = { nome: caminho[cid].nome, linhas: [] }; });

    ecVisiveis = Object.entries(porCliente).map(([cid, c]) => ({ cid: +cid, nome: c.nome, fantasia: c.fantasia,
      vendedor: (vpc[cid] || {}).nome || '', linhas: c.linhas.filter(l => l.saldo > 0) })).filter(c => c.linhas.length);
    const blocos = Object.entries(porCliente).map(([cid, c]) => {
      const total = c.linhas.reduce((s, l) => s + (l.saldo || 0), 0);
      const temSaldo = c.linhas.some(l => l.saldo > 0);
      const prod = (caminho[cid]?.pedidos || []).map(p => `<span style="font-size:11px;background:var(--surface2);border-radius:10px;padding:2px 8px;margin-right:4px">🏭 ${e(p.numero_pedido)} em produção</span>`).join('');
      return `<div class="table-wrap" style="margin-bottom:14px">
        <div class="table-head" style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">
          <span class="table-head-title">🏷️ ${e(c.nome)}${c.fantasia && c.fantasia !== c.nome ? ` <span style="font-size:12px;color:var(--muted);font-weight:400">${e(c.fantasia)}</span>` : ''} <span style="font-size:12px;background:var(--surface2);border-radius:10px;padding:2px 8px;margin-left:6px">${n(total)} un</span>
            ${ecDados.filtro_vendedor ? `<span class="ec-vend ${vpc[cid] ? '' : 'sem'}">👤 ${vpc[cid] ? e(vpc[cid].nome) : 'sem vendedor'}</span>` : ''}</span>
          <span style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">${prod}
            ${temSaldo ? `<button class="btn btn-sm btn-secondary" title="Ver em texto para copiar e mandar (WhatsApp, e-mail)" onclick="ecCopiar([${cid}])">📋 Copiar</button>
            <button class="btn btn-sm btn-secondary" title="Imprimir o estoque deste cliente" onclick="ecImprimir([${cid}])">🖨️</button>` : ''}
            ${ecDados.pode_mexer && ecDados.filtro_vendedor ? `<button class="btn btn-sm btn-secondary" title="Trocar o vendedor deste cliente" onclick="ecTrocarVendedor(${cid})">👤 Vendedor</button>` : ''}
            ${temSaldo ? `<button class="btn btn-sm btn-primary" onclick="ecAbrirEntrega(${cid})">🚚 Entregar</button>` : ''}</span>
        </div>
        <table>
          <thead><tr><th>Produto</th><th style="text-align:right">Saldo</th><th style="text-align:right">Consumo/mês</th><th>Dura</th><th>Última entrega</th><th>Situação</th><th></th></tr></thead>
          <tbody>${c.linhas.length ? c.linhas.map(l => {
            const [bg, cor, txt] = SIT[l.situacao] || SIT.ok;
            const k = encodeURIComponent(JSON.stringify([l.cliente_id, l.produto_id, l.descricao]));
            return `<tr>
              <td><strong>${e(l.descricao)}</strong>${l.produto_nome ? `<div style="font-size:11px;color:var(--muted)">base: ${e(l.produto_nome)}</div>` : ''}</td>
              <td style="text-align:right;font-weight:700">${n(l.saldo)}</td>
              <td style="text-align:right">${l.consumo_mensal ? n(l.consumo_mensal) : '—'}</td>
              <td>${l.cobertura_dias == null ? '—' : '~' + l.cobertura_dias + ' dias'}</td>
              <td>${dt(l.ultima_entrega)}</td>
              <td><span style="display:inline-flex;align-items:center;gap:6px;background:${bg};color:${cor};border-radius:12px;padding:3px 10px;font-size:12px;font-weight:700;white-space:nowrap">${txt}</span></td>
              <td style="text-align:right;white-space:nowrap">
                <button class="btn btn-sm btn-secondary" title="Movimentações" onclick="ecHistorico('${k}')">📜</button>
                ${ecDados.pode_mexer ? `<button class="btn btn-sm btn-secondary" title="Baixa ou ajuste" onclick="ecAbrirAjuste('${k}')">✏️</button>` : ''}
                ${ecDados.pode_excluir ? `<button class="btn btn-sm btn-danger" title="Excluir item do estoque do cliente" onclick="ecExcluir('${k}')">🗑️</button>` : ''}
              </td></tr>`;
          }).join('') : '<tr><td colspan="7" style="text-align:center;color:var(--muted);padding:14px">Ainda sem saldo — aguardando a produção</td></tr>'}</tbody>
        </table>
      </div>`;
    }).join('');

    document.getElementById('ec-lista').innerHTML = blocos || `<div class="card" style="text-align:center;color:var(--muted);padding:28px">${busca ? 'Nada encontrado.' : 'Nenhum cliente com estoque guardado.<br><span style="font-size:12px">Para guardar, marque <strong>“🏷️ Vai para o estoque do cliente”</strong> no lançamento da produção do pedido.</span>'}</div>`;
  }

  window.ecMontar = async function (containerId) {
    garantirModais();
    ecContainer = document.getElementById(containerId);
    if (!ecContainer) return;
    if (!ecContainer.dataset.montado) {
      ecContainer.dataset.montado = '1';
      ecContainer.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:14px">
          <div style="font-size:13px;color:var(--muted)">Copos personalizados guardados para o cliente. Entram quando a produção de um pedido marcado <strong>🏷️ para o estoque do cliente</strong> termina; saem pelo botão <strong>Entregar</strong>.</div>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <select id="ec-filtro-vend" onchange="ecRender()" style="display:none;min-width:190px" aria-label="Filtrar por vendedor"></select>
            <input type="text" id="ec-busca" placeholder="Buscar cliente ou produto..." oninput="ecRender()" style="min-width:220px">
            <button class="btn btn-sm btn-secondary" onclick="ecMontar('${containerId}')" title="Atualizar">↻</button>
            <button class="btn btn-sm btn-secondary" onclick="ecCopiar()" title="Copiar em texto os clientes da tela (com o filtro atual)">📋 Copiar lista</button>
            <button class="btn btn-sm btn-secondary" onclick="ecImprimir()" title="Imprimir os clientes da tela (com o filtro atual)">🖨️ Imprimir</button>
            <button class="btn btn-sm btn-secondary" id="ec-btn-novo" style="display:none" onclick="ecAbrirNovo()">➕ Saldo inicial</button>
          </div>
        </div>
        <div id="ec-lista"><p style="color:var(--muted)">Carregando...</p></div>`;
    }
    try { ecDados = await chamar('/pedidos/estoque-cliente') || ecDados; }
    catch (err) { document.getElementById('ec-lista').innerHTML = `<p style="color:var(--danger)">${e(err.message)}</p>`; return; }
    document.getElementById('ec-btn-novo').style.display = ecDados.pode_mexer ? '' : 'none';
    const fsel = document.getElementById('ec-filtro-vend');
    if (fsel) {
      if (ecDados.filtro_vendedor) {
        const atual = fsel.value;
        const vs = {};
        Object.values(ecDados.vendedor_por_cliente || {}).forEach(v => { vs[v.id] = v.nome; });
        fsel.innerHTML = '<option value="">👤 Todos os vendedores</option>' +
          Object.entries(vs).sort((a, b) => a[1].localeCompare(b[1], 'pt-BR')).map(([id, nm]) => `<option value="${id}">${e(nm)}</option>`).join('') +
          '<option value="sem">— Sem vendedor</option>';
        fsel.value = [...fsel.options].some(o => o.value === atual) ? atual : '';
        fsel.style.display = '';
      } else fsel.style.display = 'none';
    }
    render();
  };
  window.ecRender = render;

  // ── Copiar / imprimir o estoque (o que está na tela, ou só um cliente) ──
  let ecVisiveis = [];
  const hoje = () => new Date().toLocaleDateString('pt-BR');
  function escolher(ids) { return ids ? ecVisiveis.filter(c => ids.includes(c.cid)) : ecVisiveis; }
  function textoEstoque(lista) {
    return lista.map(c => {
      const tot = c.linhas.reduce((s, l) => s + (l.saldo || 0), 0);
      return `*Estoque de copos — ${c.nome}*\n` + (c.vendedor ? `Vendedor: ${c.vendedor}\n` : '')
        + c.linhas.map(l => `• ${l.descricao}: *${n(l.saldo)} un*`).join('\n')
        + (c.linhas.length > 1 ? `\nTotal: ${n(tot)} un` : '');
    }).join('\n\n') + `\n\n_Posição em ${hoje()} — Pratic Rio Preto_`;
  }
  window.ecCopiar = function (ids) {
    const lista = escolher(ids);
    if (!lista.length) { aviso('Nada com saldo para copiar', 'danger'); return; }
    let m = document.getElementById('modal-ec-copiar');
    if (!m) {
      m = document.createElement('div'); m.className = 'modal-overlay'; m.id = 'modal-ec-copiar';
      m.innerHTML = `<div class="modal" style="max-width:620px;width:94vw">
        <div class="modal-title">📋 Estoque para enviar</div>
        <div style="font-size:12.5px;color:var(--muted);margin-bottom:8px">Os *asteriscos* viram negrito no WhatsApp. Pode editar antes de copiar.</div>
        <label for="ec-copiar-txt" style="position:absolute;left:-9999px">Texto do estoque</label>
        <textarea id="ec-copiar-txt" rows="14" style="width:100%;font-family:inherit;font-size:13.5px"></textarea>
        <div class="modal-footer"><button class="btn btn-secondary" onclick="document.getElementById('modal-ec-copiar').classList.remove('open')">Fechar</button>
          <button class="btn btn-primary" id="ec-copiar-btn">📋 Copiar texto</button></div></div>`;
      document.body.appendChild(m);
      m.addEventListener('click', ev => { if (ev.target === m) m.classList.remove('open'); });
      document.getElementById('ec-copiar-btn').onclick = async () => {
        const ta = document.getElementById('ec-copiar-txt');
        try { await navigator.clipboard.writeText(ta.value); }
        catch (_) { ta.select(); document.execCommand && document.execCommand('copy'); }
        aviso('📋 Texto copiado — é só colar no WhatsApp ou no e-mail');
      };
    }
    document.getElementById('ec-copiar-txt').value = textoEstoque(lista);
    m.classList.add('open');
  };
  window.ecImprimir = function (ids) {
    const lista = escolher(ids);
    if (!lista.length) { aviso('Nada com saldo para imprimir', 'danger'); return; }
    const w = window.open('', '_blank');
    if (!w) { aviso('O navegador bloqueou a janela de impressão', 'danger'); return; }
    const filtro = document.getElementById('ec-filtro-vend');
    const fTxt = !ids && filtro && filtro.value ? ' · ' + filtro.selectedOptions[0].text.replace('👤 ', '') : '';
    w.document.write(`<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8"><title>Estoque de clientes ${hoje()}</title>
      <style>@page{size:A4;margin:12mm}body{font-family:Arial,Helvetica,sans-serif;color:#111;font-size:13px}
      h1{font-size:18px;margin:0 0 2px}.sub{color:#555;font-size:12px;margin-bottom:14px}
      .cli{border:1.5px solid #222;border-radius:6px;margin-bottom:12px;page-break-inside:avoid}
      .cab{display:flex;justify-content:space-between;gap:10px;padding:7px 10px;background:#eee;border-bottom:1px solid #222;font-weight:700;-webkit-print-color-adjust:exact;print-color-adjust:exact}
      .vend{font-weight:600}table{width:100%;border-collapse:collapse}td{padding:6px 10px;border-top:1px solid #ccc}
      td.q{text-align:right;font-weight:700;white-space:nowrap}tr.tot td{border-top:1.5px solid #222;font-weight:700}</style></head><body>
      <h1>Estoque de clientes — Pratic Rio Preto</h1><div class="sub">Posição em ${hoje()}${fTxt} · ${lista.length} cliente(s)</div>
      ${lista.map(c => {
        const tot = c.linhas.reduce((s, l) => s + (l.saldo || 0), 0);
        return `<div class="cli"><div class="cab"><span>${e(c.nome)}</span><span class="vend">${c.vendedor ? 'Vendedor: ' + e(c.vendedor) : ''}</span></div>
          <table>${c.linhas.map(l => `<tr><td>${e(l.descricao)}</td><td class="q">${n(l.saldo)} un</td></tr>`).join('')}
          ${c.linhas.length > 1 ? `<tr class="tot"><td>Total</td><td class="q">${n(tot)} un</td></tr>` : ''}</table></div>`;
      }).join('')}
      <script>window.onload=()=>setTimeout(()=>window.print(),300)<\/script></body></html>`);
    w.document.close();
  };

  // ── Trocar o vendedor do cliente ──
  window.ecTrocarVendedor = async function (cid) {
    let vend = [];
    try { vend = ((await chamar('/pedidos/estoque-cliente/vendedores')) || {}).vendedores || []; } catch (err) { aviso(err.message, 'danger'); return; }
    const atual = (ecDados.vendedor_por_cliente || {})[cid];
    const nomeCli = ((ecDados.linhas || []).find(l => l.cliente_id === cid) || {}).cliente_nome || '';
    let m = document.getElementById('modal-ec-vend');
    if (!m) {
      m = document.createElement('div'); m.className = 'modal-overlay'; m.id = 'modal-ec-vend';
      m.innerHTML = `<div class="modal" style="max-width:460px">
        <div class="modal-title">👤 Vendedor do estoque do cliente</div>
        <div id="ec-vend-cli" style="font-weight:700;margin-bottom:10px"></div>
        <div class="form-group"><label for="ec-vend-sel">Vendedor (vê este estoque no portal Comercial)</label><select id="ec-vend-sel"></select></div>
        <div class="modal-footer"><button class="btn btn-secondary" onclick="document.getElementById('modal-ec-vend').classList.remove('open')">Cancelar</button>
          <button class="btn btn-primary" id="ec-vend-ok">Salvar</button></div></div>`;
      document.body.appendChild(m);
      m.addEventListener('click', ev => { if (ev.target === m) m.classList.remove('open'); });
    }
    document.getElementById('ec-vend-cli').textContent = nomeCli;
    document.getElementById('ec-vend-sel').innerHTML = '<option value="">— sem vendedor —</option>'
      + vend.map(v => `<option value="${v.id}"${atual && atual.id === v.id ? ' selected' : ''}>${e(v.nome)}</option>`).join('');
    document.getElementById('ec-vend-ok').onclick = async () => {
      const v = +document.getElementById('ec-vend-sel').value || null;
      try {
        const r = await chamar('/pedidos/estoque-cliente/vendedor', 'POST', { cliente_id: cid, vendedor_usuario_id: v });
        m.classList.remove('open');
        aviso('👤 ' + ((r && r.mensagem) || 'Vendedor atualizado'));
        window.ecMontar(ecContainer.id);
      } catch (err) { aviso(err.message, 'danger'); }
    };
    m.classList.add('open');
  };

  function linhaPorChave(k) {
    const [cid, pid, desc] = JSON.parse(decodeURIComponent(k));
    return (ecDados.linhas || []).find(l => l.cliente_id === cid && (l.produto_id || null) === (pid || null) && l.descricao === desc);
  }

  window.ecAbrirEntrega = function (cid) {
    ecEntregaCliente = +cid;
    const linhas = (ecDados.linhas || []).filter(l => l.cliente_id === +cid && l.saldo > 0);
    if (!linhas.length) return;
    document.getElementById('ec-ent-cab').innerHTML = `Cliente: <strong>${e(linhas[0].cliente_nome)}</strong>`;
    document.getElementById('ec-ent-itens').innerHTML = linhas.map((l, i) => `<tr>
      <td>${e(l.descricao)}</td><td style="text-align:right">${n(l.saldo)}</td>
      <td><input type="number" min="0" max="${l.saldo}" step="1" data-i="${i}" class="ec-ent-qtd" placeholder="0" style="width:100%"></td></tr>`).join('');
    document.getElementById('ec-ent-itens').dataset.linhas = JSON.stringify(linhas.map(l => ({ produto_id: l.produto_id, descricao: l.descricao })));
    document.getElementById('ec-ent-obs').value = '';
    document.getElementById('modal-ec-entrega').classList.add('open');
  };

  window.ecConfirmarEntrega = async function () {
    const base = JSON.parse(document.getElementById('ec-ent-itens').dataset.linhas || '[]');
    const itens = [...document.querySelectorAll('.ec-ent-qtd')].map(inp => ({ ...base[+inp.dataset.i], quantidade: parseFloat(inp.value) || 0 }))
      .filter(i => i.quantidade > 0);
    if (!itens.length) { aviso('Informe a quantidade a entregar', 'danger'); return; }
    try {
      const r = await chamar('/pedidos/estoque-cliente/entrega', 'POST', { cliente_id: ecEntregaCliente, itens, observacao: document.getElementById('ec-ent-obs').value.trim() });
      document.getElementById('modal-ec-entrega').classList.remove('open');
      aviso('✅ ' + r.mensagem);
      if (ecContainer) window.ecMontar(ecContainer.id);
      if (typeof window.ecAoCriarEntrega === 'function') window.ecAoCriarEntrega(r);
    } catch (err) { aviso(err.message, 'danger'); }
  };

  let ecAjusteLinha = null;
  window.ecAbrirAjuste = function (k) {
    ecAjusteLinha = linhaPorChave(k);
    if (!ecAjusteLinha) return;
    document.getElementById('ec-aj-cab').innerHTML = `<strong>${e(ecAjusteLinha.cliente_nome)}</strong><br>${e(ecAjusteLinha.descricao)} · saldo <strong>${n(ecAjusteLinha.saldo)}</strong>`;
    document.getElementById('ec-aj-tipo').value = 'baixa';
    document.getElementById('ec-aj-qtd').value = '';
    document.getElementById('ec-aj-obs').value = '';
    document.getElementById('modal-ec-ajuste').classList.add('open');
  };
  window.ecConfirmarAjuste = async function () {
    const qtd = parseFloat(document.getElementById('ec-aj-qtd').value) || 0;
    if (qtd <= 0) { aviso('Informe a quantidade', 'danger'); return; }
    const sinal = document.getElementById('ec-aj-tipo').value === 'baixa' ? -1 : 1;
    try {
      await chamar('/pedidos/estoque-cliente/ajuste', 'POST', {
        cliente_id: ecAjusteLinha.cliente_id, produto_id: ecAjusteLinha.produto_id, descricao: ecAjusteLinha.descricao,
        quantidade: sinal * qtd, observacao: document.getElementById('ec-aj-obs').value.trim(),
      });
      document.getElementById('modal-ec-ajuste').classList.remove('open');
      aviso('✅ Estoque do cliente atualizado');
      window.ecMontar(ecContainer.id);
    } catch (err) { aviso(err.message, 'danger'); }
  };

  window.ecExcluir = async function (k) {
    const l = linhaPorChave(k);
    if (!l) return;
    const motivo = prompt(`Excluir do estoque de ${l.cliente_nome}:\n${l.descricao} — saldo ${n(l.saldo)} un\n\n` +
      'O item sai da lista e o histórico (📜) guarda quem excluiu e por quê.\nInforme o motivo:');
    if (motivo === null) return;
    if (motivo.trim().length < 3) { aviso('Informe o motivo da exclusão', 'danger'); return; }
    try {
      const r = await chamar('/pedidos/estoque-cliente/excluir', 'POST', {
        cliente_id: l.cliente_id, produto_id: l.produto_id, descricao: l.descricao, motivo: motivo.trim() });
      aviso('🗑️ ' + ((r && r.mensagem) || 'Item excluído'));
      window.ecMontar(ecContainer.id);
    } catch (err) { aviso(err.message, 'danger'); }
  };

  let ecClientesCache = [];
  let ecVendInfo = { vendedores: [], ultimo_vendedor: {} };
  let ecProdsCache = [];
  window.ecAbrirNovo = async function () {
    const [cli, vend, prods] = await Promise.all([
      chamar('/pedidos/clientes').catch(() => []),
      chamar('/pedidos/estoque-cliente/vendedores').catch(() => ({ vendedores: [], ultimo_vendedor: {} })),
      chamar('/estoque/produtos').catch(() => []),
    ]);
    ecClientesCache = Array.isArray(cli) ? cli : (cli && cli.clientes) || [];
    ecVendInfo = vend || { vendedores: [], ultimo_vendedor: {} };
    ecProdsCache = Array.isArray(prods) ? prods.filter(p => p.ativo !== 0) : [];
    document.getElementById('ec-novo-vend').innerHTML = '<option value="">— escolha o vendedor —</option>' +
      (ecVendInfo.vendedores || []).map(v => `<option value="${v.id}">${e(v.nome)}</option>`).join('');
    document.getElementById('ec-novo-prods').innerHTML = ecProdsCache.map(p => `<option value="${e(p.nome)}">${e(p.marca || '')}</option>`).join('');
    window.ecTrocarCliente();
    document.getElementById('ec-novo-itens').innerHTML = '';
    window.ecNovoLinha(false);
    document.getElementById('ec-novo-ja').style.display = 'none';
    document.getElementById('ec-novo-obs').value = 'Saldo inicial';
    document.getElementById('modal-ec-novo').classList.add('open');
    setTimeout(() => document.getElementById('ec-novo-cli-busca').focus(), 50);
  };
  window.ecFiltrarClientesNovo = function () {
    const b = document.getElementById('ec-novo-cli-busca').value.toLowerCase().trim();
    const lista = ecClientesCache.filter(c => !b || ((c.razao_social || '') + ' ' + (c.nome_fantasia || '') + ' ' + (c.cnpj || '')).toLowerCase().includes(b)).slice(0, 80);
    document.getElementById('ec-novo-cli-lista').innerHTML = lista.length ? lista.map(c =>
      `<div role="option" tabindex="0" style="padding:7px 10px;cursor:pointer;border-bottom:1px solid var(--border);font-size:13px"
         onmouseover="this.style.background='var(--surface2)'" onmouseout="this.style.background=''"
         onclick="ecEscolherCliente(${c.id})" onkeydown="if(event.key==='Enter')ecEscolherCliente(${c.id})">
         ${e(c.razao_social)}${c.nome_fantasia && c.nome_fantasia !== c.razao_social ? ' <span style="color:var(--muted)">— ' + e(c.nome_fantasia) + '</span>' : ''}</div>`).join('')
      : '<div style="padding:8px 10px;color:var(--muted);font-size:13px">Nenhum cliente encontrado</div>';
  };
  window.ecEscolherCliente = function (id) {
    const c = ecClientesCache.find(x => x.id === id);
    if (!c) return;
    document.getElementById('ec-novo-cli').value = id;
    const sel = document.getElementById('ec-novo-cli-sel');
    sel.innerHTML = `<span>✓ ${e(c.razao_social)}${c.nome_fantasia && c.nome_fantasia !== c.razao_social ? ' — ' + e(c.nome_fantasia) : ''}</span>
      <button type="button" class="btn btn-sm btn-secondary" onclick="ecTrocarCliente()">Trocar</button>`;
    sel.style.display = 'flex';
    document.getElementById('ec-novo-cli-escolha').style.display = 'none';
    // vendedor: o do último pedido do cliente (pode trocar)
    const v = (ecVendInfo.ultimo_vendedor || {})[id];
    document.getElementById('ec-novo-vend').value = v ? String(v) : '';
    // o que este cliente já tem guardado (para não lançar em dobro)
    const ja = (ecDados.linhas || []).filter(l => l.cliente_id === id && l.saldo > 0);
    const box = document.getElementById('ec-novo-ja');
    box.innerHTML = ja.length ? '⚠️ Já tem no estoque deste cliente: ' + ja.map(l => `<b>${e(l.descricao)}</b> ${n(l.saldo)}`).join(' · ')
      + '<br><span style="font-size:11.5px">O que você lançar aqui SOMA a esse saldo.</span>' : '';
    box.style.display = ja.length ? '' : 'none';
    const p1 = document.querySelector('#ec-novo-itens .ec-ni-desc');
    if (p1) p1.focus();
  };
  // Linhas de produto do saldo inicial
  window.ecNovoLinha = function (foco) {
    const box = document.getElementById('ec-novo-itens');
    const div = document.createElement('div');
    div.className = 'ec-ni';
    div.style.cssText = 'display:grid;grid-template-columns:1fr 120px auto;gap:6px;margin-bottom:6px';
    div.innerHTML = `<input class="ec-ni-desc" list="ec-novo-prods" placeholder="Produto do estoque (ou como no pedido)" autocomplete="off" aria-label="Produto">
      <input class="ec-ni-qtd" type="number" min="1" step="1" placeholder="Qtd" aria-label="Quantidade">
      <button type="button" class="btn btn-sm btn-danger" title="Tirar esta linha" aria-label="Tirar esta linha">✕</button>`;
    div.querySelector('button').onclick = () => { div.remove(); if (!box.children.length) window.ecNovoLinha(false); ecNovoTotal(); };
    div.querySelector('.ec-ni-qtd').addEventListener('input', ecNovoTotal);
    div.querySelector('.ec-ni-qtd').addEventListener('keydown', ev => { if (ev.key === 'Enter') { ev.preventDefault(); window.ecNovoLinha(true); } });
    box.appendChild(div);
    if (foco) div.querySelector('.ec-ni-desc').focus();
    ecNovoTotal();
  };
  function ecNovoTotal() {
    const linhas = [...document.querySelectorAll('#ec-novo-itens .ec-ni')];
    const tot = linhas.reduce((s, d) => s + (parseFloat(d.querySelector('.ec-ni-qtd').value) || 0), 0);
    const el = document.getElementById('ec-novo-total');
    if (el) el.textContent = tot ? `${linhas.length} linha(s) · total ${n(tot)} un` : '';
  }
  window.ecTrocarCliente = function () {
    document.getElementById('ec-novo-cli').value = '';
    document.getElementById('ec-novo-cli-sel').style.display = 'none';
    document.getElementById('ec-novo-cli-escolha').style.display = '';
    document.getElementById('ec-novo-cli-busca').value = '';
    window.ecFiltrarClientesNovo();
  };
  window.ecConfirmarNovo = async function () {
    const cid = +document.getElementById('ec-novo-cli').value;
    const vend = +document.getElementById('ec-novo-vend').value || null;
    if (!cid) { aviso('Clique no cliente na lista para escolher', 'danger'); return; }
    const linhas = [...document.querySelectorAll('#ec-novo-itens .ec-ni')].map(d => ({
      descricao: d.querySelector('.ec-ni-desc').value.trim(), quantidade: parseFloat(d.querySelector('.ec-ni-qtd').value) || 0 }));
    const meio = linhas.find(l => (l.descricao && !l.quantidade) || (!l.descricao && l.quantidade));
    if (meio) { aviso(meio.descricao ? `Falta a quantidade de ${meio.descricao}` : 'Tem quantidade sem produto', 'danger'); return; }
    // mesmo produto em duas linhas: soma
    const juntos = {};
    linhas.filter(l => l.descricao && l.quantidade > 0).forEach(l => {
      const k = l.descricao.toUpperCase();
      juntos[k] = juntos[k] ? { ...juntos[k], quantidade: juntos[k].quantidade + l.quantidade } : { ...l };
    });
    const itens = Object.values(juntos).map(l => {
      const prod = ecProdsCache.find(p => (p.nome || '').trim().toUpperCase() === l.descricao.toUpperCase());
      return { descricao: prod ? prod.nome : l.descricao, quantidade: l.quantidade, produto_id: prod ? prod.id : null };
    });
    if (!itens.length) { aviso('Informe o produto e a quantidade', 'danger'); return; }
    const semCadastro = itens.filter(i => !i.produto_id).map(i => i.descricao);
    if (semCadastro.length && !confirm('Estes produtos não são do cadastro do estoque (ficam só pelo nome):\n• ' + semCadastro.join('\n• ') + '\n\nContinuar?')) return;
    if (!vend && !confirm('Nenhum vendedor escolhido: este estoque só aparece no portal Comercial se o cliente tiver pedido com algum vendedor.\n\nSalvar assim mesmo?')) return;
    try {
      const r = await chamar('/pedidos/estoque-cliente/saldo-lote', 'POST', { cliente_id: cid, itens, vendedor_usuario_id: vend,
        observacao: document.getElementById('ec-novo-obs').value.trim() });
      document.getElementById('modal-ec-novo').classList.remove('open');
      aviso('✅ Saldo lançado — ' + ((r && r.mensagem) || ''));
      window.ecMontar(ecContainer.id);
    } catch (err) { aviso(err.message, 'danger'); }
  };

  const TIPO = { entrada: '➕ Entrada (produção)', entrega: '🚚 Entrega', baixa: '➖ Baixa manual', ajuste: '➕ Entrada manual', exclusao: '🗑️ Excluído pelo gestor' };
  window.ecHistorico = async function (k) {
    const l = linhaPorChave(k);
    if (!l) return;
    document.getElementById('ec-hist-tit').textContent = '· ' + l.cliente_nome + ' · ' + l.descricao;
    const tb = document.getElementById('ec-hist-tbody');
    tb.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--muted)">Carregando...</td></tr>';
    document.getElementById('modal-ec-hist').classList.add('open');
    try {
      const qs = `cliente_id=${l.cliente_id}&descricao=${encodeURIComponent(l.descricao)}` + (l.produto_id ? `&produto_id=${l.produto_id}` : '');
      const rows = await chamar('/pedidos/estoque-cliente/historico?' + qs) || [];
      tb.innerHTML = rows.map(m => `<tr>
        <td style="white-space:nowrap">${dt(m.created_at)} <span style="font-size:11px;color:var(--muted)">${String(m.created_at || '').slice(11, 16)}</span></td>
        <td>${TIPO[m.tipo] || e(m.tipo)}</td>
        <td style="text-align:right;font-weight:700;color:${m.quantidade < 0 ? 'var(--danger)' : 'var(--success)'}">${m.quantidade > 0 ? '+' : ''}${n(m.quantidade)}</td>
        <td>${m.numero_pedido ? e(m.numero_pedido) : '—'}</td>
        <td>${e(m.usuario || '')}</td>
        <td style="font-size:12px;color:var(--muted)">${e(m.observacao || '')}</td></tr>`).join('') || '<tr><td colspan="6" style="text-align:center;color:var(--muted)">Sem movimentações</td></tr>';
    } catch (err) { tb.innerHTML = `<tr><td colspan="6" style="color:var(--danger)">${e(err.message)}</td></tr>`; }
  };
})();
