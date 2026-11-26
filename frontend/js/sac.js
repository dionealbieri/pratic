/* Pedidos SAC — caixa de entrada das vendas do SAC Varejo (só gestor).
   Usa api(), showAlert() e _escHtml() do app.js. */
(function () {
  const ABAS = [
    { id: 'aguardando', rot: 'Aguardando decisão' },
    { id: 'fabrica', rot: 'Enviados à fábrica' },
    { id: 'terceirizado', rot: 'Terceirizados' },
    { id: 'ignorado', rot: 'Ignorados' },
    { id: 'cancelados', rot: 'Cancelados no SAC', perigo: true },
  ];
  let aba = 'aguardando';
  let dados = null;
  let produtos = null;      // estoque para os seletores do de-para
  const esc = (v) => (typeof _escHtml === 'function' ? _escHtml(v) : String(v == null ? '' : v));
  const brl = (v) => (v == null ? '—' : 'R$ ' + Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
  const dt = (s) => (s ? String(s).slice(8, 10) + '/' + String(s).slice(5, 7) + ' ' + String(s).slice(11, 16) : '');

  // estilos da tela (uma vez)
  function css() {
    if (document.getElementById('sac-css')) return;
    const st = document.createElement('style');
    st.id = 'sac-css';
    st.textContent = `
      .sac-wrap{display:flex;flex-direction:column;gap:16px}
      .sac-topo{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:12px}
      .sac-titulo{font-family:var(--font-head);font-size:24px;font-weight:800;color:var(--text)}
      .sac-sub{color:var(--muted);font-size:13px;margin-top:4px}
      .sac-robo{display:flex;flex-wrap:wrap;align-items:center;gap:10px;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:10px 14px}
      .sac-robo label{font-size:13px;font-weight:600;color:var(--text);margin:0}
      .sac-robo input[type=date]{width:auto}
      .sac-robo-st{font-size:12.5px;color:var(--muted);display:flex;align-items:center;gap:6px}
      .sac-dot{width:8px;height:8px;border-radius:50%;display:inline-block}
      .sac-abas{display:flex;flex-wrap:wrap;gap:8px}
      .sac-aba{border-radius:999px;padding:8px 15px;font-weight:600;font-size:13px;border:1px solid var(--border);background:var(--surface);color:var(--text);cursor:pointer;min-height:38px}
      .sac-aba.on{background:var(--accent);color:#1a1300;border-color:var(--accent);font-weight:700}
      .sac-aba.perigo{color:var(--danger);border-color:color-mix(in srgb,var(--danger) 45%,transparent)}
      .sac-aba.perigo.on{background:var(--danger);color:#fff}
      .sac-card{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:16px 18px;display:flex;flex-direction:column;gap:12px}
      .sac-cab{display:flex;flex-wrap:wrap;justify-content:space-between;gap:10px;align-items:flex-start}
      .sac-venda{font-family:var(--font-head);font-size:18px;font-weight:800;color:var(--text)}
      .sac-tag{border-radius:6px;padding:2px 8px;font-size:11.5px;font-weight:700;display:inline-block}
      .sac-ok{background:color-mix(in srgb,var(--success) 16%,transparent);color:var(--success)}
      .sac-av{background:color-mix(in srgb,var(--warn) 16%,transparent);color:var(--warn)}
      .sac-err{background:color-mix(in srgb,var(--danger) 16%,transparent);color:var(--danger)}
      .sac-total{font-family:var(--font-head);font-size:19px;font-weight:800;color:var(--text);white-space:nowrap}
      .sac-itens{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:8px 16px;background:var(--surface2);border-radius:10px;padding:10px 12px;font-size:13px;align-items:center}
      .sac-itens .sac-sac{color:var(--muted)}
      .sac-itens select{padding:6px 8px;font-size:13px;max-width:100%}
      .sac-acoes{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
      .sac-acoes .btn{min-height:40px}
      .sac-alerta{display:flex;flex-wrap:wrap;align-items:center;gap:14px;border:1px solid color-mix(in srgb,var(--danger) 55%,transparent);background:color-mix(in srgb,var(--danger) 10%,transparent);border-radius:14px;padding:14px 18px}
      .sac-rodape{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
      .sac-info{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:12px 14px;font-size:13px;color:var(--text);display:flex;flex-direction:column;gap:4px}
      .sac-info-t{color:var(--muted);font-size:11.5px;font-weight:700;text-transform:uppercase;letter-spacing:.5px}
      @media (max-width:700px){.sac-itens{grid-template-columns:minmax(0,1fr)}}
    `;
    document.head.appendChild(st);
  }

  async function carregarProdutos() {
    if (produtos) return produtos;
    try {
      const r = await api('/estoque/produtos');
      produtos = (Array.isArray(r) ? r : (r.produtos || [])).filter(p => p.ativo !== 0)
        .sort((a, b) => String(a.nome).localeCompare(String(b.nome), 'pt-BR'));
    } catch (e) { produtos = []; }
    return produtos;
  }

  function opcoesProduto(selId) {
    return '<option value="">Produto do estoque…</option>'
      + '<option value="terc"' + (selId === 'terc' ? ' selected' : '') + '>🤝 Não é da fábrica (terceirizado)</option>'
      + (produtos || []).map(p => `<option value="${p.id}"${String(selId) === String(p.id) ? ' selected' : ''}>${esc(p.nome)}${p.marca ? ' · ' + esc(p.marca) : ''}</option>`).join('');
  }

  async function sacCarregar(novaAba) {
    css();
    if (novaAba) aba = novaAba;
    const lista = document.getElementById('sac-lista');
    if (!lista) return;
    try {
      [dados] = await Promise.all([api('/sac/caixa?aba=' + encodeURIComponent(aba)), carregarProdutos()]);
    } catch (e) {
      lista.innerHTML = `<p style="color:var(--danger)">${esc(e.message)}</p>`;
      return;
    }
    desenharTopo();
    desenharAbas();
    desenharCancelamentos();
    desenharLista();
    atualizarBadge(dados.contagem);
  }

  function desenharTopo() {
    const r = dados.robo || {};
    const st = document.getElementById('sac-robo-status');
    const inp = document.getElementById('sac-desde');
    if (inp && document.activeElement !== inp) inp.value = r.importar_desde || '';
    const chk = document.getElementById('sac-auto-fabrica');
    if (chk) chk.checked = r.auto_fabrica !== false;
    if (!st) return;
    st.title = '';
    const btn = document.getElementById('sac-btn-sync');
    if (btn) btn.style.display = (r.disponivel && r.configurado && !r.desligado) ? '' : 'none';
    if (!r.disponivel) {
      st.innerHTML = '<span class="sac-dot" style="background:var(--warn)"></span>Leitura automática em preparação — envie os PDFs';
    } else if (r.desligado) {
      st.innerHTML = '<span class="sac-dot" style="background:var(--muted)"></span>' + esc(r.desligado);
    } else if (!r.configurado) {
      st.innerHTML = '<span class="sac-dot" style="background:var(--warn)"></span>Robô sem login do SAC (SAC_USUARIO / SAC_SENHA) — envie os PDFs';
    } else if (r.ultimo_erro) {
      st.innerHTML = '<span class="sac-dot" style="background:var(--danger)"></span>Erro na última leitura: ' + esc(String(r.ultimo_erro).slice(0, 140));
      st.title = r.ultimo_erro;
    } else {
      const res = r.ultimo_resumo || {};
      st.innerHTML = '<span class="sac-dot" style="background:var(--success)"></span>' + (r.automatico ? 'Robô ativo (a cada 15 min)' : 'Robô manual')
        + (r.ultima_leitura ? ' · última leitura ' + dt(r.ultima_leitura) : '')
        + (res.novas != null ? ' · ' + res.novas + ' nova(s)' : '');
      if (res.erros && res.erros.length) st.title = res.erros.join('\n');
    }
  }

  function desenharAbas() {
    const c = dados.contagem || {};
    const n = { aguardando: c.aguardando, fabrica: c.fabrica, terceirizado: c.terceirizado, ignorado: c.ignorado, cancelados: c.cancelados_pendentes };
    document.getElementById('sac-abas').innerHTML = ABAS.map(a =>
      `<button type="button" class="sac-aba${a.id === aba ? ' on' : ''}${a.perigo ? ' perigo' : ''}" onclick="sacCarregar('${a.id}')">${a.rot} · ${n[a.id] || 0}</button>`).join('');
  }

  function desenharCancelamentos() {
    const el = document.getElementById('sac-cancelamentos');
    const cs = (dados.cancelamentos || []);
    el.innerHTML = cs.map(v => {
      const comProd = v.pedido && v.pedido.tem_producao;
      return `<div class="sac-alerta" style="margin-bottom:10px">
        <div style="font-size:22px" aria-hidden="true">⛔</div>
        <div style="flex:999 1 380px;min-width:0">
          <div style="font-weight:800;color:var(--danger)">Venda ${esc(v.venda)} foi cancelada no SAC (A → C)</div>
          <div style="font-size:13px;color:var(--text);margin-top:2px">${esc(v.cliente || '')} · ${brl(v.total)} · ${v.pedido
            ? (comProd ? 'no PRATIC <b>já tem produção lançada</b> — confira estoque e produção antes de excluir.' : 'no PRATIC está <b>sem produção lançada</b> — pode excluir sem mexer no estoque.')
            : 'o pedido não existe mais no PRATIC.'}</div>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          ${v.pedido ? `<button class="btn btn-danger" onclick="sacExcluirPedido('${esc(v.venda)}', ${v.pedido.id}, ${comProd ? 'true' : 'false'})">Excluir do PRATIC</button>` : ''}
          ${v.pedido ? `<button class="btn btn-secondary" onclick="sacCancelamento('${esc(v.venda)}','mantido')">Manter</button>`
                     : `<button class="btn btn-secondary" onclick="sacCancelamento('${esc(v.venda)}','excluido')">Ok, resolvido</button>`}
        </div></div>`;
    }).join('');
  }

  function linhasItens(v, editavel) {
    if (!v.itens || !v.itens.length) return '<div class="sac-sac" style="grid-column:1/-1">Não consegui ler os itens deste PDF — veja o PDF.</div>';
    return v.itens.map((it, i) => {
      const esq = `<div class="sac-sac">${it.codigo ? '<b>' + esc(it.codigo) + '</b> · ' : ''}${esc(it.descricao)} — ${Number(it.quantidade || 0).toLocaleString('pt-BR')} ${esc(it.unidade || '')}</div>`;
      let dir;
      if (it.vinculo === 'produto') dir = `<div style="color:var(--success)">→ ${esc(it.produto_nome)}${it.do_pedido ? ' <span style="color:var(--muted);font-size:11px">(no pedido)</span>' : ''}</div>`;
      else if (it.vinculo === 'pedido_sem_produto') dir = `<div style="color:var(--warn)">no pedido sem produto do estoque — ajuste em Pedidos</div>`;
      else if (it.vinculo === 'terceirizado') dir = `<div style="color:var(--accent2)">→ 🤝 não é da fábrica (fica fora do pedido)</div>`;
      else if (!it.chave) dir = `<div style="color:var(--muted)">não deu para ler o nome do produto</div>`;
      else if (!editavel) dir = `<div style="color:var(--warn)">sem vínculo</div>`;
      else dir = `<div style="display:flex;flex-direction:column;gap:3px">
          <label for="sac-v-${esc(v.venda)}-${i}" style="font-size:11.5px;color:var(--warn);margin:0">Produto novo — escolha uma vez${it.sugestao_id ? ' (sugestão marcada, confira)' : ''}:</label>
          <select id="sac-v-${esc(v.venda)}-${i}" data-venda="${esc(v.venda)}" data-chave="${esc(it.chave)}" data-codigo="${esc(it.codigo)}" data-desc="${esc(it.descricao)}" onchange="sacChecar('${esc(v.venda)}')">${opcoesProduto(it.sugestao_id || '')}</select></div>`;
      return esq + dir;
    }).join('');
  }

  function desenharLista() {
    const el = document.getElementById('sac-lista');
    const vs = dados.vendas || [];
    if (!vs.length) {
      const msg = { aguardando: 'Nenhuma venda esperando decisão. 🎉', cancelados: 'Nenhuma venda cancelada no SAC.' }[aba] || 'Nada aqui por enquanto.';
      el.innerHTML = `<p style="color:var(--muted);padding:20px 0">${msg}</p>`;
      return;
    }
    el.innerHTML = '<div style="display:flex;flex-direction:column;gap:12px">' + vs.map(v => {
      const editavel = aba === 'aguardando';
      const tags = [`<span class="sac-tag ${v.situacao === 'C' ? 'sac-err' : 'sac-ok'}">Situação ${esc(v.situacao || '?')}</span>`];
      if (editavel) tags.push(v.itens_sem_vinculo ? `<span class="sac-tag sac-av">${v.itens_sem_vinculo} item(ns) sem vínculo</span>` : '<span class="sac-tag sac-ok">Todos os itens vinculados</span>');
      if (v.origem === 'manual') tags.push('<span class="sac-tag" style="background:var(--surface2);color:var(--muted)">PDF enviado à mão</span>');
      let acoes = '';
      if (editavel) {
        acoes = `<button class="btn btn-primary" id="sac-fab-${esc(v.venda)}" onclick="sacFabrica('${esc(v.venda)}')">🏭 Enviar para a fábrica</button>
          <button class="btn btn-secondary" onclick="sacDestino('${esc(v.venda)}','terceirizado')">🤝 Terceirizado</button>
          <button class="btn btn-secondary" style="opacity:.85" onclick="sacDestino('${esc(v.venda)}','ignorado')">🚫 Ignorar</button>
          <span id="sac-aviso-${esc(v.venda)}" style="color:var(--muted);font-size:12px"></span>`;
      } else if (aba === 'terceirizado' || aba === 'ignorado') {
        acoes = `<button class="btn btn-secondary" onclick="sacDestino('${esc(v.venda)}','aguardando')">↩ Voltar para a caixa</button>`;
      } else if (aba === 'fabrica' && v.pedido) {
        acoes = `<span style="color:var(--muted);font-size:13px">Pedido no PRATIC: <b style="color:var(--text)">${esc(v.venda)}</b> · ${esc(v.pedido.status)}${v.decidido_por ? ' · por ' + esc(v.decidido_por) : ''}</span>`;
      }
      const decisao = (!editavel && v.decidido_em) ? `<div style="color:var(--muted);font-size:12px">${esc(v.decidido_por || '')} · ${dt(v.decidido_em)}</div>` : '';
      return `<div class="sac-card">
        <div class="sac-cab">
          <div style="display:flex;flex-direction:column;gap:3px;min-width:0">
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap"><span class="sac-venda">Venda ${esc(v.venda)}</span>${tags.join('')}</div>
            <div style="color:var(--text)">${esc(v.cliente || '—')}${v.vendedor ? ' · vendedor <b>' + esc(v.vendedor) + '</b>' : ''}${v.lancamento ? ' · ' + esc(v.lancamento) : ''}</div>
            ${decisao}
          </div>
          <div class="sac-total">${brl(v.total)}</div>
        </div>
        <div class="sac-itens">${linhasItens(v, editavel)}</div>
        ${v.observacoes ? `<div style="font-size:12.5px;color:var(--muted)"><b>Obs.:</b> ${esc(String(v.observacoes).replace(/\s*Arquivo importado:.*$/is, ''))}</div>` : ''}
        <div class="sac-acoes">${acoes}<a href="/api/sac/vendas/${encodeURIComponent(v.venda)}/pdf" target="_blank" rel="noopener" style="margin-left:auto;font-size:13px;font-weight:600;color:var(--accent)">📄 Ver PDF do SAC</a></div>
      </div>`;
    }).join('') + '</div>';
    if (aba === 'aguardando') vs.forEach(v => sacChecar(v.venda));
  }

  // "Enviar para a fábrica" só libera com todos os códigos escolhidos
  function sacChecar(venda) {
    const sels = document.querySelectorAll(`select[data-venda="${CSS.escape(venda)}"]`);
    const faltam = Array.from(sels).filter(s => !s.value).length;
    const b = document.getElementById('sac-fab-' + venda);
    const av = document.getElementById('sac-aviso-' + venda);
    if (b) { b.disabled = faltam > 0; b.style.opacity = faltam ? '.45' : ''; }
    if (av) av.textContent = faltam ? `Escolha o produto de ${faltam} item(ns) para liberar a fábrica.` : (sels.length ? 'Os vínculos escolhidos ficam salvos para as próximas vendas.' : '');
  }

  async function sacFabrica(venda) {
    const vinculos = Array.from(document.querySelectorAll(`select[data-venda="${CSS.escape(venda)}"]`)).map(s => ({
      chave: s.dataset.chave, codigo: s.dataset.codigo, descricao: s.dataset.desc,
      terceirizado: s.value === 'terc', produto_id: s.value && s.value !== 'terc' ? Number(s.value) : null,
    }));
    if (vinculos.some(v => !v.terceirizado && !v.produto_id)) { showAlert('Escolha o produto de todos os itens.', 'danger'); return; }
    const b = document.getElementById('sac-fab-' + venda);
    if (b) { b.disabled = true; b.textContent = 'Criando pedido…'; }
    try {
      const r = await api('/sac/vendas/' + encodeURIComponent(venda) + '/fabrica', 'POST', { vinculos });
      showAlert(r.status === 'duplicado' ? `O pedido ${venda} já existia no PRATIC — ficou ligado a ele.` : `Pedido ${venda} criado na fábrica (${r.qtd_itens || 0} item(ns)).`);
      sacCarregar();
    } catch (e) {
      showAlert(e.message, 'danger');
      if (b) { b.disabled = false; b.textContent = '🏭 Enviar para a fábrica'; }
    }
  }

  async function sacDestino(venda, destino) {
    try {
      await api('/sac/vendas/' + encodeURIComponent(venda) + '/destino', 'POST', { destino });
      showAlert({ terceirizado: 'Marcada como terceirizada.', ignorado: 'Venda ignorada.', aguardando: 'Voltou para a caixa de entrada.' }[destino]);
      sacCarregar();
    } catch (e) { showAlert(e.message, 'danger'); }
  }

  async function sacExcluirPedido(venda, pedidoId, comProducao) {
    const msg = comProducao
      ? `O pedido ${venda} JÁ TEM PRODUÇÃO lançada. Excluir devolve ao estoque o que foi baixado. Confirma a exclusão?`
      : `Excluir o pedido ${venda} do PRATIC? (foi cancelado no SAC)`;
    if (!confirm(msg)) return;
    try {
      await api('/pedidos/' + pedidoId, 'DELETE');
      await api('/sac/vendas/' + encodeURIComponent(venda) + '/cancelamento', 'POST', { acao: 'excluido' });
      showAlert(`Pedido ${venda} excluído.`);
      sacCarregar();
    } catch (e) { showAlert(e.message, 'danger'); }
  }

  async function sacCancelamento(venda, acao) {
    try {
      await api('/sac/vendas/' + encodeURIComponent(venda) + '/cancelamento', 'POST', { acao });
      sacCarregar();
    } catch (e) { showAlert(e.message, 'danger'); }
  }

  async function sacSalvarData(v) {
    if (!v) return;
    try { await api('/sac/config', 'POST', { importar_desde: v }); showAlert('Data de importação salva.'); }
    catch (e) { showAlert(e.message, 'danger'); }
  }

  async function sacAutoFabrica(lig) {
    try {
      const r = await api('/sac/config', 'POST', { auto_fabrica: !!lig });
      showAlert(lig ? ('Vendas já vinculadas vão direto para a fábrica.' + (r.enviadas ? ` ${r.enviadas} enviada(s) agora.` : ''))
                    : 'Todas as vendas vão esperar a sua decisão.');
      if (r.enviadas) sacCarregar();
    } catch (e) { showAlert(e.message, 'danger'); }
  }

  async function sacSincronizar() {
    const b = document.getElementById('sac-btn-sync');
    if (b) { b.disabled = true; b.textContent = 'Lendo o SAC…'; }
    try {
      const r = await api('/sac/sincronizar', 'POST');
      showAlert(r.mensagem || 'Leitura concluída.', (r.erros && r.erros.length) ? 'warn' : 'success');
      sacCarregar();
    } catch (e) { showAlert(e.message, 'danger'); }
    finally { if (b) { b.disabled = false; b.textContent = '↻ Sincronizar agora'; } }
  }

  async function sacEnviarPdfs(inp) {
    const files = Array.from(inp.files || []);
    if (!files.length) return;
    const fd = new FormData();
    files.forEach(f => fd.append('files', f));
    try {
      const r = await fetch('/api/sac/upload', { method: 'POST', body: fd, credentials: 'same-origin' });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail || 'Erro ao enviar');
      const res = j.resultados || [];
      const n = (s) => res.filter(x => x.status === s).length;
      const erros = res.filter(x => x.status === 'erro').map(x => `${x.arquivo}: ${x.motivo}`);
      const auto = res.filter(x => x.automatico === 'fabrica').length;
      showAlert(`${n('registrada')} venda(s) na caixa de entrada` + (auto ? ` · ${auto} já foram direto para a fábrica` : '') + (n('ja_existe') ? ` · ${n('ja_existe')} já estavam aqui` : '')
        + (erros.length ? ` · ${erros.length} com erro` : ''), erros.length ? 'danger' : 'success');
      if (erros.length) console.warn('Pedidos SAC — erros:', erros);
      aba = 'aguardando';
      sacCarregar();
    } catch (e) { showAlert(e.message, 'danger'); }
    finally { inp.value = ''; }
  }

  async function sacAbrirDepara() {
    let rows = [];
    try { rows = await api('/sac/depara'); } catch (e) { showAlert(e.message, 'danger'); return; }
    await carregarProdutos();
    const ov = document.createElement('div');
    ov.className = 'modal-overlay open';
    ov.style.display = 'flex';
    ov.innerHTML = `<div class="modal" style="max-width:860px;width:96%">
      <div class="modal-title">De-para de produtos (SAC → estoque PRATIC)</div>
      <div style="font-size:13px;color:var(--muted);margin-bottom:10px">Cada produto como aparece no PDF do SAC aponta para um produto do estoque. Mudar aqui vale para as próximas vendas (pedidos já criados não mudam).</div>
      <div style="max-height:60vh;overflow:auto">
      ${rows.length ? `<table style="width:100%"><thead><tr><th>Produto no SAC</th><th>Cód.</th><th>Produto PRATIC</th></tr></thead><tbody>
        ${rows.map((r, i) => `<tr><td><b>${esc(r.chave)}</b></td><td>${esc(r.codigo || '')}</td>
          <td><label for="sac-dp-${i}" style="position:absolute;left:-9999px">Produto PRATIC para ${esc(r.chave)}</label>
          <select id="sac-dp-${i}" data-chave="${esc(r.chave)}" data-codigo="${esc(r.codigo || '')}" data-desc="${esc(r.descricao || '')}" style="max-width:340px">${opcoesProduto(r.terceirizado ? 'terc' : (r.produto_id || ''))}</select></td></tr>`).join('')}
      </tbody></table>` : '<p style="color:var(--muted)">Nenhum vínculo ainda — eles são criados ao enviar vendas para a fábrica.</p>'}
      </div>
      <div class="modal-footer"><button class="btn btn-secondary" data-x>Fechar</button></div></div>`;
    document.body.appendChild(ov);
    ov.querySelector('[data-x]').onclick = () => ov.remove();
    ov.addEventListener('click', (e) => { if (e.target === ov) ov.remove(); });
    ov.querySelectorAll('select[data-chave]').forEach(s => s.addEventListener('change', async () => {
      try {
        await api('/sac/depara', 'POST', { chave: s.dataset.chave, codigo: s.dataset.codigo, descricao: s.dataset.desc,
          terceirizado: s.value === 'terc', produto_id: s.value && s.value !== 'terc' ? Number(s.value) : null });
        showAlert('Vínculo atualizado.');
      } catch (e) { showAlert(e.message, 'danger'); }
    }));
  }

  function atualizarBadge(c) {
    if (!c) return;
    const n = (c.aguardando || 0) + (c.cancelados_pendentes || c.cancelados || 0);
    const alerta = !!(c.cancelados_pendentes || c.cancelados);
    ['nav-sac-badge', 'ptab-sac-badge'].forEach(id => {
      const b = document.getElementById(id);
      if (!b) return;
      b.textContent = n;
      b.style.display = n ? '' : 'none';
      b.style.background = alerta ? 'var(--danger)' : '#f5b81c';
      b.style.color = alerta ? '#fff' : '#1a1300';
    });
  }
  async function sacBadge() {
    try { atualizarBadge(await api('/sac/resumo')); } catch (e) {}
  }
  if (localStorage.getItem('user_role') === 'gestor') {
    setTimeout(sacBadge, 2500);
    setInterval(sacBadge, 120000);
  }

  Object.assign(window, { sacCarregar, sacChecar, sacFabrica, sacDestino, sacExcluirPedido, sacCancelamento,
                          sacSalvarData, sacSincronizar, sacEnviarPdfs, sacAbrirDepara, sacAutoFabrica });
})();
