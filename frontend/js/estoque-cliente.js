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
    if (document.getElementById('modal-ec-entrega')) return;
    const wrap = document.createElement('div');
    wrap.innerHTML = `
    <div class="modal-overlay" id="modal-ec-entrega">
      <div class="modal" style="max-width:760px;width:96vw">
        <div class="modal-title">🚚 Entregar do estoque do cliente</div>
        <div id="ec-ent-cab" style="font-size:14px;margin-bottom:12px;background:rgba(255,255,255,0.05);padding:10px 12px;border-radius:8px;border-left:4px solid var(--accent)"></div>
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
      <div class="modal" style="max-width:560px">
        <div class="modal-title">➕ Saldo inicial no estoque de um cliente</div>
        <div class="form-grid">
          <div class="form-group" style="grid-column:1/-1"><label>Cliente</label><input id="ec-novo-cli-busca" placeholder="Digite para buscar..." oninput="ecFiltrarClientesNovo()"><select id="ec-novo-cli" size="5" style="margin-top:6px"></select></div>
          <div class="form-group" style="grid-column:1/-1"><label>Descrição do produto (como no pedido)</label><input id="ec-novo-desc" placeholder="Ex.: COPO PP 330ML PERSONALIZADO"></div>
          <div class="form-group"><label>Quantidade</label><input type="number" id="ec-novo-qtd" min="1" step="1"></div>
          <div class="form-group"><label>Motivo *</label><input id="ec-novo-obs" value="Saldo inicial"></div>
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
    if (busca) linhas = linhas.filter(l => (l.cliente_nome + ' ' + (l.nome_fantasia || '') + ' ' + l.descricao + ' ' + (l.produto_nome || '')).toLowerCase().includes(busca));
    const porCliente = {};
    linhas.forEach(l => { (porCliente[l.cliente_id] = porCliente[l.cliente_id] || { nome: l.cliente_nome, fantasia: l.nome_fantasia, linhas: [] }).linhas.push(l); });
    const caminho = {};
    (ecDados.a_caminho || []).forEach(p => { (caminho[p.cliente_id] = caminho[p.cliente_id] || { nome: p.cliente_nome, pedidos: [] }).pedidos.push(p); });
    Object.keys(caminho).forEach(cid => { if (!porCliente[cid] && !busca) porCliente[cid] = { nome: caminho[cid].nome, linhas: [] }; });

    const blocos = Object.entries(porCliente).map(([cid, c]) => {
      const total = c.linhas.reduce((s, l) => s + (l.saldo || 0), 0);
      const temSaldo = c.linhas.some(l => l.saldo > 0);
      const prod = (caminho[cid]?.pedidos || []).map(p => `<span style="font-size:11px;background:var(--surface2);border-radius:10px;padding:2px 8px;margin-right:4px">🏭 ${e(p.numero_pedido)} em produção</span>`).join('');
      return `<div class="table-wrap" style="margin-bottom:14px">
        <div class="table-head" style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">
          <span class="table-head-title">🏷️ ${e(c.nome)}${c.fantasia ? ` <span style="font-size:12px;color:var(--muted);font-weight:400">${e(c.fantasia)}</span>` : ''} <span style="font-size:12px;background:var(--surface2);border-radius:10px;padding:2px 8px;margin-left:6px">${n(total)} un</span></span>
          <span style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">${prod}${temSaldo ? `<button class="btn btn-sm btn-primary" onclick="ecAbrirEntrega(${cid})">🚚 Entregar</button>` : ''}</span>
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
            <input type="text" id="ec-busca" placeholder="Buscar cliente ou produto..." oninput="ecRender()" style="min-width:220px">
            <button class="btn btn-sm btn-secondary" onclick="ecMontar('${containerId}')">↻</button>
            <button class="btn btn-sm btn-secondary" id="ec-btn-novo" style="display:none" onclick="ecAbrirNovo()">➕ Saldo inicial</button>
          </div>
        </div>
        <div id="ec-lista"><p style="color:var(--muted)">Carregando...</p></div>`;
    }
    try { ecDados = await chamar('/pedidos/estoque-cliente') || ecDados; }
    catch (err) { document.getElementById('ec-lista').innerHTML = `<p style="color:var(--danger)">${e(err.message)}</p>`; return; }
    document.getElementById('ec-btn-novo').style.display = ecDados.pode_mexer ? '' : 'none';
    render();
  };
  window.ecRender = render;

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

  let ecClientesCache = [];
  window.ecAbrirNovo = async function () {
    try { ecClientesCache = await chamar('/pedidos/clientes') || []; } catch (_) { ecClientesCache = []; }
    if (!Array.isArray(ecClientesCache)) ecClientesCache = ecClientesCache.clientes || [];
    document.getElementById('ec-novo-cli-busca').value = '';
    document.getElementById('ec-novo-desc').value = '';
    document.getElementById('ec-novo-qtd').value = '';
    document.getElementById('ec-novo-obs').value = 'Saldo inicial';
    window.ecFiltrarClientesNovo();
    document.getElementById('modal-ec-novo').classList.add('open');
  };
  window.ecFiltrarClientesNovo = function () {
    const b = document.getElementById('ec-novo-cli-busca').value.toLowerCase().trim();
    const lista = ecClientesCache.filter(c => !b || ((c.razao_social || '') + ' ' + (c.nome_fantasia || '') + ' ' + (c.cnpj || '')).toLowerCase().includes(b)).slice(0, 80);
    document.getElementById('ec-novo-cli').innerHTML = lista.map(c => `<option value="${c.id}">${e(c.razao_social)}${c.nome_fantasia ? ' — ' + e(c.nome_fantasia) : ''}</option>`).join('');
  };
  window.ecConfirmarNovo = async function () {
    const cid = +document.getElementById('ec-novo-cli').value;
    const desc = document.getElementById('ec-novo-desc').value.trim();
    const qtd = parseFloat(document.getElementById('ec-novo-qtd').value) || 0;
    if (!cid) { aviso('Escolha o cliente', 'danger'); return; }
    if (!desc) { aviso('Informe a descrição do produto', 'danger'); return; }
    if (qtd <= 0) { aviso('Informe a quantidade', 'danger'); return; }
    try {
      await chamar('/pedidos/estoque-cliente/ajuste', 'POST', { cliente_id: cid, descricao: desc, quantidade: qtd, observacao: document.getElementById('ec-novo-obs').value.trim() });
      document.getElementById('modal-ec-novo').classList.remove('open');
      aviso('✅ Saldo lançado');
      window.ecMontar(ecContainer.id);
    } catch (err) { aviso(err.message, 'danger'); }
  };

  const TIPO = { entrada: '➕ Entrada (produção)', entrega: '🚚 Entrega', baixa: '➖ Baixa manual', ajuste: '➕ Entrada manual' };
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
