/* Mostra em que servidor o usuário está. Controlado pela variável PRATIC_AMBIENTE
   no Coolify: "treinamento" (faixa laranja), "teste" (faixa roxa) ou vazio/"producao"
   (nada aparece). Evita lançar pedido real no treino — ou o contrário.

   No treinamento, o Gestor que conduz o treino ganha na faixa os botões
   "Ver como": Gestor · Comercial · Produção · Estoque · Expedição — troca de
   perfil com um clique, sem digitar senha e sem abrir outra janela. */
(function () {
  var CORES = {
    treinamento: { bg: '#f97316', txt: '🎓 AMBIENTE DE TREINAMENTO — nada do que é feito aqui vale de verdade', tit: '🎓 TREINO · ' },
    teste:       { bg: '#7c3aed', txt: '🧪 SERVIDOR DE TESTE — não é o sistema oficial', tit: '🧪 TESTE · ' }
  };

  function el(tag, css, txt) {
    var e = document.createElement(tag);
    if (css) e.style.cssText = css;
    if (txt != null) e.textContent = txt;
    return e;
  }

  function aplicar(amb) {
    var c = CORES[amb];
    if (!c || document.getElementById('pratic-ambiente-faixa')) return;
    var f = el('div', 'position:fixed;left:0;right:0;bottom:0;z-index:2147483000;background:' + c.bg +
      ';color:#fff;font:700 13px/1.2 Arial,Helvetica,sans-serif;text-align:center;padding:7px 10px;' +
      'letter-spacing:.3px;box-shadow:0 -2px 10px rgba(0,0,0,.35);pointer-events:none');
    f.id = 'pratic-ambiente-faixa';
    f.setAttribute('role', 'status');
    var txt = el('span', '', c.txt);
    txt.id = 'pratic-ambiente-txt';
    f.appendChild(txt);
    document.body.appendChild(f);
    document.body.style.paddingBottom = '34px';
    // borda colorida em volta da tela inteira: dá para perceber mesmo sem ler a faixa
    var b = el('div', 'position:fixed;inset:0;border:4px solid ' + c.bg + ';pointer-events:none;z-index:2147482999');
    document.body.appendChild(b);
    if (document.title.indexOf(c.tit) !== 0) document.title = c.tit + document.title;
    var obs = new MutationObserver(function () { if (document.title.indexOf(c.tit) !== 0) document.title = c.tit + document.title; });
    var t = document.querySelector('title'); if (t) obs.observe(t, { childList: true });
    window.PRATIC_AMBIENTE = amb;
    if (amb === 'treinamento') montarTrocaPerfil(f, txt);
  }

  // ─── Modo treinador ──────────────────────────────────────────────────────────
  function montarTrocaPerfil(faixa, txt) {
    fetch('/api/auth/treino/perfis', { credentials: 'same-origin', cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || !d.perfis) return;           // não é o treinador: faixa normal
        faixa.style.pointerEvents = 'auto';
        faixa.style.display = 'flex';
        faixa.style.flexWrap = 'wrap';
        faixa.style.alignItems = 'center';
        faixa.style.justifyContent = 'center';
        faixa.style.gap = '6px 8px';
        faixa.style.padding = '5px 10px';
        txt.textContent = '🎓 TREINAMENTO — vendo como: ' + d.atual.nome;
        txt.style.marginRight = '6px';

        d.perfis.forEach(function (p) {
          var ativo = p.role === d.atual.role;
          var btn = el('button',
            'font:700 12px Arial,Helvetica,sans-serif;padding:4px 10px;border-radius:14px;cursor:pointer;' +
            'border:2px solid #fff;' + (ativo ? 'background:#fff;color:#c2410c;' : 'background:rgba(0,0,0,.18);color:#fff;'),
            p.rotulo + (p.usuarios.length > 1 ? ' ▾' : ''));
          btn.type = 'button';
          btn.title = p.usuarios.length
            ? 'Entrar como ' + p.rotulo.replace(/^\S+\s/, '')
            : 'Nenhum usuário com esse perfil — será criado um usuário de treino';
          btn.onclick = function (ev) {
            ev.stopPropagation();
            if (p.usuarios.length > 1) abrirMenu(btn, p, d);
            else if (p.usuarios.length === 1) entrar({ usuario_id: p.usuarios[0].id }, btn);
            else entrar({ role: p.role }, btn);
          };
          faixa.appendChild(btn);
        });
        // Atualizar os dados do treino com uma cópia do servidor de origem
        var sep = el('span', 'width:1px;height:20px;background:rgba(255,255,255,.5);margin:0 4px');
        faixa.appendChild(sep);
        var bt = el('button',
          'font:700 12px Arial,Helvetica,sans-serif;padding:4px 10px;border-radius:14px;cursor:pointer;' +
          'border:2px solid #fff;background:#7c2d12;color:#fff', '🔄 Atualizar dados');
        bt.type = 'button';
        bt.title = d.dados_de ? 'Dados copiados de ' + d.origem + ' em ' + d.dados_de : 'Copiar os dados atuais de ' + d.origem;
        bt.onclick = function (ev) { ev.stopPropagation(); atualizarDados(d, bt); };
        faixa.appendChild(bt);
        if (d.dados_de) faixa.appendChild(el('span', 'font-size:11px;font-weight:600;opacity:.9', 'dados de ' + d.dados_de));

        document.body.style.paddingBottom = faixa.offsetHeight + 'px';
        window.addEventListener('resize', function () { document.body.style.paddingBottom = faixa.offsetHeight + 'px'; });
      })
      .catch(function () {});
  }

  function fecharMenu() {
    var m = document.getElementById('pratic-treino-menu');
    if (m) m.remove();
  }

  function abrirMenu(btn, perfil, d) {
    var jaAberto = document.getElementById('pratic-treino-menu');
    fecharMenu();
    if (jaAberto && jaAberto.getAttribute('data-role') === perfil.role) return;
    var r = btn.getBoundingClientRect();
    var m = el('div', 'position:fixed;z-index:2147483001;background:#1f2937;border:2px solid #f97316;border-radius:10px;' +
      'box-shadow:0 8px 24px rgba(0,0,0,.5);padding:6px;max-height:60vh;overflow:auto;min-width:200px;' +
      'font:600 13px Arial,Helvetica,sans-serif;color:#fff;bottom:' + (window.innerHeight - r.top + 6) + 'px;' +
      'left:' + Math.max(8, Math.min(r.left, window.innerWidth - 230)) + 'px');
    m.id = 'pratic-treino-menu';
    m.setAttribute('data-role', perfil.role);
    m.appendChild(el('div', 'padding:4px 8px 6px;color:#fdba74;font-size:11px;text-transform:uppercase;letter-spacing:.5px',
      'Entrar como ' + perfil.rotulo.replace(/^\S+\s/, '')));
    perfil.usuarios.forEach(function (u) {
      var atual = u.id === d.atual.id;
      var it = el('button', 'display:block;width:100%;text-align:left;padding:7px 10px;border:0;border-radius:6px;cursor:pointer;' +
        'font:inherit;color:#fff;background:' + (atual ? '#f97316' : 'transparent'),
        u.nome + (u.id === d.treinador.id ? '  (você)' : '') + (atual ? '  ✓' : ''));
      it.type = 'button';
      it.onmouseenter = function () { if (!atual) it.style.background = '#374151'; };
      it.onmouseleave = function () { if (!atual) it.style.background = 'transparent'; };
      it.onclick = function (ev) { ev.stopPropagation(); entrar({ usuario_id: u.id }, btn); };
      m.appendChild(it);
    });
    document.body.appendChild(m);
  }
  document.addEventListener('click', fecharMenu);

  function entrar(corpo, btn) {
    fecharMenu();
    if (btn) { btn.disabled = true; btn.style.opacity = '.6'; }
    fetch('/api/auth/treino/entrar', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(corpo)
    })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (!res.ok) throw new Error((res.j && res.j.detail) || 'Não foi possível trocar de perfil.');
        var u = res.j.usuario;
        try {
          localStorage.setItem('user_nome', u.nome);
          localStorage.setItem('user_role', u.role);
          localStorage.setItem('user_username', u.username);
        } catch (e) {}
        // "/" leva cada perfil para a tela dele (Comercial → Meus Pedidos, Produção → setor...)
        window.location.href = '/';
      })
      .catch(function (e) {
        alert(e.message);
        if (btn) { btn.disabled = false; btn.style.opacity = ''; }
      });
  }

  function atualizarDados(d, bt) {
    fecharMenu();
    if (!d.copia_configurada) {
      alert('A cópia automática ainda não está configurada.\n\nFalta a variável PRATIC_SYNC_TOKEN no Coolify (igual no app de treino e no app de teste).');
      return;
    }
    if (!confirm('Copiar agora os dados de ' + d.origem + ' para o treinamento?\n\n' +
                 '• Tudo o que foi feito aqui no treino será apagado e substituído.\n' +
                 '• ' + d.origem + ' não é alterado (só é lido).\n' +
                 '• Pode levar alguns minutos.')) return;
    var ov = el('div', 'position:fixed;inset:0;z-index:2147483002;background:rgba(0,0,0,.7);display:flex;align-items:center;' +
      'justify-content:center;font:700 18px Arial,Helvetica,sans-serif;color:#fff;text-align:center;padding:20px',
      '🔄 Copiando os dados de ' + d.origem + '…\nNão feche esta tela.');
    ov.style.whiteSpace = 'pre-line';
    document.body.appendChild(ov);
    bt.disabled = true;
    fetch('/api/treino/atualizar-dados', { method: 'POST', credentials: 'same-origin' })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (!res.ok) throw new Error((res.j && res.j.detail) || 'Não foi possível copiar os dados.');
        alert('✅ ' + res.j.mensagem + (res.j.continua_logado ? '' : '\n\nSeu usuário não existe na origem: entre de novo.'));
        try { localStorage.removeItem('user_nome'); localStorage.removeItem('user_role'); localStorage.removeItem('user_username'); } catch (e) {}
        window.location.href = res.j.continua_logado ? '/' : '/login';
      })
      .catch(function (e) {
        ov.remove(); bt.disabled = false;
        alert('❌ ' + e.message);
      });
  }

  function iniciar() {
    fetch('/api/ambiente', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { if (d && d.ambiente) aplicar(String(d.ambiente).toLowerCase()); })
      .catch(function () {});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar); else iniciar();
})();
