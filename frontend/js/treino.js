/* Treinamento do Comercial (carregado pelo ambiente.js só no servidor de treino).
   - 🎯 Missões: painel flutuante com as tarefas do vendedor, conferidas sozinhas.
   - 🧭 Tour: balões explicando a tela Meus Pedidos (/comercial).
   - 📋 Turma: painel do Gestor treinador com o progresso de cada vendedor. */
(function () {
  if (window.PraticTreino) return;
  var NO_COMERCIAL = location.pathname.indexOf('/comercial') === 0;
  var LARANJA = '#f97316';

  function el(tag, css, txt) {
    var e = document.createElement(tag);
    if (css) e.style.cssText = css;
    if (txt != null) e.textContent = txt;
    return e;
  }
  function req(url, metodo, corpo) {
    var op = { method: metodo || 'GET', credentials: 'same-origin', cache: 'no-store' };
    if (corpo) { op.headers = { 'Content-Type': 'application/json' }; op.body = JSON.stringify(corpo); }
    return fetch(url, op).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) throw new Error(j.detail || ('Erro ' + r.status));
        return j;
      });
    });
  }
  function alturaFaixa() {
    var f = document.getElementById('pratic-ambiente-faixa');
    return f ? f.offsetHeight : 0;
  }
  function evento(tipo) { return req('/api/treino/evento', 'POST', { tipo: tipo }).catch(function () {}); }
  function toast(msg) {
    var t = el('div', 'position:fixed;left:50%;transform:translateX(-50%);z-index:2147483003;background:#16a34a;color:#fff;' +
      'font:700 14px Arial,Helvetica,sans-serif;padding:12px 18px;border-radius:12px;box-shadow:0 8px 24px rgba(0,0,0,.45);' +
      'bottom:' + (alturaFaixa() + 80) + 'px', msg);
    document.body.appendChild(t);
    setTimeout(function () { t.style.transition = 'opacity .5s'; t.style.opacity = '0'; }, 3200);
    setTimeout(function () { t.remove(); }, 3800);
  }

  // ═══ 🎯 MISSÕES ═══════════════════════════════════════════════════════════════
  var dados = null, feitasAntes = null, botao = null, painel = null;

  function carregarMissoes() {
    return req('/api/treino/missoes').then(function (d) {
      if (!d || !d.aplicavel) return;
      if (feitasAntes) {
        d.missoes.forEach(function (m) {
          if (m.feita && feitasAntes[m.id] === false) toast('✅ Missão concluída: ' + m.titulo);
        });
      }
      feitasAntes = {};
      d.missoes.forEach(function (m) { feitasAntes[m.id] = m.feita; });
      dados = d;
      desenharBotao();
      if (painel) desenharPainel();
    }).catch(function () {});
  }

  function desenharBotao() {
    if (!botao) {
      botao = el('button', 'position:fixed;right:18px;z-index:2147483001;border:2px solid #fff;border-radius:24px;cursor:pointer;' +
        'background:' + LARANJA + ';color:#fff;font:800 14px Arial,Helvetica,sans-serif;padding:10px 16px;' +
        'box-shadow:0 6px 20px rgba(0,0,0,.45)');
      botao.type = 'button';
      botao.onclick = function () { painel ? fecharPainel() : abrirPainel(); };
      document.body.appendChild(botao);
    }
    botao.style.bottom = (alturaFaixa() + 14) + 'px';
    var ok = dados.total && dados.feitas >= dados.total;
    botao.textContent = (ok ? '🏆 Missões ' : '🎯 Missões ') + dados.feitas + '/' + dados.total;
    botao.style.background = ok ? '#16a34a' : LARANJA;
  }

  function abrirPainel() {
    painel = el('div', 'position:fixed;right:18px;z-index:2147483001;width:360px;max-width:calc(100vw - 36px);' +
      'max-height:calc(100vh - 160px);overflow:auto;background:#111827;color:#f3f4f6;border:2px solid ' + LARANJA + ';' +
      'border-radius:14px;box-shadow:0 12px 36px rgba(0,0,0,.6);font:14px/1.35 Arial,Helvetica,sans-serif');
    document.body.appendChild(painel);
    desenharPainel();
  }
  function fecharPainel() { if (painel) painel.remove(); painel = null; }

  function desenharPainel() {
    if (!painel || !dados) return;
    painel.style.bottom = (alturaFaixa() + 66) + 'px';
    painel.innerHTML = '';
    var topo = el('div', 'display:flex;justify-content:space-between;align-items:center;padding:12px 14px;border-bottom:1px solid #374151');
    topo.appendChild(el('div', 'font-weight:800;font-size:15px', '🎯 Missões do treinamento'));
    var x = el('button', 'background:none;border:0;color:#9ca3af;font-size:20px;cursor:pointer;line-height:1', '×');
    x.type = 'button'; x.onclick = fecharPainel; topo.appendChild(x);
    painel.appendChild(topo);

    var pct = dados.total ? Math.round(100 * dados.feitas / dados.total) : 0;
    var barra = el('div', 'margin:10px 14px 4px;height:8px;background:#374151;border-radius:6px;overflow:hidden');
    barra.appendChild(el('div', 'height:100%;width:' + pct + '%;background:' + (pct === 100 ? '#16a34a' : LARANJA)));
    painel.appendChild(barra);
    painel.appendChild(el('div', 'margin:0 14px 8px;font-size:12px;color:#9ca3af',
      dados.feitas + ' de ' + dados.total + ' concluídas' + (pct === 100 ? ' — parabéns! 🏆' : '')));

    var lista = el('div', 'padding:0 8px 6px');
    dados.missoes.forEach(function (m) {
      var it = el('div', 'display:flex;gap:10px;padding:8px 6px;border-radius:8px;' + (m.disponivel ? '' : 'opacity:.45'));
      it.appendChild(el('div', 'font-size:18px;width:24px;text-align:center', m.feita ? '✅' : m.icone));
      var tx = el('div', 'flex:1');
      tx.appendChild(el('div', 'font-weight:700;' + (m.feita ? 'text-decoration:line-through;color:#86efac' : ''), m.titulo));
      if (!m.feita) tx.appendChild(el('div', 'font-size:12px;color:#9ca3af;margin-top:2px',
        m.disponivel ? m.dica : 'Disponível quando a Programação da Produção for liberada para o Comercial.'));
      it.appendChild(tx);
      lista.appendChild(it);
    });
    painel.appendChild(lista);

    var rod = el('div', 'display:flex;gap:8px;flex-wrap:wrap;padding:10px 14px 14px;border-top:1px solid #374151');
    var bt = el('button', 'flex:1;min-width:140px;background:' + LARANJA + ';color:#fff;border:0;border-radius:10px;' +
      'padding:9px 10px;font:800 13px Arial,Helvetica,sans-serif;cursor:pointer', '▶ Começar tour');
    bt.type = 'button';
    bt.onclick = function () {
      if (NO_COMERCIAL) { fecharPainel(); iniciarTour(); }
      else location.href = '/comercial?tour=1';
    };
    rod.appendChild(bt);
    var rb = el('button', 'background:#374151;color:#fff;border:0;border-radius:10px;padding:9px 10px;' +
      'font:700 13px Arial,Helvetica,sans-serif;cursor:pointer', '↺ Recomeçar');
    rb.type = 'button';
    rb.onclick = function () {
      if (!confirm('Recomeçar as missões do zero?')) return;
      req('/api/treino/missoes/reiniciar', 'POST').then(function () { feitasAntes = null; carregarMissoes(); });
    };
    rod.appendChild(rb);
    painel.appendChild(rod);
  }

  // marca busca e "ver detalhes" (missões de tela) — só na tela do vendedor
  function ligarMarcadores() {
    if (!NO_COMERCIAL) return;
    var b = document.getElementById('mp-busca'), marcou = false, tm = null;
    if (b) b.addEventListener('input', function () {
      clearTimeout(tm);
      if (marcou || b.value.trim().length < 3) return;
      tm = setTimeout(function () { marcou = true; evento('busca').then(carregarMissoes); }, 1200);
    });
    var tentativas = 0;
    (function embrulhar() {
      if (typeof window.verDetalhe === 'function' && !window.verDetalhe._treino) {
        var orig = window.verDetalhe;
        window.verDetalhe = function () {
          evento('detalhe').then(carregarMissoes);
          return orig.apply(this, arguments);
        };
        window.verDetalhe._treino = true;
      } else if (++tentativas < 20) setTimeout(embrulhar, 500);
    })();
  }

  // ═══ 🧭 TOUR ══════════════════════════════════════════════════════════════════
  var PASSOS = [
    { alvo: null, tit: 'Bem-vindo ao Portal Comercial! 👋',
      txt: 'Este é o seu painel de vendedor. Vamos ver rapidinho para que serve cada parte. Use “Próximo” para avançar.' },
    { alvo: '#tabbtn-pedidos', aba: 'pedidos', tit: '🧾 Meus Pedidos',
      txt: 'Aqui ficam todos os SEUS pedidos, do momento em que são importados até a entrega.' },
    { alvo: '#mp-busca', aba: 'pedidos', tit: '🔎 Busca',
      txt: 'Digite o número do pedido, o nome do cliente ou o número da nota fiscal. Ela procura em todas as etapas.' },
    { alvo: '#mp-novidades', aba: 'pedidos', tit: '🔔 Novidades',
      txt: 'Avisos do que mudou nos seus pedidos: produção terminou, nota fiscal saiu, cliente precisa autorizar o frete...' },
    { alvo: '#com-cards', aba: 'pedidos', tit: '📊 Resumo',
      txt: 'Quantos pedidos você tem em cada situação. Clique num cartão para ir direto àquela lista.' },
    { alvo: '#mp-secoes', aba: 'pedidos', tit: '📋 Pedidos por etapa',
      txt: 'Os pedidos aparecem separados pela etapa em que estão. A seção “com você” mostra o que depende de uma ação SUA.' },
    { alvo: '#mp-secoes .mp-ico', aba: 'pedidos', tit: '⋯ Ações do pedido',
      txt: 'Neste botão ficam as ações de cada pedido: ver detalhes, PDF, cotação de frete, cliente retira, nota fiscal...' },
    { alvo: '#tabbtn-importar', tit: '📥 Importar pedido',
      txt: 'Para lançar um pedido novo: envie o PDF (ou foto) e confira cliente e itens antes de salvar. Depois você passa as informações para a produção.' },
    { alvo: '#tabbtn-estoque', tit: '🏷️ Estoque dos meus clientes',
      txt: 'Copos personalizados que ficam guardados para o cliente. Daqui você pede entregas desse estoque.' },
    { alvo: '#mp-som-btn', tit: '🔔 Aviso sonoro',
      txt: 'Liga ou desliga o som que toca quando chega novidade nos seus pedidos.' },
    { alvo: 'button[onclick*="modal-ajuda-comercial"]', tit: '❓ Ajuda',
      txt: 'Se esquecer algo, a Ajuda explica cada parte da tela.' },
    { alvo: null, tit: 'Agora é com você! 🎯',
      txt: 'Abra o botão 🎯 Missões (canto de baixo, à direita) e faça cada tarefa. Elas ficam marcadas sozinhas quando você conclui. Aqui é treino: pode errar à vontade!' }
  ];
  var tourI = 0, tourEls = null;

  function iniciarTour() {
    fecharTour();
    tourI = 0;
    var sombra = el('div', 'position:fixed;z-index:2147483004;border-radius:10px;pointer-events:none;' +
      'box-shadow:0 0 0 9999px rgba(0,0,0,.62);border:3px solid ' + LARANJA + ';transition:all .25s');
    var tampa = el('div', 'position:fixed;inset:0;z-index:2147483003');      // impede cliques durante o tour
    var balao = el('div', 'position:fixed;z-index:2147483005;width:340px;max-width:calc(100vw - 24px);background:#fff;' +
      'color:#111827;border-radius:14px;padding:16px;box-shadow:0 12px 36px rgba(0,0,0,.5);font:14px/1.45 Arial,Helvetica,sans-serif');
    document.body.appendChild(tampa); document.body.appendChild(sombra); document.body.appendChild(balao);
    tourEls = { sombra: sombra, balao: balao, tampa: tampa };
    document.addEventListener('keydown', teclaTour);
    mostrarPasso();
  }
  function teclaTour(e) {
    if (!tourEls) return;
    if (e.key === 'Escape') fecharTour();
    else if (e.key === 'ArrowRight' || e.key === 'Enter') irPasso(1);
    else if (e.key === 'ArrowLeft') irPasso(-1);
  }
  function fecharTour() {
    if (!tourEls) return;
    tourEls.sombra.remove(); tourEls.balao.remove(); tourEls.tampa.remove();
    tourEls = null;
    document.removeEventListener('keydown', teclaTour);
  }
  function visivel(e) { if (!e || e.offsetParent === null) return false; var r = e.getBoundingClientRect(); return r.width > 8 && r.height > 8; }
  function irPasso(d) {
    var n = tourI + d;
    while (n > 0 && n < PASSOS.length - 1 && PASSOS[n].alvo && !alvoDe(PASSOS[n])) n += d;   // pula o que não existe
    if (n < 0) return;
    if (n >= PASSOS.length) {
      fecharTour();
      evento('tour').then(function () { carregarMissoes(); if (!painel) abrirPainel(); });
      return;
    }
    tourI = n; mostrarPasso();
  }
  function alvoDe(p) {
    if (p.aba && typeof window.switchTab === 'function' && document.getElementById('tab-' + p.aba) &&
        document.getElementById('tab-' + p.aba).style.display === 'none') {
      try { window.switchTab(p.aba); } catch (e) {}
    }
    var e = p.alvo ? document.querySelector(p.alvo) : null;
    return visivel(e) ? e : null;
  }
  function mostrarPasso() {
    var p = PASSOS[tourI], e = alvoDe(p), s = tourEls.sombra, b = tourEls.balao;
    b.innerHTML = '';
    b.appendChild(el('div', 'font-size:12px;color:' + LARANJA + ';font-weight:800;margin-bottom:4px',
      '🎓 TOUR · ' + (tourI + 1) + ' de ' + PASSOS.length));
    b.appendChild(el('div', 'font-weight:800;font-size:16px;margin-bottom:6px', p.tit));
    b.appendChild(el('div', '', p.txt));
    var rod = el('div', 'display:flex;gap:8px;justify-content:space-between;align-items:center;margin-top:14px');
    var sair = el('button', 'background:none;border:0;color:#6b7280;cursor:pointer;font:600 13px Arial', 'Sair do tour');
    sair.type = 'button'; sair.onclick = fecharTour; rod.appendChild(sair);
    var dir = el('div', 'display:flex;gap:6px');
    if (tourI > 0) {
      var ant = el('button', 'background:#e5e7eb;border:0;border-radius:8px;padding:8px 12px;cursor:pointer;font:700 13px Arial', '← Anterior');
      ant.type = 'button'; ant.onclick = function () { irPasso(-1); }; dir.appendChild(ant);
    }
    var prox = el('button', 'background:' + LARANJA + ';color:#fff;border:0;border-radius:8px;padding:8px 14px;cursor:pointer;font:800 13px Arial',
      tourI === PASSOS.length - 1 ? 'Concluir ✓' : 'Próximo →');
    prox.type = 'button'; prox.onclick = function () { irPasso(1); }; dir.appendChild(prox);
    rod.appendChild(dir); b.appendChild(rod);

    if (e) {
      e.scrollIntoView({ block: 'center' });
      var r = e.getBoundingClientRect(), pad = 6;
      var alt = Math.min(r.height, window.innerHeight * 0.45);
      s.style.display = '';
      s.style.left = (r.left - pad) + 'px'; s.style.top = (r.top - pad) + 'px';
      s.style.width = (r.width + pad * 2) + 'px'; s.style.height = (alt + pad * 2) + 'px';
      var bw = b.offsetWidth, bh = b.offsetHeight;
      var top = r.top + alt + pad + 14;
      if (top + bh > window.innerHeight - alturaFaixa() - 10) top = Math.max(10, r.top - pad - bh - 14);
      var left = Math.min(Math.max(10, r.left), window.innerWidth - bw - 10);
      b.style.top = top + 'px'; b.style.left = left + 'px'; b.style.transform = '';
    } else {
      s.style.display = 'none';
      b.style.top = '50%'; b.style.left = '50%'; b.style.transform = 'translate(-50%,-50%)';
      tourEls.tampa.style.background = 'rgba(0,0,0,.62)';
      return;
    }
    tourEls.tampa.style.background = 'transparent';
  }

  // ═══ 📋 TURMA (painel do treinador) ═══════════════════════════════════════════
  var turmaEl = null, turmaTimer = null;
  function fmtHora(s) { return s ? s.slice(8, 10) + '/' + s.slice(5, 7) + ' ' + s.slice(11, 16) : '—'; }
  function abrirTurma() {
    if (turmaEl) return;
    turmaEl = el('div', 'position:fixed;inset:0;z-index:2147483002;background:rgba(0,0,0,.6);display:flex;align-items:flex-start;' +
      'justify-content:center;padding:30px 12px;overflow:auto');
    turmaEl.onclick = function (e) { if (e.target === turmaEl) fecharTurma(); };
    var caixa = el('div', 'width:980px;max-width:100%;background:#111827;color:#f3f4f6;border:2px solid ' + LARANJA + ';border-radius:14px;' +
      'box-shadow:0 12px 36px rgba(0,0,0,.6);font:14px/1.4 Arial,Helvetica,sans-serif');
    caixa.id = 'pratic-turma-caixa';
    turmaEl.appendChild(caixa);
    document.body.appendChild(turmaEl);
    carregarTurma();
    turmaTimer = setInterval(carregarTurma, 15000);
  }
  function fecharTurma() { clearInterval(turmaTimer); if (turmaEl) turmaEl.remove(); turmaEl = null; }
  function carregarTurma() {
    var caixa = document.getElementById('pratic-turma-caixa');
    if (!caixa) return;
    req('/api/treino/turma').then(function (d) {
      caixa.innerHTML = '';
      var topo = el('div', 'display:flex;justify-content:space-between;align-items:center;padding:14px 18px;border-bottom:1px solid #374151;gap:10px;flex-wrap:wrap');
      var tt = el('div'); tt.appendChild(el('div', 'font-weight:800;font-size:17px', '📋 Turma do treinamento — Comercial'));
      tt.appendChild(el('div', 'font-size:12px;color:#9ca3af', 'Atualiza sozinho a cada 15 s · ' + fmtHora(d.agora) +
        (d.programacao_liberada ? '' : ' · Programação desligada: missões de informações/pagamento/prioridade ficam de fora')));
      topo.appendChild(tt);
      var x = el('button', 'background:#374151;color:#fff;border:0;border-radius:8px;padding:6px 12px;cursor:pointer;font:700 13px Arial', 'Fechar');
      x.type = 'button'; x.onclick = fecharTurma; topo.appendChild(x);
      caixa.appendChild(topo);
      if (!d.vendedores.length) {
        caixa.appendChild(el('div', 'padding:30px 18px;color:#9ca3af;text-align:center',
          'Nenhum vendedor entrou no treino ainda. Quando alguém do Comercial entrar e abrir 🎯 Missões, aparece aqui.'));
        return;
      }
      d.vendedores.forEach(function (v) {
        var card = el('div', 'padding:14px 18px;border-bottom:1px solid #1f2937');
        var lin = el('div', 'display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:center');
        lin.appendChild(el('div', 'font-weight:800;font-size:15px', '👤 ' + v.nome));
        var pct = v.total ? Math.round(100 * v.feitas / v.total) : 0;
        lin.appendChild(el('div', 'font-weight:800;color:' + (pct === 100 ? '#4ade80' : '#fdba74'),
          v.feitas + '/' + v.total + ' missões' + (pct === 100 ? ' 🏆' : '') + ' · última atividade ' + fmtHora(v.ultima_atividade)));
        card.appendChild(lin);
        var ms = el('div', 'display:flex;flex-wrap:wrap;gap:6px;margin:8px 0');
        v.missoes.forEach(function (m) {
          if (!m.disponivel) return;
          ms.appendChild(el('span', 'font-size:12px;padding:3px 8px;border-radius:12px;' +
            (m.feita ? 'background:#14532d;color:#86efac' : 'background:#374151;color:#9ca3af'),
            (m.feita ? '✓ ' : m.icone + ' ') + m.titulo));
        });
        card.appendChild(ms);
        if (v.acoes.length) {
          var ac = el('div', 'font-size:12px;color:#d1d5db;display:grid;grid-template-columns:auto 1fr;gap:2px 12px');
          v.acoes.forEach(function (a) {
            ac.appendChild(el('span', 'color:#9ca3af', fmtHora(a.em)));
            ac.appendChild(el('span', '', a.acao));
          });
          card.appendChild(ac);
        }
        var ver = el('button', 'margin-top:8px;background:none;border:1px solid ' + LARANJA + ';color:#fdba74;border-radius:8px;' +
          'padding:4px 10px;cursor:pointer;font:700 12px Arial', '👁 Ver a tela dele(a)');
        ver.type = 'button';
        ver.onclick = function () {
          req('/api/auth/treino/entrar', 'POST', { usuario_id: v.id }).then(function (r) {
            try { localStorage.setItem('user_nome', r.usuario.nome); localStorage.setItem('user_role', r.usuario.role);
                  localStorage.setItem('user_username', r.usuario.username); } catch (e) {}
            location.href = '/comercial';   // tela do vendedor (vale também p/ quem é "Também é vendedor")
          }).catch(function (e) { alert(e.message); });
        };
        card.appendChild(ver);
        caixa.appendChild(card);
      });
    }).catch(function (e) { caixa.innerHTML = ''; caixa.appendChild(el('div', 'padding:20px', '❌ ' + e.message)); });
  }

  window.PraticTreino = { abrirTurma: abrirTurma, iniciarTour: iniciarTour };

  // ═══ início ═══════════════════════════════════════════════════════════════════
  carregarMissoes().then(function () {
    if (!dados) return;
    ligarMarcadores();
    setInterval(carregarMissoes, 15000);
    window.addEventListener('resize', function () { if (botao) desenharBotao(); if (painel) desenharPainel(); });
    if (NO_COMERCIAL && /[?&]tour=1/.test(location.search)) setTimeout(iniciarTour, 1500);
  });
})();
