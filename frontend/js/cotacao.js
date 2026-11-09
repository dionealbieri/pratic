/* PRATIC — Dados para cotação de frete (caixas, peso e cubagem do pedido).
   Usado no portal do vendedor (/comercial) e no painel (despacho da Expedição).
   - Cada item é calculado pelo cadastro do produto (unidades por caixa + medidas/peso da caixa).
   - Caixas lançadas à mão (revenda ou caixa diferente) ligadas a um item substituem o cálculo dele. */
(function () {
  const API_COT = window.location.origin + '/api';
  let cotPedidoId = null;
  let cotDados = null;

  function e(v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
  function n(v, casas) {
    return Number(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: casas == null ? 2 : casas });
  }
  function medidas(c, l, a) { return `${n(c, 1)} × ${n(l, 1)} × ${n(a, 1)} cm`; }

  async function chamar(path, method, body) {
    const opts = { method: method || 'GET', headers: { 'Content-Type': 'application/json' }, cache: 'no-store' };
    if (body) opts.body = JSON.stringify(body);
    const r = await fetch(API_COT + path, opts);
    if (r.status === 401) { window.location.href = '/login'; return null; }
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || 'Erro');
    return d;
  }

  function garantirModal() {
    if (document.getElementById('modal-cotacao')) return;
    const div = document.createElement('div');
    div.className = 'modal-overlay';
    div.id = 'modal-cotacao';
    div.innerHTML = `
      <div class="modal" style="max-width:860px;width:96vw">
        <div class="modal-title">📦 Dados para cotação do frete <span id="cot-num" style="color:var(--muted);font-weight:400"></span></div>
        <div id="cot-totais" style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-bottom:14px"></div>
        <div id="cot-avisos"></div>
        <div id="cot-itens-bloco">
        <div style="font-weight:700;font-size:13px;margin:6px 0">Caixas por item <span style="font-weight:400;color:var(--muted)">(pelo cadastro do produto)</span></div>
        <div style="overflow-x:auto"><table style="width:100%">
          <thead><tr><th>Item</th><th>Qtd. pedido</th><th>Caixas</th><th>Medidas da caixa</th><th>Peso total</th><th>m³</th></tr></thead>
          <tbody id="cot-itens"></tbody>
        </table></div>
        </div>
        <div id="cot-itens-nota" style="display:none;font-size:12px;color:var(--muted);margin:4px 0 2px"></div>
        <div style="font-weight:700;font-size:13px;margin:16px 0 6px">Caixas lançadas manualmente</div>
        <div style="overflow-x:auto"><table style="width:100%">
          <thead><tr><th>Item / descrição</th><th>Caixas</th><th>Medidas</th><th>Peso/caixa</th><th>Peso total</th><th>m³</th><th></th></tr></thead>
          <tbody id="cot-manuais"></tbody>
        </table></div>
        <div id="cot-somente-leitura" style="display:none;margin-top:12px;font-size:13px;color:var(--muted);background:rgba(255,255,255,0.04);border:1px solid var(--border);border-radius:10px;padding:10px 12px"></div>
        <div id="cot-form" style="margin-top:12px;background:rgba(255,255,255,0.04);border:1px solid var(--border);border-radius:10px;padding:12px">
          <div style="font-size:12px;color:var(--muted);margin-bottom:8px">Use quando a caixa for diferente da cadastrada no produto (ex.: caixa montada para caber o pedido todo) ou quando o produto não tem embalagem cadastrada.
            <strong>Marque os itens que vão dentro desta caixa</strong> — pode marcar vários (ex.: 100 tampas de cada modelo numa caixa só). Os itens marcados deixam de ser calculados pelo cadastro. Sem nenhum item marcado, a caixa entra como volume extra. Lance uma linha para cada tamanho de caixa.</div>
          <div class="form-grid" style="grid-template-columns:repeat(6,minmax(0,1fr));gap:8px;align-items:end">
            <div class="form-group" style="grid-column:1/-1;min-width:0"><label>Itens nesta caixa</label>
              <div id="cot-item" style="display:flex;flex-wrap:wrap;gap:6px"></div></div>
            <div class="form-group" style="grid-column:1/-1;min-width:0"><label>Descrição <span style="color:var(--muted);font-weight:400">(opcional)</span></label><input id="cot-desc" placeholder="Ex.: caixa única com as tampas, caixa do fornecedor, fardo..." style="width:100%"></div>
            <div class="form-group" style="min-width:0"><label>Qtd. caixas</label><input type="number" id="cot-qtd" min="1" step="1" value="1" style="width:100%"></div>
            <div class="form-group" style="min-width:0"><label>Comp. (cm)</label><input type="number" id="cot-c" min="0" step="0.1" style="width:100%"></div>
            <div class="form-group" style="min-width:0"><label>Larg. (cm)</label><input type="number" id="cot-l" min="0" step="0.1" style="width:100%"></div>
            <div class="form-group" style="min-width:0"><label>Alt. (cm)</label><input type="number" id="cot-a" min="0" step="0.1" style="width:100%"></div>
            <div class="form-group" style="min-width:0"><label>Peso/caixa (kg)</label><input type="number" id="cot-p" min="0" step="0.01" style="width:100%"></div>
            <div class="form-group" style="min-width:0"><button class="btn btn-primary" style="width:100%" onclick="cotLancarVolume()">＋ Lançar</button></div>
          </div>
        </div>
        <div class="modal-footer" style="justify-content:space-between;flex-wrap:wrap;gap:8px">
          <button class="btn btn-secondary" onclick="cotCopiarResumo()">📋 Copiar resumo</button>
          <button class="btn btn-secondary" onclick="document.getElementById('modal-cotacao').classList.remove('open')">Fechar</button>
        </div>
      </div>`;
    document.body.appendChild(div);
    div.addEventListener('click', ev => { if (ev.target === div) div.classList.remove('open'); });
  }

  function cardTotal(rotulo, valor, sub) {
    return `<div class="card" style="padding:12px"><div class="card-label">${rotulo}</div><div class="card-value accent" style="font-size:22px">${valor}</div>${sub ? `<div style="font-size:11px;color:var(--muted)">${sub}</div>` : ''}</div>`;
  }

  function render() {
    const d = cotDados;
    document.getElementById('cot-num').textContent = '· Pedido ' + (d.numero_pedido || d.pedido_id);
    const t = d.totais || {};
    document.getElementById('cot-totais').innerHTML =
      cardTotal('Volumes (caixas)', n(t.caixas, 0)) +
      cardTotal('Peso total', n(t.peso_kg) + ' kg', 'última caixa pode ir incompleta') +
      cardTotal('Cubagem', n(t.cubagem_m3, 3) + ' m³');
    document.getElementById('cot-avisos').innerHTML = (d.avisos || []).length
      ? `<div style="background:rgba(245,158,11,.12);border:1px solid rgba(245,158,11,.4);border-radius:10px;padding:8px 12px;margin-bottom:10px;font-size:12px;color:var(--warn)">⚠ ${d.avisos.map(e).join('<br>⚠ ')}<br><span style="color:var(--muted)">Os totais acima não incluem esses itens até que as caixas sejam lançadas.</span></div>`
      : '';
    // Itens que estão nas caixas lançadas à mão saem daqui (aparecem só embaixo, nas caixas lançadas)
    const itensManual = (d.itens || []).filter(it => it.origem === 'manual');
    const itensCalc = (d.itens || []).filter(it => it.origem !== 'manual');
    document.getElementById('cot-itens-bloco').style.display = itensCalc.length ? '' : 'none';
    const nota = document.getElementById('cot-itens-nota');
    nota.style.display = itensManual.length ? '' : 'none';
    nota.innerHTML = itensManual.length ? `📦 ${itensManual.length === (d.itens || []).length ? 'Todos os itens estão' : itensManual.length + ' item(ns) estão'} nas caixas lançadas manualmente (abaixo).` : '';
    document.getElementById('cot-itens').innerHTML = itensCalc.map(it => {
      const qtd = `${n(it.quantidade, 0)} ${e(it.unidade || '')}`;
      const nome = `${e(it.descricao)}${it.revenda ? ' <span style="font-size:10px;color:var(--warn)">REVENDA</span>' : ''}`;
      if (it.origem === 'manual') return `<tr><td>${nome}</td><td>${qtd}</td><td colspan="4" style="color:var(--muted)">↓ usa as caixas lançadas manualmente</td></tr>`;
      if (it.origem === 'sem_dados') return `<tr><td>${nome}</td><td>${qtd}</td><td colspan="4" style="color:var(--warn)">sem dados: ${e((it.falta || []).join(', '))}</td></tr>`;
      return `<tr><td>${nome}<div style="font-size:11px;color:var(--muted)">${n(it.unid_por_caixa, 0)} un. por caixa</div></td><td>${qtd}</td>
        <td><strong>${n(it.caixas, 0)}</strong></td><td>${medidas(it.comprimento, it.largura, it.altura)}</td>
        <td>${it.sem_peso ? '<span style="color:var(--warn)">sem peso</span>' : n(it.peso_total) + ' kg'}</td><td>${n(it.cubagem_m3, 3)}</td></tr>`;
    }).join('') || '<tr><td colspan="6" style="text-align:center;color:var(--muted)">Pedido sem itens</td></tr>';
    const nomeItem = {};
    (d.itens || []).forEach(it => { nomeItem[it.item_id] = it.descricao; });
    const nomesDe = m => { const ids = (m.itens_ids && m.itens_ids.length) ? m.itens_ids : (m.pedido_item_id ? [m.pedido_item_id] : []);
      return ids.length ? ids.map(i => e(nomeItem[i] || 'Item')).join('<br>') : '<span style="color:var(--muted)">(volume extra, sem item)</span>'; };
    document.getElementById('cot-manuais').innerHTML = (d.manuais || []).map(m => `<tr>
        <td>${nomesDe(m)}${m.descricao ? `<div style="font-size:11px;color:var(--muted)">${e(m.descricao)}</div>` : ''}</td>
        <td><strong>${n(m.qtd_caixas, 0)}</strong></td><td>${medidas(m.comprimento, m.largura, m.altura)}</td>
        <td>${n(m.peso_caixa)} kg</td><td>${n(m.peso_total)} kg</td><td>${n(m.cubagem_m3, 3)}</td>
        <td style="text-align:right"><button class="btn btn-sm btn-secondary cot-del" title="Excluir lançamento por ${e(m.usuario || '')}" onclick="cotExcluirVolume(${m.id})">🗑</button></td></tr>`).join('')
      || '<tr><td colspan="7" style="text-align:center;color:var(--muted)">Nenhum lançamento manual</td></tr>';
    const podeEditar = !!d.pode_editar;
    document.getElementById('cot-form').style.display = podeEditar ? '' : 'none';
    document.getElementById('cot-somente-leitura').style.display = podeEditar ? 'none' : '';
    document.getElementById('cot-somente-leitura').innerHTML = d.completo
      ? '✅ Embalagem completa. As caixas são informadas pelo Estoque/Expedição.'
      : '⏳ A embalagem ainda está sendo informada pelo Estoque/Expedição. O pedido é liberado para o frete quando estiver completa.';
    document.querySelectorAll('#cot-manuais .cot-del').forEach(b => { b.style.display = podeEditar ? '' : 'none'; });
    // Itens da caixa: marcar um ou vários (mantém o que já estava marcado ao recarregar)
    const box = document.getElementById('cot-item');
    const marcados = new Set([...box.querySelectorAll('input:checked')].map(c => +c.value));
    const primeiraVez = !box.dataset.pronto;
    box.innerHTML = (d.itens || []).map(it => {
      const ck = marcados.has(it.item_id) || (primeiraVez && !marcados.size && it.origem === 'sem_dados');
      return `<label style="display:inline-flex;align-items:center;gap:6px;border:1px solid var(--border);border-radius:8px;padding:6px 10px;font-size:12px;cursor:pointer;background:var(--surface)">
        <input type="checkbox" value="${it.item_id}" ${ck ? 'checked' : ''} style="width:15px;height:15px;accent-color:var(--accent)">
        ${e(it.descricao)}${it.origem === 'sem_dados' ? ' <span style="color:var(--warn)">⚠</span>' : it.origem === 'manual' ? ' <span style="color:var(--muted)">(já tem caixa)</span>' : ''}</label>`;
    }).join('') || '<span style="font-size:12px;color:var(--muted)">Pedido sem itens</span>';
    box.dataset.pronto = '1';
  }

  async function recarregar() {
    cotDados = await chamar(`/pedidos/${cotPedidoId}/cotacao`);
    render();
    if (typeof window.cotAoAlterar === 'function') { try { window.cotAoAlterar(cotPedidoId, cotDados); } catch (_) {} }
  }

  window.abrirCotacaoPedido = async function (id) {
    garantirModal();
    cotPedidoId = id;
    ['cot-desc', 'cot-c', 'cot-l', 'cot-a', 'cot-p'].forEach(i => { document.getElementById(i).value = ''; });
    document.getElementById('cot-qtd').value = 1;
    document.getElementById('cot-item').innerHTML = '';
    delete document.getElementById('cot-item').dataset.pronto;
    try {
      await recarregar();
      document.getElementById('modal-cotacao').classList.add('open');
    } catch (err) { alert('Erro ao carregar dados da cotação: ' + err.message); }
  };

  window.cotLancarVolume = async function () {
    const v = id => parseFloat(String(document.getElementById(id).value || '0').replace(',', '.')) || 0;
    const body = {
      pedido_itens_ids: [...document.querySelectorAll('#cot-item input:checked')].map(c => +c.value),
      descricao: document.getElementById('cot-desc').value.trim(),
      qtd_caixas: v('cot-qtd'), comprimento: v('cot-c'), largura: v('cot-l'), altura: v('cot-a'), peso_caixa: v('cot-p'),
    };
    try {
      await chamar(`/pedidos/${cotPedidoId}/volumes`, 'POST', body);
      ['cot-desc', 'cot-c', 'cot-l', 'cot-a', 'cot-p'].forEach(i => { document.getElementById(i).value = ''; });
      document.getElementById('cot-qtd').value = 1;
      document.querySelectorAll('#cot-item input').forEach(c => { c.checked = false; });
      await recarregar();
    } catch (err) { alert(err.message); }
  };

  window.cotExcluirVolume = async function (vid) {
    if (!confirm('Excluir este lançamento de caixas?')) return;
    try { await chamar(`/pedidos/${cotPedidoId}/volumes/${vid}`, 'DELETE'); await recarregar(); }
    catch (err) { alert(err.message); }
  };

  function textoResumo(d) {
    const t = d.totais || {};
    const linhas = [`Pedido ${d.numero_pedido || d.pedido_id}`,
      `Volumes: ${n(t.caixas, 0)} caixa(s) | Peso: ${n(t.peso_kg)} kg | Cubagem: ${n(t.cubagem_m3, 3)} m³`];
    (d.itens || []).filter(it => it.origem === 'cadastro').forEach(it => {
      linhas.push(`- ${it.descricao}: ${n(it.caixas, 0)} cx de ${medidas(it.comprimento, it.largura, it.altura)}, ${n(it.peso_caixa)} kg/cx`);
    });
    (d.manuais || []).forEach(m => {
      linhas.push(`- ${m.descricao || 'Caixas avulsas'}: ${n(m.qtd_caixas, 0)} cx de ${medidas(m.comprimento, m.largura, m.altura)}, ${n(m.peso_caixa)} kg/cx`);
    });
    if ((d.avisos || []).length) linhas.push('Atenção: há itens sem dados de embalagem (não somados).');
    return linhas.join('\n');
  }

  window.cotCopiarResumo = async function () {
    if (!cotDados) return;
    const txt = textoResumo(cotDados);
    try { await navigator.clipboard.writeText(txt); alert('Resumo copiado. Cole na cotação da transportadora.'); }
    catch (_) { prompt('Copie o resumo:', txt); }
  };

  /* Painel completo para a janela de cotação do frete do vendedor: totais, caixas por item
     e o botão para copiar e mandar para a transportadora (une "Cotação" + "Enviar cotação"). */
  let painelDados = null;
  window.cotPainelEnvio = async function (id, el) {
    if (!el) return null;
    el.innerHTML = '<span style="color:var(--muted)">Carregando caixas, peso e cubagem...</span>';
    let d;
    try { d = await chamar(`/pedidos/${id}/cotacao`); }
    catch (err) { el.innerHTML = '<span style="color:var(--muted)">Dados de embalagem indisponíveis</span>'; return null; }
    painelDados = d;
    const t = d.totais || {};
    const mini = (rot, val) => `<div style="background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:8px 10px">
        <div style="font-size:10px;font-weight:700;letter-spacing:.7px;color:var(--muted);text-transform:uppercase">${rot}</div>
        <div style="font-size:20px;font-weight:800;color:var(--accent)">${val}</div></div>`;
    const linhas = (d.itens || []).filter(it => it.origem === 'cadastro').map(it =>
        `<li>${e(it.descricao)}: <strong>${n(it.caixas, 0)} cx</strong> de ${medidas(it.comprimento, it.largura, it.altura)} · ${n(it.peso_caixa)} kg/cx</li>`)
      .concat((d.manuais || []).map(m => `<li>${e(m.descricao || 'Caixas avulsas')}: <strong>${n(m.qtd_caixas, 0)} cx</strong> de ${medidas(m.comprimento, m.largura, m.altura)} · ${n(m.peso_caixa)} kg/cx</li>`));
    el.dataset.pedidoId = id;
    el.innerHTML = `<div style="border:1px solid rgba(96,165,250,.45);background:rgba(96,165,250,.07);border-radius:12px;padding:12px 14px">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px">
        <strong style="color:#8fb8ff">① Dados para cotar com a transportadora</strong>
        <span style="display:flex;gap:6px;flex-wrap:wrap">
          <button type="button" class="btn btn-sm btn-primary" onclick="cotCopiarPainel()">📋 Copiar para a transportadora</button>
          <button type="button" class="btn btn-sm" style="background:rgba(59,130,246,.16);border:1px solid #3b82f6;color:#8fb8ff;font-weight:700" onclick="abrirCotacaoPedido(${id})">📦 ${d.pode_editar ? 'Ver / lançar caixas' : 'Ver caixas'}</button>
        </span>
      </div>
      <div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px">${mini('Volumes', n(t.caixas, 0) + ' cx')}${mini('Peso', n(t.peso_kg) + ' kg')}${mini('Cubagem', n(t.cubagem_m3, 3) + ' m³')}</div>
      ${linhas.length ? `<ul style="margin:8px 0 0 18px;padding:0;font-size:12px;color:var(--muted);line-height:1.6">${linhas.join('')}</ul>` : ''}
      ${(d.avisos || []).length ? `<div style="margin-top:8px;font-size:12px;color:var(--warn)">⚠ ${d.avisos.length} item(ns) sem dados de embalagem — não somados nos totais</div>` : ''}
    </div>`;
    return d;
  };
  window.cotCopiarPainel = async function () {
    if (!painelDados) return;
    const txt = textoResumo(painelDados);
    try { await navigator.clipboard.writeText(txt); alert('Copiado! Cole na cotação da transportadora (WhatsApp, e-mail ou site).'); }
    catch (_) { prompt('Copie o resumo:', txt); }
  };

  /* Resumo curto (uma linha) para colocar em outras telas, ex.: modal de despacho. */
  window.resumoCotacaoHTML = async function (id, el) {
    if (!el) return;
    el.innerHTML = '<span style="color:var(--muted)">Carregando volumes...</span>';
    try {
      const d = await chamar(`/pedidos/${id}/cotacao`);
      const t = d.totais || {};
      el.dataset.pedidoId = id;
      el.innerHTML = `📦 <strong>${n(t.caixas, 0)}</strong> volume(s) · <strong>${n(t.peso_kg)}</strong> kg · ${n(t.cubagem_m3, 3)} m³` +
        ((d.avisos || []).length ? ` <span style="color:var(--warn)">· ⚠ ${d.avisos.length} item(ns) sem embalagem</span>` : ' <span style="color:var(--success)">· embalagem completa</span>') +
        ` <button type="button" class="btn btn-sm" style="margin-left:6px;background:rgba(59,130,246,.16);border:1px solid #3b82f6;color:#8fb8ff;font-weight:700" onclick="abrirCotacaoPedido(${id})">📦 ${d.pode_editar ? 'Ver / lançar caixas' : 'Ver caixas'}</button>`;
      return d;
    } catch (err) { el.innerHTML = '<span style="color:var(--muted)">Volumes indisponíveis</span>'; return null; }
  };
})();
