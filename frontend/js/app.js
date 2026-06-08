const API = window.location.origin + '/api';

// ─── UTILS ───────────────────────────────────────────────────────────────────

function fmtNum(n) {
  return Number(n || 0).toLocaleString('pt-BR');
}
function fmtBRL(n) {
  return Number(n || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}
function fmtDate(s) {
  if (!s) return '—';
  const [y, m, d] = s.split('-');
  return `${d}/${m}/${y}`;
}
function mesLabel(mes) {
  if (!mes) return '—';
  const [y, m] = mes.split('-');
  const nomes = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];
  return `${nomes[+m - 1]} ${y}`;
}
function currentMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}
function showAlert(msg, type = 'success') {
  const el = document.getElementById('alert-global');
  el.innerHTML = `<div class="alert alert-${type}">${msg}</div>`;
  setTimeout(() => el.innerHTML = '', 3000);
}

// ─── CONSTANTES DE PERMISSÕES ────────────────────────────────────────────────

const PAGINAS_SISTEMA = [
  { key:'dashboard',     label:'📊 Dashboard'         },
  { key:'producao',      label:'🏭 Produção Diária'   },
  { key:'premiacao',     label:'🏆 Premiação'          },
  { key:'pedidos',       label:'🧾 Pedidos'            },
  { key:'estoque',       label:'📦 Estoque'            },
  { key:'graficos',      label:'📈 Gráficos'           },
  { key:'relatorios',    label:'📋 Relatórios'         },
  { key:'colaboradores', label:'👥 Colaboradores'      },
  { key:'maquinas',      label:'⚙️ Máquinas'           },
  { key:'epi',           label:'🦺 EPI'               },
  { key:'configuracoes', label:'🔧 Configurações'      },
  { key:'backup',        label:'💾 Backup'             },
  { key:'permissoes',    label:'🔐 Controle de Acesso' },
  { key:'empresa',       label:'🏢 Dados da Empresa'   },
  { key:'producao_simplificada', label:'⚡ Lançamento Simplificado (Total Produzido)' }
];

const PORTAIS_MOBILE = [
  { key:'mobile',         label:'📱 Mobile Operador',  url:'/mobile'          },
  { key:'estoque_mobile', label:'📦 Mobile Estoque',   url:'/estoque-mobile'  },
];

const TODAS_PAGINAS = [...PAGINAS_SISTEMA, ...PORTAIS_MOBILE];

const PERFIS = [
  { key:'gestor',    label:'🖥️ Gestor' },
  { key:'producao',  label:'🏭 Produção' },
  { key:'comercial', label:'🏢 Comercial' },
  { key:'estoque',   label:'📦 Estoque' },
];

let permissoesAtuais = {};
let chartDashEvolucaoInstance = null;
let chartDashPerdasTipoInstance = null;

async function api(path, method = 'GET', body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(API + path, opts);
  if (r.status === 401) {
    window.location.href = '/login?redirect=' + encodeURIComponent(window.location.pathname + window.location.search);
    return new Promise(() => {});
  }
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || 'Erro na requisição');
  return data;
}

async function sairSistema() {
  if (!confirm('Deseja realmente sair?')) return;
  try {
    await fetch('/api/auth/logout', { method: 'POST' });
  } catch (e) {
    console.error(e);
  }
  localStorage.removeItem('user_nome');
  localStorage.removeItem('user_role');
  localStorage.removeItem('user_username');
  window.location.href = '/login';
}

function highlightField(id, hasError, errorMsg = '') {
  const el = document.getElementById(id);
  if (!el) return;
  const parent = el.parentElement;
  const existingError = parent.querySelector('.error-message');
  if (existingError) {
    existingError.remove();
  }
  if (hasError) {
    el.classList.add('invalid-field');
    if (errorMsg) {
      const errSpan = document.createElement('span');
      errSpan.className = 'error-message';
      errSpan.textContent = errorMsg;
      parent.appendChild(errSpan);
    }
  } else {
    el.classList.remove('invalid-field');
  }
}

function clearFieldHighlights(containerId) {
  const container = containerId ? document.getElementById(containerId) : document;
  if (!container) return;
  container.querySelectorAll('.invalid-field').forEach(el => {
    el.classList.remove('invalid-field');
  });
  container.querySelectorAll('.error-message').forEach(el => {
    el.remove();
  });
}

// ─── NAVIGATION ──────────────────────────────────────────────────────────────

const pageTitles = {
  dashboard: 'Dashboard',
  producao: 'Produção Diária',
  premiacao: 'Premiação',
  colaboradores: 'Colaboradores',
  maquinas: 'Máquinas',
  configuracoes: 'Configurações',
  graficos: 'Análise Gráfica',
  relatorios: 'Relatórios',
  estoque: 'Estoque',
  pedidos: 'Pedidos & Fila de Produção',
  backup: 'Backup & Restauração',
  epi: 'Controle de EPI',
  empresa: 'Dados da Empresa',
  permissoes: 'Controle de Acesso'
};

const PAGE_META_MAIN = {
  dashboard:     { icon:'📊', label:'Dashboard', section:'Visão Geral' },
  producao:      { icon:'🏭', label:'Produção Diária', section:'Lançamentos' },
  premiacao:     { icon:'🏆', label:'Premiação', section:'Lançamentos' },
  colaboradores: { icon:'👥', label:'Colaboradores', section:'Cadastros' },
  maquinas:      { icon:'⚙️', label:'Máquinas', section:'Cadastros' },
  pedidos:       { icon:'🧾', label:'Pedidos', section:'Operações' },
  estoque:       { icon:'📦', label:'Estoque', section:'Operações' },
  epi:           { icon:'🦺', label:'EPI', section:'Operações' },
  graficos:      { icon:'📈', label:'Gráficos', section:'Análises' },
  relatorios:    { icon:'📋', label:'Relatórios', section:'Análises' },
  configuracoes: { icon:'🔧', label:'Configurações', section:'Sistema' },
  backup:        { icon:'💾', label:'Backup', section:'Sistema' },
  permissoes:    { icon:'🔐', label:'Controle de Acesso', section:'Sistema' },
  empresa:       { icon:'🏢', label:'Dados da Empresa', section:'Sistema' }
};

let perfilAtual = 'gestor';
let paginasLiberadas = Object.keys(PAGE_META_MAIN);

function getPerfilAtual() {
  const params = new URLSearchParams(window.location.search);
  return (params.get('perfil') || params.get('setor') || 'gestor').toLowerCase();
}

async function carregarAcessoPrincipal() {
  let me;
  try {
    me = await api('/auth/me');
    const elNomeTxt = document.getElementById('topbar-user-name-txt');
    if (elNomeTxt) elNomeTxt.textContent = me.nome;
    
    perfilAtual = me.role;
    paginasLiberadas = me.permissions
      ? me.permissions.split(',').map(p => p.trim()).filter(p => PAGE_META_MAIN[p])
      : (perfilAtual === 'gestor' ? Object.keys(PAGE_META_MAIN) : ['dashboard']);
    
    const path = window.location.pathname;
    const params = new URLSearchParams(window.location.search);
    const temPaginaSolicitada = params.has('page') || params.has('pagina') || params.has('perfil') || params.has('setor');

    if ((path === '/' || path === '/index.html') && !temPaginaSolicitada) {
      if (me.role === 'producao') {
        window.location.href = '/producao-setor';
        return;
      } else if (me.role === 'comercial') {
        // Comercial agora pode usar o painel principal quando tiver outras abas liberadas
        // pelo Controle de Acesso. Antes o sistema sempre redirecionava para /comercial,
        // que é uma tela simplificada somente de pedidos.
        const somentePedidos = paginasLiberadas.every(p => ['pedidos'].includes(p));
        if (somentePedidos) {
          window.location.href = '/comercial';
          return;
        }
      } else if (me.role === 'estoque') {
        window.location.href = '/estoque-mobile';
        return;
      }
    }
  } catch (e) {
    window.location.href = '/login?redirect=' + encodeURIComponent(window.location.pathname + window.location.search);
    return;
  }

  const labelPerfil = {
    gestor: '🖥️ Setor Gestor',
    producao: '🏭 Setor Produção',
    comercial: '🏢 Setor Comercial',
    estoque: '📦 Setor Estoque'
  }[perfilAtual] || '🖥️ Setor Gestor';

  const sectorBadgeEl = document.getElementById('topbar-setor');
  if (sectorBadgeEl) {
    sectorBadgeEl.textContent = labelPerfil;
    sectorBadgeEl.style.display = '';
  }

  montarMenuPrincipal();
}

function montarMenuPrincipal() {
  const nav = document.querySelector('.sidebar nav');
  if (!nav) return;
  const sections = {};
  paginasLiberadas.forEach(key => {
    const cfg = PAGE_META_MAIN[key];
    if (!document.getElementById('page-' + key)) return;
    if (!sections[cfg.section]) sections[cfg.section] = [];
    sections[cfg.section].push({key, ...cfg});
  });
  nav.innerHTML = Object.entries(sections).map(([sec, items]) => `
    <div class="nav-section">${sec}</div>
    ${items.map(item => `
      <a class="nav-item" data-page="${item.key}" onclick="showPage('${item.key}')" style="cursor:pointer">
        <span class="icon">${item.icon}</span> ${item.label}
        ${item.key === 'pedidos' ? '<span id="nav-pedidos-badge" style="display:none;background:var(--danger);color:#fff;font-size:10px;font-weight:700;padding:2px 6px;border-radius:20px;margin-left:4px">!</span>' : ''}
        ${item.key === 'estoque' ? '<span id="nav-alerta-badge" style="display:none;background:var(--danger);color:#fff;font-size:10px;font-weight:700;padding:2px 6px;border-radius:20px;margin-left:4px">!</span>' : ''}
        ${item.key === 'epi' ? '<span id="nav-epi-badge" style="display:none;background:var(--danger);color:#fff;font-size:10px;font-weight:700;padding:2px 6px;border-radius:20px;margin-left:4px">!</span>' : ''}
      </a>`).join('')}
  `).join('');
}

function paginaPermitida(name) {
  return perfilAtual === 'gestor' || paginasLiberadas.includes(name);
}

function showPage(name) {
  if (!paginaPermitida(name)) {
    showAlert('Acesso não liberado para este perfil.', 'danger');
    return;
  }
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const pageEl = document.getElementById('page-' + name);
  if (pageEl) pageEl.classList.add('active');
  document.querySelectorAll('.nav-item').forEach(n => {
    if ((n.dataset && n.dataset.page === name) || (n.getAttribute('onclick') && n.getAttribute('onclick').includes("'" + name + "'"))) {
      n.classList.add('active');
    }
  });
  document.getElementById('topbar-title').textContent = pageTitles[name] || name;

  const handlers = {
    dashboard: loadDashboard,
    producao: loadProducao,
    premiacao: loadPremiacao,
    colaboradores: loadColaboradores,
    maquinas: loadMaquinas,
    configuracoes: loadConfiguracoes,
    graficos: loadGraficos,
    relatorios: loadRelatorios,
    estoque: loadEstoque,
    pedidos: loadPedidos_init,
    backup: () => {},
    epi: loadEPI,
    empresa: loadEmpresa,
    permissoes: loadPermissoes
  };
  if (handlers[name]) handlers[name]();
}

// ─── MODAL ───────────────────────────────────────────────────────────────────

function openModal(id) { document.getElementById(id).classList.add('open'); }
function closeModal(id) { document.getElementById(id).classList.remove('open'); }

document.querySelectorAll('.modal-overlay').forEach(m => {
  m.addEventListener('click', e => { if (e.target === m) m.classList.remove('open'); });
});

// ─── DASHBOARD ───────────────────────────────────────────────────────────────

async function loadDashboard() {
  const mesEl = document.getElementById('dash-mes');
  if (!mesEl.value) mesEl.value = currentMonth();
  const mes = mesEl.value;
  document.getElementById('topbar-mes').textContent = mesLabel(mes);

  const cardsEl = document.getElementById('dash-cards');
  if (cardsEl) {
    cardsEl.innerHTML = `
      <div class="card"><div class="skeleton skeleton-title"></div><div class="skeleton skeleton-value"></div><div class="skeleton skeleton-text"></div></div>
      <div class="card"><div class="skeleton skeleton-title"></div><div class="skeleton skeleton-value"></div><div class="skeleton skeleton-text"></div></div>
      <div class="card"><div class="skeleton skeleton-title"></div><div class="skeleton skeleton-value"></div><div class="skeleton skeleton-text"></div></div>
      <div class="card"><div class="skeleton skeleton-title"></div><div class="skeleton skeleton-value"></div><div class="skeleton skeleton-text"></div></div>
      <div class="card"><div class="skeleton skeleton-title"></div><div class="skeleton skeleton-value"></div><div class="skeleton skeleton-text"></div></div>
      <div class="card"><div class="skeleton skeleton-title"></div><div class="skeleton skeleton-value"></div><div class="skeleton skeleton-text"></div></div>
      <div class="card"><div class="skeleton skeleton-title"></div><div class="skeleton skeleton-value"></div><div class="skeleton skeleton-text"></div></div>
      <div class="card"><div class="skeleton skeleton-title"></div><div class="skeleton skeleton-value"></div><div class="skeleton skeleton-text"></div></div>
    `;
  }

  try {
    const data = await api('/premiacao/dashboard/' + mes);

    const totalProd = data.total_producao_geral || 0;
    const elegiveis = data.operadores.filter(o => o.elegivel).length;
    const pctPerda = (totalProd > 0 ? (data.total_perdas_geral / totalProd * 100).toFixed(1) : '0.0');

    // 1. CARDS
    document.getElementById('dash-cards').innerHTML = `
      <div class="card">
        <div class="card-label">Total Produzido</div>
        <div class="card-value accent">${fmtNum(totalProd)}</div>
        <div class="card-sub">${mesLabel(mes)}</div>
      </div>
      <div class="card">
        <div class="card-label">Média Diária Geral</div>
        <div class="card-value info">${fmtNum(data.media_geral)}</div>
        <div class="card-sub">peças / dia</div>
      </div>
      <div class="card">
        <div class="card-label">Aderência à Meta</div>
        <div class="card-value success">${data.aderencia_meta_percentual}%</div>
        <div class="card-sub">meta de 8.000 peças</div>
      </div>
      <div class="card">
        <div class="card-label">Índice de Perdas</div>
        <div class="card-value ${data.total_perdas_geral > 0 ? 'negative' : 'neutral'}">${pctPerda}%</div>
        <div class="card-sub">${fmtNum(data.total_perdas_geral)} peças perdidas</div>
      </div>
      <div class="card">
        <div class="card-label">Custo das Perdas</div>
        <div class="card-value ${data.custo_perdas_geral > 0 ? 'negative' : 'neutral'}">${fmtBRL(data.custo_perdas_geral)}</div>
        <div class="card-sub">estoque estimado</div>
      </div>
      <div class="card">
        <div class="card-label">Pedidos Críticos</div>
        <div class="card-value ${data.pedidos_atrasados > 0 ? 'negative' : 'neutral'}">${data.pedidos_atrasados}</div>
        <div class="card-sub">${data.pedidos_pendentes} pendentes no total</div>
      </div>
      <div class="card">
        <div class="card-label">Pendências de EPI</div>
        <div class="card-value ${data.epi_vencidos_count > 0 ? 'negative' : 'neutral'}">${data.epi_vencidos_count}</div>
        <div class="card-sub">funcionários com EPI vencido</div>
      </div>
      <div class="card">
        <div class="card-label">Insumos Críticos</div>
        <div class="card-value ${data.estoque_alertas_count > 0 ? 'negative' : 'neutral'}">${data.estoque_alertas_count}</div>
        <div class="card-sub">produtos abaixo do mínimo</div>
      </div>
    `;

    // 2. GRAFICOS
    if (chartDashEvolucaoInstance) {
      chartDashEvolucaoInstance.destroy();
    }
    const ctxEvolucao = document.getElementById('chart-dash-evolucao').getContext('2d');
    const labelsEvolucao = data.evolucao_diaria.map(item => {
      const partes = item.data.split('-');
      return `${partes[2]}/${partes[1]}`;
    });
    const producoes = data.evolucao_diaria.map(item => item.producao);
    const perdas = data.evolucao_diaria.map(item => item.perda);

    chartDashEvolucaoInstance = new Chart(ctxEvolucao, {
      type: 'line',
      data: {
        labels: labelsEvolucao,
        datasets: [
          {
            label: 'Produção Real',
            data: producoes,
            borderColor: '#3b82f6',
            backgroundColor: 'rgba(59, 130, 246, 0.1)',
            borderWidth: 2,
            tension: 0.3,
            fill: true
          },
          {
            label: 'Perdas (Desperdício)',
            data: perdas,
            borderColor: '#ef4444',
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            borderWidth: 2,
            tension: 0.3,
            fill: true
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'top',
            labels: { color: '#e8eaf0', font: { family: 'DM Sans' } }
          }
        },
        scales: {
          x: {
            grid: { color: '#2a2f3f' },
            ticks: { color: '#6b7280' }
          },
          y: {
            grid: { color: '#2a2f3f' },
            ticks: { color: '#6b7280' }
          }
        }
      }
    });

    if (chartDashPerdasTipoInstance) {
      chartDashPerdasTipoInstance.destroy();
    }
    const ctxPerdasTipo = document.getElementById('chart-dash-perdas-tipo').getContext('2d');
    const labelsPerdasTipo = data.perdas_por_tipo.map(item => item.tipo_perda);
    const qtdsPerdasTipo = data.perdas_por_tipo.map(item => item.quantidade);

    chartDashPerdasTipoInstance = new Chart(ctxPerdasTipo, {
      type: 'doughnut',
      data: {
        labels: labelsPerdasTipo.length > 0 ? labelsPerdasTipo : ['Nenhuma perda registrada'],
        datasets: [{
          data: qtdsPerdasTipo.length > 0 ? qtdsPerdasTipo : [1],
          backgroundColor: qtdsPerdasTipo.length > 0
            ? ['#ef4444', '#f0b429', '#3b82f6', '#10b981', '#a855f7', '#6b7280']
            : ['#2a2f3f'],
          borderWidth: 1,
          borderColor: '#161920'
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'right',
            labels: { color: '#e8eaf0', font: { family: 'DM Sans' } }
          }
        }
      }
    });

    // 3. RANKING
    const rankEl = document.getElementById('dash-ranking');
    if (!data.operadores.length) {
      rankEl.innerHTML = '<p class="text-muted" style="padding:10px 0">Nenhum dado para este mês.</p>';
    } else {
      rankEl.innerHTML = data.operadores.map((op, i) => `
        <div class="rank-card">
          <div class="rank-num ${i === 0 ? 'gold' : i === 1 ? 'silver' : ''}">${i + 1}º</div>
          <div class="rank-info">
            <div class="rank-name">${op.colaborador}</div>
            <div class="rank-detail">
              Média: ${fmtNum(Math.round(op.media_diaria || 0))} |
              Total: ${fmtNum(op.total_producao)} |
              Dias: ${op.dias_trabalhados}
            </div>
          </div>
          <div class="rank-premio">
            ${op.elegivel
              ? `<div class="rank-valor">${fmtBRL(op.valor_premio)}</div><div class="pill pill-success" style="font-size:11px">✓ Premiado</div>`
              : `<div class="pill pill-danger">Abaixo da meta</div>`
            }
          </div>
        </div>
      `).join('');
    }

    // 4. DETALHE OPERADORES
    const detalheEl = document.getElementById('dash-detalhe-operadores');
    detalheEl.innerHTML = data.operadores.map(op => `
      <div class="card" style="border-left: 3px solid ${op.elegivel ? 'var(--success)' : 'var(--danger)'}">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
          <div style="font-family:var(--font-head);font-size:16px;font-weight:700">${op.colaborador}</div>
          ${op.elegivel
            ? '<span class="pill pill-success">✓ Premiado</span>'
            : '<span class="pill pill-danger">Abaixo da meta</span>'
          }
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <div>
            <div class="card-label">Total Produzido</div>
            <div style="font-family:var(--font-head);font-size:20px;font-weight:800;color:var(--accent)">${fmtNum(op.total_producao)}</div>
          </div>
          <div>
            <div class="card-label">Média Diária</div>
            <div style="font-family:var(--font-head);font-size:20px;font-weight:800;color:var(--accent2)">${fmtNum(Math.round(op.media_diaria || 0))}</div>
          </div>
          <div>
            <div class="card-label">Dias Trabalhados</div>
            <div style="font-family:var(--font-head);font-size:20px;font-weight:800">${op.dias_trabalhados}</div>
          </div>
          <div>
            <div class="card-label">Excedente Total</div>
            <div style="font-family:var(--font-head);font-size:20px;font-weight:800;color:${(op.excedente_total||0)>=0?'var(--success)':'var(--danger)'}">
              ${(op.excedente_total||0) >= 0 ? '+' : ''}${fmtNum(op.excedente_total || 0)}
            </div>
          </div>
          <div>
            <div class="card-label">Meta Diária</div>
            <div style="font-family:var(--font-head);font-size:20px;font-weight:800;color:var(--muted)">${fmtNum(op.meta || 8000)}</div>
          </div>
          <div>
            <div class="card-label">Prêmio</div>
            <div style="font-family:var(--font-head);font-size:20px;font-weight:800;color:var(--success)">${fmtBRL(op.valor_premio)}</div>
          </div>
        </div>
      </div>
    `).join('');

    // 5. AUXILIARES
    const auxEl = document.getElementById('dash-auxiliares');
    if (!data.auxiliares.length) {
      auxEl.innerHTML = '<p class="text-muted" style="padding:10px 0">Nenhum auxiliar premiado este mês.</p>';
    } else {
      auxEl.innerHTML = data.auxiliares.map(a => `
        <div class="rank-card">
          <div class="rank-num ${a.posicao === 1 ? 'gold' : 'silver'}">${a.posicao}º</div>
          <div class="rank-info">
            <div class="rank-name">${a.colaborador_nome}</div>
            <div class="rank-detail">${a.observacao || 'Auxiliar destaque'}</div>
          </div>
          <div class="rank-premio">
            <div class="rank-valor">${fmtBRL(a.valor_bonus)}</div>
          </div>
        </div>
      `).join('');
    }

    // 6. WIDGET INSUMOS CRÍTICOS
    const insumosEl = document.getElementById('dash-insumos-criticos');
    if (!data.insumos_criticos.length) {
      insumosEl.innerHTML = '<p class="text-muted" style="padding:10px 0">Nenhum insumo crítico (estoque OK).</p>';
    } else {
      insumosEl.innerHTML = data.insumos_criticos.map(item => {
        const min = item.estoque_minimo || 1;
        const pct = Math.min(100, Math.round((item.quantidade_atual / min) * 100));
        let progressColor = 'var(--danger)';
        if (pct > 50) progressColor = 'var(--accent)';
        return `
          <div style="margin-bottom:8px">
            <div style="display:flex; justify-content:space-between; font-size:13px; margin-bottom:4px">
              <strong>${item.nome}</strong>
              <span style="color:var(--danger)">${fmtNum(item.quantidade_atual)} / ${fmtNum(item.estoque_minimo)} ${item.unidade}</span>
            </div>
            <div style="width:100%; height:6px; background:var(--surface2); border-radius:3px; overflow:hidden;">
              <div style="width:${pct}%; height:100%; background:${progressColor}; border-radius:3px;"></div>
            </div>
          </div>
        `;
      }).join('');
    }

    // 7. WIDGET EPIs PENDENTES
    const epiEl = document.getElementById('dash-epi-pendentes');
    if (!data.epi_criticos.length) {
      epiEl.innerHTML = '<p class="text-muted" style="padding:10px 0">Nenhuma pendência de EPI ativa.</p>';
    } else {
      epiEl.innerHTML = data.epi_criticos.map(item => {
        const dias = item.dias_restantes;
        let label = '';
        let cls = '';
        if (dias < 0) {
          label = `Vencido há ${Math.abs(dias)} dia(s)`;
          cls = 'pill-danger';
        } else if (dias === 0) {
          label = 'Vence hoje';
          cls = 'pill-danger';
        } else {
          label = `Vence em ${dias} dia(s)`;
          cls = 'pill-warn';
        }
        return `
          <div style="display:flex; align-items:center; justify-content:space-between; font-size:13px; padding:6px 0; border-bottom:1px solid var(--border)">
            <div style="flex:1">
              <strong>${item.colaborador_name}</strong>
              <div style="font-size:11px; color:var(--muted)">${item.epi_nome} &bull; Validade: ${fmtDate(item.data_validade)}</div>
            </div>
            <span class="pill ${cls}" style="font-size:10px; height:fit-content; white-space:nowrap">${label}</span>
          </div>
        `;
      }).join('');
    }

    // 8. WIDGET PEDIDOS CRÍTICOS
    const pedEl = document.getElementById('dash-pedidos-criticos');
    if (!data.pedidos_criticos.length) {
      pedEl.innerHTML = '<p class="text-muted" style="padding:10px 0">Nenhum pedido atrasado ou crítico.</p>';
    } else {
      pedEl.innerHTML = data.pedidos_criticos.map(item => {
        const dias = item.dias_restantes;
        let label = '';
        let cls = '';
        if (dias < 0) {
          label = `Atrasado há ${Math.abs(dias)} dia(s)`;
          cls = 'pill-danger';
        } else if (dias === 0) {
          label = 'Vence hoje';
          cls = 'pill-danger';
        } else {
          label = `Vence em ${dias} dia(s)`;
          cls = 'pill-warn';
        }
        return `
          <div style="display:flex; align-items:center; justify-content:space-between; font-size:13px; padding:6px 0; border-bottom:1px solid var(--border)">
            <div style="flex:1">
              <strong>Pedido: ${item.numero_pedido}</strong>
              <div style="font-size:11px; color:var(--muted)">${item.cliente_name} &bull; Status: <span style="text-transform:capitalize">${item.status.replace('_', ' ')}</span></div>
            </div>
            <span class="pill ${cls}" style="font-size:10px; height:fit-content; white-space:nowrap">${label}</span>
          </div>
        `;
      }).join('');
    }

  } catch (e) {
    showAlert('Erro ao carregar dashboard: ' + e.message, 'danger');
  }

  // Alertas independentes (não bloqueiam o dashboard)
  try { await checkAlertasPedidos(); } catch(e) {}
  try {
    const alertas = await api('/estoque/alertas');
    const bannerEl = document.getElementById('dash-alerta-estoque');
    const badge = document.getElementById('nav-alerta-badge');
    if (alertas && alertas.length > 0) {
      if (badge) badge.style.display = 'inline';
      if (bannerEl) bannerEl.innerHTML = `
        <div style="background:rgba(239,68,68,.12);border:1px solid rgba(239,68,68,.35);border-radius:10px;padding:14px 18px;margin-bottom:20px;display:flex;align-items:center;gap:14px">
          <span style="font-size:22px">⚠️</span>
          <div style="flex:1">
            <div style="font-family:var(--font-head);font-weight:700;color:var(--danger);margin-bottom:4px">${alertas.length} produto(s) abaixo do estoque mínimo</div>
            <div style="font-size:13px;color:var(--muted)">${alertas.map(a => `<strong>${a.nome}${a.marca ? ' ' + a.marca : ''}</strong>: ${a.quantidade_atual} ${a.unidade} (mín: ${a.estoque_minimo})`).join(' &nbsp;|&nbsp; ')}</div>
          </div>
          <button class="btn btn-sm btn-secondary" onclick="showPage('estoque')" style="white-space:nowrap">Ver estoque →</button>
        </div>`;
    } else {
      if (badge) badge.style.display = 'none';
      if (bannerEl) bannerEl.innerHTML = '';
    }
  } catch(e) {}
}

// ─── PRODUÇÃO ─────────────────────────────────────────────────────────────────

async function loadProducao() {
  const mesEl = document.getElementById('prod-mes');
  if (!mesEl.value) mesEl.value = currentMonth();
  const mes = mesEl.value;
  const topbarMesEl = document.getElementById('topbar-mes');
  if (topbarMesEl) topbarMesEl.textContent = mesLabel(mes);

  const filtroEl = document.getElementById('prod-filtro-colaborador');
  if (filtroEl.options.length <= 1) {
    const cols = await api('/colaboradores/?tipo=operador');
    cols.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = c.nome;
      filtroEl.appendChild(opt);
    });
  }
  const colaboradorId = filtroEl.value;

  try {
    let url = '/producao/?mes=' + mes;
    if (colaboradorId) url += '&colaborador_id=' + colaboradorId;
    const rows = await api(url);
    const tbody = document.getElementById('prod-tbody');
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--muted);padding:32px">Nenhum registro encontrado</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(r => {
      const exc = r.excedente || 0;
      const cls = exc > 0 ? 'positive' : exc < 0 ? 'negative' : 'neutral';
      const signal = exc > 0 ? '+' : '';
      return `<tr>
        <td>${fmtDate(r.data)}</td>
        <td><strong>${r.colaborador_nome}</strong></td>
        <td>${r.maquina_nome}</td>
        <td>${fmtNum(r.meta)}</td>
        <td>${fmtNum(r.producao)}</td>
        <td class="${cls}">${signal}${fmtNum(exc)}</td>
        <td class="flex gap-2">
          <button class="btn btn-sm btn-secondary" onclick="editarProducao(${r.id}, ${r.colaborador_id}, ${r.maquina_id}, '${r.data}', ${r.meta}, ${r.producao}, ${r.produto_estoque_id || 'null'}, ${r.perda_quantidade || 0}, ${r.sobra_quantidade || 0}, '${r.pedido_numero || ''}')">✏️</button>
          <button class="btn btn-sm btn-danger" onclick="deletarProducao(${r.id})">✕</button>
        </td>
      </tr>`;
    }).join('');
  } catch (e) {
    showAlert('Erro ao carregar produção: ' + e.message, 'danger');
  }
}

let maquinas = [], colaboradores = [];


async function deletarProducao(id) {
  if (!confirm('Remover este registro?')) return;
  await api('/producao/' + id, 'DELETE');
  showAlert('Registro removido');
  loadProducao();
  loadDashboard();
}

// ── MODAL PRODUÇÃO (múltiplos produtos)
let prodItens = [];
let prodEstoqueCache = [];
const TIPOS_PERDA_MOD = ['Quebra','Defeito','Contaminação','Transporte','Outros'];

async function openModalProducao() {
  const [mqs, cols, prods, pedidos] = await Promise.all([
    api('/maquinas/'),
    api('/colaboradores/?tipo=operador'),
    api('/estoque/produtos').catch(()=>[]),
    api('/pedidos/').catch(()=>[])
  ]);
  prodEstoqueCache = prods;
  document.getElementById('prod-colaborador').innerHTML = cols.map(c => `<option value="${c.id}">${c.nome}</option>`).join('');
  document.getElementById('prod-maquina').innerHTML = mqs.filter(m=>m.ativa).map(m => `<option value="${m.id}">${m.nome}</option>`).join('');
  document.getElementById('prod-data').value = new Date().toISOString().split('T')[0];
  document.getElementById('prod-meta').value = '8000';
  document.getElementById('prod-edit-id').value = '';
  document.getElementById('prod-pedido-manual').value = '';
  document.getElementById('prod-pedido').innerHTML = '<option value="">— Sem pedido vinculado —</option>' +
    pedidos.filter(p => p.status !== 'entregue').map(p => `<option value="${p.id}">${p.numero_pedido} — ${p.cliente_nome}</option>`).join('');
  document.getElementById('modal-prod-title').textContent = 'Registrar Produção';
  document.getElementById('prod-save-btn').textContent = 'Salvar';

  // Toggle Visibility Check
  const allowed = perfilAtual === 'gestor' || paginasLiberadas.includes('producao_simplificada');
  const toggleContainer = document.getElementById('prod-toggle-container');
  if (toggleContainer) toggleContainer.style.display = allowed ? 'block' : 'none';

  const checkbox = document.getElementById('prod-toggle-simplificado');
  if (checkbox) {
    const saved = localStorage.getItem('prod-simplificado');
    checkbox.checked = allowed && (saved === null ? true : saved === 'true');
  }

  prodItens = [{ produto_id: null, producao: 0, perda: 0, sobra: 0, tipo_perda: 'Quebra' }];

  // Clean simple inputs
  document.getElementById('prod-simples-qtd').value = '';
  document.getElementById('prod-simples-perda').value = '';
  document.getElementById('prod-simples-sobra').value = '';
  document.getElementById('prod-simples-tipo-perda').value = 'Quebra';

  toggleFormSimplificado();
  openModal('modal-producao');
}

function toggleFormSimplificado() {
  const checkbox = document.getElementById('prod-toggle-simplificado');
  const isSimplificado = checkbox && checkbox.checked;

  const secaoSimplificada = document.getElementById('prod-secao-simplificada');
  const secaoDetalhada = document.getElementById('prod-secao-detalhada');

  if (secaoSimplificada) secaoSimplificada.style.display = isSimplificado ? 'grid' : 'none';
  if (secaoDetalhada) secaoDetalhada.style.display = isSimplificado ? 'none' : 'block';

  if (checkbox) {
    localStorage.setItem('prod-simplificado', isSimplificado ? 'true' : 'false');
  }

  if (isSimplificado) {
    atualizarSimplificadoData();
  } else {
    renderProdItens();
    atualizarTotalProd();
  }
}

function atualizarSimplificadoData() {
  const qtd = +document.getElementById('prod-simples-qtd').value || 0;
  const perda = +document.getElementById('prod-simples-perda').value || 0;
  const sobra = +document.getElementById('prod-simples-sobra').value || 0;
  const tipo = document.getElementById('prod-simples-tipo-perda').value || 'Quebra';

  prodItens = [{
    produto_id: null,
    producao: qtd,
    perda: perda,
    sobra: sobra,
    tipo_perda: tipo
  }];
  atualizarTotalProd();
}

function renderProdItens() {
  const el = document.getElementById('prod-itens-list');
  if (!el) return;
  el.innerHTML = prodItens.map((item, idx) => `
    <div class="prod-item-row">
      <div class="prod-field-col prod-field-produto">
        <label class="prod-field-label">Produto do Estoque</label>
        <select onchange="prodItens[${idx}].produto_id=+this.value||null" style="font-size:13px;padding:8px 10px;width:100%;min-width:0">
          <option value="">— Sem produto —</option>
          ${prodEstoqueCache.map(p => `<option value="${p.id}" ${item.produto_id===p.id?'selected':''}>${_produtoLabel(p)} (${fmtNum(p.quantidade_atual)} ${p.unidade})</option>`).join('')}
        </select>
      </div>
      <div class="prod-field-col prod-field-producao">
        <label class="prod-field-label">Produção</label>
        <input type="number" value="${item.producao||''}" min="0" placeholder="0"
               oninput="prodItens[${idx}].producao=+this.value;atualizarTotalProd()"
               style="font-size:13px;text-align:center;padding:8px 4px;width:100%;min-width:0">
      </div>
      <div class="prod-field-col prod-field-perda">
        <label class="prod-field-label">Perda</label>
        <input type="number" value="${item.perda||''}" min="0" placeholder="0"
               oninput="prodItens[${idx}].perda=+this.value"
               style="font-size:13px;text-align:center;padding:8px 4px;border-color:rgba(239,68,68,.35);width:100%;min-width:0">
      </div>
      <div class="prod-field-col prod-field-sobra">
        <label class="prod-field-label">Sobra</label>
        <input type="number" value="${item.sobra||''}" min="0" placeholder="0"
               oninput="prodItens[${idx}].sobra=+this.value"
               style="font-size:13px;text-align:center;padding:8px 4px;border-color:rgba(16,185,129,.35);width:100%;min-width:0">
      </div>
      <div class="prod-field-col prod-field-tipoperda">
        <label class="prod-field-label">Tipo Perda</label>
        <select onchange="prodItens[${idx}].tipo_perda=this.value" style="font-size:12px;padding:8px 4px;width:100%;min-width:0">
          ${TIPOS_PERDA_MOD.map(t => `<option value="${t}" ${item.tipo_perda===t?'selected':''}>${t}</option>`).join('')}
        </select>
      </div>
      <div class="prod-field-col prod-field-acoes">
        <button class="btn btn-sm btn-danger" onclick="removeProdItem(${idx})" ${prodItens.length===1?'disabled':''} style="padding:6px 8px;width:100%">✕</button>
      </div>
    </div>`).join('');
}

function addItemProducao() {
  prodItens.push({ produto_id: null, producao: 0, perda: 0, sobra: 0, tipo_perda: 'Quebra' });
  renderProdItens();
}

function removeProdItem(idx) {
  if (prodItens.length <= 1) return;
  prodItens.splice(idx, 1);
  renderProdItens();
  atualizarTotalProd();
}

function atualizarTotalProd() {
  const total = prodItens.reduce((s, i) => s + (i.producao || 0), 0);
  const el = document.getElementById('prod-total-label');
  if (el) el.textContent = fmtNum(total);
}

async function editarProducao(id, colId, maqId, data, meta, producao, produtoEstoqueId = null, perdaQtd = 0, sobraQtd = 0, pedidoNumero = '') {
  await openModalProducao();
  document.getElementById('prod-edit-id').value = id;
  document.getElementById('prod-colaborador').value = colId;
  document.getElementById('prod-maquina').value = maqId;
  document.getElementById('prod-data').value = data;
  document.getElementById('prod-meta').value = meta;
  document.getElementById('prod-pedido-manual').value = pedidoNumero || '';
  document.getElementById('modal-prod-title').textContent = 'Editar Produção';
  document.getElementById('prod-save-btn').textContent = 'Atualizar';

  const isSimplificado = !produtoEstoqueId;
  const checkbox = document.getElementById('prod-toggle-simplificado');
  if (checkbox) {
    checkbox.checked = isSimplificado;
  }

  if (isSimplificado) {
    document.getElementById('prod-simples-qtd').value = producao || '';
    document.getElementById('prod-simples-perda').value = perdaQtd || '';
    document.getElementById('prod-simples-sobra').value = sobraQtd || '';
    document.getElementById('prod-simples-tipo-perda').value = 'Quebra';
    prodItens = [{ produto_id: null, producao: producao, perda: perdaQtd, sobra: sobraQtd, tipo_perda: 'Quebra' }];
  } else {
    prodItens = [{ produto_id: produtoEstoqueId, producao: producao, perda: perdaQtd, sobra: sobraQtd, tipo_perda: 'Quebra' }];
  }

  toggleFormSimplificado();
  atualizarTotalProd();
}

async function salvarProducao() {
  const editId = document.getElementById('prod-edit-id').value;
  const colId = +document.getElementById('prod-colaborador').value;
  const maqId = +document.getElementById('prod-maquina').value;
  const data = document.getElementById('prod-data').value;
  const meta = +document.getElementById('prod-meta').value;
  const pedidoManual = document.getElementById('prod-pedido-manual').value.trim();

  let valid = true;
  clearFieldHighlights('modal-producao');
  if (!data) { highlightField('prod-data', true, 'Informe a data'); valid = false; }
  else { highlightField('prod-data', false); }
  if (!colId) { highlightField('prod-colaborador', true, 'Selecione o colaborador'); valid = false; }
  else { highlightField('prod-colaborador', false); }
  if (!valid) return;

  const totalProducao = prodItens.reduce((s, i) => s + (i.producao || 0), 0);
  try {
    if (editId) {
      const item = prodItens[0];
      await api('/producao/' + editId, 'PUT', {
        colaborador_id: colId, maquina_id: maqId, data, meta,
        producao: item.producao || 0,
        produto_estoque_id: item.produto_id,
        perda_quantidade: item.perda || 0,
        sobra_quantidade: item.sobra || 0
      });
      showAlert('Produção atualizada!');
    } else {
      // Múltiplos produtos: soma tudo numa produção, baixas de estoque separadas
      const itensValidos = prodItens.filter(i => (i.producao || 0) > 0 || (i.perda || 0) > 0);
      if (!itensValidos.length) { showAlert('Informe pelo menos um item com produção', 'danger'); return; }

      // Lançar a produção total (soma de todos os itens)
      const primItem = itensValidos[0];
      const res = await api('/producao/', 'POST', {
        colaborador_id: colId, maquina_id: maqId, data, meta,
        producao: totalProducao,
        produto_estoque_id: primItem.produto_id,
        perda_quantidade: primItem.perda || 0,
        perda_tipo: primItem.tipo_perda,
        sobra_quantidade: primItem.sobra || 0,
        pedido_numero: pedidoManual || null
      });

      // Baixas adicionais de estoque para os demais itens
      for (let i = 1; i < itensValidos.length; i++) {
        const item = itensValidos[i];
        if (item.produto_id && (item.producao > 0 || item.perda > 0 || item.sobra > 0)) {
          try {
            if (item.producao > 0) {
              await api('/estoque/movimentacoes', 'POST', {
                produto_id: item.produto_id,
                tipo: 'saida',
                quantidade: item.producao,
                motivo: 'Produção diária — ' + data,
                responsavel: document.getElementById('prod-colaborador').selectedOptions[0]?.text || '',
                data
              });
            }
            if (item.perda > 0) {
              await api('/estoque/movimentacoes', 'POST', {
                produto_id: item.produto_id,
                tipo: 'perda',
                quantidade: item.perda,
                motivo: 'Perda na produção — ' + data,
                tipo_perda: item.tipo_perda,
                data
              });
            }
            if (item.sobra > 0) {
              await api('/estoque/movimentacoes', 'POST', {
                produto_id: item.produto_id,
                tipo: 'sobra',
                quantidade: item.sobra,
                motivo: 'Sobra de produção — ' + data,
                data
              });
            }
          } catch(e) {}
        }
      }
      showAlert('Produção registrada! Total: ' + fmtNum(totalProducao) + ' peças');
    }
    closeModal('modal-producao');
    loadProducao();
  } catch(e) { showAlert(e.message, 'danger'); }
}

// ─── PREMIAÇÃO ────────────────────────────────────────────────────────────────

async function loadPremiacao() {
  const mesEl = document.getElementById('prem-mes');
  if (!mesEl.value) mesEl.value = currentMonth();
  const mes = mesEl.value;
  const topbarMesEl = document.getElementById('topbar-mes');
  if (topbarMesEl) topbarMesEl.textContent = mesLabel(mes);

  try {
    const [ops, auxs] = await Promise.all([
      api('/premiacao/operadores/' + mes),
      api('/premiacao/auxiliares/' + mes)
    ]);

    document.getElementById('prem-operadores').innerHTML = ops.length
      ? ops.map((op, i) => `
        <div class="rank-card">
          <div class="rank-num ${i === 0 ? 'gold' : i === 1 ? 'silver' : ''}">${i + 1}º</div>
          <div class="rank-info">
            <div class="rank-name">${op.colaborador}</div>
            <div class="rank-detail">
              Média: ${fmtNum(Math.round(op.media_diaria || 0))} pçs/dia &nbsp;|&nbsp;
              ${op.dias_trabalhados} dias
            </div>
          </div>
          <div class="rank-premio">
            ${op.elegivel
              ? `<div class="rank-valor">${fmtBRL(op.valor_premio)}</div><div class="pill pill-success" style="font-size:11px">✓ Elegível</div>`
              : `<span class="pill pill-danger">Abaixo da média</span>`
            }
          </div>
        </div>`).join('')
      : '<p class="text-muted">Sem dados para este mês.</p>';

    document.getElementById('prem-auxiliares').innerHTML = auxs.length
      ? auxs.map(a => `
        <div class="rank-card">
          <div class="rank-num ${a.posicao === 1 ? 'gold' : 'silver'}">${a.posicao}º</div>
          <div class="rank-info">
            <div class="rank-name">${a.colaborador_nome}</div>
            <div class="rank-detail">${a.observacao || '—'}</div>
          </div>
          <div class="rank-premio">
            <div class="rank-valor">${fmtBRL(a.valor_bonus)}</div>
            <button class="btn btn-sm btn-danger" onclick="removerAuxiliar(${a.id})" style="margin-top:4px">✕</button>
          </div>
        </div>`).join('')
      : '<p class="text-muted">Nenhum auxiliar premiado.</p>';
  } catch (e) {
    showAlert('Erro: ' + e.message, 'danger');
  }
}

async function openModalAuxiliar() {
  const auxs = await api('/colaboradores/?tipo=auxiliar');
  document.getElementById('aux-colaborador').innerHTML =
    auxs.map(c => `<option value="${c.id}">${c.nome}</option>`).join('');
  const config = await api('/configuracoes/');
  const b1 = config.find(c => c.chave === 'bonus_auxiliar_1');
  if (b1) document.getElementById('aux-valor').value = b1.valor;
  openModal('modal-auxiliar');
}

async function salvarAuxiliar() {
  const mes = document.getElementById('prem-mes').value || currentMonth();
  try {
    const body = {
      colaborador_id: +document.getElementById('aux-colaborador').value,
      mes_referencia: mes,
      posicao: +document.getElementById('aux-posicao').value,
      valor_bonus: +document.getElementById('aux-valor').value,
      observacao: document.getElementById('aux-obs').value
    };
    await api('/premiacao/auxiliares', 'POST', body);
    showAlert('Premiação de auxiliar salva!');
    closeModal('modal-auxiliar');
    loadPremiacao();
  } catch (e) {
    showAlert(e.message, 'danger');
  }
}

async function removerAuxiliar(id) {
  if (!confirm('Remover premiação?')) return;
  await api('/premiacao/auxiliares/' + id, 'DELETE');
  loadPremiacao();
}

// ─── COLABORADORES ────────────────────────────────────────────────────────────

function tipoKeyColaborador(tipo) {
  return (tipo || '')
    .toString()
    .trim()
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '');
}

function formatTipoColaborador(tipo) {
  return (tipo || '')
    .toString()
    .trim()
    .toLowerCase()
    .split(/([\s-]+)/)
    .map(parte => /^[\s-]+$/.test(parte) ? parte : parte.charAt(0).toUpperCase() + parte.slice(1))
    .join('');
}

function pillTipoColaborador(tipo) {
  const key = tipoKeyColaborador(tipo);
  const mapa = {
    operador: 'pill-info',
    auxiliar: 'pill-warn',
    lider: 'pill-purple',
    supervisor: 'pill-success',
    conferente: 'pill-teal',
    estoquista: 'pill-pink'
  };
  if (mapa[key]) return mapa[key];
  const cores = ['pill-purple', 'pill-success', 'pill-teal', 'pill-pink', 'pill-slate'];
  let soma = 0;
  for (let i = 0; i < key.length; i++) soma += key.charCodeAt(i);
  return cores[soma % cores.length];
}

async function carregarTiposColaborador(selected = 'operador') {
  const tipos = await api('/colaboradores/tipos').catch(() => ([
    { nome: 'operador' },
    { nome: 'auxiliar' }
  ]));
  const sel = document.getElementById('col-tipo');
  if (sel) {
    sel.innerHTML = tipos.map(t => {
      const nome = t.nome || '';
      return `<option value="${nome}" ${nome === selected ? 'selected' : ''}>${formatTipoColaborador(nome)}</option>`;
    }).join('');
    if (selected && !tipos.some(t => t.nome === selected)) {
      sel.innerHTML += `<option value="${selected}" selected>${formatTipoColaborador(selected)}</option>`;
    }
  }
  return tipos;
}

async function openModalTipoColaborador() {
  document.getElementById('col-tipo-novo').value = '';
  await renderTiposColaborador();
  openModal('modal-tipo-colaborador');
}

async function renderTiposColaborador() {
  const lista = document.getElementById('col-tipos-lista');
  if (!lista) return;
  const tipos = await api('/colaboradores/tipos').catch(() => []);
  lista.innerHTML = tipos.length ? tipos.map(t => `
    <span class="pill ${pillTipoColaborador(t.nome)}" style="display:inline-flex;align-items:center;gap:6px">
      ${formatTipoColaborador(t.nome)}
      ${['operador','auxiliar'].includes(t.nome) ? '' : `<button class="btn btn-sm btn-danger" style="padding:2px 6px" onclick="deletarTipoColaborador(${t.id})">×</button>`}
    </span>
  `).join('') : '<span style="color:var(--muted)">Nenhum tipo cadastrado</span>';
}

async function salvarTipoColaborador() {
  const input = document.getElementById('col-tipo-novo');
  const nome = (input?.value || '').trim();
  clearFieldHighlights('modal-tipo-colaborador');
  if (!nome) { highlightField('col-tipo-novo', true, 'Informe o tipo'); return; }
  const btn = document.getElementById('btn-salvar-tipo-colaborador');
  if (btn) btn.disabled = true;
  try {
    await api('/colaboradores/tipos', 'POST', { nome });
    showAlert('Tipo cadastrado!');
    input.value = '';
    await renderTiposColaborador();
    await carregarTiposColaborador(nome.toLowerCase());
  } catch (e) {
    showAlert(e.message || 'Erro ao salvar tipo de colaborador', 'danger');
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function deletarTipoColaborador(id) {
  if (!confirm('Desativar este tipo?')) return;
  try {
    await api('/colaboradores/tipos/' + id, 'DELETE');
    showAlert('Tipo desativado');
    await renderTiposColaborador();
    await carregarTiposColaborador();
  } catch (e) {
    showAlert(e.message, 'danger');
  }
}

async function loadColaboradores() {
  const rows = await api('/colaboradores/');
  const tbody = document.getElementById('col-tbody');
  tbody.innerHTML = rows.map(c => `
    <tr>
      <td><strong>${c.nome}</strong></td>
      <td><span class="pill ${pillTipoColaborador(c.tipo)}">${formatTipoColaborador(c.tipo)}</span></td>
      <td>${c.maquina_nome || '—'}</td>
      <td><span class="pill pill-success">Ativo</span></td>
      <td class="flex gap-2">
        <button class="btn btn-sm btn-secondary" onclick="editColaborador(${c.id})">Editar</button>
        <button class="btn btn-sm btn-danger" onclick="deletarColaborador(${c.id})">Remover</button>
      </td>
    </tr>
  `).join('');
}

async function openModalColaborador() {
  document.getElementById('col-id').value = '';
  document.getElementById('col-nome').value = '';
  await carregarTiposColaborador('operador');
  const mqs = await api('/maquinas/');
  document.getElementById('col-maquina').innerHTML =
    mqs.filter(m => m.ativa).map(m => `<option value="${m.id}">${m.nome}</option>`).join('');
  toggleMaquina();
  openModal('modal-colaborador');
}

function toggleMaquina() {
  const tipo = document.getElementById('col-tipo').value;
  document.getElementById('col-maquina-group').style.display = tipo === 'operador' ? '' : 'none';
}

async function editColaborador(id) {
  const c = await api('/colaboradores/' + id);
  const mqs = await api('/maquinas/');
  document.getElementById('col-id').value = c.id;
  document.getElementById('col-nome').value = c.nome;
  await carregarTiposColaborador(c.tipo);
  document.getElementById('col-maquina').innerHTML =
    mqs.filter(m => m.ativa).map(m =>
      `<option value="${m.id}" ${m.id === c.maquina_id ? 'selected' : ''}>${m.nome}</option>`
    ).join('');
  toggleMaquina();
  openModal('modal-colaborador');
}

async function salvarColaborador() {
  const id = document.getElementById('col-id').value;
  const tipo = document.getElementById('col-tipo').value;
  const nome = document.getElementById('col-nome').value.trim();

  clearFieldHighlights('modal-colaborador');
  if (!nome) { highlightField('col-nome', true, 'Informe o nome'); return; }
  if (!tipo) { highlightField('col-tipo', true, 'Selecione o tipo'); return; }

  const maquinaVal = document.getElementById('col-maquina')?.value || '';
  const body = {
    nome,
    tipo,
    maquina_id: tipo === 'operador' && maquinaVal ? +maquinaVal : null,
    ativo: 1
  };
  const btn = document.getElementById('btn-salvar-colaborador');
  if (btn) btn.disabled = true;
  try {
    if (id) await api('/colaboradores/' + id, 'PUT', body);
    else await api('/colaboradores/', 'POST', body);
    showAlert('Colaborador salvo!');
    closeModal('modal-colaborador');
    await loadColaboradores();
  } catch (e) {
    showAlert(e.message || 'Erro ao salvar colaborador', 'danger');
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function deletarColaborador(id) {
  if (!confirm('Desativar este colaborador?')) return;
  await api('/colaboradores/' + id, 'DELETE');
  showAlert('Colaborador desativado');
  loadColaboradores();
}

// ─── MÁQUINAS ─────────────────────────────────────────────────────────────────

async function loadMaquinas() {
  const rows = await api('/maquinas/');
  const tbody = document.getElementById('maq-tbody');
  tbody.innerHTML = rows.map(m => `
    <tr>
      <td><strong>${m.nome}</strong></td>
      <td>${m.setor || '—'}</td>
      <td>${fmtNum(m.meta_padrao)} pçs/dia</td>
      <td><span class="pill ${m.ativa ? 'pill-success' : 'pill-danger'}">${m.ativa ? 'Ativa' : 'Inativa'}</span></td>
      <td class="flex gap-2">
        <button class="btn btn-sm btn-secondary" onclick="editMaquina(${m.id})">Editar</button>
        <button class="btn btn-sm btn-danger" onclick="deletarMaquina(${m.id})">Desativar</button>
      </td>
    </tr>
  `).join('');
}

async function openModalMaquina() {
  document.getElementById('maq-id').value = '';
  document.getElementById('maq-nome').value = '';
  document.getElementById('maq-setor').value = '';
  document.getElementById('maq-meta').value = '8000';
  openModal('modal-maquina');
}

async function editMaquina(id) {
  const m = await api('/maquinas/' + id);
  document.getElementById('maq-id').value = m.id;
  document.getElementById('maq-nome').value = m.nome;
  document.getElementById('maq-setor').value = m.setor || '';
  document.getElementById('maq-meta').value = m.meta_padrao;
  openModal('modal-maquina');
}

async function salvarMaquina() {
  const id = document.getElementById('maq-id').value;
  const nome = document.getElementById('maq-nome').value.trim();

  clearFieldHighlights('modal-maquina');
  if (!nome) { highlightField('maq-nome', true, 'Informe o nome'); return; }

  const body = {
    nome,
    setor: document.getElementById('maq-setor').value,
    meta_padrao: +document.getElementById('maq-meta').value,
    ativa: 1
  };
  try {
    if (id) await api('/maquinas/' + id, 'PUT', body);
    else await api('/maquinas/', 'POST', body);
    showAlert('Máquina salva!');
    closeModal('modal-maquina');
    loadMaquinas();
  } catch (e) {
    showAlert(e.message, 'danger');
  }
}

async function deletarMaquina(id) {
  if (!confirm('Desativar esta máquina?')) return;
  await api('/maquinas/' + id, 'DELETE');
  showAlert('Máquina desativada');
  loadMaquinas();
}


// ─── RELATÓRIOS ───────────────────────────────────────────────────────────────

let charts = {};

function destroyChart(id) {
  if (charts[id]) { charts[id].destroy(); delete charts[id]; }
}

function mesLabel2(mes) {
  if (!mes) return '';
  const [y, m] = mes.split('-');
  const n = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];
  return n[+m-1] + '/' + y.slice(2);
}

const CORES = ['#f0b429','#3b82f6','#10b981','#f43f5e','#a855f7','#f97316'];

async function loadRelatorios() {
  const mes = new Date().toISOString().slice(0,7);
  const topbarMesEl = document.getElementById('topbar-mes');
  if (topbarMesEl) topbarMesEl.textContent = mesLabel(mes);

  // Inicializar filtros se os elementos existirem (nova versão com abas)
  const mesIniEl = document.getElementById('rel-prod-mes-ini');
  const mesFimEl = document.getElementById('rel-prod-mes-fim');
  const premEl = document.getElementById('rel-prem-mes');
  if (mesIniEl && !mesIniEl.value) mesIniEl.value = mes;
  if (mesFimEl && !mesFimEl.value) mesFimEl.value = mes;
  if (premEl && !premEl.value) premEl.value = mes;
  try {
    const cols = await api('/colaboradores/');
    const sel = document.getElementById('rel-prod-col');
    if (sel && sel.options.length<=1) cols.forEach(c => { const o=document.createElement('option'); o.value=c.id; o.textContent=c.nome; sel.appendChild(o); });
  } catch(e) {}
  await carregarCategoriasRelEstoque();
  // Só carrega se a aba produção estiver visível
  if (document.getElementById('rel-content-producao')) loadRelProducao();
}

async function loadRelProducao() {
  const mesIni = document.getElementById('rel-prod-mes-ini')?.value || new Date().toISOString().slice(0,7);
  const mesFim = document.getElementById('rel-prod-mes-fim')?.value || '';
  const colId = document.getElementById('rel-prod-col')?.value || '';
  let url = '/producao/?';
  if (mesIni) url += 'mes=' + mesIni;
  if (colId) url += '&colaborador_id=' + colId;
  const rows = await api(url);
  const tbody = document.getElementById('rel-prod-tbody');
  if (!rows.length) { tbody.innerHTML='<tr><td colspan="9" style="text-align:center;color:var(--muted);padding:24px">Nenhum registro</td></tr>'; return; }
  const total = rows.reduce((s,r)=>s+(r.producao||0),0);
  const totalPerda = rows.reduce((s,r)=>s+(r.perda_quantidade||0),0);
  document.getElementById('rel-prod-cards').innerHTML = `
    <div class="card"><div class="card-label">Total Registros</div><div class="card-value accent">${rows.length}</div></div>
    <div class="card"><div class="card-label">Total Produzido</div><div class="card-value info">${fmtNum(total)}</div></div>
    <div class="card"><div class="card-label">Total Perdas</div><div class="card-value danger">${fmtNum(totalPerda)}</div></div>
  `;
  tbody.innerHTML = rows.map(r => {
    const exc = r.excedente||0;
    return `<tr>
      <td>${fmtDate(r.data)}</td>
      <td><strong>${r.colaborador_nome}</strong></td>
      <td>${r.maquina_nome}</td>
      <td>${fmtNum(r.meta)}</td>
      <td>${fmtNum(r.producao)}</td>
      <td class="${exc>=0?'positive':'negative'}">${exc>=0?'+':''}${fmtNum(exc)}</td>
      <td class="danger">${r.perda_quantidade>0?fmtNum(r.perda_quantidade):'—'}</td>
      <td class="positive">${r.sobra_quantidade>0?fmtNum(r.sobra_quantidade):'—'}</td>
      <td style="color:var(--muted)">${r.pedido_numero||'—'}</td>
    </tr>`;
  }).join('');
}

async function loadRelPremiacao() {
  const mes = document.getElementById('rel-prem-mes').value || new Date().toISOString().slice(0,7);
  const [ops, auxs] = await Promise.all([api('/premiacao/operadores/'+mes), api('/premiacao/auxiliares/'+mes)]);
  const el = document.getElementById('rel-prem-content');
  el.innerHTML = `
    <div class="table-wrap" style="margin-bottom:20px">
      <div class="table-head"><span class="table-head-title">Operadores — ${mes}</span></div>
      <table>
        <thead><tr><th>Posição</th><th>Colaborador</th><th>Total Prod.</th><th>Média/Dia</th><th>Dias</th><th>Elegível</th><th>Prêmio</th></tr></thead>
        <tbody>${ops.map((r,i)=>`<tr>
          <td><strong>${i+1}º</strong></td>
          <td>${r.colaborador}</td>
          <td>${fmtNum(r.total_producao)}</td>
          <td>${fmtNum(Math.round(r.media_diaria||0))}</td>
          <td>${r.dias_trabalhados}</td>
          <td><span class="pill ${r.elegivel?'pill-success':'pill-danger'}">${r.elegivel?'✓ Sim':'✕ Não'}</span></td>
          <td>${fmtBRL(r.valor_premio)}</td>
        </tr>`).join('')}</tbody>
      </table>
    </div>
    <div class="table-wrap">
      <div class="table-head"><span class="table-head-title">Auxiliares — ${mes}</span></div>
      <table>
        <thead><tr><th>Posição</th><th>Nome</th><th>Bônus</th><th>Observação</th></tr></thead>
        <tbody>${auxs.map(a=>`<tr>
          <td><strong>${a.posicao}º</strong></td>
          <td>${a.colaborador_nome}</td>
          <td>${fmtBRL(a.valor_bonus)}</td>
          <td style="color:var(--muted)">${a.observacao||'—'}</td>
        </tr>`).join('')}</tbody>
      </table>
    </div>`;
}


async function carregarCategoriasRelEstoque() {
  const sel = document.getElementById('rel-est-categoria');
  if (!sel) return;
  const atual = sel.value || '';
  try {
    const cats = await api('/estoque/categorias');
    sel.innerHTML = '<option value="">Todas as categorias</option>' + cats.map(c => `<option value="${c.id}">${c.nome}</option>`).join('');
    if (atual) sel.value = atual;
  } catch (e) {
    console.warn('Não foi possível carregar categorias do relatório de estoque', e);
  }
}

function statusEstoqueRel(p) {
  const saldo = Number(p.quantidade_atual || 0);
  const minimo = Number(p.estoque_minimo || 0);
  if (saldo <= 0) return { texto: 'Falta em estoque', pill: 'pill-danger', cor: 'var(--danger)' };
  if (saldo <= minimo) return { texto: 'Abaixo do mínimo', pill: 'pill-warn', cor: 'var(--warn)' };
  return { texto: 'OK', pill: 'pill-success', cor: 'var(--success)' };
}

function cardRelatorioEstoque(titulo, valor, detalhe) {
  return `<div class="card metric-card"><div class="metric-label">${titulo}</div><div class="metric-value">${valor}</div><div class="metric-sub">${detalhe || ''}</div></div>`;
}

async function loadRelEstoque() {
  await carregarCategoriasRelEstoque();

  const modelo = document.getElementById('rel-est-modelo')?.value || 'geral';
  const categoriaId = document.getElementById('rel-est-categoria')?.value || '';
  const tipoMov = document.getElementById('rel-est-tipo-mov')?.value || '';
  const dataIni = document.getElementById('rel-est-data-ini')?.value || '';
  const dataFim = document.getElementById('rel-est-data-fim')?.value || '';

  const isMov = modelo === 'movimentacoes';
  ['rel-est-tipo-mov','rel-est-data-ini','rel-est-data-sep','rel-est-data-fim'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = isMov ? '' : 'none';
  });

  const tbody = document.getElementById('rel-est-tbody');
  const thead = document.getElementById('rel-est-thead');
  const title = document.getElementById('rel-est-title');
  const cards = document.getElementById('rel-est-cards');
  if (!tbody || !thead) return;

  if (isMov) {
    const params = [];
    if (categoriaId) params.push('categoria_id=' + encodeURIComponent(categoriaId));
    if (tipoMov) params.push('tipo=' + encodeURIComponent(tipoMov));
    if (dataIni) params.push('data_inicio=' + encodeURIComponent(dataIni));
    if (dataFim) params.push('data_fim=' + encodeURIComponent(dataFim));
    const movs = await api('/estoque/movimentacoes' + (params.length ? '?' + params.join('&') : ''));

    const entradas = movs.filter(m => m.tipo === 'entrada').reduce((a,m)=>a+Number(m.quantidade||0),0);
    const saidas = movs.filter(m => ['saida','perda'].includes(m.tipo)).reduce((a,m)=>a+Number(m.quantidade||0),0);
    if (title) title.textContent = 'Movimentações de Estoque';
    if (cards) cards.innerHTML = [
      cardRelatorioEstoque('Movimentações', movs.length, 'registros encontrados'),
      cardRelatorioEstoque('Entradas', fmtNum(entradas), 'quantidade movimentada'),
      cardRelatorioEstoque('Saídas/Perdas', fmtNum(saidas), 'quantidade movimentada')
    ].join('');
    thead.innerHTML = '<tr><th>Data</th><th>Código</th><th>Produto</th><th>Categoria</th><th>Tipo</th><th>Quantidade</th><th>Saldo Depois</th><th>Motivo/Obs.</th></tr>';
    tbody.innerHTML = movs.length ? movs.map(m => {
      const tipoLabel = {entrada:'Entrada',saida:'Saída',perda:'Perda',ajuste:'Ajuste'}[m.tipo] || m.tipo;
      const pill = m.tipo === 'entrada' ? 'pill-success' : (m.tipo === 'perda' ? 'pill-danger' : 'pill-warn');
      return `<tr>
        <td>${fmtDate(m.data)}</td>
        <td><strong>${m.produto_codigo || '—'}</strong></td>
        <td>${m.produto_nome || '—'}</td>
        <td>${m.categoria_nome || '—'}</td>
        <td><span class="pill ${pill}">${tipoLabel}</span></td>
        <td>${fmtNum(m.quantidade)}</td>
        <td>${fmtNum(m.saldo_posterior)}</td>
        <td>${m.motivo || m.observacao || '—'}</td>
      </tr>`;
    }).join('') : '<tr><td colspan="8" style="text-align:center;color:var(--muted);padding:28px">Nenhuma movimentação encontrada</td></tr>';
    return;
  }

  let prods = await api('/estoque/produtos' + (categoriaId ? '?categoria_id=' + encodeURIComponent(categoriaId) : ''));
  const todos = prods.slice();

  if (modelo === 'falta') prods = prods.filter(p => Number(p.quantidade_atual || 0) <= 0);
  if (modelo === 'baixo') prods = prods.filter(p => Number(p.quantidade_atual || 0) > 0 && Number(p.quantidade_atual || 0) <= Number(p.estoque_minimo || 0));
  if (modelo === 'positivo') prods = prods.filter(p => Number(p.quantidade_atual || 0) > 0);
  if (modelo === 'sem_minimo') prods = prods.filter(p => Number(p.estoque_minimo || 0) <= 0);
  if (modelo === 'sem_movimento') {
    let movs = [];
    try { movs = await api('/estoque/movimentacoes'); } catch(e) { movs = []; }
    const idsComMov = new Set(movs.map(m => Number(m.produto_id)));
    prods = prods.filter(p => !idsComMov.has(Number(p.id)));
  }

  const titulos = {
    geral: 'Relatório Geral de Estoque',
    categoria: 'Produtos por Categoria',
    falta: 'Produtos em Falta no Estoque',
    baixo: 'Produtos com Estoque Baixo',
    positivo: 'Produtos com Saldo Positivo',
    sem_minimo: 'Produtos sem Estoque Mínimo Cadastrado',
    sem_movimento: 'Produtos sem Movimentação'
  };
  if (title) title.textContent = titulos[modelo] || 'Posição de Estoque';

  const totalGeral = todos.length;
  const totalFalta = todos.filter(p => Number(p.quantidade_atual || 0) <= 0).length;
  const totalBaixo = todos.filter(p => Number(p.quantidade_atual || 0) > 0 && Number(p.quantidade_atual || 0) <= Number(p.estoque_minimo || 0)).length;
  const totalOk = todos.filter(p => Number(p.quantidade_atual || 0) > Number(p.estoque_minimo || 0)).length;
  if (cards) cards.innerHTML = [
    cardRelatorioEstoque('Itens filtrados', prods.length, `de ${totalGeral} produtos ativos`),
    cardRelatorioEstoque('Falta em estoque', totalFalta, 'saldo igual ou menor que zero'),
    cardRelatorioEstoque('Estoque baixo', totalBaixo, 'saldo abaixo ou igual ao mínimo'),
    cardRelatorioEstoque('Estoque OK', totalOk, 'acima do mínimo')
  ].join('');

  thead.innerHTML = '<tr><th>Código</th><th>Produto</th><th>Categoria</th><th>Unidade</th><th>Saldo Atual</th><th>Mínimo</th><th>Situação</th></tr>';
  tbody.innerHTML = prods.length ? prods.map(p => {
    const st = statusEstoqueRel(p);
    return `<tr>
      <td><strong>${p.codigo || '—'}</strong></td>
      <td><strong>${p.nome}${p.marca ? ' — ' + p.marca : ''}</strong></td>
      <td>${p.categoria_nome || '—'}</td>
      <td>${p.unidade || '—'}</td>
      <td style="font-weight:700;color:${st.cor}">${fmtNum(p.quantidade_atual)}</td>
      <td>${fmtNum(p.estoque_minimo)}</td>
      <td><span class="pill ${st.pill}">${st.texto}</span></td>
    </tr>`;
  }).join('') : '<tr><td colspan="7" style="text-align:center;color:var(--muted);padding:28px">Nenhum produto encontrado para este filtro</td></tr>';
}

async function loadRelPedidos() {
  const status = document.getElementById('rel-ped-status').value;
  let url = '/pedidos/';
  if (status) url += '?status=' + status;
  const rows = await api(url);
  const STATUS_LABEL = {aberto:'📋 Aberto',em_producao:'🏭 Em produção',produzido:'✅ Produzido',entregue:'📦 Entregue'};
  const STATUS_PILL  = {aberto:'pill-info',em_producao:'pill-warn',produzido:'pill-success',entregue:'pill-success'};
  document.getElementById('rel-ped-tbody').innerHTML = rows.map(p => {
    const dias = Math.round(p.dias_restantes);
    const cor = dias<0?'var(--danger)':dias<=3?'var(--warn)':'var(--success)';
    return `<tr>
      <td><strong>${p.numero_pedido}</strong></td>
      <td>${p.cliente_nome}</td>
      <td>${fmtDate(p.prazo_entrega)}</td>
      <td style="color:${cor};font-weight:700">${dias<0?'Vencido':dias+'d'}</td>
      <td>${p.itens_entregues}/${p.total_itens}</td>
      <td><span class="pill ${STATUS_PILL[p.status]}">${STATUS_LABEL[p.status]}</span></td>
    </tr>`;
  }).join('');
}

async function loadRelEPI() {
  const rows = await api('/epi/entregas');
  const EPI_ST = {ativo:'pill-success',vencendo:'pill-warn',vencido:'pill-danger',devolvido:'pill-info',extraviado:'pill-danger'};
  document.getElementById('rel-epi-tbody').innerHTML = rows.map(r => {
    const sc = r.status_calculado||r.status;
    const dias = r.dias_restantes;
    const cor = dias<0?'var(--danger)':dias<=30?'var(--warn)':'var(--success)';
    return `<tr>
      <td><strong>${r.colaborador_nome}</strong></td>
      <td>${r.epi_nome}</td>
      <td>${r.epi_categoria||'—'}</td>
      <td>${fmtDate(r.data_entrega)}</td>
      <td>${fmtDate(r.data_validade)}</td>
      <td style="color:${cor};font-weight:700">${dias<0?'Vencido':dias+'d'}</td>
      <td><span class="pill ${EPI_ST[sc]||'pill-info'}">${sc}</span></td>
    </tr>`;
  }).join('');
}

// ─── EXPORTAR RELATÓRIOS ──────────────────────────────────────────────────────

async function exportarRelatorio(tipo, formato) {
  if (formato === 'pdf') {
    const tabelas = { producao:'rel-prod-tbody', premiacao:'rel-prem-content', estoque:'rel-est-tbody', pedidos:'rel-ped-tbody', epi:'rel-epi-tbody' };
    const titulos = { producao:'Relatório de Produção', premiacao:'Relatório de Premiação', estoque:'Relatório de Estoque', pedidos:'Relatório de Pedidos', epi:'Relatório de EPI' };
    const el = document.getElementById(tabelas[tipo]);
    const tabela = el?.closest('table') || el;
    const win = window.open('','_blank');
    win.document.write(`<html><head><title>${titulos[tipo]}</title><style>body{font-family:Arial,sans-serif;margin:20px;font-size:12px}table{width:100%;border-collapse:collapse}th{background:#333;color:#fff;padding:8px}td{padding:7px;border-bottom:1px solid #ddd}h2{font-size:16px}</style></head><body>
      <h2>PRATIC — ${titulos[tipo]}</h2>
      <p style="color:#666">Gerado em: ${new Date().toLocaleString('pt-BR')}</p>
      ${tabela?.outerHTML || '<p>Sem dados</p>'}
    </body></html>`);
    win.document.close();
    setTimeout(() => win.print(), 500);
  } else {
    // Excel via CSV
    const tabelas = { producao:'rel-prod-tbody', estoque:'rel-est-tbody', pedidos:'rel-ped-tbody', epi:'rel-epi-tbody' };
    const el = document.getElementById(tabelas[tipo]);
    if (!el) return;
    const table = el.closest('table');
    if (!table) return;
    const rows = [];
    table.querySelectorAll('tr').forEach(tr => {
      const row = [];
      tr.querySelectorAll('th,td').forEach(td => row.push('"' + td.textContent.trim().replace(/"/g,'""') + '"'));
      rows.push(row.join(';'));
    });
    const csv = '\uFEFF' + rows.join('\n');
    const blob = new Blob([csv], {type:'text/csv;charset=utf-8'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `pratic_${tipo}_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
  }
}

// ─── SAIR DO SISTEMA ─────────────────────────────────────────────────────────

function sairSistema() {
  if (!confirm('Deseja realmente sair do sistema PRATIC?')) return;
  document.body.innerHTML = `
    <div style="min-height:100vh;display:flex;align-items:center;justify-content:center;background:#0d0f14;font-family:'DM Sans',sans-serif">
      <div style="text-align:center;padding:40px">
        <div style="font-family:'Syne',sans-serif;font-size:32px;font-weight:800;color:#f0b429;letter-spacing:3px;margin-bottom:8px">PRATIC</div>
        <div style="font-size:14px;color:#6b7280;margin-bottom:32px">Sistema de Produção</div>
        <div style="font-size:16px;color:#e8eaf0;margin-bottom:24px">Sessão encerrada com sucesso.</div>
        <button onclick="location.reload()" style="padding:14px 32px;background:#f0b429;color:#000;border:none;border-radius:10px;font-family:'Syne',sans-serif;font-size:15px;font-weight:700;cursor:pointer;letter-spacing:.5px">
          → Entrar novamente
        </button>
      </div>
    </div>`;
}

// ─── TABS RELATÓRIOS ──────────────────────────────────────────────────────────

function switchRelTab(tab) {
  ['producao','premiacao','estoque','pedidos','epi'].forEach(t=>{
    const el=document.getElementById('rel-content-'+t);
    const btn=document.getElementById('rtab-'+t);
    if(el) el.style.display = t===tab?'':'none';
    if(btn){btn.style.borderColor=t===tab?'var(--accent)':'';btn.style.color=t===tab?'var(--accent)':'';}
  });
  if(tab==='producao') loadRelProducao();
  if(tab==='premiacao') loadRelPremiacao();
  if(tab==='estoque') loadRelEstoque();
  if(tab==='pedidos') loadRelPedidos();
  if(tab==='epi') loadRelEPI();
}

async function loadRelPremiacao() {
  const mes = document.getElementById('rel-prem-mes')?.value || new Date().toISOString().slice(0,7);
  const [ops,auxs] = await Promise.all([api('/premiacao/operadores/'+mes),api('/premiacao/auxiliares/'+mes)]);
  const el = document.getElementById('rel-prem-content');
  if(!el) return;
  const STATUS_PILL = {aberto:'pill-info',em_producao:'pill-warn',produzido:'pill-success',entregue:'pill-success'};
  el.innerHTML = `
    <div class="table-wrap" style="margin-bottom:20px">
      <div class="table-head"><span class="table-head-title">Operadores — ${mes}</span></div>
      <table><thead><tr><th>Pos.</th><th>Colaborador</th><th>Total</th><th>Média/Dia</th><th>Dias</th><th>Elegível</th><th>Prêmio</th></tr></thead>
      <tbody>${ops.map((r,i)=>`<tr><td><strong>${i+1}º</strong></td><td>${r.colaborador}</td><td>${fmtNum(r.total_producao)}</td><td>${fmtNum(Math.round(r.media_diaria||0))}</td><td>${r.dias_trabalhados}</td><td><span class="pill ${r.elegivel?'pill-success':'pill-danger'}">${r.elegivel?'✓':'✕'}</span></td><td>${fmtBRL(r.valor_premio)}</td></tr>`).join('')}</tbody>
      </table></div>
    <div class="table-wrap">
      <div class="table-head"><span class="table-head-title">Auxiliares — ${mes}</span></div>
      <table><thead><tr><th>Pos.</th><th>Nome</th><th>Bônus</th><th>Observação</th></tr></thead>
      <tbody>${auxs.length?auxs.map(a=>`<tr><td><strong>${a.posicao}º</strong></td><td>${a.colaborador_nome}</td><td>${fmtBRL(a.valor_bonus)}</td><td style="color:var(--muted)">${a.observacao||'—'}</td></tr>`).join(''):'<tr><td colspan="4" style="text-align:center;color:var(--muted);padding:20px">Sem auxiliares premiados</td></tr>'}</tbody>
      </table></div>`;
}

async function loadRelEstoque() {
  await carregarCategoriasRelEstoque();

  const modelo = document.getElementById('rel-est-modelo')?.value || 'geral';
  const categoriaId = document.getElementById('rel-est-categoria')?.value || '';
  const tipoMov = document.getElementById('rel-est-tipo-mov')?.value || '';
  const dataIni = document.getElementById('rel-est-data-ini')?.value || '';
  const dataFim = document.getElementById('rel-est-data-fim')?.value || '';

  const isMov = modelo === 'movimentacoes';
  ['rel-est-tipo-mov','rel-est-data-ini','rel-est-data-sep','rel-est-data-fim'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = isMov ? '' : 'none';
  });

  const tbody = document.getElementById('rel-est-tbody');
  const thead = document.getElementById('rel-est-thead');
  const title = document.getElementById('rel-est-title');
  const cards = document.getElementById('rel-est-cards');
  if (!tbody || !thead) return;

  if (isMov) {
    const params = [];
    if (categoriaId) params.push('categoria_id=' + encodeURIComponent(categoriaId));
    if (tipoMov) params.push('tipo=' + encodeURIComponent(tipoMov));
    if (dataIni) params.push('data_inicio=' + encodeURIComponent(dataIni));
    if (dataFim) params.push('data_fim=' + encodeURIComponent(dataFim));
    const movs = await api('/estoque/movimentacoes' + (params.length ? '?' + params.join('&') : ''));

    const entradas = movs.filter(m => m.tipo === 'entrada').reduce((a,m)=>a+Number(m.quantidade||0),0);
    const saidas = movs.filter(m => ['saida','perda'].includes(m.tipo)).reduce((a,m)=>a+Number(m.quantidade||0),0);
    if (title) title.textContent = 'Movimentações de Estoque';
    if (cards) cards.innerHTML = [
      cardRelatorioEstoque('Movimentações', movs.length, 'registros encontrados'),
      cardRelatorioEstoque('Entradas', fmtNum(entradas), 'quantidade movimentada'),
      cardRelatorioEstoque('Saídas/Perdas', fmtNum(saidas), 'quantidade movimentada')
    ].join('');
    thead.innerHTML = '<tr><th>Data</th><th>Código</th><th>Produto</th><th>Categoria</th><th>Tipo</th><th>Quantidade</th><th>Saldo Depois</th><th>Motivo/Obs.</th></tr>';
    tbody.innerHTML = movs.length ? movs.map(m => {
      const tipoLabel = {entrada:'Entrada',saida:'Saída',perda:'Perda',ajuste:'Ajuste'}[m.tipo] || m.tipo;
      const pill = m.tipo === 'entrada' ? 'pill-success' : (m.tipo === 'perda' ? 'pill-danger' : 'pill-warn');
      return `<tr>
        <td>${fmtDate(m.data)}</td>
        <td><strong>${m.produto_codigo || '—'}</strong></td>
        <td>${m.produto_nome || '—'}</td>
        <td>${m.categoria_nome || '—'}</td>
        <td><span class="pill ${pill}">${tipoLabel}</span></td>
        <td>${fmtNum(m.quantidade)}</td>
        <td>${fmtNum(m.saldo_posterior)}</td>
        <td>${m.motivo || m.observacao || '—'}</td>
      </tr>`;
    }).join('') : '<tr><td colspan="8" style="text-align:center;color:var(--muted);padding:28px">Nenhuma movimentação encontrada</td></tr>';
    return;
  }

  let prods = await api('/estoque/produtos' + (categoriaId ? '?categoria_id=' + encodeURIComponent(categoriaId) : ''));
  const todos = prods.slice();

  if (modelo === 'falta') prods = prods.filter(p => Number(p.quantidade_atual || 0) <= 0);
  if (modelo === 'baixo') prods = prods.filter(p => Number(p.quantidade_atual || 0) > 0 && Number(p.quantidade_atual || 0) <= Number(p.estoque_minimo || 0));
  if (modelo === 'positivo') prods = prods.filter(p => Number(p.quantidade_atual || 0) > 0);
  if (modelo === 'sem_minimo') prods = prods.filter(p => Number(p.estoque_minimo || 0) <= 0);
  if (modelo === 'sem_movimento') {
    let movs = [];
    try { movs = await api('/estoque/movimentacoes'); } catch(e) { movs = []; }
    const idsComMov = new Set(movs.map(m => Number(m.produto_id)));
    prods = prods.filter(p => !idsComMov.has(Number(p.id)));
  }

  const titulos = {
    geral: 'Relatório Geral de Estoque',
    categoria: 'Produtos por Categoria',
    falta: 'Produtos em Falta no Estoque',
    baixo: 'Produtos com Estoque Baixo',
    positivo: 'Produtos com Saldo Positivo',
    sem_minimo: 'Produtos sem Estoque Mínimo Cadastrado',
    sem_movimento: 'Produtos sem Movimentação'
  };
  if (title) title.textContent = titulos[modelo] || 'Posição de Estoque';

  const totalGeral = todos.length;
  const totalFalta = todos.filter(p => Number(p.quantidade_atual || 0) <= 0).length;
  const totalBaixo = todos.filter(p => Number(p.quantidade_atual || 0) > 0 && Number(p.quantidade_atual || 0) <= Number(p.estoque_minimo || 0)).length;
  const totalOk = todos.filter(p => Number(p.quantidade_atual || 0) > Number(p.estoque_minimo || 0)).length;
  if (cards) cards.innerHTML = [
    cardRelatorioEstoque('Itens filtrados', prods.length, `de ${totalGeral} produtos ativos`),
    cardRelatorioEstoque('Falta em estoque', totalFalta, 'saldo igual ou menor que zero'),
    cardRelatorioEstoque('Estoque baixo', totalBaixo, 'saldo abaixo ou igual ao mínimo'),
    cardRelatorioEstoque('Estoque OK', totalOk, 'acima do mínimo')
  ].join('');

  thead.innerHTML = '<tr><th>Código</th><th>Produto</th><th>Categoria</th><th>Unidade</th><th>Saldo Atual</th><th>Mínimo</th><th>Situação</th></tr>';
  tbody.innerHTML = prods.length ? prods.map(p => {
    const st = statusEstoqueRel(p);
    return `<tr>
      <td><strong>${p.codigo || '—'}</strong></td>
      <td><strong>${p.nome}${p.marca ? ' — ' + p.marca : ''}</strong></td>
      <td>${p.categoria_nome || '—'}</td>
      <td>${p.unidade || '—'}</td>
      <td style="font-weight:700;color:${st.cor}">${fmtNum(p.quantidade_atual)}</td>
      <td>${fmtNum(p.estoque_minimo)}</td>
      <td><span class="pill ${st.pill}">${st.texto}</span></td>
    </tr>`;
  }).join('') : '<tr><td colspan="7" style="text-align:center;color:var(--muted);padding:28px">Nenhum produto encontrado para este filtro</td></tr>';
}

async function loadRelPedidos() {
  const status = document.getElementById('rel-ped-status')?.value||'';
  let url = '/pedidos/'; if(status) url+='?status='+status;
  const rows = await api(url);
  const SL={aberto:'📋 Aberto',em_producao:'🏭 Em produção',produzido:'✅ Produzido',entregue:'📦 Entregue'};
  const SP={aberto:'pill-info',em_producao:'pill-warn',produzido:'pill-success',entregue:'pill-success'};
  const tbody = document.getElementById('rel-ped-tbody');
  if(!tbody) return;
  tbody.innerHTML = rows.map(p=>{
    const dias=Math.round(p.dias_restantes);
    const cor=dias<0?'var(--danger)':dias<=3?'var(--warn)':'var(--success)';
    return `<tr><td><strong>${p.numero_pedido}</strong></td><td>${p.cliente_nome}</td><td>${fmtDate(p.prazo_entrega)}</td><td style="color:${cor};font-weight:700">${dias<0?'Vencido':dias+'d'}</td><td>${p.itens_entregues}/${p.total_itens}</td><td><span class="pill ${SP[p.status]}">${SL[p.status]}</span></td></tr>`;
  }).join('');
}

async function loadRelEPI() {
  const rows = await api('/epi/entregas');
  const ES={ativo:'pill-success',vencendo:'pill-warn',vencido:'pill-danger',devolvido:'pill-info',extraviado:'pill-danger'};
  const tbody = document.getElementById('rel-epi-tbody');
  if(!tbody) return;
  tbody.innerHTML = rows.map(r=>{
    const sc=r.status_calculado||r.status;
    const dias=r.dias_restantes;
    const cor=dias<0?'var(--danger)':dias<=30?'var(--warn)':'var(--success)';
    return `<tr><td><strong>${r.colaborador_nome}</strong></td><td>${r.epi_nome}</td><td>${r.epi_categoria||'—'}</td><td>${fmtDate(r.data_entrega)}</td><td>${fmtDate(r.data_validade)}</td><td style="color:${cor};font-weight:700">${dias<0?'Vencido':dias+'d'}</td><td><span class="pill ${ES[sc]||'pill-info'}">${sc}</span></td></tr>`;
  }).join('');
}

async function exportarRelatorio(tipo, formato) {
  if (formato==='pdf') {
    const maps={producao:'rel-prod-tbody',premiacao:'rel-prem-content',estoque:'rel-est-tbody',pedidos:'rel-ped-tbody',epi:'rel-epi-tbody'};
    const tits={producao:'Relatório de Produção',premiacao:'Relatório de Premiação',estoque:'Relatório de Estoque',pedidos:'Relatório de Pedidos',epi:'Relatório de EPI'};
    const el=document.getElementById(maps[tipo]);
    const tabela=el?.closest('table')||el;
    const win=window.open('','_blank');
    win.document.write(`<html><head><title>${tits[tipo]}</title><style>body{font-family:Arial,sans-serif;margin:20px;font-size:12px}table{width:100%;border-collapse:collapse}th{background:#333;color:#fff;padding:8px;text-align:left}td{padding:7px;border-bottom:1px solid #ddd}h2{font-size:16px}</style></head><body><h2>PRATIC — ${tits[tipo]}</h2><p style="color:#666">Gerado em: ${new Date().toLocaleString('pt-BR')}</p>${tabela?.outerHTML||'<p>Sem dados</p>'}</body></html>`);
    win.document.close();
    setTimeout(()=>win.print(),500);
  } else {
    const maps={producao:'rel-prod-tbody',estoque:'rel-est-tbody',pedidos:'rel-ped-tbody',epi:'rel-epi-tbody'};
    const el=document.getElementById(maps[tipo]);
    if(!el) return;
    const table=el.closest('table');
    if(!table) return;
    const rows=[];
    table.querySelectorAll('tr').forEach(tr=>{const row=[];tr.querySelectorAll('th,td').forEach(td=>row.push('"'+td.textContent.trim().replace(/"/g,'""')+'"'));rows.push(row.join(';'));});
    const csv='\uFEFF'+rows.join('\n');
    const blob=new Blob([csv],{type:'text/csv;charset=utf-8'});
    const a=document.createElement('a');
    a.href=URL.createObjectURL(blob);
    a.download=`pratic_${tipo}_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
  }
}

// ─── CONFIGURAÇÕES ────────────────────────────────────────────────────────────

async function loadConfiguracoes() {
  const configs = await api('/configuracoes/');
  const form = document.getElementById('config-form');
  if (!form) return;
  const sistemaConfigs = configs.filter(c =>
    !c.chave.startsWith('empresa_') && !c.chave.startsWith('perm_')
  );
  form.innerHTML = sistemaConfigs.map(c => `
    <div class="form-group mb-4">
      <label>${c.descricao || c.chave}</label>
      <div class="flex gap-2 items-center">
        <input type="${['valor','meta','bonus','qtd'].some(k=>c.chave.includes(k))?'number':'text'}"
          id="cfg-${c.chave}" value="${c.valor}" style="flex:1">
        <button class="btn btn-secondary" onclick="salvarConfig('${c.chave}')">Salvar</button>
      </div>
    </div>`).join('');
}

async function salvarConfig(chave) {
  const val = document.getElementById('cfg-' + chave)?.value;
  if (val === undefined) return;
  try {
    await api('/configuracoes/' + chave, 'PUT', { valor: val });
    showAlert('Configuração salva!');
  } catch(e) { showAlert(e.message, 'danger'); }
}

// ─── ESTOQUE ──────────────────────────────────────────────────────────────────

async function loadEstoque() {
  await Promise.all([loadCategoriasFiltro(), loadProdutos()]);
  loadAlertasEstoque();
}

async function loadCategoriasFiltro() {
  try {
    const cats = await api('/estoque/categorias');
    const sel = document.getElementById('est-filtro-cat');
    if (!sel) return;
    const val = sel.value;
    sel.innerHTML = '<option value="">Todas as categorias</option>' +
      cats.map(c => `<option value="${c.id}" ${c.id==val?'selected':''}>${c.nome}</option>`).join('');
  } catch(e) {}
}

async function loadProdutos() {
  const catId = document.getElementById('est-filtro-cat')?.value || '';
  let url = '/estoque/produtos';
  if (catId) url += '?categoria_id=' + catId;
  const prods = await api(url);
  const tbody = document.getElementById('est-tbody');
  if (!tbody) return;
  if (!prods.length) { tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--muted);padding:28px">Nenhum produto</td></tr>'; return; }
  tbody.innerHTML = prods.map(p => `
    <tr>
      <td><strong>${p.nome}${p.marca?' <span style="color:var(--muted)">— '+p.marca+'</span>':''}</strong></td>
      <td>${p.categoria_nome||'—'}</td>
      <td>${p.unidade}</td>
      <td style="font-weight:700;color:${p.alerta?'var(--danger)':'var(--text)'}">${fmtNum(p.quantidade_atual)}</td>
      <td>${fmtNum(p.estoque_minimo)}</td>
      <td><span class="pill ${p.alerta?'pill-danger':'pill-success'}">${p.alerta?'⚠ Abaixo':'✓ OK'}</span></td>
      <td class="flex gap-2">
        <button class="btn btn-sm btn-secondary" onclick="openModalMovimentacao(${p.id},'${p.nome}',${p.quantidade_atual})">📦 Mov.</button>
        <button class="btn btn-sm btn-secondary" onclick="editProduto(${p.id})">✏️</button>
        <button class="btn btn-sm btn-danger" onclick="deletarProduto(${p.id})">✕</button>
      </td>
    </tr>`).join('');
}

async function loadAlertasEstoque() {
  try {
    const alertas = await api('/estoque/alertas');
    const bannerEl = document.getElementById('dash-alerta-estoque');
    const badge = document.getElementById('nav-alerta-badge');
    if (alertas && alertas.length > 0) {
      if (badge) badge.style.display = 'inline';
      if (bannerEl) bannerEl.innerHTML = `
        <div style="background:rgba(239,68,68,.12);border:1px solid rgba(239,68,68,.35);border-radius:10px;padding:14px 18px;margin-bottom:20px;display:flex;align-items:center;gap:14px">
          <span style="font-size:22px">⚠️</span>
          <div style="flex:1">
            <div style="font-family:var(--font-head);font-weight:700;color:var(--danger);margin-bottom:4px">${alertas.length} produto(s) abaixo do estoque mínimo</div>
            <div style="font-size:13px;color:var(--muted)">${alertas.map(a=>`<strong>${a.codigo?'['+a.codigo+'] ':''}${a.nome}</strong>: ${a.quantidade_atual} ${a.unidade} (mín: ${a.estoque_minimo})`).join(' | ')}</div>
          </div>
          <button class="btn btn-sm btn-secondary" onclick="showPage('estoque')">Ver estoque →</button>
        </div>`;
    } else {
      if (badge) badge.style.display = 'none';
      if (bannerEl) bannerEl.innerHTML = '';
    }
  } catch(e) {}
}

async function openModalProduto() {
  const cats = await api('/estoque/categorias');
  const sel = document.getElementById('prod-categoria-id');
  if (sel) sel.innerHTML = '<option value="">— Sem categoria —</option>' + cats.map(c=>`<option value="${c.id}">${c.nome}</option>`).join('');
  ['prod-nome-est','prod-marca','prod-unidade','prod-minimo'].forEach(id => { const el=document.getElementById(id); if(el) el.value=''; });
  const u = document.getElementById('prod-unidade'); if(u) u.value='unidade';
  const m = document.getElementById('prod-minimo'); if(m) m.value='0';
  const ti = document.getElementById('modal-prod-est-title'); if(ti) ti.textContent='Novo Produto';
  const id = document.getElementById('prod-est-id'); if(id) id.value='';
  openModal('modal-produto-estoque');
}

async function editProduto(id) {
  const p = await api('/estoque/produtos/' + id);
  const cats = await api('/estoque/categorias');
  const sel = document.getElementById('prod-categoria-id');
  if (sel) sel.innerHTML = '<option value="">— Sem categoria —</option>' + cats.map(c=>`<option value="${c.id}" ${c.id===p.categoria_id?'selected':''}>${c.nome}</option>`).join('');
  const setVal = (elId, val) => { const el=document.getElementById(elId); if(el) el.value=val||''; };
  setVal('prod-est-id', p.id);
  setVal('prod-nome-est', p.nome);
  setVal('prod-marca', p.marca);
  setVal('prod-unidade', p.unidade);
  setVal('prod-minimo', p.estoque_minimo);
  const ti = document.getElementById('modal-prod-est-title'); if(ti) ti.textContent='Editar Produto';
  openModal('modal-produto-estoque');
}

async function salvarProdutoEstoque() {
  const id = document.getElementById('prod-est-id')?.value;
  const nome = (document.getElementById('prod-nome-est')?.value || '').trim();

  clearFieldHighlights('modal-produto-estoque');
  if (!nome) { highlightField('prod-nome-est', true, 'Informe o nome'); return; }

  const body = {
    codigo: _getVal('est-prod-codigo').trim(),
    categoria_id: +document.getElementById('prod-categoria-id')?.value || null,
    nome,
    marca: document.getElementById('prod-marca')?.value || '',
    unidade: document.getElementById('prod-unidade')?.value || 'unidade',
    estoque_minimo: +document.getElementById('prod-minimo')?.value || 0,
    ativo: 1
  };
  try {
    if (id) await api('/estoque/produtos/' + id, 'PUT', body);
    else await api('/estoque/produtos', 'POST', body);
    showAlert('Produto salvo!');
    closeModal('modal-produto-estoque');
    loadProdutos();
  } catch(e) { showAlert(e.message, 'danger'); }
}

async function deletarProduto(id) {
  if (!confirm('Desativar produto?')) return;
  await api('/estoque/produtos/' + id, 'DELETE');
  loadProdutos();
}

async function openModalMovimentacao(prodId, nome, saldo) {
  const el = document.getElementById('mov-produto-id'); if(el) el.value = prodId;
  const sEl = document.getElementById('mov-saldo-atual-label'); if(sEl) sEl.textContent = fmtNum(saldo);
  const nEl = document.getElementById('mov-produto-nome'); if(nEl) nEl.textContent = nome;
  const qEl = document.getElementById('mov-quantidade-est'); if(qEl) qEl.value = '';
  const obsEl = document.getElementById('mov-obs-est'); if(obsEl) obsEl.value = '';
  const dtEl = document.getElementById('mov-data-est'); if(dtEl) dtEl.value = new Date().toISOString().split('T')[0];
  openModal('modal-movimentacao');
}

async function salvarMovimentacao() {
  const qtd = +document.getElementById('mov-quantidade-est')?.value || 0;

  clearFieldHighlights('modal-movimentacao');
  if (qtd <= 0) { highlightField('mov-quantidade-est', true, 'Informe a quantidade (deve ser maior que 0)'); return; }

  const body = {
    produto_id: +document.getElementById('mov-produto-id')?.value,
    tipo: document.getElementById('mov-tipo-est')?.value || 'entrada',
    quantidade: qtd,
    responsavel: document.getElementById('mov-responsavel-est')?.value || '',
    observacao: document.getElementById('mov-obs-est')?.value || '',
    data: document.getElementById('mov-data-est')?.value || new Date().toISOString().split('T')[0]
  };
  try {
    await api('/estoque/movimentacoes', 'POST', body);
    showAlert('Movimentação registrada!');
    closeModal('modal-movimentacao');
    loadProdutos();
    loadAlertasEstoque();
  } catch(e) { showAlert(e.message, 'danger'); }
}

async function openModalCategoria() {
  const el = document.getElementById('cat-nome'); if(el) el.value = '';
  const el2 = document.getElementById('cat-desc'); if(el2) el2.value = '';
  const el3 = document.getElementById('cat-id'); if(el3) el3.value = '';
  openModal('modal-categoria-est');
}

async function salvarCategoria() {
  const id = document.getElementById('cat-id')?.value;
  const nome = (document.getElementById('cat-nome')?.value || '').trim();

  clearFieldHighlights('modal-categoria-est');
  if (!nome) { highlightField('cat-nome', true, 'Informe o nome'); return; }

  const body = { nome, descricao: document.getElementById('cat-desc')?.value || '' };
  try {
    if (id) await api('/estoque/categorias/' + id, 'PUT', body);
    else await api('/estoque/categorias', 'POST', body);
    showAlert('Categoria salva!');
    closeModal('modal-categoria-est');
    loadCategoriasFiltro();
  } catch(e) { showAlert(e.message, 'danger'); }
}

// ─── PEDIDOS (init) ───────────────────────────────────────────────────────────

async function loadPedidos_init() {
  await loadFila();
  await checkAlertasPedidos();
}

// ─── PERMISSÕES ───────────────────────────────────────────────────────────────

async function loadPermissoes() {
  try { permissoesAtuais = await api('/configuracoes/permissoes/all'); } catch(e) {
    permissoesAtuais = {
      perm_gestor:'dashboard,producao,premiacao,colaboradores,maquinas,pedidos,estoque,epi,graficos,relatorios,configuracoes,backup,permissoes,empresa',
      perm_producao:'dashboard,producao,premiacao,relatorios',
      perm_comercial:'dashboard,pedidos,relatorios',
      perm_estoque:'dashboard,estoque,relatorios'
    };
  }
  const tbody = document.getElementById('perm-tbody');
  if (!tbody) return;
  
  let html = '';
  
  // Section 1: Painel Principal
  html += `<tr><td colspan="5" class="perm-group-header">🖥️ Módulos do Painel Principal (Gestor)</td></tr>`;
  html += PAGINAS_SISTEMA.map(pg => {
    const cols = PERFIS.map(perf => {
      const chave = 'perm_' + perf.key;
      const perms = (permissoesAtuais[chave]||'').split(',').map(p=>p.trim());
      const checked = perms.includes(pg.key);
      return `
        <td style="text-align:center; vertical-align:middle; padding:8px 0;">
          <label class="switch-container">
            <input type="checkbox" id="perm_${perf.key}_${pg.key}" ${checked?'checked':''}>
            <span class="switch-slider"></span>
          </label>
        </td>`;
    }).join('');
    return `<tr><td style="font-weight:500; vertical-align:middle; padding-left:16px;">${pg.label}</td>${cols}</tr>`;
  }).join('');
  
  // Section 2: Portais & Apps Mobile
  html += `<tr><td colspan="5" class="perm-group-header" style="border-top:1px solid var(--border)">📱 Postos de Trabalho & Apps Mobile</td></tr>`;
  html += PORTAIS_MOBILE.map(pg => {
    const cols = PERFIS.map(perf => {
      const chave = 'perm_' + perf.key;
      const perms = (permissoesAtuais[chave]||'').split(',').map(p=>p.trim());
      const checked = perms.includes(pg.key);
      return `
        <td style="text-align:center; vertical-align:middle; padding:8px 0;">
          <label class="switch-container">
            <input type="checkbox" id="perm_${perf.key}_${pg.key}" ${checked?'checked':''}>
            <span class="switch-slider"></span>
          </label>
        </td>`;
    }).join('');
    return `<tr style="background:rgba(240,180,41,.02)"><td style="font-weight:500; vertical-align:middle; padding-left:16px;">${pg.label}</td>${cols}</tr>`;
  }).join('');
  
  tbody.innerHTML = html;

  // URLs
  let host = window.location.hostname;
  let isLoopback = host === 'localhost' || host === '127.0.0.1';
  if (isLoopback) {
    try {
      const res = await api('/configuracoes/local-ip');
      if (res && res.ip && res.ip !== '127.0.0.1') {
        host = res.ip;
        isLoopback = false;
      }
    } catch (e) {
      console.warn('Não foi possível obter o IP local da máquina:', e);
    }
  }
  const port = window.location.port || '8000';
  const urlsEl = document.getElementById('perm-urls');
  if (urlsEl) {
    const cardsHtml = [
      {perfil:'🖥️ Gestor',url:'/'},
      {perfil:'🏭 Setor Produção',url:'/producao-setor'},
      {perfil:'🏢 Comercial',url:'/?perfil=comercial'},
      {perfil:'📱 Mobile Operador',url:'/mobile'},
      {perfil:'📦 Mobile Estoque',url:'/estoque-mobile'},
      {perfil:'📖 Manual do Usuário',url:'/manual.html'},
    ].map(u=>`
      <div class="perm-url-card">
        <div style="font-weight:600; font-family:var(--font-head); font-size:14px;">${u.perfil}</div>
        <a href="${window.location.origin}${u.url}" target="_blank" style="text-decoration:none;display:flex;align-items:center;gap:8px;min-width:0;overflow:hidden">
          <span class="badge-url" style="min-width:0;overflow:hidden;text-overflow:ellipsis;">${window.location.origin}${u.url}</span>
          <span style="padding:8px 14px;font-size:12px;white-space:nowrap;background:var(--accent);color:#000;border-radius:6px;font-weight:bold;font-family:var(--font-head);cursor:pointer;transition:all 0.2s;flex-shrink:0;">Acessar ↗</span>
        </a>
      </div>
    `).join('');

    const tipHtml = `
      <div style="grid-column:1/-1;background:rgba(59,130,246,.08);border:1px solid rgba(59,130,246,.2);border-radius:8px;padding:12px 16px;margin-top:8px;font-size:13px;line-height:1.5;color:var(--text)">
        <div style="font-weight:700;color:var(--accent2);margin-bottom:4px;display:flex;align-items:center;gap:6px">💡 Dica de Acesso Mobile:</div>
        <p>Para acessar o sistema de outro dispositivo (como celular ou tablet conectado na mesma rede Wi-Fi):</p>
        <ul style="margin-left:20px;margin-top:4px;color:var(--muted)">
          <li>Use o endereço contendo o IP local da máquina: <strong>${window.location.origin}/mobile</strong></li>
          <li>Certifique-se de que o computador e o dispositivo móvel estão conectados no <strong>mesmo Wi-Fi</strong>.</li>
          <li>Caso não consiga conectar, garanta que a rede do Windows está configurada como <strong>Particular (Privada)</strong> ou que o <strong>Firewall do Windows</strong> possui uma regra de entrada liberando a porta necessária.</li>
        </ul>
      </div>
    `;
    urlsEl.innerHTML = cardsHtml + tipHtml;
  }
}

// ─── EPI ──────────────────────────────────────────────────────────────────────

let EPI_ENTREGAS_ATUAIS = [];

const EPI_STATUS = {
  ativo:{label:'✓ Ativo',pill:'pill-success'},
  vencendo:{label:'⚠ Vencendo',pill:'pill-warn'},
  vencido:{label:'✕ Vencido',pill:'pill-danger'},
  devolvido:{label:'↩ Devolvido',pill:'pill-info'},
  extraviado:{label:'? Extraviado',pill:'pill-danger'}
};

async function loadEPI() {
  await loadColsFiltroEPI();
  await loadEntregas();
  await checkAlertasEPI();
}

function switchEpiTab(tab) {
  ['entregas','cadastro','funcoes','alertas'].forEach(t=>{
    const el=document.getElementById('epi-content-'+t);
    const btn=document.getElementById('epi-tab-'+t);
    if(el) el.style.display=t===tab?'':'none';
    if(btn){btn.style.borderColor=t===tab?'var(--accent)':'';btn.style.color=t===tab?'var(--accent)':'';}
  });
  if(tab==='entregas') loadEntregas();
  if(tab==='cadastro') loadEPILista();
  if(tab==='funcoes') loadFuncaoEPIs();
  if(tab==='alertas') loadAlertasEPI();
}

async function checkAlertasEPI() {
  try {
    const al = await api('/epi/alertas');
    const badge = document.getElementById('nav-epi-badge');
    const total = (al.vencidos||0) + (al.vencendo||0);
    if(badge){badge.style.display=total>0?'inline':'none';badge.textContent=total;}
    const banner = document.getElementById('epi-alerta-banner');
    if(banner && total>0) {
      banner.innerHTML=`<div style="background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.3);border-radius:8px;padding:12px 16px;margin-bottom:16px;font-size:13px;color:var(--danger)">⚠️ <strong>${al.vencidos} EPI(s) vencido(s)</strong> | <strong>${al.vencendo} vencendo em 30 dias</strong> <button class="btn btn-sm btn-secondary" onclick="switchEpiTab('alertas')" style="margin-left:8px">Ver →</button></div>`;
    } else if(banner) banner.innerHTML='';
  } catch(e) {}
}

async function loadColsFiltroEPI() {
  const cols = await api('/colaboradores/');
  const sel = document.getElementById('epi-filtro-col');
  if(!sel || sel.options.length>1) return;
  cols.forEach(c=>{const o=document.createElement('option');o.value=c.id;o.textContent=c.nome;sel.appendChild(o);});
}

async function loadEntregas() {
  const colId = document.getElementById('epi-filtro-col')?.value||'';
  const status = document.getElementById('epi-filtro-status')?.value||'';
  let url='/epi/entregas';
  const p=[];
  if(colId) p.push('colaborador_id='+colId);
  if(status) p.push('status='+status);
  if(p.length) url+='?'+p.join('&');
  const rows = await api(url);
  EPI_ENTREGAS_ATUAIS = Array.isArray(rows) ? rows : [];
  const tbody = document.getElementById('epi-entregas-tbody');
  if(!tbody) return;
  if(!rows.length){tbody.innerHTML='<tr><td colspan="8" style="text-align:center;color:var(--muted);padding:28px">Nenhum registro</td></tr>';return;}
  tbody.innerHTML = rows.map(r=>{
    const sc=r.status_calculado||r.status;
    const st=EPI_STATUS[sc]||{label:sc,pill:'pill-info'};
    const dias=r.dias_restantes;
    const cor=dias<0?'var(--danger)':dias<=30?'var(--warn)':'var(--success)';
    return `<tr>
      <td><strong>${r.colaborador_nome}</strong></td>
      <td>${r.epi_nome}</td>
      <td style="color:var(--muted)">${r.epi_categoria||'—'}</td>
      <td>${fmtDate(r.data_entrega)}</td>
      <td>${fmtDate(r.data_validade)}</td>
      <td style="color:${cor};font-weight:600">${dias<0?'Vencido':dias+'d'}</td>
      <td><span class="pill ${st.pill}">${st.label}</span></td>
      <td class="flex gap-2">
        <button class="btn btn-sm btn-secondary" title="Gerar comprovante deste funcionário" onclick="gerarComprovante(${r.colaborador_id})">🖨️</button>
        <button class="btn btn-sm btn-secondary" onclick="renovarEPI(${r.id},${r.colaborador_id},${r.epi_id})">🔄</button>
        <button class="btn btn-sm btn-danger" onclick="deletarEntrega(${r.id})">✕</button>
      </td>
    </tr>`;
  }).join('');
}

async function loadEPILista() {
  const rows = await api('/epi/epis');
  const tbody = document.getElementById('epi-lista-tbody');
  if(!tbody) return;
  tbody.innerHTML = rows.map(r=>`<tr>
    <td><strong>${r.nome}</strong></td>
    <td><span class="pill pill-info">${r.categoria||'—'}</span></td>
    <td style="color:var(--muted)">${r.descricao||'—'}</td>
    <td><span class="pill ${r.ativo?'pill-success':'pill-danger'}">${r.ativo?'Ativo':'Inativo'}</span></td>
    <td class="flex gap-2">
      <button class="btn btn-sm btn-secondary" onclick="editEPI(${r.id},'${r.nome.replace(/'/g,"\\'")}','${r.categoria||''}','${r.descricao||''}')">✏️</button>
      <button class="btn btn-sm btn-danger" onclick="deletarEPI(${r.id})">✕</button>
    </td>
  </tr>`).join('');
}

async function loadFuncaoEPIs() {
  const [epis, funcaoEpis] = await Promise.all([api('/epi/epis'),api('/epi/funcoes-epis')]);
  const funcoes=['Operador MQ','Auxiliar','Gestor','Manutenção','Administrativo'];
  const el=document.getElementById('epi-funcoes-grid');
  if(!el) return;
  el.innerHTML = funcoes.map(f=>{
    const selecionados=(funcaoEpis[f]||[]).map(e=>e.epi_id);
    return `<div class="card" style="margin-bottom:16px">
      <div style="font-family:var(--font-head);font-weight:700;font-size:15px;margin-bottom:14px">⚙️ ${f}</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px;margin-bottom:14px">
        ${epis.map(e=>`<label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer">
          <input type="checkbox" id="funcao_${f.replace(/\s/g,'_')}_${e.id}" ${selecionados.includes(e.id)?'checked':''} style="width:16px;height:16px;accent-color:var(--accent)">
          ${e.nome} <span style="color:var(--muted);font-size:11px">(${e.categoria||'—'})</span>
        </label>`).join('')}
      </div>
      <button class="btn btn-sm btn-primary" onclick="salvarFuncaoEPI('${f}',${JSON.stringify(epis.map(e=>e.id))})">Salvar</button>
    </div>`;
  }).join('');
}

async function salvarFuncaoEPI(funcao, todosIds) {
  const selecionados = todosIds.filter(id=>{
    const el=document.getElementById(`funcao_${funcao.replace(/\s/g,'_')}_${id}`);
    return el&&el.checked;
  });
  try {
    await api('/epi/funcoes-epis','POST',{funcao,epi_ids:selecionados});
    showAlert(`EPIs da função "${funcao}" salvos!`);
  } catch(e){showAlert(e.message,'danger');}
}

async function loadAlertasEPI() {
  const al = await api('/epi/alertas');
  const el = document.getElementById('epi-alertas-content');
  if(!el) return;
  el.innerHTML = `
    <div class="cards-grid" style="margin-bottom:24px">
      <div class="card"><div class="card-label">EPIs Vencidos</div><div class="card-value danger">${al.vencidos}</div></div>
      <div class="card"><div class="card-label">Vencendo em 30 dias</div><div class="card-value accent">${al.vencendo}</div></div>
    </div>
    <div class="table-wrap">
      <div class="table-head"><span class="table-head-title">Pendências</span></div>
      <table><thead><tr><th>Funcionário</th><th>EPI</th><th>Validade</th><th>Situação</th></tr></thead>
      <tbody>${al.lista.length?al.lista.map(r=>{
        const cor=r.dias_restantes<0?'var(--danger)':'var(--warn)';
        return `<tr><td><strong>${r.colaborador}</strong></td><td>${r.epi}</td><td>${fmtDate(r.data_validade)}</td><td style="color:${cor};font-weight:600">${r.dias_restantes<0?'Vencido há '+Math.abs(r.dias_restantes)+'d':'Vence em '+r.dias_restantes+'d'}</td></tr>`;
      }).join(''):'<tr><td colspan="4" style="text-align:center;color:var(--muted);padding:20px">Nenhuma pendência</td></tr>'}</tbody></table>
    </div>`;
}

function openModalEPI() {
  document.getElementById('epi-id').value='';
  document.getElementById('epi-nome').value='';
  document.getElementById('epi-descricao').value='';
  document.getElementById('modal-epi-title').textContent='Cadastrar EPI';
  openModal('modal-epi');
}

function editEPI(id,nome,cat,desc) {
  document.getElementById('epi-id').value=id;
  document.getElementById('epi-nome').value=nome;
  document.getElementById('epi-categoria').value=cat;
  document.getElementById('epi-descricao').value=desc;
  document.getElementById('modal-epi-title').textContent='Editar EPI';
  openModal('modal-epi');
}

async function salvarEPI() {
  const id=document.getElementById('epi-id').value;
  const body={nome:document.getElementById('epi-nome').value,categoria:document.getElementById('epi-categoria').value,descricao:document.getElementById('epi-descricao').value,ativo:1};
  try {
    if(id) await api('/epi/epis/'+id,'PUT',body);
    else await api('/epi/epis','POST',body);
    showAlert('EPI salvo!');
    closeModal('modal-epi');
    loadEPILista();
  } catch(e){showAlert(e.message,'danger');}
}

async function deletarEPI(id) {
  if(!confirm('Desativar este EPI?')) return;
  await api('/epi/epis/'+id,'DELETE');
  showAlert('EPI desativado');
  loadEPILista();
}

async function openModalEntrega() {
  const [cols,epis] = await Promise.all([api('/colaboradores/'),api('/epi/epis')]);
  document.getElementById('entrega-colaborador').innerHTML=cols.map(c=>`<option value="${c.id}" data-tipo="${c.tipo}">${c.nome} (${formatTipoColaborador(c.tipo)})</option>`).join('');
  document.getElementById('entrega-epi').innerHTML=epis.map(e=>`<option value="${e.id}">${e.nome} — ${e.categoria||'—'}</option>`).join('');
  document.getElementById('entrega-data').value=new Date().toISOString().split('T')[0];
  document.getElementById('entrega-validade').value='';
  document.getElementById('entrega-responsavel').value='';
  document.getElementById('entrega-obs').value='';
  document.getElementById('entrega-sugestoes').style.display='none';
  openModal('modal-entrega-epi');
}

async function sugerirEPIs() {
  const sel=document.getElementById('entrega-colaborador').selectedOptions[0];
  const tipo=sel?.getAttribute('data-tipo')||'';
  if(!tipo) return;
  try {
    const epis=await api('/epi/epis-por-funcao/'+encodeURIComponent(tipo));
    if(epis.length){
      document.getElementById('entrega-sugestoes').style.display='';
      document.getElementById('entrega-sugestoes-lista').textContent=epis.map(e=>e.nome).join(', ');
    } else document.getElementById('entrega-sugestoes').style.display='none';
  } catch(e){}
}

async function salvarEntrega() {
  const body={
    colaborador_id:+document.getElementById('entrega-colaborador').value,
    epi_id:+document.getElementById('entrega-epi').value,
    data_entrega:document.getElementById('entrega-data').value,
    data_validade:document.getElementById('entrega-validade').value,
    motivo:document.getElementById('entrega-motivo').value,
    responsavel:document.getElementById('entrega-responsavel').value,
    observacao:document.getElementById('entrega-obs').value
  };
  if(!body.data_validade){showAlert('Informe a data de validade','danger');return;}
  try {
    await api('/epi/entregas','POST',body);
    showAlert('Entrega registrada!');
    closeModal('modal-entrega-epi');
    loadEntregas();
    checkAlertasEPI();
  } catch(e){showAlert(e.message,'danger');}
}

async function renovarEPI(id,colId,epiId) {
  await openModalEntrega();
  document.getElementById('entrega-colaborador').value=colId;
  document.getElementById('entrega-epi').value=epiId;
  document.getElementById('entrega-motivo').value='Troca periódica';
}

async function deletarEntrega(id) {
  if(!confirm('Remover registro?')) return;
  await api('/epi/entregas/'+id,'DELETE');
  showAlert('Registro removido');
  loadEntregas();
}

async function gerarComprovante(colaboradorId = null) {
  let colId = colaboradorId || document.getElementById('epi-filtro-col')?.value || '';

  if (!colId) {
    const idsVisiveis = [...new Set((EPI_ENTREGAS_ATUAIS || []).map(r => String(r.colaborador_id)).filter(Boolean))];
    if (idsVisiveis.length === 1) {
      colId = idsVisiveis[0];
    }
  }

  if(!colId){
    showAlert('Selecione um funcionário no filtro ou clique no botão de comprovante da linha do funcionário.','danger');
    return;
  }

  const data = await api('/epi/comprovante/' + colId);
  const emp = data.empresa || {};
  const agora = new Date();
  const dataHoraGeracao = agora.toLocaleString('pt-BR', { dateStyle:'short', timeStyle:'short' });
  const dataGeracaoExtenso = agora.toLocaleDateString('pt-BR', { day:'2-digit', month:'long', year:'numeric' });

  const safe = (v) => String(v ?? '').trim();
  const line = (...vals) => vals.map(safe).filter(Boolean).join(' ');
  const join = (sep, ...vals) => vals.map(safe).filter(Boolean).join(sep);
  const empresaNome = safe(emp.nome) || 'PRATIC';
  const enderecoLinha1 = join(', ', safe(emp.logradouro || emp.endereco), safe(emp.numero));
  const enderecoLinha2 = join(' - ', safe(emp.bairro), safe(emp.complemento));
  const cidadeUF = join('/', safe(emp.cidade), safe(emp.uf));
  const cep = safe(emp.cep);
  const cidadeRodape = cidadeUF || safe(emp.cidade) || 'Cidade não informada';
  const logoHtml = emp.logo
    ? `<img src="${emp.logo}" style="max-height:72px;max-width:210px;object-fit:contain">`
    : `<div style="font-size:24px;font-weight:800;letter-spacing:.5px">${empresaNome}</div>`;
  const epis = Array.isArray(data.epis) ? data.epis : [];

  document.getElementById('comprovante-content').innerHTML = `
    <div id="print-area" style="font-family:Arial,sans-serif;font-size:12px;color:#111;line-height:1.35;max-width:900px;margin:0 auto;min-height:1040px;position:relative;padding:14px 20px 54px;background:#fff">
      <div style="display:grid;grid-template-columns:220px 1fr;gap:20px;align-items:center;border-bottom:2px solid #222;padding-bottom:12px;margin-bottom:12px">
        <div style="display:flex;align-items:center;justify-content:flex-start;min-height:76px">${logoHtml}</div>
        <div style="text-align:right;font-size:11px;color:#333">
          <div style="font-size:15px;font-weight:800;text-transform:uppercase;color:#111;margin-bottom:4px">${empresaNome}</div>
          <div>${line('CNPJ:', emp.cnpj)}</div>
          <div>${line('Telefone:', emp.telefone)}${emp.email ? ' | E-mail: ' + safe(emp.email) : ''}</div>
          <div>${enderecoLinha1}</div>
          <div>${enderecoLinha2}</div>
          <div>${cidadeUF}${cep ? ' | CEP: ' + cep : ''}</div>
        </div>
      </div>

      <h2 style="text-align:center;margin:8px 0 12px;font-size:16px;text-transform:uppercase;letter-spacing:.3px">Comprovante de Entrega de EPI</h2>

      <table style="width:100%;border-collapse:collapse;margin-bottom:12px;font-size:12px">
        <tbody>
          <tr>
            <td style="border:1px solid #ddd;padding:7px;background:#f3f4f6;width:18%;font-weight:bold">Funcionário</td>
            <td style="border:1px solid #ddd;padding:7px;width:32%">${safe(data.colaborador?.nome)}</td>
            <td style="border:1px solid #ddd;padding:7px;background:#f3f4f6;width:15%;font-weight:bold">Função</td>
            <td style="border:1px solid #ddd;padding:7px;width:35%">${safe(data.colaborador?.tipo || 'Não informada')}</td>
          </tr>
          <tr>
            <td style="border:1px solid #ddd;padding:7px;background:#f3f4f6;font-weight:bold">Data do comprovante</td>
            <td style="border:1px solid #ddd;padding:7px">${fmtDate(data.data_geracao)}</td>
            <td style="border:1px solid #ddd;padding:7px;background:#f3f4f6;font-weight:bold">Gerado em</td>
            <td style="border:1px solid #ddd;padding:7px">${dataHoraGeracao}</td>
          </tr>
        </tbody>
      </table>

      <div style="border:1px solid #ddd;background:#fafafa;padding:10px 12px;margin:0 0 12px;font-size:11.5px;text-align:justify">
        <strong>Motivo e base legal:</strong> o presente comprovante registra a entrega gratuita de Equipamento de Proteção Individual ao colaborador acima identificado, para proteção contra riscos ocupacionais da função e controle formal de fornecimento pela empresa. Conforme o art. 166 da CLT, a empresa deve fornecer gratuitamente EPI adequado ao risco, em perfeito estado de conservação e funcionamento, quando as medidas de proteção coletiva não oferecerem proteção completa. Conforme a NR-6, cabe à organização adquirir EPI aprovado, orientar e treinar o empregado quanto ao uso adequado, guarda e conservação, exigir seu uso, substituir quando danificado ou extraviado e registrar o fornecimento. O colaborador declara ciência de que deve utilizar o EPI apenas para a finalidade a que se destina, zelar pela guarda e conservação e comunicar qualquer alteração que o torne impróprio para uso.
      </div>

      <table style="width:100%;border-collapse:collapse;margin-bottom:20px;font-size:12px">
        <thead>
          <tr style="background:#222;color:#fff">
            <th style="padding:8px;text-align:left;border:1px solid #222">EPI Entregue</th>
            <th style="padding:8px;text-align:left;border:1px solid #222">Categoria</th>
            <th style="padding:8px;text-align:center;border:1px solid #222">Entregue em</th>
            <th style="padding:8px;text-align:center;border:1px solid #222">Válido até</th>
            <th style="padding:8px;text-align:left;border:1px solid #222">Motivo</th>
          </tr>
        </thead>
        <tbody>${epis.length ? epis.map((e,i)=>`<tr style="background:${i%2?'#fbfbfb':'#fff'}">
          <td style="padding:7px 8px;border:1px solid #ddd;font-weight:bold">${safe(e.epi_nome)}</td>
          <td style="padding:7px 8px;border:1px solid #ddd">${safe(e.categoria) || '—'}</td>
          <td style="padding:7px 8px;border:1px solid #ddd;text-align:center">${fmtDate(e.data_entrega)}</td>
          <td style="padding:7px 8px;border:1px solid #ddd;text-align:center">${fmtDate(e.data_validade)}</td>
          <td style="padding:7px 8px;border:1px solid #ddd">${safe(e.motivo) || 'Entrega inicial'}</td>
        </tr>`).join('') : `<tr><td colspan="5" style="padding:10px;border:1px solid #ddd;text-align:center;color:#666">Nenhum EPI ativo encontrado para este colaborador.</td></tr>`}</tbody>
      </table>

      <div style="border:1px solid #ddd;padding:10px 12px;margin-bottom:34px;font-size:11.5px;text-align:justify">
        Declaro que recebi os EPIs listados neste comprovante, em boas condições de uso, bem como as orientações necessárias sobre utilização, conservação, guarda e comunicação de qualquer irregularidade, comprometendo-me a utilizá-los corretamente durante a execução das minhas atividades.
      </div>

      <div style="margin-top:30px;display:grid;grid-template-columns:1fr 1fr;gap:44px">
        <div style="text-align:center"><div style="border-top:1px solid #333;padding-top:8px;font-size:12px;font-weight:bold">Assinatura do Funcionário</div><div style="font-size:11px;color:#555;margin-top:4px">${safe(data.colaborador?.nome)}</div></div>
        <div style="text-align:center"><div style="border-top:1px solid #333;padding-top:8px;font-size:12px;font-weight:bold">Responsável pela Entrega</div><div style="font-size:11px;color:#555;margin-top:4px">${safe(epis[0]?.responsavel) || '_______________'}</div></div>
      </div>

      <div style="position:absolute;left:20px;right:20px;bottom:12px;border-top:1px solid #ddd;padding-top:7px;font-size:10.5px;color:#555;display:flex;justify-content:space-between;gap:20px">
        <span>${cidadeRodape}, ${dataGeracaoExtenso} — gerado às ${agora.toLocaleTimeString('pt-BR', {hour:'2-digit', minute:'2-digit'})}</span>
        <span>Comprovante emitido pelo sistema PRATIC</span>
      </div>
    </div>`;
  openModal('modal-comprovante');
}

function imprimirComprovante() {
  const content = document.getElementById('print-area')?.outerHTML;
  if(!content) return;
  const win = window.open('', '_blank');
  win.document.write(`<html><head><title>Comprovante de Entrega de EPI</title><style>
    @page { size: A4; margin: 12mm; }
    * { box-sizing: border-box; }
    body { font-family: Arial, sans-serif; margin: 0; background: #fff; }
    table { page-break-inside: auto; }
    tr { page-break-inside: avoid; page-break-after: auto; }
    img { max-width: 100%; }
  </style></head><body>${content}</body></html>`);
  win.document.close();
  win.focus();
  setTimeout(() => win.print(), 300);
}

// ─── PEDIDOS ──────────────────────────────────────────────────────────────────

const STATUS_LABEL_PED={aberto:'📋 Aberto',em_producao:'🏭 Em produção',produzido:'✅ Produzido',entregue:'📦 Entregue'};
const STATUS_PILL_PED={aberto:'pill-info',em_producao:'pill-warn',produzido:'pill-success',entregue:'pill-success'};
const STATUS_NEXT_PED={aberto:'em_producao',em_producao:'produzido',produzido:'entregue',entregue:null};
const STATUS_NEXT_LABEL_PED={aberto:'→ Iniciar',em_producao:'→ Produzido',produzido:'→ Entregue',entregue:null};

function switchPedidosTab(tab) {
  ['fila','pedidos','clientes'].forEach(t=>{
    const el=document.getElementById('ped-tab-'+t);
    const btn=document.getElementById('ptab-'+t);
    if(el) el.style.display=t===tab?'':'none';
    if(btn){btn.style.borderColor=t===tab?'var(--accent)':'';btn.style.color=t===tab?'var(--accent)':'';}
  });
  if(tab==='fila') loadFila();
  if(tab==='pedidos') loadPedidos();
  if(tab==='clientes') loadClientes();
}

async function loadPedidos_init() {
  await loadFila();
  await checkAlertasPedidos();
}

async function checkAlertasPedidos() {
  try {
    const al=await api('/pedidos/alertas/resumo');
    const badge=document.getElementById('nav-pedidos-badge');
    const total=(al.vencidos||0)+(al.urgentes||0);
    if(badge){badge.style.display=total>0?'inline':'none';badge.textContent=total;}
    const dashEl=document.getElementById('dash-alerta-pedidos');
    if(dashEl&&total>0){
      const lista=al.lista_urgentes.map(p=>{const dias=Math.round(p.dias_restantes);const cor=dias<0?'var(--danger)':'var(--accent)';return `<strong>${p.numero_pedido}</strong> — ${p.cliente} <span style="color:${cor}">(${dias<0?'vencido há '+Math.abs(dias)+'d':dias+'d restantes'})</span>`;}).join(' | ');
      dashEl.innerHTML=`<div style="background:rgba(239,68,68,.12);border:1px solid rgba(239,68,68,.35);border-radius:10px;padding:14px 18px;margin-bottom:20px;display:flex;align-items:center;gap:14px"><span style="font-size:22px">🧾</span><div style="flex:1"><div style="font-family:var(--font-head);font-weight:700;color:var(--danger);margin-bottom:4px">${al.vencidos} pedido(s) vencido(s) | ${al.urgentes} vencem em até 3 dias</div><div style="font-size:13px;color:var(--muted)">${lista}</div></div><button class="btn btn-sm btn-secondary" onclick="showPage('pedidos')" style="white-space:nowrap">Ver pedidos →</button></div>`;
    } else if(dashEl) dashEl.innerHTML='';
  } catch(e){}
}

async function loadFila() {
  const status=document.getElementById('ped-fila-status')?.value||'';
  let url='/pedidos/fila/producao';if(status) url+='?status='+status;
  const itens=await api(url);
  const el=document.getElementById('ped-fila-cards');
  if(!el) return;
  try {
    const al=await api('/pedidos/alertas/resumo');
    const banner=document.getElementById('ped-alertas-banner');
    if(banner&&(al.vencidos+al.urgentes)>0){banner.innerHTML=`<div style="background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.3);border-radius:8px;padding:12px 16px;margin-bottom:16px;font-size:13px;color:var(--danger)">⚠️ <strong>${al.vencidos} vencido(s)</strong> | <strong>${al.urgentes} urgente(s)</strong></div>`;}
    else if(banner) banner.innerHTML='';
  } catch(e){}
  if(!itens.length){el.innerHTML='<div class="table-wrap"><p style="padding:32px;text-align:center;color:var(--muted)">Nenhum item na fila</p></div>';return;}
  const grupos={};
  itens.forEach(i=>{const k=i.pedido_id;if(!grupos[k])grupos[k]={pedido:i,itens:[]};grupos[k].itens.push(i);});
  el.innerHTML=Object.values(grupos).map(g=>{
    const p=g.pedido;
    const dias=Math.round(p.dias_restantes);
    const diasCor=dias<0?'var(--danger)':dias<=3?'var(--accent)':'var(--success)';
    const diasLabel=dias<0?`Vencido há ${Math.abs(dias)}d`:dias===0?'Vence hoje!':`${dias}d restantes`;
    const itensList=g.itens.map(i=>{
      const pct=Math.min(100,Math.round((i.qtd_produzida/i.quantidade)*100));
      const prox=STATUS_NEXT_PED[i.status];
      return `<div style="padding:12px 0;border-bottom:1px solid var(--border)">
        <div class="flex items-center justify-between" style="margin-bottom:8px">
          <div><span style="font-weight:600">${i.descricao}</span><span class="pill ${STATUS_PILL_PED[i.status]}" style="margin-left:8px;font-size:11px">${STATUS_LABEL_PED[i.status]}</span></div>
          <div class="flex gap-2">
            ${prox?`<button class="btn btn-sm btn-secondary" onclick="avancarItemStatus(${i.id},'${prox}',${i.quantidade})">${STATUS_NEXT_LABEL_PED[i.status]}</button>`:''}
            <button class="btn btn-sm btn-danger" onclick="removerItemFila(${i.id})">✕</button>
          </div>
        </div>
        <div style="font-size:12px;color:var(--muted);margin-bottom:6px">Qtd: <strong style="color:var(--text)">${fmtNum(i.qtd_produzida)} / ${fmtNum(i.quantidade)} ${i.unidade}</strong></div>
        <div style="height:6px;background:var(--surface2);border-radius:3px;overflow:hidden"><div style="height:100%;width:${pct}%;background:${pct>=100?'var(--success)':'var(--accent)'};border-radius:3px"></div></div>
      </div>`;
    }).join('');
    return `<div class="card" style="margin-bottom:16px;border-left:3px solid ${diasCor}">
      <div class="flex items-center justify-between" style="margin-bottom:12px">
        <div><div style="font-family:var(--font-head);font-size:16px;font-weight:700">${p.numero_pedido}</div><div style="font-size:13px;color:var(--muted);margin-top:2px">${p.cliente_nome}</div></div>
        <div style="text-align:right"><div style="font-family:var(--font-head);font-weight:800;color:${diasCor}">${diasLabel}</div><div style="font-size:12px;color:var(--muted)">${fmtDate(p.prazo_entrega)}</div></div>
      </div>${itensList}
    </div>`;
  }).join('');
}

async function avancarItemStatus(id,novoStatus,qtdTotal) {
  const qtd=novoStatus==='produzido'||novoStatus==='entregue'?qtdTotal:0;
  try {
    await api('/pedidos/itens/'+id+'/status','PUT',{status:novoStatus,qtd_produzida:qtd});
    showAlert('Status atualizado!');
    loadFila();
    checkAlertasPedidos();
  } catch(e){showAlert(e.message,'danger');}
}

async function removerItemFila(id) {
  if(!confirm('Remover item?')) return;
  await api('/pedidos/itens/'+id,'DELETE');
  loadFila();
}

async function loadPedidos() {
  const status=document.getElementById('ped-status-filtro')?.value||'';
  let url='/pedidos/';if(status) url+='?status='+status;
  const rows=await api(url);
  const tbody=document.getElementById('ped-tbody');
  if(!tbody) return;
  tbody.innerHTML=rows.map(p=>{
    const dias=Math.round(p.dias_restantes);
    const diasCor=dias<0?'var(--danger)':dias<=3?'var(--warn)':'var(--success)';
    return `<tr>
      <td><strong>${p.numero_pedido}</strong></td>
      <td>${p.cliente_nome}</td>
      <td>${fmtDate(p.prazo_entrega)}</td>
      <td style="color:${diasCor};font-weight:700">${dias<0?'Vencido':dias+'d'}</td>
      <td>${p.itens_entregues}/${p.total_itens}</td>
      <td><span class="pill ${STATUS_PILL_PED[p.status]}">${STATUS_LABEL_PED[p.status]}</span></td>
      <td class="flex gap-2">
        <button class="btn btn-sm btn-secondary" onclick="verDetalhesPedido(${p.id})">Ver</button>
        <button class="btn btn-sm btn-danger" onclick="deletarPedido(${p.id})">✕</button>
      </td>
    </tr>`;
  }).join('');
}

async function verDetalhesPedido(id) {
  const p=await api('/pedidos/'+id);
  const dias=Math.round(p.dias_restantes);
  const diasCor=dias<0?'var(--danger)':dias<=3?'var(--warn)':'var(--success)';
  document.getElementById('modal-ped-det-title').textContent='Pedido '+p.numero_pedido;
  document.getElementById('modal-ped-det-content').innerHTML=`
    <div class="cards-grid" style="margin-bottom:16px">
      <div class="card"><div class="card-label">Cliente</div><div style="font-weight:600">${p.cliente_nome}</div></div>
      <div class="card"><div class="card-label">Prazo</div><div style="font-family:var(--font-head);font-weight:800;color:${diasCor}">${fmtDate(p.prazo_entrega)}</div></div>
      <div class="card"><div class="card-label">Status</div><span class="pill ${STATUS_PILL_PED[p.status]}">${STATUS_LABEL_PED[p.status]}</span></div>
    </div>
    <div class="table-wrap">
      <div class="table-head"><span class="table-head-title">Itens</span></div>
      <table><thead><tr><th>Descrição</th><th>Qtd</th><th>Produzido</th><th>Status</th><th></th></tr></thead>
      <tbody>${p.itens.map(i=>{
        const pct=Math.min(100,Math.round((i.qtd_produzida/i.quantidade)*100));
        const prox=STATUS_NEXT_PED[i.status];
        return `<tr><td>${i.descricao}</td><td>${fmtNum(i.quantidade)}</td>
          <td><div>${fmtNum(i.qtd_produzida)} (${pct}%)</div><div style="height:4px;background:var(--surface2);border-radius:2px;margin-top:4px;width:80px"><div style="height:100%;width:${pct}%;background:${pct>=100?'var(--success)':'var(--accent)'};border-radius:2px"></div></div></td>
          <td><span class="pill ${STATUS_PILL_PED[i.status]}">${STATUS_LABEL_PED[i.status]}</span></td>
          <td>${prox?`<button class="btn btn-sm btn-secondary" onclick="avancarItemStatus(${i.id},'${prox}',${i.quantidade});closeModal('modal-ped-detalhe');loadPedidos()">${STATUS_NEXT_LABEL_PED[i.status]}</button>`:''}</td>
        </tr>`;
      }).join('')}</tbody></table>
    </div>`;
  openModal('modal-ped-detalhe');
}

async function deletarPedido(id) {
  if(!confirm('Remover pedido?')) return;
  await api('/pedidos/'+id,'DELETE');
  showAlert('Pedido removido');
  loadPedidos();
}

let pedidoItens=[];
async function openModalPedido() {
  pedidoItens=[];
  document.getElementById('ped-id').value='';
  document.getElementById('ped-numero').value='';
  document.getElementById('ped-prazo').value='';
  document.getElementById('ped-vendedor').value='';
  document.getElementById('ped-obs').value='';
  const clientes=await api('/pedidos/clientes');
  document.getElementById('ped-cliente').innerHTML=clientes.map(c=>`<option value="${c.id}">${c.razao_social}${c.nome_fantasia?' — '+c.nome_fantasia:''}</option>`).join('');
  renderItensPedido();
  openModal('modal-pedido');
}

function renderItensPedido() {
  const el=document.getElementById('ped-itens-list');
  if(!el) return;
  if(!pedidoItens.length){el.innerHTML='<p style="color:var(--muted);font-size:13px;padding:8px 0">Nenhum item</p>';return;}
  el.innerHTML=pedidoItens.map((item,idx)=>`
    <div style="display:grid;grid-template-columns:1fr auto auto auto;gap:8px;align-items:center;margin-bottom:8px">
      <input type="text" value="${item.descricao}" placeholder="Descrição *" oninput="pedidoItens[${idx}].descricao=this.value" style="font-size:13px">
      <input type="number" value="${item.quantidade}" min="1" placeholder="Qtd" oninput="pedidoItens[${idx}].quantidade=+this.value" style="width:80px;font-size:13px">
      <select onchange="pedidoItens[${idx}].unidade=this.value" style="font-size:13px">
        ${['unidade','kg','litro','metro','caixa','pacote'].map(u=>`<option value="${u}" ${item.unidade===u?'selected':''}>${u}</option>`).join('')}
      </select>
      <button class="btn btn-sm btn-danger" onclick="pedidoItens.splice(${idx},1);renderItensPedido()">✕</button>
    </div>`).join('');
}

function addItemPedido(){pedidoItens.push({descricao:'',quantidade:1,unidade:'unidade'});renderItensPedido();}

async function salvarPedido() {
  const body={numero_pedido:document.getElementById('ped-numero').value,cliente_id:+document.getElementById('ped-cliente').value,prazo_entrega:document.getElementById('ped-prazo').value,vendedor:document.getElementById('ped-vendedor').value,observacoes:document.getElementById('ped-obs').value,itens:pedidoItens.filter(i=>i.descricao.trim())};
  if(!body.numero_pedido){showAlert('Informe o número','danger');return;}
  if(!body.prazo_entrega){showAlert('Informe o prazo','danger');return;}
  if(!body.itens.length){showAlert('Adicione ao menos um item','danger');return;}
  try {
    await api('/pedidos/','POST',body);
    showAlert('Pedido salvo!');
    closeModal('modal-pedido');
    loadFila();
    checkAlertasPedidos();
  } catch(e){showAlert(e.message,'danger');}
}

async function loadClientes() {
  const busca=document.getElementById('ped-busca-cliente')?.value||'';
  let url='/pedidos/clientes';if(busca) url+='?busca='+encodeURIComponent(busca);
  const rows=await api(url);
  const tbody=document.getElementById('ped-clientes-tbody');
  if(!tbody) return;
  tbody.innerHTML=rows.map(c=>`<tr>
    <td><strong>${c.razao_social}</strong></td>
    <td>${c.nome_fantasia||'—'}</td>
    <td>${c.cnpj?c.cnpj.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/,'$1.$2.$3/$4-$5'):'—'}</td>
    <td>${c.cidade?c.cidade+'/'+c.uf:'—'}</td>
    <td>${c.total_pedidos||0}</td>
    <td class="flex gap-2">
      <button class="btn btn-sm btn-secondary" onclick="editCliente(${c.id})">Editar</button>
      <button class="btn btn-sm btn-danger" onclick="deletarCliente(${c.id})">✕</button>
    </td>
  </tr>`).join('');
}

function openModalCliente(){
  ['cnpj','razao','fantasia','ie','email','telefone','cep','numero','logradouro','bairro','complemento','cidade','uf','obs'].forEach(f=>{const el=document.getElementById('cli-'+f);if(el)el.value='';});
  document.getElementById('cli-id').value='';
  document.getElementById('modal-cli-title').textContent='Cadastrar Cliente';
  openModal('modal-cliente');
}

async function editCliente(id) {
  const c=await api('/pedidos/clientes/'+id);
  const setV=(k,v)=>{const el=document.getElementById('cli-'+k);if(el)el.value=v||'';};
  setV('id',c.id);setV('cnpj',c.cnpj);setV('razao',c.razao_social);setV('fantasia',c.nome_fantasia);
  setV('ie',c.ie);setV('email',c.email);setV('telefone',c.telefone);setV('cep',c.cep);
  setV('numero',c.numero);setV('logradouro',c.logradouro);setV('bairro',c.bairro);
  setV('complemento',c.complemento);setV('cidade',c.cidade);setV('uf',c.uf);setV('obs',c.observacoes);
  document.getElementById('modal-cli-title').textContent='Editar Cliente';
  openModal('modal-cliente');
}

async function buscarCNPJ() {
  const cnpj=document.getElementById('cli-cnpj')?.value.replace(/\D/g,'');
  if(cnpj?.length!==14){showAlert('CNPJ deve ter 14 dígitos','danger');return;}
  try {
    const d=await api('/pedidos/busca-cnpj/'+cnpj);
    const setV=(k,v)=>{const el=document.getElementById('cli-'+k);if(el)el.value=v||'';};
    setV('razao',d.razao_social);setV('fantasia',d.nome_fantasia);setV('email',d.email);
    setV('telefone',d.telefone);setV('cep',d.cep);setV('logradouro',d.logradouro);
    setV('numero',d.numero);setV('bairro',d.bairro);setV('cidade',d.cidade);setV('uf',d.uf);
    showAlert('CNPJ encontrado!');
  } catch(e){showAlert('CNPJ não encontrado','danger');}
}

async function buscarCEP() {
  const cep=document.getElementById('cli-cep')?.value.replace(/\D/g,'');
  if(cep?.length!==8){showAlert('CEP inválido','danger');return;}
  try {
    const d=await api('/pedidos/busca-cep/'+cep);
    const setV=(k,v)=>{const el=document.getElementById('cli-'+k);if(el)el.value=v||'';};
    setV('logradouro',d.logradouro);setV('bairro',d.bairro);setV('cidade',d.cidade);setV('uf',d.uf);
    showAlert('CEP encontrado!');
  } catch(e){showAlert('CEP não encontrado','danger');}
}

async function salvarCliente() {
  const getV=k=>{const el=document.getElementById('cli-'+k);return el?el.value:'';};
  const body={cnpj:getV('cnpj').replace(/\D/g,''),razao_social:getV('razao'),nome_fantasia:getV('fantasia'),ie:getV('ie'),email:getV('email'),telefone:getV('telefone'),cep:getV('cep').replace(/\D/g,''),logradouro:getV('logradouro'),numero:getV('numero'),complemento:getV('complemento'),bairro:getV('bairro'),cidade:getV('cidade'),uf:getV('uf'),observacoes:getV('obs')};
  if(!body.razao_social){showAlert('Informe a razão social','danger');return;}
  const id=getV('id');
  try {
    if(id) await api('/pedidos/clientes/'+id,'PUT',body);
    else await api('/pedidos/clientes','POST',body);
    showAlert('Cliente salvo!');
    closeModal('modal-cliente');
    loadClientes();
  } catch(e){showAlert(e.message,'danger');}
}

async function deletarCliente(id){
  if(!confirm('Desativar cliente?')) return;
  await api('/pedidos/clientes/'+id,'DELETE');
  loadClientes();
}

// ─── EMPRESA ──────────────────────────────────────────────────────────────────

async function loadEmpresa() {
  const campos = ['nome','cnpj','telefone','email','cep','numero','logradouro','bairro','complemento','cidade','uf'];
  try {
    const r = await fetch(API + '/configuracoes/empresa', { cache: 'no-store' });
    const dados = await r.json();
    if (!r.ok) throw new Error(dados.detail || dados.mensagem || 'Erro ao carregar dados da empresa');

    for (const campo of campos) {
      const el = document.getElementById('emp-' + campo);
      if (el) el.value = dados[campo] || '';
    }

    const prev = document.getElementById('empresa-logo-preview');
    if (prev) {
      if (dados.logo) prev.innerHTML = `<img src="${dados.logo}" style="max-width:100%;max-height:100%;object-fit:contain">`;
      else prev.innerHTML = 'Sem logo';
    }
  } catch(e) {
    console.error('Erro ao carregar dados da empresa:', e);
    const alertEl = document.getElementById('empresa-alert');
    if (alertEl) alertEl.innerHTML = `<div class="alert alert-danger">Erro ao carregar dados da empresa: ${e.message}</div>`;
  }
}

async function salvarEmpresa() {
  const campos = ['nome','cnpj','telefone','email','cep','numero','logradouro','bairro','complemento','cidade','uf'];
  const alertEl = document.getElementById('empresa-alert');
  const body = {};

  for (const campo of campos) {
    const el = document.getElementById('emp-' + campo);
    body[campo] = el ? el.value.trim() : '';
  }

  try {
    let r = await fetch(API + '/configuracoes/empresa', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(body)
    });

    // Compatibilidade para cache/versões antigas do servidor que possam rejeitar POST.
    if (r.status === 405) {
      r = await fetch(API + '/configuracoes/empresa', {
        method: 'PUT',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(body)
      });
    }

    const d = await r.json().catch(() => ({}));
    if (!r.ok) {
      if (r.status === 405) throw new Error('Servidor antigo em execução. Feche o terminal do sistema, abra novamente pelo Iniciar_PRATIC.bat e pressione Ctrl + F5.');
      throw new Error(d.detail || d.mensagem || 'Não foi possível salvar os dados da empresa');
    }

    if (alertEl) {
      alertEl.innerHTML = '<div class="alert alert-success">✅ Dados da empresa salvos no banco!</div>';
      setTimeout(()=>alertEl.innerHTML='',3000);
    }
    await loadEmpresa();
    await loadTopbarWidgets();
  } catch(e) {
    if (alertEl) alertEl.innerHTML = `<div class="alert alert-danger">${e.message}</div>`;
  }
}

function formatCEPEmp(el) {
  let v = el.value.replace(/\D/g,'');
  if (v.length > 5) v = v.slice(0,5) + '-' + v.slice(5,8);
  el.value = v;
}

async function buscarCEPEmp() {
  const cep = document.getElementById('emp-cep')?.value.replace(/\D/g,'');
  if (!cep || cep.length !== 8) { showAlert('CEP inválido','danger'); return; }
  try {
    const r = await fetch(`https://viacep.com.br/ws/${cep}/json/`);
    const d = await r.json();
    if (d.erro) { showAlert('CEP não encontrado','danger'); return; }
    const setV = (k,v) => { const el=document.getElementById('emp-'+k); if(el) el.value=v||''; };
    setV('logradouro',d.logradouro); setV('bairro',d.bairro); setV('cidade',d.localidade); setV('uf',d.uf);
    showAlert('CEP encontrado!');
  } catch(e) { showAlert('Erro ao buscar CEP','danger'); }
}

async function uploadLogo(input) {
  const file = input.files[0];
  if (!file) return;
  const form = new FormData();
  form.append('file', file);
  try {
    const r = await fetch(API.replace('/api','') + '/api/empresa/logo', { method:'POST', body:form });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail);
    const reader = new FileReader();
    reader.onload = e => {
      const prev = document.getElementById('empresa-logo-preview');
      if (prev) prev.innerHTML = `<img src="${e.target.result}" style="max-width:100%;max-height:100%;object-fit:contain">`;
    };
    reader.readAsDataURL(file);
    showAlert('Logo salvo!');
  } catch(e) { showAlert('Erro ao salvar logo: '+e.message,'danger'); }
}

async function salvarPermissoes() {
  const body = {};
  PERFIS.forEach(perf => {
    const chave = 'perm_' + perf.key;
    const paginas = TODAS_PAGINAS.filter(pg => {
      const el = document.getElementById(`perm_${perf.key}_${pg.key}`);
      return el && el.checked;
    }).map(pg => pg.key);
    body[chave] = paginas.join(',');
  });
  try {
    const r = await fetch(API + '/configuracoes/permissoes/salvar', {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)
    });
    const d = await r.json();
    if(!r.ok) throw new Error(d.detail||'Erro');
    const alertEl = document.getElementById('perm-alert');
    if(alertEl){alertEl.innerHTML='<div class="alert alert-success">✅ '+d.mensagem+'</div>';setTimeout(()=>alertEl.innerHTML='',4000);}
    permissoesAtuais = body;
  } catch(e){showAlert('Erro: '+e.message,'danger');}
}

// ─── INICIALIZAÇÃO ────────────────────────────────────────────────────────────

async function loadTopbarWidgets() {
  const dateEl = document.querySelector('#topbar-date span');
  if (dateEl) {
    const hoje = new Date();
    const dia = String(hoje.getDate()).padStart(2, '0');
    const mes = String(hoje.getMonth() + 1).padStart(2, '0');
    const ano = hoje.getFullYear();
    dateEl.textContent = `${dia}/${mes}/${ano}`;
  }

  let cidade = '';
  let uf = '';
  try {
    const r = await fetch(API + '/configuracoes/empresa', { cache: 'no-store' });
    if (r.ok) {
      const dados = await r.json();
      cidade = dados.cidade || '';
      uf = dados.uf || '';
    }
  } catch (e) {
    console.error('Erro ao buscar dados da empresa para topbar:', e);
  }

  const cityEl = document.querySelector('#topbar-city span');
  if (cityEl) {
    if (cidade) {
      cityEl.textContent = uf ? `${cidade} - ${uf.toUpperCase()}` : cidade;
    } else {
      cityEl.textContent = 'Sem cidade';
    }
  }

  const tempEl = document.querySelector('#topbar-temp span');
  if (tempEl && cidade) {
    try {
      const geoUrl = `https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(cidade)}&count=1&language=pt&format=json`;
      const geoRes = await fetch(geoUrl);
      if (geoRes.ok) {
        const geoData = await geoRes.json();
        if (geoData.results && geoData.results.length > 0) {
          const { latitude, longitude } = geoData.results[0];
          const weatherUrl = `https://api.open-meteo.com/v1/forecast?latitude=${latitude}&longitude=${longitude}&current_weather=true`;
          const weatherRes = await fetch(weatherUrl);
          if (weatherRes.ok) {
            const weatherData = await weatherRes.json();
            if (weatherData.current_weather && typeof weatherData.current_weather.temperature !== 'undefined') {
              const temp = Math.round(weatherData.current_weather.temperature);
              tempEl.textContent = `${temp}°C`;
              return;
            }
          }
        }
      }
    } catch (err) {
      console.error('Erro ao obter temperatura:', err);
    }
  }
  
  if (tempEl) {
    tempEl.textContent = '—°C';
  }

  const topbarMesEl = document.getElementById('topbar-mes');
  if (topbarMesEl && (topbarMesEl.textContent === '—' || !topbarMesEl.textContent)) {
    const mesAtual = new Date().toISOString().slice(0, 7);
    topbarMesEl.textContent = mesLabel(mesAtual);
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  await carregarAcessoPrincipal();
  loadTopbarWidgets();
  const params = new URLSearchParams(window.location.search);
  const paginaSolicitada = params.get('page') || params.get('pagina');
  const paginaInicial = (paginaSolicitada && paginasLiberadas.includes(paginaSolicitada)) ? paginaSolicitada : (paginasLiberadas[0] || 'dashboard');
  showPage(paginaInicial);
});

// ─── GRÁFICOS ─────────────────────────────────────────────────────────────────

const grafCharts = {};
function destroyGrafChart(id) { if(grafCharts[id]){grafCharts[id].destroy();delete grafCharts[id];} }

async function loadGraficoAnual() {
  const anoSel = document.getElementById('graf-ano');
  if(!anoSel) return;
  const ano = anoSel.value || new Date().getFullYear().toString();

  try {
    const dados = await api('/relatorios/resumo-anual/'+ano);
    const TC = ['#f0b429','#3b82f6','#10b981','#f43f5e'];
    const gc='#2a2f3f', tc='#6b7280';
    const ml = m => { const[,mo]=m.split('-');return['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'][+mo-1]; };

    // KPIs anuais
    const totalProd = dados.reduce((s,r)=>s+(r.total_producao||0),0);
    const totalPerda = dados.reduce((s,r)=>s+(r.total_perda||0),0);
    const totalSobra = dados.reduce((s,r)=>s+(r.total_sobra||0),0);
    const totalExc = dados.reduce((s,r)=>s+(r.total_excedente||0),0);
    const idxPerda = totalProd>0?((totalPerda/totalProd)*100).toFixed(1):'0.0';
    const kpiEl = document.getElementById('graf-kpi-anual');
    if(kpiEl) kpiEl.innerHTML = `
      <div style="background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:12px;text-align:center">
        <div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:4px">Total Produzido</div>
        <div style="font-family:var(--font-head);font-size:20px;font-weight:800;color:var(--accent)">${fmtNum(totalProd)}</div>
        <div style="font-size:11px;color:var(--muted)">peças em ${ano}</div>
      </div>
      <div style="background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:12px;text-align:center">
        <div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:4px">Total Perdas</div>
        <div style="font-family:var(--font-head);font-size:20px;font-weight:800;color:var(--danger)">${fmtNum(totalPerda)}</div>
        <div style="font-size:11px;color:var(--muted)">${idxPerda}% da produção</div>
      </div>
      <div style="background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:12px;text-align:center">
        <div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:4px">Total Sobras</div>
        <div style="font-family:var(--font-head);font-size:20px;font-weight:800;color:var(--success)">${fmtNum(totalSobra)}</div>
        <div style="font-size:11px;color:var(--muted)">retornaram ao estoque</div>
      </div>
      <div style="background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:12px;text-align:center">
        <div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:4px">Excedente Total</div>
        <div style="font-family:var(--font-head);font-size:20px;font-weight:800;color:${totalExc>=0?'var(--success)':'var(--danger)'}">${totalExc>=0?'+':''}${fmtNum(Math.round(totalExc))}</div>
        <div style="font-size:11px;color:var(--muted)">vs meta acumulada</div>
      </div>
    `;

    // Gráfico anual com 3 datasets: produção, perda, sobra
    destroyGrafChart('anual');
    grafCharts['anual'] = new Chart(document.getElementById('chart-anual'), {
      type: 'bar',
      data: {
        labels: dados.map(r=>ml(r.mes_referencia)),
        datasets: [
          {
            label: 'Produção', data: dados.map(r=>r.total_producao||0),
            backgroundColor: '#f0b429cc', borderColor: '#f0b429', borderWidth: 1, borderRadius: 4,
            yAxisID: 'y'
          },
          {
            label: 'Perda', data: dados.map(r=>r.total_perda||0),
            backgroundColor: '#ef4444cc', borderColor: '#ef4444', borderWidth: 1, borderRadius: 4,
            yAxisID: 'y'
          },
          {
            label: 'Sobra', data: dados.map(r=>r.total_sobra||0),
            backgroundColor: '#10b981cc', borderColor: '#10b981', borderWidth: 1, borderRadius: 4,
            yAxisID: 'y'
          },
          {
            label: 'Média/dia', data: dados.map(r=>Math.round(r.media_diaria||0)),
            type: 'line', borderColor: '#3b82f6', backgroundColor: 'transparent',
            borderWidth: 2, pointRadius: 5, pointBackgroundColor: '#3b82f6',
            tension: 0.4, yAxisID: 'y2'
          }
        ]
      },
      options: {
        responsive: true,
        plugins: { legend: { labels: { color: tc } },
          tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${fmtNum(ctx.raw)}` } }
        },
        scales: {
          x: { ticks: { color: tc }, grid: { color: gc } },
          y: { ticks: { color: tc, callback: v=>fmtNum(v) }, grid: { color: gc }, title: { display: true, text: 'Peças', color: tc } },
          y2: { position: 'right', ticks: { color: '#3b82f6', callback: v=>fmtNum(v) }, grid: { display: false }, title: { display: true, text: 'Média/dia', color: '#3b82f6' } }
        }
      }
    });
  } catch(e) { console.error('Erro gráfico anual:', e); }
}

async function loadGraficos() {
  const mes = new Date().toISOString().slice(0,7);
  const iniEl = document.getElementById('graf-mes-ini');
  const fimEl = document.getElementById('graf-mes-fim');
  const anoAtual = new Date().getFullYear();
  if(iniEl && !iniEl.value) iniEl.value=`${anoAtual}-01`;
  if(fimEl && !fimEl.value) fimEl.value = mes;
  const mesIni = iniEl?.value || `${anoAtual}-01`;
  const mesFim = fimEl?.value || mes;
  const mesAtual = mesFim;
  const periodoQS = `?mes_ini=${encodeURIComponent(mesIni)}&mes_fim=${encodeURIComponent(mesFim)}`;

  // Popular seletor de ano
  const anoSel = document.getElementById('graf-ano');
  if(anoSel && anoSel.options.length===0) {
    for(let y=anoAtual; y>=anoAtual-3; y--) {
      const o=document.createElement('option');
      o.value=y; o.textContent=y;
      if(y===anoAtual) o.selected=true;
      anoSel.appendChild(o);
    }
  }
  // Carregar gráfico anual
  loadGraficoAnual();

  const TC = ['#f0b429','#3b82f6','#10b981','#f43f5e','#a855f7'];
  const gc = '#2a2f3f', tc = '#6b7280';
  const ml = m => { const[y,mo]=m.split('-');return['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'][+mo-1]+'/'+y.slice(2); };

  try {
    const [resumoPeriodo, evolucao, ranking, diario] = await Promise.all([
      api('/relatorios/resumo-periodo'+periodoQS),
      api('/relatorios/evolucao-mensal'+periodoQS),
      api('/relatorios/ranking-historico'+periodoQS),
      api('/relatorios/producao-diaria/'+mesAtual)
    ]);

    const meses = [...new Set(evolucao.map(r=>r.mes_referencia))].sort();
    const ops = [...new Set(evolucao.map(r=>r.colaborador))];

    // ── KPI Cards
    const totalPeriodo = resumoPeriodo.total_producao || evolucao.reduce((s,r)=>s+(r.total_producao||0),0);
    const diasPeriodo = resumoPeriodo.dias_registrados || 0;
    const lancamentosPeriodo = resumoPeriodo.total_lancamentos || evolucao.reduce((s,r)=>s+(r.dias_trabalhados||0),0);
    const mediaGeral = Math.round(resumoPeriodo.media_diaria_geral || (diasPeriodo ? totalPeriodo / diasPeriodo : 0));
    const melhorOp = resumoPeriodo.melhor_operador?.colaborador || ranking[0]?.colaborador || '—';
    const melhorMedia = resumoPeriodo.melhor_operador?.media_diaria || ranking[0]?.media_geral || 0;
    const totalPerda = resumoPeriodo.total_perdas || evolucao.reduce((s,r)=>s+(r.total_perdas||0),0);
    const totalSobra = resumoPeriodo.total_sobras || evolucao.reduce((s,r)=>s+(r.total_sobras||0),0);
    const saldoExcedente = resumoPeriodo.saldo_excedente || evolucao.reduce((s,r)=>s+((r.excedente_total ?? ((r.excedente_positivo||0)+(r.excedente_negativo||0)))||0),0);
    const idxPerda = totalPeriodo > 0 ? ((totalPerda/totalPeriodo)*100).toFixed(1) : '0.0';
    const cardsEl = document.getElementById('graf-kpi-cards');
    if(cardsEl) cardsEl.innerHTML = `
      <div class="card" style="border-left:3px solid var(--accent)"><div class="card-label">Total Produzido</div><div class="card-value accent">${fmtNum(totalPeriodo)}</div><div style="font-size:11px;color:var(--muted)">${mesLabel(mesIni)} até ${mesLabel(mesFim)}</div></div>
      <div class="card" style="border-left:3px solid var(--accent2)"><div class="card-label">Média Diária Geral</div><div class="card-value info">${fmtNum(mediaGeral)}</div><div style="font-size:11px;color:var(--muted)">${fmtNum(diasPeriodo)} dias registrados | ${fmtNum(lancamentosPeriodo)} lançamentos</div></div>
      <div class="card" style="border-left:3px solid var(--success)"><div class="card-label">Melhor Operador</div><div class="card-value success" style="font-size:18px">${melhorOp}</div><div style="font-size:11px;color:var(--muted)">${fmtNum(Math.round(melhorMedia||0))} pçs/dia</div></div>
      <div class="card" style="border-left:3px solid var(--danger)"><div class="card-label">Índice de Perda</div><div class="card-value danger">${idxPerda}%</div><div style="font-size:11px;color:var(--muted)">${fmtNum(totalPerda)} perdas | ${fmtNum(totalSobra)} sobras</div></div>
      <div class="card" style="border-left:3px solid ${saldoExcedente>=0?'var(--success)':'var(--danger)'}"><div class="card-label">Saldo vs Meta</div><div class="card-value ${saldoExcedente>=0?'success':'danger'}">${saldoExcedente>=0?'+':''}${fmtNum(Math.round(saldoExcedente))}</div><div style="font-size:11px;color:var(--muted)">excedente acumulado</div></div>
    `;

    // 1. Total por mês (barras empilhadas)
    destroyGrafChart('total-mes');
    grafCharts['total-mes'] = new Chart(document.getElementById('chart-total-mes'), {
      type:'bar',
      data:{ labels:meses.map(ml), datasets:ops.map((op,i)=>({
        label:op, data:meses.map(m=>{const r=evolucao.find(r=>r.colaborador===op&&r.mes_referencia===m);return r?r.total_producao:0;}),
        backgroundColor:TC[i%TC.length]+'bb', borderColor:TC[i%TC.length], borderWidth:1, borderRadius:4
      }))},
      options:{responsive:true,plugins:{legend:{labels:{color:tc}},tooltip:{callbacks:{label:ctx=>`${ctx.dataset.label}: ${fmtNum(ctx.raw)} pçs`}}},
        scales:{x:{stacked:true,ticks:{color:tc},grid:{color:gc}},y:{stacked:true,ticks:{color:tc,callback:v=>fmtNum(v)},grid:{color:gc}}}}
    });

    // 2. Evolução média diária (linha)
    destroyGrafChart('evolucao-graf');
    grafCharts['evolucao-graf'] = new Chart(document.getElementById('chart-evolucao-graf'), {
      type:'line',
      data:{ labels:meses.map(ml), datasets:ops.map((op,i)=>({
        label:op, borderColor:TC[i%TC.length], backgroundColor:TC[i%TC.length]+'22',
        data:meses.map(m=>{const r=evolucao.find(r=>r.colaborador===op&&r.mes_referencia===m);return r?Math.round(r.media_diaria||0):null;}),
        tension:0.4, fill:true, pointRadius:5, pointHoverRadius:8, spanGaps:true
      }))},
      options:{responsive:true,plugins:{legend:{labels:{color:tc}}},
        scales:{x:{ticks:{color:tc},grid:{color:gc}},y:{ticks:{color:tc,callback:v=>fmtNum(v)},grid:{color:gc}}}}
    });

    // 3. Comparativo média × meta (barras agrupadas)
    destroyGrafChart('comparativo');
    grafCharts['comparativo'] = new Chart(document.getElementById('chart-comparativo'), {
      type:'bar',
      data:{
        labels:ops,
        datasets:[
          {label:'Média Geral', data:ops.map(op=>{const r=ranking.find(r=>r.colaborador===op);return Math.round(r?.media_geral||0);}), backgroundColor:ops.map((_,i)=>TC[i%TC.length]+'cc'), borderColor:ops.map((_,i)=>TC[i%TC.length]), borderWidth:1, borderRadius:6},
          {label:'Meta média', data:ops.map(op=>{const r=ranking.find(r=>r.colaborador===op);return Math.round(r?.media_meta||0);}), type:'line', borderColor:'#ef4444', borderDash:[6,3], borderWidth:2, pointRadius:3, fill:false}
        ]
      },
      options:{responsive:true,plugins:{legend:{labels:{color:tc}}},
        scales:{x:{ticks:{color:tc},grid:{color:gc}},y:{ticks:{color:tc,callback:v=>fmtNum(v)},grid:{color:gc}}}}
    });

    // 4. Índice de perda por mês (linha)
    destroyGrafChart('perda-idx');
    grafCharts['perda-idx'] = new Chart(document.getElementById('chart-perda-idx'), {
      type:'line',
      data:{ labels:meses.map(ml), datasets:ops.map((op,i)=>{
        const dados = meses.map(m=>{
          const r=evolucao.find(r=>r.colaborador===op&&r.mes_referencia===m);
          if(!r||!r.total_producao) return 0;
          return +((r.total_perdas||0)/r.total_producao*100).toFixed(2);
        });
        return {label:op, borderColor:TC[i%TC.length], backgroundColor:'transparent', data:dados, tension:0.3, pointRadius:4, spanGaps:true};
      })},
      options:{responsive:true,plugins:{legend:{labels:{color:tc}}},
        scales:{x:{ticks:{color:tc},grid:{color:gc}},y:{ticks:{color:tc,callback:v=>v+'%'},grid:{color:gc},title:{display:true,text:'% perda',color:tc}}}}
    });

    // 5. Dias abaixo da meta (barras agrupadas)
    destroyGrafChart('dias-meta');
    grafCharts['dias-meta'] = new Chart(document.getElementById('chart-dias-meta'), {
      type:'bar',
      data:{ labels:meses.map(ml), datasets:ops.map((op,i)=>({
        label:op,
        data:meses.map(m=>{const r=evolucao.find(r=>r.colaborador===op&&r.mes_referencia===m);
          if(!r) return 0;
          return r.dias_abaixo_meta || Math.max(0,(r.dias_trabalhados||0)-(r.dias_acima_meta||0));
        }),
        backgroundColor:TC[i%TC.length]+'99', borderColor:TC[i%TC.length], borderWidth:1, borderRadius:4
      }))},
      options:{responsive:true,plugins:{legend:{labels:{color:tc}}},
        scales:{x:{ticks:{color:tc},grid:{color:gc}},y:{ticks:{color:tc},grid:{color:gc},title:{display:true,text:'dias',color:tc}}}}
    });

    // 6. Excedente acumulado (barras + linha zero)
    destroyGrafChart('excedente');
    grafCharts['excedente'] = new Chart(document.getElementById('chart-excedente'), {
      type:'bar',
      data:{ labels:meses.map(ml), datasets:ops.map((op,i)=>({
        label:op,
        data:meses.map(m=>{const r=evolucao.find(r=>r.colaborador===op&&r.mes_referencia===m);return Math.round((r?.excedente_total ?? ((r?.excedente_positivo||0)+(r?.excedente_negativo||0))) || 0);}),
        backgroundColor:meses.map(m=>{const r=evolucao.find(r=>r.colaborador===op&&r.mes_referencia===m);return (((r?.excedente_total ?? ((r?.excedente_positivo||0)+(r?.excedente_negativo||0))) || 0)>=0)?TC[i%TC.length]+'99':'#ef444499';}),
        borderColor:meses.map(m=>{const r=evolucao.find(r=>r.colaborador===op&&r.mes_referencia===m);return (((r?.excedente_total ?? ((r?.excedente_positivo||0)+(r?.excedente_negativo||0))) || 0)>=0)?TC[i%TC.length]:'#ef4444';}),
        borderWidth:1, borderRadius:3
      }))},
      options:{responsive:true,plugins:{legend:{labels:{color:tc}}},
        scales:{x:{ticks:{color:tc},grid:{color:gc}},y:{ticks:{color:tc,callback:v=>fmtNum(v)},grid:{color:gc}}}}
    });

    // 7. Produção diária do mês
    const dias=[...new Set(diario.map(r=>r.data))].sort();
    const opsD=[...new Set(diario.map(r=>r.colaborador))];
    const metaDia=diario[0]?.meta||8000;
    destroyGrafChart('diario-graf');
    const dsets=opsD.map((op,i)=>({label:op, data:dias.map(d=>{const r=diario.find(r=>r.colaborador===op&&r.data===d);return r?r.producao:0;}), backgroundColor:TC[i%TC.length]+'cc', borderColor:TC[i%TC.length], borderWidth:1, borderRadius:3}));
    dsets.push({label:`Meta (${fmtNum(metaDia)})`,data:dias.map(()=>metaDia),type:'line',borderColor:'#ef4444',borderDash:[6,3],borderWidth:2,pointRadius:0,fill:false});
    grafCharts['diario-graf'] = new Chart(document.getElementById('chart-diario-graf'), {
      type:'bar', data:{labels:dias.map(fmtDate),datasets:dsets},
      options:{responsive:true,plugins:{legend:{labels:{color:tc}}},
        scales:{x:{ticks:{color:tc,maxRotation:45},grid:{color:gc}},y:{ticks:{color:tc,callback:v=>fmtNum(v)},grid:{color:gc}}}}
    });

    // 8. Ranking histórico horizontal
    destroyGrafChart('ranking-graf');
    grafCharts['ranking-graf'] = new Chart(document.getElementById('chart-ranking-graf'), {
      type:'bar',
      data:{labels:ranking.map(r=>r.colaborador), datasets:[{
        label:'Média (pçs/dia)',
        data:ranking.map(r=>Math.round(r.media_geral||0)),
        backgroundColor:ranking.map((_,i)=>TC[i%TC.length]+'cc'), borderColor:ranking.map((_,i)=>TC[i%TC.length]), borderWidth:1, borderRadius:6
      }]},
      options:{indexAxis:'y',responsive:true,plugins:{legend:{display:false}},
        scales:{x:{ticks:{color:tc,callback:v=>fmtNum(v)},grid:{color:gc}},y:{ticks:{color:tc},grid:{color:gc}}}}
    });

    // 9. Pedidos por status (rosca)
    try {
      const pedidos=await api('/pedidos/');
      const sc={aberto:0,em_producao:0,produzido:0,entregue:0};
      pedidos.forEach(p=>{if(sc[p.status]!==undefined)sc[p.status]++;});
      destroyGrafChart('pedidos-status');
      grafCharts['pedidos-status'] = new Chart(document.getElementById('chart-pedidos-status'), {
        type:'doughnut',
        data:{labels:['Aberto','Em produção','Produzido','Entregue'], datasets:[{data:Object.values(sc), backgroundColor:['#3b82f6cc','#f0b429cc','#10b981cc','#6b7280cc'], borderWidth:0}]},
        options:{responsive:true,plugins:{legend:{labels:{color:tc},position:'bottom'}}}
      });

      // 10. Prazo: no prazo vs atrasados
      const noPrazo=pedidos.filter(p=>p.status!=='entregue'&&Math.round(p.dias_restantes)>=0).length;
      const atrasados=pedidos.filter(p=>p.status!=='entregue'&&Math.round(p.dias_restantes)<0).length;
      const entregues=pedidos.filter(p=>p.status==='entregue').length;
      destroyGrafChart('prazo');
      grafCharts['prazo'] = new Chart(document.getElementById('chart-prazo'), {
        type:'doughnut',
        data:{labels:['No prazo','Atrasados','Entregues'], datasets:[{data:[noPrazo,atrasados,entregues], backgroundColor:['#10b981cc','#ef4444cc','#6b7280cc'], borderWidth:0}]},
        options:{responsive:true,plugins:{legend:{labels:{color:tc},position:'bottom'}}}
      });
    } catch(e){}

    // 11. Estoque por categoria
    try {
      const prods=await api('/estoque/produtos');
      const cm={};
      prods.forEach(p=>{const c=p.categoria_nome||'Sem categoria';if(!cm[c])cm[c]=0;cm[c]+=p.quantidade_atual||0;});
      destroyGrafChart('estoque-cat');
      grafCharts['estoque-cat'] = new Chart(document.getElementById('chart-estoque-cat'), {
        type:'bar',
        data:{labels:Object.keys(cm), datasets:[{label:'Saldo', data:Object.values(cm), backgroundColor:'#3b82f6cc', borderColor:'#3b82f6', borderWidth:1, borderRadius:4}]},
        options:{responsive:true,plugins:{legend:{display:false}},
          scales:{x:{ticks:{color:tc},grid:{color:gc}},y:{ticks:{color:tc,callback:v=>fmtNum(v)},grid:{color:gc}}}}
      });
    } catch(e){}

  } catch(e) { showAlert('Erro ao carregar gráficos: '+e.message,'danger'); }
}

function exportarGraficoPDF() {
  const win=window.open('','_blank');
  const canvases=document.getElementById('graf-content')?.querySelectorAll('canvas')||[];
  let imgs='';
  canvases.forEach(c=>{try{imgs+=`<img src="${c.toDataURL()}" style="width:48%;margin:1%">`;}catch(e){}});
  win.document.write(`<html><head><title>Análise PRATIC</title><style>body{font-family:Arial;margin:20px}h2{font-size:16px;color:#333}img{display:inline-block;vertical-align:top}</style></head><body><h2>PRATIC — Análise Gráfica — ${new Date().toLocaleDateString('pt-BR')}</h2>${imgs}</body></html>`);
  win.document.close();
  setTimeout(()=>win.print(),800);
}

// ─── CORREÇÃO ESTOQUE — abas, tabelas e modais compatíveis com index.html ───
let estoqueTabAtual = 'produtos';

function _setVal(id, val) { const el = document.getElementById(id); if (el) el.value = val ?? ''; }
function _getVal(id) { return document.getElementById(id)?.value || ''; }
function _numVal(id) { return +(_getVal(id)) || 0; }
function _produtoLabel(p) {
  const codigo = p.codigo ? '[' + p.codigo + '] ' : '';
  const marca = p.marca ? ' — ' + p.marca : '';
  return codigo + (p.nome || '') + marca;
}


function _prefixoCategoriaProduto(nomeCategoria) {
  const base = (nomeCategoria || 'GERAL')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^A-Za-z0-9]/g, '')
    .toUpperCase();
  return (base.substring(0, 3) || 'GER').padEnd(3, 'X');
}

async function gerarCodigoProdutoAutomatico(categoriaId, excluirId = '') {
  const cats = await api('/estoque/categorias').catch(() => []);
  const categoria = cats.find(c => String(c.id) === String(categoriaId));
  const prefixo = _prefixoCategoriaProduto(categoria?.nome);
  const produtos = await api('/estoque/produtos').catch(() => []);
  const padrao = new RegExp('^' + prefixo.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '[^0-9]*(\\d+)', 'i');
  let maior = 0;

  produtos.forEach(p => {
    if (String(p.id) === String(excluirId || '')) return;
    const codigoAtual = String(p.codigo || '').trim().toUpperCase();
    const m = codigoAtual.match(padrao);
    if (m) maior = Math.max(maior, parseInt(m[1], 10) || 0);
  });

  let proximo = maior + 1;
  let codigo = '';
  do {
    codigo = prefixo + '-' + String(proximo).padStart(3, '0');
    proximo++;
  } while (produtos.some(p => String(p.id) !== String(excluirId || '') && String(p.codigo || '').trim().toLowerCase() === codigo.toLowerCase()));

  return codigo;
}

function switchEstoqueTab(tab) {
  estoqueTabAtual = tab || 'produtos';
  ['produtos', 'movimentacoes', 'perdas', 'categorias'].forEach(t => {
    const pane = document.getElementById('est-tab-' + t);
    const btn = document.getElementById('tab-' + t);
    if (pane) pane.style.display = (t === estoqueTabAtual) ? '' : 'none';
    if (btn) {
      btn.style.borderColor = (t === estoqueTabAtual) ? 'var(--accent)' : 'var(--border)';
      btn.style.color = (t === estoqueTabAtual) ? 'var(--accent)' : 'var(--text)';
    }
  });
  if (estoqueTabAtual === 'produtos') loadProdutos();
  if (estoqueTabAtual === 'movimentacoes') loadMovimentacoes();
  if (estoqueTabAtual === 'perdas') loadPerdas();
  if (estoqueTabAtual === 'categorias') loadCategoriasEstoque();
}

async function loadEstoque() {
  await loadCategoriasFiltro();
  await loadProdutos();
  await loadAlertasEstoque();
  switchEstoqueTab(estoqueTabAtual || 'produtos');
}

async function loadCategoriasFiltro() {
  try {
    const cats = await api('/estoque/categorias');
    const filtro = document.getElementById('est-filtro-cat');
    const produtoSel = document.getElementById('est-prod-cat');
    const filtroVal = filtro?.value || '';
    if (filtro) {
      filtro.innerHTML = '<option value="">Todas as categorias</option>' +
        cats.map(c => `<option value="${c.id}" ${String(c.id)===String(filtroVal)?'selected':''}>${c.nome}</option>`).join('');
    }
    if (produtoSel) {
      const prodVal = produtoSel.value || '';
      produtoSel.innerHTML = '<option value="">— Sem categoria —</option>' +
        cats.map(c => `<option value="${c.id}" ${String(c.id)===String(prodVal)?'selected':''}>${c.nome}</option>`).join('');
    }
    return cats;
  } catch(e) { return []; }
}

async function loadProdutos() {
  const catId = _getVal('est-filtro-cat');
  let url = '/estoque/produtos';
  if (catId) url += '?categoria_id=' + encodeURIComponent(catId);
  const prods = await api(url);
  const tbody = document.getElementById('est-produtos-tbody');
  if (!tbody) return;
  if (!prods.length) {
    tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--muted);padding:28px">Nenhum produto cadastrado</td></tr>';
    return;
  }
  tbody.innerHTML = prods.map(p => `
    <tr>
      <td><strong>${p.codigo || '—'}</strong></td>
      <td><strong>${p.nome || ''}</strong></td>
      <td>${p.categoria_nome || '—'}</td>
      <td>${p.marca || '—'}</td>
      <td>${p.unidade || 'unidade'}</td>
      <td style="font-weight:700;color:${p.alerta?'var(--danger)':'var(--text)'}">${fmtNum(p.quantidade_atual || 0)}</td>
      <td>${fmtNum(p.estoque_minimo || 0)}</td>
      <td><span class="pill ${p.alerta?'pill-danger':'pill-success'}">${p.alerta?'⚠ Abaixo':'✓ OK'}</span></td>
      <td class="flex gap-2">
        <button class="btn btn-sm btn-secondary" onclick="openModalMovimentacao(${p.id})">📦 Mov.</button>
        <button class="btn btn-sm btn-secondary" onclick="editProduto(${p.id})">✏️</button>
        <button class="btn btn-sm btn-danger" onclick="deletarProduto(${p.id})">✕</button>
      </td>
    </tr>`).join('');
}

async function openModalProduto() {
  await loadCategoriasFiltro();
  _setVal('est-prod-id', '');
  _setVal('est-prod-codigo', '');
  _setVal('est-prod-nome', '');
  _setVal('est-prod-cat', '');
  _setVal('est-prod-marca', '');
  _setVal('est-prod-unidade', 'unidade');
  _setVal('est-prod-minimo', '0');
  const ti = document.getElementById('modal-prod-est-title'); if (ti) ti.textContent = 'Cadastrar Produto';
  openModal('modal-produto');
}

async function editProduto(id) {
  const p = await api('/estoque/produtos/' + id);
  await loadCategoriasFiltro();
  _setVal('est-prod-id', p.id);
  _setVal('est-prod-codigo', p.codigo || '');
  _setVal('est-prod-nome', p.nome);
  _setVal('est-prod-cat', p.categoria_id || '');
  _setVal('est-prod-marca', p.marca || '');
  _setVal('est-prod-unidade', p.unidade || 'unidade');
  _setVal('est-prod-minimo', p.estoque_minimo || 0);
  const ti = document.getElementById('modal-prod-est-title'); if (ti) ti.textContent = 'Editar Produto';
  openModal('modal-produto');
}

async function salvarProduto() {
  const id = _getVal('est-prod-id');
  const categoriaId = _getVal('est-prod-cat') ? +_getVal('est-prod-cat') : null;
  const body = {
    codigo: _getVal('est-prod-codigo').trim(),
    categoria_id: categoriaId,
    nome: _getVal('est-prod-nome').trim(),
    marca: _getVal('est-prod-marca').trim(),
    unidade: _getVal('est-prod-unidade') || 'unidade',
    estoque_minimo: _numVal('est-prod-minimo')
  };
  if (!body.nome) { showAlert('Informe o nome do produto', 'danger'); return; }
  try {
    if (!body.codigo) {
      body.codigo = await gerarCodigoProdutoAutomatico(categoriaId, id);
      _setVal('est-prod-codigo', body.codigo);
    }
    if (id) await api('/estoque/produtos/' + id, 'PUT', body);
    else await api('/estoque/produtos', 'POST', body);
    closeModal('modal-produto');
    showAlert('Produto salvo!');
    await loadCategoriasFiltro();
    await loadProdutos();
    await loadAlertasEstoque();
  } catch(e) { showAlert(e.message, 'danger'); }
}

async function salvarProdutoEstoque() { return salvarProduto(); }

async function deletarProduto(id) {
  if (!confirm('Desativar este produto?')) return;
  try {
    await api('/estoque/produtos/' + id, 'DELETE');
    showAlert('Produto removido da lista ativa.');
    await loadProdutos();
    await loadAlertasEstoque();
  } catch(e) { showAlert(e.message, 'danger'); }
}

async function _popularProdutosSelect(selectId, selectedId) {
  const prods = await api('/estoque/produtos');
  const sel = document.getElementById(selectId);
  if (!sel) return prods;
  sel.innerHTML = prods.map(p => `<option value="${p.id}" ${String(p.id)===String(selectedId||'')?'selected':''}>${_produtoLabel(p)} (${fmtNum(p.quantidade_atual || 0)} ${p.unidade || 'unidade'})</option>`).join('');
  return prods;
}

async function openModalMovimentacao(prodId) {
  await _popularProdutosSelect('est-mov-produto', prodId);
  _setVal('est-mov-tipo', 'entrada');
  _setVal('est-mov-data', new Date().toISOString().slice(0,10));
  _setVal('est-mov-quantidade', '');
  _setVal('est-mov-responsavel', '');
  _setVal('est-mov-fornecedor', '');
  _setVal('est-mov-custo', '');
  _setVal('est-mov-motivo', '');
  toggleMovTipo();
  openModal('modal-movimentacao');
}

function toggleMovTipo() {
  const tipo = _getVal('est-mov-tipo');
  const fornecedor = document.getElementById('est-mov-fornecedor-group');
  const custo = document.getElementById('est-mov-custo-group');
  const show = tipo === 'entrada';
  if (fornecedor) fornecedor.style.display = show ? '' : 'none';
  if (custo) custo.style.display = show ? '' : 'none';
}

async function salvarMovimentacao() {
  const body = {
    produto_id: +_getVal('est-mov-produto'),
    tipo: _getVal('est-mov-tipo') || 'entrada',
    quantidade: _numVal('est-mov-quantidade'),
    responsavel: _getVal('est-mov-responsavel').trim(),
    fornecedor: _getVal('est-mov-fornecedor').trim(),
    custo_unitario: _numVal('est-mov-custo'),
    observacao: _getVal('est-mov-motivo').trim(),
    motivo: _getVal('est-mov-motivo').trim(),
    data: _getVal('est-mov-data') || new Date().toISOString().slice(0,10)
  };
  if (!body.produto_id) { showAlert('Selecione o produto', 'danger'); return; }
  if (!body.quantidade || body.quantidade <= 0) { showAlert('Informe a quantidade', 'danger'); return; }
  try {
    await api('/estoque/movimentacoes', 'POST', body);
    closeModal('modal-movimentacao');
    showAlert('Movimentação registrada!');
    await loadProdutos();
    await loadMovimentacoes();
    await loadAlertasEstoque();
  } catch(e) { showAlert(e.message, 'danger'); }
}

async function loadMovimentacoes() {
  const tipo = _getVal('est-filtro-tipo');
  let url = '/estoque/movimentacoes';
  if (tipo) url += '?tipo=' + encodeURIComponent(tipo);
  const movs = await api(url);
  const tbody = document.getElementById('est-movs-tbody');
  if (!tbody) return;
  if (!movs.length) {
    tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--muted);padding:28px">Nenhuma movimentação registrada</td></tr>';
    return;
  }
  const labels = {entrada:'Entrada', saida:'Saída', perda:'Perda', ajuste:'Ajuste', sobra:'Sobra'};
  tbody.innerHTML = movs.map(m => `
    <tr>
      <td>${fmtDate(m.data)}</td>
      <td>${m.produto_codigo || '—'}</td>
      <td>${m.produto_nome || '—'}</td>
      <td><span class="pill">${labels[m.tipo] || m.tipo}</span></td>
      <td>${fmtNum(m.quantidade || 0)} ${m.unidade || ''}</td>
      <td>${fmtNum(m.saldo_anterior || 0)}</td>
      <td>${fmtNum(m.saldo_posterior || 0)}</td>
      <td>${m.responsavel || '—'}</td>
      <td><button class="btn btn-sm btn-danger" onclick="deletarMovimentacao(${m.id})">✕</button></td>
    </tr>`).join('');
}

async function deletarMovimentacao(id) {
  if (!confirm('Remover esta movimentação? O saldo atual não será recalculado automaticamente.')) return;
  try {
    await api('/estoque/movimentacoes/' + id, 'DELETE');
    showAlert('Movimentação removida.');
    await loadMovimentacoes();
  } catch(e) { showAlert(e.message, 'danger'); }
}

async function openModalPerda() {
  await _popularProdutosSelect('est-perda-produto');
  _setVal('est-perda-tipo', 'quebra');
  _setVal('est-perda-data', new Date().toISOString().slice(0,10));
  _setVal('est-perda-quantidade', '');
  _setVal('est-perda-responsavel', '');
  _setVal('est-perda-obs', '');
  openModal('modal-perda');
}

async function salvarPerda() {
  const body = {
    produto_id: +_getVal('est-perda-produto'),
    tipo: 'perda',
    tipo_perda: _getVal('est-perda-tipo'),
    quantidade: _numVal('est-perda-quantidade'),
    responsavel: _getVal('est-perda-responsavel').trim(),
    observacao: _getVal('est-perda-obs').trim(),
    data: _getVal('est-perda-data') || new Date().toISOString().slice(0,10)
  };
  if (!body.produto_id) { showAlert('Selecione o produto', 'danger'); return; }
  if (!body.quantidade || body.quantidade <= 0) { showAlert('Informe a quantidade', 'danger'); return; }
  try {
    await api('/estoque/movimentacoes', 'POST', body);
    closeModal('modal-perda');
    showAlert('Perda registrada!');
    await loadPerdas();
    await loadProdutos();
    await loadAlertasEstoque();
  } catch(e) { showAlert(e.message, 'danger'); }
}

async function loadPerdas() {
  const mes = _getVal('est-perdas-mes');
  let url = '/estoque/relatorio-perdas';
  if (mes) url += '?mes=' + encodeURIComponent(mes);
  const perdas = await api(url);
  const tbody = document.getElementById('est-perdas-tbody');
  if (!tbody) return;
  if (!perdas.length) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--muted);padding:28px">Nenhuma perda registrada</td></tr>';
    return;
  }
  tbody.innerHTML = perdas.map(p => `
    <tr>
      <td>${fmtDate(p.data)}</td>
      <td>${p.produto_codigo || '—'}</td>
      <td>${p.produto || '—'} ${p.unidade ? '('+p.unidade+')' : ''}</td>
      <td>${p.categoria || '—'}</td>
      <td>${p.tipo_perda || '—'}</td>
      <td>${fmtNum(p.quantidade || 0)}</td>
      <td>${p.responsavel || '—'}</td>
      <td>${p.observacao || '—'}</td>
    </tr>`).join('');
}

async function loadCategoriasEstoque() {
  const cats = await api('/estoque/categorias');
  const tbody = document.getElementById('est-cat-tbody');
  if (!tbody) return;
  if (!cats.length) {
    tbody.innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--muted);padding:28px">Nenhuma categoria cadastrada</td></tr>';
    return;
  }
  tbody.innerHTML = cats.map(c => `
    <tr>
      <td><strong>${c.nome || ''}</strong></td>
      <td>${c.descricao || '—'}</td>
      <td class="flex gap-2">
        <button class="btn btn-sm btn-secondary" onclick="editCategoria(${c.id})">✏️</button>
        <button class="btn btn-sm btn-danger" onclick="deletarCategoria(${c.id})">✕</button>
      </td>
    </tr>`).join('');
}

async function openModalCategoria() {
  _setVal('est-cat-id', '');
  _setVal('est-cat-nome', '');
  _setVal('est-cat-desc', '');
  const ti = document.getElementById('modal-cat-title'); if (ti) ti.textContent = 'Nova Categoria';
  openModal('modal-categoria');
}

async function editCategoria(id) {
  const cats = await api('/estoque/categorias');
  const c = cats.find(x => Number(x.id) === Number(id));
  if (!c) return;
  _setVal('est-cat-id', c.id);
  _setVal('est-cat-nome', c.nome || '');
  _setVal('est-cat-desc', c.descricao || '');
  const ti = document.getElementById('modal-cat-title'); if (ti) ti.textContent = 'Editar Categoria';
  openModal('modal-categoria');
}

async function salvarCategoria() {
  const id = _getVal('est-cat-id');
  const body = { nome: _getVal('est-cat-nome').trim(), descricao: _getVal('est-cat-desc').trim() };
  if (!body.nome) { showAlert('Informe o nome da categoria', 'danger'); return; }
  try {
    if (id) await api('/estoque/categorias/' + id, 'PUT', body);
    else await api('/estoque/categorias', 'POST', body);
    closeModal('modal-categoria');
    showAlert('Categoria salva!');
    await loadCategoriasFiltro();
    await loadCategoriasEstoque();
  } catch(e) { showAlert(e.message, 'danger'); }
}

async function deletarCategoria(id) {
  if (!confirm('Remover esta categoria? Produtos sem categoria continuarão cadastrados.')) return;
  try {
    await api('/estoque/categorias/' + id, 'DELETE');
    showAlert('Categoria removida.');
    await loadCategoriasFiltro();
    await loadCategoriasEstoque();
    await loadProdutos();
  } catch(e) { showAlert(e.message, 'danger'); }
}

// ─── CORREÇÃO GERAL DE BOTÕES — backup, restauração, CSV e máscaras ───
// Estas funções estavam sendo chamadas pelo index.html, mas não existiam no app.js.

function _showLocalAlert(id, msg, type = 'success') {
  const el = document.getElementById(id);
  const cls = type === 'danger' ? 'alert-danger' : 'alert-success';
  if (el) el.innerHTML = `<div class="alert ${cls}">${msg}</div>`;
  else showAlert(msg, type);
}

function formatCEP(el) {
  if (!el) return;
  let v = String(el.value || '').replace(/\D/g, '').slice(0, 8);
  if (v.length > 5) v = v.slice(0, 5) + '-' + v.slice(5);
  el.value = v;
}

function formatDocCli(el) {
  if (!el) return;
  let v = String(el.value || '').replace(/\D/g, '').slice(0, 14);
  const tipo = document.getElementById('doc-tipo-cli');
  if (v.length <= 11) {
    if (v.length > 9) v = v.replace(/(\d{3})(\d{3})(\d{3})(\d{0,2})/, '$1.$2.$3-$4');
    else if (v.length > 6) v = v.replace(/(\d{3})(\d{3})(\d{0,3})/, '$1.$2.$3');
    else if (v.length > 3) v = v.replace(/(\d{3})(\d{0,3})/, '$1.$2');
    if (tipo) tipo.textContent = 'CPF';
  } else {
    v = v.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{0,2})/, '$1.$2.$3/$4-$5');
    if (tipo) tipo.textContent = 'CNPJ';
  }
  el.value = v;
}

async function buscarCEPEmpresa() {
  return buscarCEPEmp();
}

async function fazerBackup() {
  try {
    const r = await fetch(API + '/backup');
    if (!r.ok) throw new Error('Não foi possível gerar o backup');
    const blob = await r.blob();
    let filename = 'pratic_backup.db';
    const disp = r.headers.get('content-disposition') || '';
    const match = disp.match(/filename="?([^";]+)"?/i);
    if (match) filename = match[1];
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    _showLocalAlert('backup-alert', 'Backup gerado com sucesso.');
  } catch (e) {
    _showLocalAlert('backup-alert', e.message || 'Erro ao fazer backup', 'danger');
  }
}

function handleRestoreDrop(event) {
  event.preventDefault();
  event.currentTarget.style.borderColor = 'var(--border)';
  const file = event.dataTransfer?.files?.[0];
  confirmarRestore(file);
}

async function confirmarRestore(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith('.db')) {
    _showLocalAlert('backup-alert', 'Selecione um arquivo .db válido.', 'danger');
    return;
  }
  if (!confirm('Restaurar este backup? Os dados atuais serão substituídos.')) return;
  const form = new FormData();
  form.append('file', file);
  try {
    const r = await fetch(API + '/restore', { method: 'POST', body: form });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || 'Erro ao restaurar backup');
    _showLocalAlert('backup-alert', (d.mensagem || 'Backup restaurado.') + ' Reinicie o servidor.');
  } catch (e) {
    _showLocalAlert('backup-alert', e.message || 'Erro ao restaurar backup', 'danger');
  }
}

let csvProdutosPreview = [];

function openModalImportCSV() {
  cancelarCSV(false);
  openModal('modal-import-csv');
}

function cancelarCSV(fechar = false) {
  csvProdutosPreview = [];
  const input = document.getElementById('csv-file-input');
  if (input) input.value = '';
  const prev = document.getElementById('csv-preview');
  if (prev) prev.style.display = 'none';
  const info = document.getElementById('csv-info');
  if (info) info.textContent = '';
  const thead = document.getElementById('csv-thead');
  const tbody = document.getElementById('csv-tbody');
  if (thead) thead.innerHTML = '';
  if (tbody) tbody.innerHTML = '';
  const alert = document.getElementById('csv-alert');
  if (alert) alert.innerHTML = '';
  const btn = document.getElementById('csv-import-btn');
  if (btn) btn.style.display = 'none';
  if (fechar) closeModal('modal-import-csv');
}

function handleCSVDrop(event) {
  event.preventDefault();
  event.currentTarget.style.borderColor = 'var(--border)';
  const file = event.dataTransfer?.files?.[0];
  handleCSVFile(file);
}

function _parseCSVLine(line) {
  const out = [];
  let cur = '', quoted = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (quoted && line[i + 1] === '"') { cur += '"'; i++; }
      else quoted = !quoted;
    } else if ((ch === ',' || ch === ';') && !quoted) {
      out.push(cur.trim()); cur = '';
    } else cur += ch;
  }
  out.push(cur.trim());
  return out;
}

function handleCSVFile(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith('.csv')) {
    _showLocalAlert('csv-alert', 'Selecione um arquivo CSV.', 'danger');
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const text = String(reader.result || '').replace(/^\uFEFF/, '');
      const lines = text.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
      if (lines.length < 2) throw new Error('CSV sem produtos para importar.');
      const headers = _parseCSVLine(lines[0]).map(h => h.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim());
      const idx = name => headers.indexOf(name);
      const col = {
        codigo: Math.max(idx('codigo'), idx('codigo/id'), idx('id')),
        nome: idx('nome'),
        marca: idx('marca'),
        unidade: idx('unidade'),
        estoque_minimo: Math.max(idx('estoque_minimo'), idx('minimo'), idx('estoque minimo')),
        categoria: idx('categoria')
      };
      if (col.nome < 0) throw new Error('A coluna "nome" é obrigatória.');
      csvProdutosPreview = lines.slice(1).map(line => {
        const p = _parseCSVLine(line);
        return {
          codigo: col.codigo >= 0 ? (p[col.codigo] || '') : '',
          nome: p[col.nome] || '',
          marca: col.marca >= 0 ? (p[col.marca] || '') : '',
          unidade: col.unidade >= 0 ? (p[col.unidade] || 'unidade') : 'unidade',
          estoque_minimo: col.estoque_minimo >= 0 ? Number(String(p[col.estoque_minimo] || '0').replace(',', '.')) || 0 : 0,
          categoria_nome: col.categoria >= 0 ? (p[col.categoria] || '') : ''
        };
      }).filter(p => p.nome);
      if (!csvProdutosPreview.length) throw new Error('Nenhum produto válido encontrado.');
      renderCSVPreview();
    } catch (e) {
      _showLocalAlert('csv-alert', e.message, 'danger');
    }
  };
  reader.readAsText(file, 'utf-8');
}

function renderCSVPreview() {
  const prev = document.getElementById('csv-preview');
  const info = document.getElementById('csv-info');
  const thead = document.getElementById('csv-thead');
  const tbody = document.getElementById('csv-tbody');
  const btn = document.getElementById('csv-import-btn');
  if (prev) prev.style.display = '';
  if (info) info.textContent = `${csvProdutosPreview.length} produto(s) prontos para importar.`;
  if (thead) thead.innerHTML = '<tr><th>Código/ID</th><th>Nome</th><th>Categoria</th><th>Marca</th><th>Unidade</th><th>Mínimo</th></tr>';
  if (tbody) tbody.innerHTML = csvProdutosPreview.slice(0, 30).map(p => `<tr><td>${p.codigo || '—'}</td><td>${p.nome}</td><td>${p.categoria_nome || '—'}</td><td>${p.marca || '—'}</td><td>${p.unidade || 'unidade'}</td><td>${fmtNum(p.estoque_minimo || 0)}</td></tr>`).join('');
  if (btn) btn.style.display = '';
}

async function confirmarImportCSV() {
  if (!csvProdutosPreview.length) {
    _showLocalAlert('csv-alert', 'Nenhum produto carregado para importar.', 'danger');
    return;
  }
  try {
    const cats = await api('/estoque/categorias');
    const catMap = new Map(cats.map(c => [String(c.nome || '').trim().toLowerCase(), c.id]));
    let ok = 0, erros = 0;
    for (const p of csvProdutosPreview) {
      let categoria_id = null;
      const catNome = String(p.categoria_nome || '').trim();
      if (catNome) {
        const key = catNome.toLowerCase();
        if (catMap.has(key)) categoria_id = catMap.get(key);
        else {
          const nova = await api('/estoque/categorias', 'POST', { nome: catNome, descricao: '' });
          categoria_id = nova.id;
          catMap.set(key, categoria_id);
        }
      }
      try {
        await api('/estoque/produtos', 'POST', {
          codigo: p.codigo || null,
          nome: p.nome,
          marca: p.marca || '',
          unidade: p.unidade || 'unidade',
          estoque_minimo: p.estoque_minimo || 0,
          categoria_id
        });
        ok++;
      } catch (e) { erros++; }
    }
    _showLocalAlert('csv-alert', `Importação concluída: ${ok} produto(s) importado(s), ${erros} erro(s).`, erros ? 'danger' : 'success');
    await loadCategoriasFiltro();
    await loadProdutos();
    await loadAlertasEstoque();
    const btn = document.getElementById('csv-import-btn'); if (btn) btn.style.display = 'none';
  } catch (e) {
    _showLocalAlert('csv-alert', e.message || 'Erro ao importar CSV', 'danger');
  }
}

function baixarModeloCSV() {
  const rows = [
    ['codigo','nome','marca','unidade','estoque_minimo','categoria'],
    ['COPO-300','Copo 300ml','','unidade','5000','Copos Descartável'],
    ['COPO-180','Copo 180ml','','unidade','1000','Copos Descartável']
  ];
  const csv = '\uFEFF' + rows.map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(';')).join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'modelo_produtos_pratic.csv';
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}


/* =========================================================
   Proteção contra duplo clique em botões de salvar/confirmar
   ========================================================= */
(function () {
  if (window.PRATIC_SAVE_GUARD_INSTALLED) return;
  window.PRATIC_SAVE_GUARD_INSTALLED = true;

  const actionWords = ['salvar', 'registrar', 'confirmar', 'importar', 'baixar backup'];
  let currentActionButton = null;

  function normalizeText(value) {
    return String(value || '')
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function isProtectedButton(btn) {
    if (!btn || btn.tagName !== 'BUTTON') return false;
    if (btn.dataset.noGuard === 'true') return false;
    const onclick = normalizeText(btn.getAttribute('onclick') || '');
    const label = normalizeText(btn.textContent || btn.innerText || '');
    return actionWords.some(w => label.includes(w)) ||
      /salvar|confirmar|registrar|importar|restore|backup/i.test(onclick);
  }

  function getButton() {
    if (currentActionButton && document.contains(currentActionButton)) return currentActionButton;
    const active = document.activeElement;
    if (active && active.tagName === 'BUTTON') return active;
    return null;
  }

  function setLoadingText(btn) {
    if (!btn || btn.dataset.originalHtml) return;
    btn.dataset.originalHtml = btn.innerHTML;
    const text = normalizeText(btn.textContent || btn.innerText || '');
    if (text.includes('importar')) btn.innerHTML = 'Importando...';
    else if (text.includes('confirmar')) btn.innerHTML = 'Confirmando...';
    else if (text.includes('registrar')) btn.innerHTML = 'Registrando...';
    else if (text.includes('backup') || text.includes('baixar')) btn.innerHTML = 'Processando...';
    else btn.innerHTML = 'Salvando...';
  }

  function lock(btn) {
    if (!btn || !isProtectedButton(btn)) return true;
    if (btn.dataset.guardBusy === '1') return false;
    btn.dataset.guardBusy = '1';
    btn.disabled = true;
    btn.classList.add('btn-loading');
    setLoadingText(btn);
    return true;
  }

  function unlock(btn) {
    if (!btn || !document.contains(btn)) return;
    delete btn.dataset.guardBusy;
    btn.disabled = false;
    btn.classList.remove('btn-loading');
    if (btn.dataset.originalHtml) {
      btn.innerHTML = btn.dataset.originalHtml;
      delete btn.dataset.originalHtml;
    }
  }

  document.addEventListener('click', function (event) {
    const btn = event.target.closest && event.target.closest('button');
    if (!btn || !isProtectedButton(btn)) return;
    if (btn.dataset.guardBusy === '1') {
      event.preventDefault();
      event.stopImmediatePropagation();
      return false;
    }
    currentActionButton = btn;
    setTimeout(() => {
      if (currentActionButton === btn) currentActionButton = null;
    }, 1000);
  }, true);

  function guardFunction(name) {
    const original = window[name];
    if (typeof original !== 'function' || original.__praticGuarded) return;
    const guarded = async function (...args) {
      const btn = getButton();
      if (btn && !lock(btn)) return;
      try {
        return await original.apply(this, args);
      } finally {
        if (btn) unlock(btn);
      }
    };
    guarded.__praticGuarded = true;
    window[name] = guarded;
  }

  function installFunctionGuards() {
    [
      'salvarProducao', 'salvarColaborador', 'salvarTipoColaborador', 'salvarMaquina', 'salvarAuxiliar',
      'salvarConfig', 'salvarProduto', 'salvarProdutoEstoque', 'salvarMovimentacao',
      'salvarPerda', 'salvarCategoria', 'salvarPedido', 'salvarCliente',
      'salvarEmpresa', 'salvarPermissoes', 'salvarEPI', 'salvarEntrega',
      'salvarFuncaoEPI', 'salvarNovoPedido', 'salvarNovoCliente', 'salvarMobile',
      'salvarColabProd', 'salvarMaqProd', 'confirmarImportCSV', 'confirmarImportacao',
      'confirmarRestore', 'confirmarMovimentacao', 'confirmarMovRapida', 'fazerBackup',
      'salvarUsuario', 'salvarNovaSenha'
    ].forEach(guardFunction);
  }

  installFunctionGuards();
  document.addEventListener('DOMContentLoaded', installFunctionGuards);
  setTimeout(installFunctionGuards, 300);
})();

/* =========================================================
   Gerenciamento de Usuários (Aba no Controle de Acesso)
   ========================================================= */

function switchPermissoesTab(tab) {
  const cfgEl = document.getElementById('perm-content-config');
  const userEl = document.getElementById('perm-content-usuarios');
  if (cfgEl) cfgEl.style.display = tab === 'config' ? '' : 'none';
  if (userEl) userEl.style.display = tab === 'usuarios' ? '' : 'none';
  
  const tabCfg = document.getElementById('perm-tab-config');
  const tabUser = document.getElementById('perm-tab-usuarios');
  
  if (tabCfg) {
    tabCfg.classList.toggle('active', tab === 'config');
    tabCfg.style.borderColor = tab === 'config' ? 'var(--accent)' : '';
    tabCfg.style.color = tab === 'config' ? 'var(--accent)' : '';
  }
  if (tabUser) {
    tabUser.classList.toggle('active', tab === 'usuarios');
    tabUser.style.borderColor = tab === 'usuarios' ? 'var(--accent)' : '';
    tabUser.style.color = tab === 'usuarios' ? 'var(--accent)' : '';
  }

  if (tab === 'usuarios') {
    loadUsuarios();
  }
}

async function loadUsuarios() {
  const tbody = document.getElementById('usuarios-tbody');
  if (!tbody) return;
  
  tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--muted);padding:24px"><div class="spinner" style="margin:0 auto"></div></td></tr>';
  
  try {
    const users = await api('/auth/usuarios');
    if (!users.length) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--muted);padding:24px">Nenhum usuário cadastrado</td></tr>';
      return;
    }
    
    const roleLabels = {
      gestor: '🖥️ Gestor',
      producao: '🏭 Produção',
      comercial: '🏢 Comercial',
      estoque: '📦 Estoque'
    };
    
    tbody.innerHTML = users.map(u => `
      <tr>
        <td><strong>${u.nome}</strong></td>
        <td><code>${u.username}</code></td>
        <td>${roleLabels[u.role] || u.role}</td>
        <td>
          <span class="pill ${u.ativo ? 'pill-success' : 'pill-danger'}">
            ${u.ativo ? 'Ativo' : 'Inativo'}
          </span>
        </td>
        <td class="flex gap-2">
          <button class="btn btn-sm btn-secondary" onclick="editarUsuario(${u.id}, '${u.username}', '${u.nome}', '${u.role}', ${u.ativo})">✏️ Editar</button>
          <button class="btn btn-sm btn-secondary" onclick="abrirAlterarSenha(${u.id}, '${u.nome}')">🔑 Senha</button>
          <button class="btn btn-sm btn-danger" onclick="excluirUsuario(${u.id}, '${u.nome}')">✕ Excluir</button>
        </td>
      </tr>
    `).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:var(--danger);padding:24px">Erro ao carregar usuários: ${e.message}</td></tr>`;
  }
}

function openModalUsuario() {
  document.getElementById('user-id').value = '';
  document.getElementById('user-nome').value = '';
  document.getElementById('user-username').value = '';
  document.getElementById('user-username').disabled = false;
  document.getElementById('user-role').value = 'producao';
  document.getElementById('user-password').value = '';
  document.getElementById('user-password-container').style.display = '';
  document.getElementById('user-ativo-container').style.display = 'none';
  document.getElementById('user-ativo').value = '1';
  
  document.getElementById('modal-user-title').textContent = 'Novo Usuário';
  openModal('modal-usuario');
}

function editarUsuario(id, username, nome, role, ativo) {
  document.getElementById('user-id').value = id;
  document.getElementById('user-nome').value = nome;
  document.getElementById('user-username').value = username;
  document.getElementById('user-username').disabled = true;
  document.getElementById('user-role').value = role;
  document.getElementById('user-password').value = '';
  document.getElementById('user-password-container').style.display = 'none';
  document.getElementById('user-ativo-container').style.display = '';
  document.getElementById('user-ativo').value = ativo;
  
  document.getElementById('modal-user-title').textContent = 'Editar Usuário';
  openModal('modal-usuario');
}

async function salvarUsuario() {
  const id = document.getElementById('user-id').value;
  const nome = document.getElementById('user-nome').value.trim();
  const username = document.getElementById('user-username').value.trim();
  const role = document.getElementById('user-role').value;
  const password = document.getElementById('user-password').value;
  const ativo = +document.getElementById('user-ativo').value;
  
  if (!nome || !username) {
    showAlert('Preencha o nome e o usuário.', 'danger');
    return;
  }
  
  try {
    if (id) {
      await api('/auth/usuarios/' + id, 'PUT', { role, nome, ativo });
      showAlert('Usuário atualizado com sucesso!');
    } else {
      if (!password || password.length < 3) {
        showAlert('A senha inicial deve conter pelo menos 3 caracteres.', 'danger');
        return;
      }
      await api('/auth/usuarios', 'POST', { username, password, role, nome });
      showAlert('Usuário cadastrado com sucesso!');
    }
    closeModal('modal-usuario');
    loadUsuarios();
  } catch (e) {
    showAlert(e.message, 'danger');
  }
}

function abrirAlterarSenha(id, nome) {
  document.getElementById('pass-user-id').value = id;
  document.getElementById('new-password').value = '';
  openModal('modal-alterar-senha');
}

async function salvarNovaSenha() {
  const id = document.getElementById('pass-user-id').value;
  const password = document.getElementById('new-password').value;
  
  if (!password || password.length < 3) {
    showAlert('A nova senha deve ter no mínimo 3 caracteres.', 'danger');
    return;
  }
  
  try {
    await api(`/auth/usuarios/${id}/password`, 'PUT', { password });
    showAlert('Senha alterada com sucesso!');
    closeModal('modal-alterar-senha');
  } catch (e) {
    showAlert(e.message, 'danger');
  }
}

async function excluirUsuario(id, nome) {
  if (!confirm(`Deseja realmente excluir o usuário "${nome}"? Esta ação não pode ser desfeita.`)) return;
  
  try {
    await api('/auth/usuarios/' + id, 'DELETE');
    showAlert('Usuário excluído com sucesso!');
    loadUsuarios();
  } catch (e) {
    showAlert(e.message, 'danger');
  }
}
// Funções expostas para os botões inline do HTML
window.openModalTipoColaborador = openModalTipoColaborador;
window.salvarTipoColaborador = salvarTipoColaborador;
window.deletarTipoColaborador = deletarTipoColaborador;
window.openModalColaborador = openModalColaborador;
window.editColaborador = editColaborador;
window.salvarColaborador = salvarColaborador;
window.deletarColaborador = deletarColaborador;
