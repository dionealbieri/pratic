/* Atualização automática das telas do PRATIC (a cada 30 s).
 * Atualiza só a tela/aba que está aberta, mantendo filtros e a posição da rolagem.
 * Não atualiza quando atrapalharia: janela (modal) aberta, alguém digitando ou mexendo
 * na tela há poucos segundos, aba do navegador em segundo plano, ou escolhas ainda não
 * enviadas na caixa Pedidos SAC. Quem voltar para a aba recebe a atualização na hora. */
(function () {
  const INTERVALO = 30;           // segundos
  const PAUSA_INTERACAO = 12;     // segundos sem mexer na tela antes de atualizar
  let ultimaAtualizacao = Date.now();
  let ultimaInteracao = 0;
  let rodando = false;
  let chip = null;

  const visivel = (id) => { const e = document.getElementById(id); return !!(e && e.offsetParent !== null); };
  const abaVisivel = (prefixo, abas) => abas.find(t => visivel(prefixo + t));
  // chama a primeira função que existir (o portal da produção usa nomes próprios)
  const chamar = async (...nomes) => { for (const n of nomes) if (typeof window[n] === 'function') return window[n](); };

  // O que atualizar em cada tela (null = tela de formulário/relatório: não mexe)
  function refresher() {
    if (document.getElementById('g-conteudo') && typeof window.carregarGerencial === 'function') {
      return () => chamar('carregarGerencial');            // painel gerencial em tela cheia (gerencial.html)
    }
    const pg = document.querySelector('.page.active');
    if (!pg) return null;
    const nome = pg.id.replace(/^page-/, '');
    switch (nome) {
      case 'dashboard': return () => chamar('loadDashboard');
      case 'producao': {
        const t = abaVisivel('prodpg-content-', ['painel', 'lancamentos', 'feriados']);
        if (t === 'painel') return () => chamar('loadPainelDoDia');
        if (t === 'lancamentos') return () => chamar('loadProducao');
        if (t === 'feriados') return () => chamar('loadFeriados');
        if (!document.getElementById('prodpg-content-painel')) return () => chamar('loadProducao');   // portal da produção
        return null;
      }
      case 'premiacao': return () => chamar('loadPremiacao');
      case 'colaboradores': return () => chamar('loadColaboradores', 'loadColabProd');
      case 'maquinas': return () => chamar('loadMaquinas', 'loadMaqProd');
      case 'graficos': return () => chamar('loadGraficos');
      case 'perdas-sobras': return () => chamar('loadPerdasSobrasDetalhado');
      case 'estoque': return () => chamar('loadEstoque');
      case 'saldo-demanda': return () => chamar('loadSaldoDemanda');
      case 'lista-compras':
        if (!visivel('lc-padrao-container')) return null;   // lista avulsa: está sendo montada à mão
        return async () => {
          lcDados = await api('/estoque/saldo-vs-demanda');   // variável da Lista de Compras (app.js)
          await chamar('renderListaCompras');
          const dt = document.getElementById('lc-ultima-atualizacao');
          if (dt) dt.textContent = '🕐 Atualizado em: ' + new Date().toLocaleString('pt-BR');
        };
      case 'consumo-medio': return () => chamar('loadConsumoMedio');
      case 'gerencial': return () => chamar('loadGerencial');
      case 'programacao': return () => chamar('loadProgramacao');
      case 'epi': return () => chamar('loadEPI');
      case 'pedidos': {
        const t = abaVisivel('ped-tab-', ['fila', 'pedidos', 'clientes', 'transportadora', 'acompanhamento', 'sac']);
        const mapa = { fila: 'loadFila', pedidos: 'loadPedidos', clientes: 'loadClientes',
                       transportadora: 'loadTransportadora', acompanhamento: 'loadAcompanhamento', sac: 'sacCarregar' };
        if (!t) return null;   // Programar Separação: tela de busca, não atualiza sozinha
        return async () => { await chamar(mapa[t]); chamar('checkAlertasPedidos'); };
      }
      default: return null;   // relatórios, pintura, configurações, backup, comunicação (já tem o próprio aviso)
    }
  }

  function janelaAberta() {
    if (document.querySelector('.modal-overlay.open')) return true;
    return Array.from(document.body.children).some(e => {
      if (e === chip) return false;
      const cs = getComputedStyle(e);
      return cs.position === 'fixed' && cs.display !== 'none' && cs.visibility !== 'hidden' &&
             cs.pointerEvents !== 'none' && e.offsetWidth >= innerWidth * 0.8 && e.offsetHeight >= innerHeight * 0.8;
    });
  }

  function escolhasPendentesSac() {
    return Array.from(document.querySelectorAll('#ped-tab-sac select[data-venda]')).some(s =>
      s.offsetParent !== null && s.options[s.selectedIndex] && !s.options[s.selectedIndex].defaultSelected);
  }

  function podeAtualizar() {
    if (document.hidden) return false;
    if (janelaAberta()) return false;
    const a = document.activeElement;
    if (a && a !== document.body && a.matches && a.matches('input, textarea, select, [contenteditable="true"]')) return false;
    if (Date.now() - ultimaInteracao < PAUSA_INTERACAO * 1000) return false;
    if (window.getSelection && String(window.getSelection()).length > 0) return false;   // texto selecionado para copiar
    if (escolhasPendentesSac()) return false;
    return true;
  }

  async function atualizar(forcar) {
    if (rodando) return;
    const fn = refresher();
    if (!fn) { desenharChip(); return; }
    if (!forcar && !podeAtualizar()) return;
    rodando = true;
    const pg = document.querySelector('.page.active') || document.getElementById('g-conteudo');
    const main = document.querySelector('main.main') || document.scrollingElement;
    const rolagemJanela = window.scrollY;
    const rolagemMain = main ? main.scrollTop : 0;
    const alturaAntes = pg ? pg.offsetHeight : 0;
    if (pg) pg.style.minHeight = alturaAntes + 'px';      // evita a tela "pular" enquanto recarrega
    const animAntes = window.Chart && Chart.defaults ? Chart.defaults.animation : undefined;
    if (window.Chart && Chart.defaults) Chart.defaults.animation = false;   // gráficos sem animar a cada 30 s
    try {
      await fn();
      ultimaAtualizacao = Date.now();
    } catch (e) {
      /* falha de rede: tenta na próxima rodada */
    } finally {
      if (window.Chart && Chart.defaults && animAntes !== undefined) Chart.defaults.animation = animAntes;
      if (pg) pg.style.minHeight = '';
      if (main && main !== document.scrollingElement) main.scrollTop = rolagemMain;
      window.scrollTo(0, rolagemJanela);
      rodando = false;
      desenharChip();
    }
  }

  function desenharChip() {
    if (!chip) {
      chip = document.createElement('button');
      chip.type = 'button';
      chip.id = 'auto-refresh-chip';
      chip.title = 'A tela se atualiza sozinha a cada 30 segundos. Clique para atualizar agora.';
      chip.style.cssText = 'position:fixed;right:18px;bottom:16px;z-index:900;background:var(--surface,#151922);' +
        'color:var(--accent,#f5b82e);border:2px solid var(--accent,#f5b82e);border-radius:22px;padding:8px 16px;' +
        'font-size:13.5px;font-weight:700;cursor:pointer;font-family:inherit;box-shadow:0 4px 14px rgba(0,0,0,.35)';
      chip.addEventListener('mouseenter', () => { chip.style.background = 'var(--accent,#f5b82e)'; chip.style.color = '#1a1300'; });
      chip.addEventListener('mouseleave', () => { chip.style.background = 'var(--surface,#151922)'; chip.style.color = 'var(--accent,#f5b82e)'; });
      chip.addEventListener('click', () => atualizar(true));
      document.body.appendChild(chip);
    }
    if (!refresher()) { chip.style.display = 'none'; return; }
    chip.style.display = '';
    const s = Math.round((Date.now() - ultimaAtualizacao) / 1000);
    const txt = s < 5 ? 'agora' : s < 60 ? 'há ' + s + ' s' : 'há ' + Math.floor(s / 60) + ' min';
    chip.textContent = (rodando ? '⏳ Atualizando…' : '🔄 Atualizar') + '  ·  ' + (rodando ? '' : 'atualizado ' + txt);
    if (rodando) chip.textContent = '⏳ Atualizando…';
  }

  ['mousedown', 'keydown', 'wheel', 'touchstart', 'input'].forEach(ev =>
    document.addEventListener(ev, (e) => { if (e.target !== chip) ultimaInteracao = Date.now(); }, { passive: true, capture: true }));

  // trocar de tela conta como dado novo
  document.addEventListener('click', (e) => {
    const n = e.target.closest && e.target.closest('.nav-item, [id^="ptab-"], [id^="prodpg-tab-"]');
    if (n) setTimeout(() => { ultimaAtualizacao = Date.now(); desenharChip(); }, 300);
  }, true);

  // voltou para a aba do navegador depois de um tempo: atualiza já
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && Date.now() - ultimaAtualizacao > INTERVALO * 1000) {
      ultimaInteracao = 0;
      atualizar(false);
    }
  });

  setInterval(() => {
    if (Date.now() - ultimaAtualizacao >= INTERVALO * 1000) atualizar(false);
    else desenharChip();
  }, 5000);

  window.praticAtualizarTela = () => atualizar(true);
  setTimeout(desenharChip, 3000);
})();
