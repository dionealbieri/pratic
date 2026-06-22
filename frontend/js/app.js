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

// Popup central de aviso (precisa ser fechado pelo usuário). Útil quando a
// mensagem não pode passar despercebida (ex.: pedido duplicado no import).
function showPopup(titulo, mensagemHtml) {
  const antigo = document.getElementById('popup-overlay-dyn');
  if (antigo) antigo.remove();
  const overlay = document.createElement('div');
  overlay.id = 'popup-overlay-dyn';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.6);display:flex;align-items:center;justify-content:center;z-index:9999;padding:16px';
  const box = document.createElement('div');
  box.style.cssText = 'background:var(--surface,#161922);border:1px solid var(--border,rgba(255,255,255,.12));border-radius:12px;padding:20px 24px;max-width:480px;width:100%;box-shadow:0 12px 48px rgba(0,0,0,.55)';
  box.innerHTML = `<div style="font-size:16px;font-weight:700;margin-bottom:10px">${titulo}</div>`
    + `<div style="font-size:14px;line-height:1.5">${mensagemHtml}</div>`
    + `<div style="text-align:right;margin-top:18px"><button class="btn btn-secondary" id="popup-ok-dyn">OK</button></div>`;
  overlay.appendChild(box);
  document.body.appendChild(overlay);
  const fechar = () => overlay.remove();
  box.querySelector('#popup-ok-dyn').onclick = fechar;
  overlay.onclick = (e) => { if (e.target === overlay) fechar(); };
}

// ─── CONSTANTES DE PERMISSÕES ────────────────────────────────────────────────

const PAGINAS_SISTEMA = [
  { key:'dashboard',     label:'📊 Dashboard'         },
  { key:'producao',      label:'🏭 Produção Diária'   },
  { key:'producao_simplificada', label:'⚡ Lançamento Simplificado' },
  { key:'premiacao',     label:'🏆 Premiação'          },
  { key:'pedidos',       label:'🧾 Pedidos'            },
  { key:'estoque',       label:'📦 Estoque'            },
  { key:'graficos',      label:'📈 Gráficos'           },
  { key:'relatorios',    label:'📋 Relatórios'         },
  { key:'colaboradores', label:'👥 Colaboradores'      },
  { key:'maquinas',      label:'⚙️ Máquinas'           },
  { key:'epi',           label:'🦺 EPI'               },
  { key:'saldo-demanda', label:'📊 Saldo vs Demanda'   },
  { key:'configuracoes', label:'🔧 Configurações'      },
  { key:'backup',        label:'💾 Backup'             },
  { key:'permissoes',    label:'🔐 Controle de Acesso' },
  { key:'empresa',       label:'🏢 Dados da Empresa'   },
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
let modoSimplificadoPerfil = false; // definido pelo Controle de Acesso (perfil tem 'producao_simplificada')
let chartDashEvolucaoInstance = null;
let chartDashPerdasTipoInstance = null;

async function api(path, method = 'GET', body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (method === 'GET') {
    opts.cache = 'no-store';
  }
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
  configuracoes: 'Central de Bonificações',
  graficos: 'Análise Gráfica',
  relatorios: 'Relatórios',
  estoque: 'Estoque',
  'saldo-demanda': 'Saldo vs Demanda',
  pedidos: 'Pedidos & Fila de Produção',
  backup: 'Backup & Restauração',
  epi: 'Controle de EPI',
  empresa: 'Dados da Empresa',
  permissoes: 'Controle de Acesso',
  'perm-usuarios': 'Permissões por Usuário'
};

let META_GLOBAL = 8000;
async function carregarMetaGlobal() {
  try {
    const configs = await api('/configuracoes/');
    const m = (configs || []).find(c => c.chave === 'meta_padrao');
    if (m && m.valor != null && m.valor !== '' && !isNaN(+m.valor)) META_GLOBAL = +m.valor;
  } catch (e) {}
}

const PAGE_META_MAIN = {
  dashboard:     { icon:'📊', label:'Dashboard', section:'Visão Geral' },
  producao:      { icon:'🏭', label:'Produção Diária', section:'Lançamentos' },
  premiacao:     { icon:'🏆', label:'Premiação', section:'Lançamentos' },
  colaboradores: { icon:'👥', label:'Colaboradores', section:'Cadastros' },
  maquinas:      { icon:'⚙️', label:'Máquinas', section:'Cadastros' },
  pedidos:       { icon:'🧾', label:'Pedidos', section:'Operações' },
  estoque:       { icon:'📦', label:'Estoque', section:'Operações' },
  epi:           { icon:'🦺', label:'EPI', section:'Operações' },
  comunicacao:   { icon:'<svg viewBox="0 0 24 24" width="17" height="17" style="vertical-align:-3px"><path fill="#25d366" d="M12 2C6.5 2 2 6 2 11c0 1.9.7 3.7 1.9 5.1L3 22l6-1.5c.9.3 1.9.5 3 .5 5.5 0 10-4 10-9S17.5 2 12 2z"/></svg>', label:'Comunicação', section:'Operações' },
  'saldo-demanda': { icon:'📊', label:'Saldo vs Demanda', section:'Operações' },
  graficos:      { icon:'📈', label:'Gráficos', section:'Análises' },
  relatorios:    { icon:'📋', label:'Relatórios', section:'Análises' },
  configuracoes: { icon:'🏆', label:'Central de Bonificações', section:'Sistema' },
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
  try {
    const r = await fetch(API + '/configuracoes/empresa', { cache: 'no-store' });
    if (r.ok) {
      window.empresaDados = await r.json();
    }
  } catch (err) {
    console.error('Erro ao inicializar dados da empresa globalmente:', err);
  }

  let me;
  try {
    me = await api('/auth/me');
    window.usuarioLogado = me;
    if (me.deve_alterar_senha) {
      window.location.href = '/login?change_password=1';
      return;
    }
    // Carregar permissões por usuário logado
    await carregarMinhasPermissoes();
    aplicarPermissoesUI();

    const elNomeTxt = document.getElementById('topbar-user-name-txt');
    if (elNomeTxt) elNomeTxt.textContent = me.nome;
    
    perfilAtual = me.role;
    paginasLiberadas = me.permissions
      ? me.permissions.split(',').map(p => p.trim()).filter(p => PAGE_META_MAIN[p])
      : (perfilAtual === 'gestor' ? Object.keys(PAGE_META_MAIN) : ['dashboard']);
    // Modo de lançamento (simplificado x detalhado) vem do Controle de Acesso, por perfil.
    // Lê da string crua porque 'producao_simplificada' não é uma página navegável.
    modoSimplificadoPerfil = me.permissions
      ? me.permissions.split(',').map(p => p.trim()).includes('producao_simplificada')
      : false;
    
    const path = window.location.pathname;
    const params = new URLSearchParams(window.location.search);
    const temPaginaSolicitada = params.has('page') || params.has('pagina') || params.has('perfil') || params.has('setor');

    if ((path === '/' || path === '/index.html') && !temPaginaSolicitada) {
      if (me.role === 'producao') {
        const somenteProducao = paginasLiberadas.every(p => ['producao', 'producao_simplificada'].includes(p));
        if (somenteProducao) {
          window.location.href = '/producao-setor';
          return;
        }
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
        const somenteEstoque = paginasLiberadas.every(p => ['estoque', 'estoque_mobile'].includes(p));
        if (somenteEstoque) {
          window.location.href = '/estoque-mobile';
          return;
        }
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
  iniciarPollComunicacao();
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
        ${item.key === 'comunicacao' ? '<span id="nav-comunicacao-badge" style="display:none;background:#25d366;color:#fff;font-size:10px;font-weight:700;padding:2px 6px;border-radius:20px;margin-left:4px">0</span>' : ''}
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
    'saldo-demanda': loadSaldoDemanda,
    pedidos: loadPedidos_init,
    backup: () => {},
    epi: loadEPI,
    comunicacao: loadComunicacao,
    empresa: loadEmpresa,
    permissoes: loadPermissoes,
    'perm-usuarios': loadPermUsuarios
  };
  if (handlers[name]) handlers[name]();
}

// ===== Comunicação (mensagens privadas 1:1 por usuário — estilo WhatsApp interno) =====
const SETOR_LABEL_COM = { gestor:'Gestor', producao:'Produção', comercial:'Comercial', estoque:'Estoque' };
const SETOR_ICONE_COM = { producao:'🏭', comercial:'🏢', estoque:'📦' };
let comUltimoId = -1;          // maior id já visto (-1 = ainda não inicializado)
let comPollTimer = null;
let _comAudioCtx = null;
let comArquivoSel = null;      // arquivo selecionado para anexar
let comUsuarioAtivo = null;    // conversa aberta (P2P): id do usuário (ou próprio ID para chat com gestor se for não-gestor)
let comCanalAtivo = null;      // canal ativo (ex: 'geral', 'producao', etc)
let comFiltroBusca = '';       // filtro de busca na sidebar
let comUsuariosCache = [];     // usuários ativos/liberados
let comRecadosCache = [];

function _maxIdRecados(recados) {
  return (recados && recados.length) ? Math.max(...recados.map(r => r.id)) : 0;
}
function _escapeHtmlCom(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function _fmtDataHoraCom(s) {
  if (!s) return '';
  try { return new Date(String(s).replace(' ', 'T') + 'Z').toLocaleString('pt-BR', { dateStyle:'short', timeStyle:'short' }); }
  catch (e) { return s; }
}

// Lista de conversas do gestor: usuários liberados + qualquer remetente presente nas mensagens
function _conversasGestor(recados) {
  const map = new Map();
  (comUsuariosCache || []).forEach(u => map.set(u.id, { id:u.id, nome:u.nome, role:u.role }));
  (recados || []).forEach(r => {
    const uid = r.conversa_usuario_id;
    if (uid && !map.has(uid)) {
      const nome = (r.autor_setor !== 'gestor' && r.autor_nome) ? r.autor_nome : ('Usuário #' + uid);
      map.set(uid, { id:uid, nome:nome, role:(r.autor_setor !== 'gestor' ? r.autor_setor : '') });
    }
  });
  return Array.from(map.values());
}
function _usuarioComMaisRecente(recados) {
  let best = null, bestId = -1;
  (recados || []).forEach(r => { if (r.conversa_usuario_id && r.id > bestId) { bestId = r.id; best = r.conversa_usuario_id; } });
  if (best) return best;
  return (comUsuariosCache && comUsuariosCache.length) ? comUsuariosCache[0].id : null;
}

async function loadComunicacao() {
  const btnConfig = document.getElementById('com-btn-config');
  if (btnConfig) btnConfig.style.display = (perfilAtual === 'gestor') ? 'block' : 'none';

  const lista = document.getElementById('com-lista');
  if (lista) lista.innerHTML = '<div style="color:var(--muted);padding:8px">Carregando...</div>';
  try {
    try {
      comUsuariosCache = await api('/comunicacao/usuarios');
    } catch (e) {
      comUsuariosCache = [];
    }

    const recados = await api('/comunicacao/');
    comRecadosCache = recados;
    comUltimoId = _maxIdRecados(recados);

    // Selecionar o primeiro canal ou conversa disponível se nada estiver ativo
    if (!comUsuarioAtivo && !comCanalAtivo) {
      comCanalAtivo = 'geral';
    }

    renderComLayout(recados);
    _marcarConversaLida(recados);
    _atualizarBadgeComMenu(recados);
  } catch (e) {
    if (lista) lista.innerHTML = '<div style="color:var(--danger);padding:8px">Erro ao carregar a comunicação.</div>';
  }
}

function _getAvatarHtmlCom(name, isChannel = false) {
  if (isChannel) {
    return `<div style="width:40px;height:40px;border-radius:50%;background:rgba(240,180,41,0.15);color:var(--accent);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:18px;flex-shrink:0">#</div>`;
  }
  const initials = (name || '').split(' ').slice(0, 2).map(n => n[0]).join('').toUpperCase() || '👤';
  let hash = 0;
  for (let i = 0; i < (name || '').length; i++) {
    hash = (name || '').charCodeAt(i) + ((hash << 5) - hash);
  }
  const colors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4'];
  const color = colors[Math.abs(hash) % colors.length];
  return `<div style="width:40px;height:40px;border-radius:50%;background:${color};color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:14px;flex-shrink:0">${initials}</div>`;
}

function _fmtHoraCom(s) {
  if (!s) return '';
  try {
    const dt = new Date(String(s).replace(' ', 'T') + 'Z');
    return dt.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  } catch(e) {
    return '';
  }
}

function _fmtDataCom(s) {
  if (!s) return '';
  try {
    const dt = new Date(String(s).replace(' ', 'T') + 'Z');
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    
    if (dt.toDateString() === today.toDateString()) return 'Hoje';
    if (dt.toDateString() === yesterday.toDateString()) return 'Ontem';
    return dt.toLocaleDateString('pt-BR', { day: 'numeric', month: 'long' });
  } catch(e) {
    return '';
  }
}

function _scrollListaComBottom() {
  const lista = document.getElementById('com-lista');
  if (lista) {
    lista.scrollTop = lista.scrollHeight;
  }
}

function renderComLayout(recados) {
  renderSidebarCom(recados);
  renderThreadCom(recados);
}

function renderSidebarCom(recados) {
  const box = document.getElementById('com-setores');
  if (!box) return;

  const termo = comFiltroBusca.toLowerCase().trim();
  let html = '';

  // 1. Canais / Grupos
  const canais = ['geral'];

  const canaisFiltrados = canais.filter(c => c.toLowerCase().includes(termo) || ('#' + c).toLowerCase().includes(termo));
  
  if (canaisFiltrados.length > 0) {
    html += `<div style="font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);margin:10px 4px 6px">📢 Canais</div>`;
    canaisFiltrados.forEach(c => {
      const msgs = (recados || []).filter(r => r.conversa_setor === c && r.conversa_usuario_id === null);
      const ultima = msgs[0];
      const unread = _unreadCanal(recados, c);
      const ativo = (comCanalAtivo === c);
      const snippet = ultima
        ? (ultima.texto ? _escapeHtmlCom(ultima.texto.slice(0, 30)) : '📎 anexo')
        : '<span style="opacity:.5">sem mensagens</span>';
      
      const avatar = _getAvatarHtmlCom(c, true);
      
      html += `
        <div onclick="selecionarCanalCom('${c}')" style="cursor:pointer;display:flex;align-items:center;gap:12px;padding:8px 10px;border-radius:10px;margin-bottom:6px;border:1px solid ${ativo ? 'rgba(37,211,102,0.3)' : 'transparent'};background:${ativo ? 'rgba(37,211,102,0.1)' : 'transparent'};transition:all 0.2s">
          ${avatar}
          <div style="flex:1;min-width:0">
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span style="font-weight:700;font-size:13px;color:var(--text)">#${c}</span>
              ${unread > 0 ? `<span style="background:#25d366;color:#fff;font-size:10px;font-weight:700;padding:2px 6px;border-radius:10px;min-width:18px;text-align:center">${unread}</span>` : ''}
            </div>
            <div style="font-size:11px;color:var(--muted);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${snippet}</div>
          </div>
        </div>`;
    });
  }

  // 2. Direct Messages (P2P / Admin)
  html += `<div style="font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);margin:16px 4px 6px">💬 Conversas Diretas</div>`;
  
  const contatos = (comUsuariosCache || [])
    .filter(u => window.usuarioLogado && u.id !== window.usuarioLogado.id)
    .map(u => ({ id: u.id, nome: u.nome, role: u.role, tipo: u.role === 'gestor' ? 'admin' : 'usuario' }));

  const contatosFiltrados = contatos.filter(c => c.nome.toLowerCase().includes(termo));
  
  if (contatosFiltrados.length > 0) {
    contatosFiltrados.forEach(c => {
      const myId = window.usuarioLogado ? window.usuarioLogado.id : 0;
      const msgs = (recados || []).filter(r => _isDirectMsg(r, myId, c.id));
      const unread = _unreadDirect(recados, c.id);
      const ativo = (comUsuarioAtivo === c.id && comCanalAtivo === null);


      const ultima = msgs[0];
      const snippet = ultima
        ? (ultima.texto ? _escapeHtmlCom(ultima.texto.slice(0, 30)) : '📎 anexo')
        : '<span style="opacity:.5">sem mensagens</span>';
      
      const avatar = _getAvatarHtmlCom(c.nome, false);

      html += `
        <div onclick="selecionarUsuarioCom(${c.id}, '${c.tipo}')" style="cursor:pointer;display:flex;align-items:center;gap:12px;padding:8px 10px;border-radius:10px;margin-bottom:6px;border:1px solid ${ativo ? 'rgba(37,211,102,0.3)' : 'transparent'};background:${ativo ? 'rgba(37,211,102,0.1)' : 'transparent'};transition:all 0.2s">
          ${avatar}
          <div style="flex:1;min-width:0">
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span style="font-weight:700;font-size:13px;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${_escapeHtmlCom(c.nome)}</span>
              ${unread > 0 ? `<span style="background:#25d366;color:#fff;font-size:10px;font-weight:700;padding:2px 6px;border-radius:10px;min-width:18px;text-align:center">${unread}</span>` : ''}
            </div>
            <div style="font-size:11px;color:var(--muted);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${snippet}</div>
          </div>
        </div>`;
    });
  } else if (canaisFiltrados.length === 0) {
    html += `<div style="color:var(--muted);font-size:12px;padding:16px;text-align:center">Nenhuma conversa encontrada</div>`;
  }

  box.innerHTML = html;
}

function renderThreadCom(recados) {
  const ehGestor = (perfilAtual === 'gestor');
  const titulo = document.getElementById('com-titulo');
  const subtitulo = document.getElementById('com-subtitulo');
  const btnLimpar = document.getElementById('com-limpar');
  const lista = document.getElementById('com-lista');
  const compositor = document.getElementById('com-compositor');

  if (btnLimpar) btnLimpar.style.display = 'none'; // Default hidden, shown only for user chats of gestor
  if (compositor) compositor.style.display = (comCanalAtivo || comUsuarioAtivo) ? 'flex' : 'none';

  let msgs = [];
  
  if (comCanalAtivo) {
    if (titulo) titulo.textContent = '#' + comCanalAtivo;
    if (subtitulo) subtitulo.textContent = 'Canal do Setor';
    msgs = (recados || []).filter(r => r.conversa_setor === comCanalAtivo && r.conversa_usuario_id === null);
  } else if (comUsuarioAtivo) {
    const myId = window.usuarioLogado ? window.usuarioLogado.id : 0;
    const u = (comUsuariosCache || []).find(x => x.id === comUsuarioAtivo);
    if (u) {
      if (titulo) titulo.textContent = u.nome;
      if (subtitulo) subtitulo.textContent = (SETOR_LABEL_COM[u.role] || u.role) === 'gestor' ? 'Administrador' : (SETOR_LABEL_COM[u.role] || u.role || 'Colaborador');
    } else {
      if (titulo) titulo.textContent = 'Conversa Direta';
      if (subtitulo) subtitulo.textContent = '';
    }
    if (btnLimpar && perfilAtual === 'gestor') btnLimpar.style.display = '';
    msgs = (recados || []).filter(r => _isDirectMsg(r, myId, comUsuarioAtivo));
  } else {
    if (titulo) titulo.textContent = 'Selecione uma conversa';
    if (subtitulo) subtitulo.textContent = '';
    if (lista) lista.innerHTML = '<div style="color:var(--muted);padding:16px;text-align:center">Selecione um canal ou colega à esquerda para iniciar o chat.</div>';
    return;
  }

  if (!lista) return;
  if (!msgs.length) {
    lista.innerHTML = '<div style="color:var(--muted);padding:16px;text-align:center">Nenhuma mensagem nesta conversa ainda. Comece enviando uma mensagem abaixo!</div>';
    return;
  }

  // Render bubbles with date separators
  let lastDate = '';
  const htmlBubbles = msgs.map(r => {
    let dateSep = '';
    const msgDate = _fmtDataCom(r.criado_em);
    if (msgDate !== lastDate) {
      dateSep = `<div style="align-self:center;background:var(--surface2);border:1px solid var(--border);color:var(--muted);font-size:11px;padding:4px 12px;border-radius:12px;margin:8px 0;font-weight:600">${msgDate}</div>`;
      lastDate = msgDate;
    }
    return dateSep + _msgBubbleCom(r);
  }).join('');

  lista.innerHTML = htmlBubbles;
}

function _msgBubbleCom(r) {
  const resolvido = !!r.resolvido;
  const ehMe = (r.autor_id === (window.usuarioLogado ? window.usuarioLogado.id : 0));
  const ehAdmin = (r.autor_setor === 'gestor');
  const setor = SETOR_LABEL_COM[r.autor_setor] || r.autor_setor || '';
  const podeExcluir = (perfilAtual === 'gestor');
  
  const bubbleStyle = ehMe 
    ? 'background:rgba(16,185,129,0.15);border:1px solid rgba(16,185,129,0.3);align-self:flex-end;border-radius:12px 12px 2px 12px;' 
    : 'background:var(--surface2);border:1px solid var(--border);align-self:flex-start;border-radius:12px 12px 12px 2px;';
    
  const textoFormatado = _escapeHtmlCom(r.texto || '').replace(/\n/g, '<br>');
  const anexoHtml = r.tem_anexo ? _anexoHtmlCom(r) : '';
  
  const showSenderHeader = !ehMe && comCanalAtivo;
  const senderHeader = showSenderHeader 
    ? `<div style="font-weight:700;font-size:11px;color:var(--accent);margin-bottom:4px">${_escapeHtmlCom(r.autor_nome || 'Usuário')} <span style="font-weight:normal;color:var(--muted);font-size:10px">(${setor})</span></div>` 
    : '';

  return `
    <div style="max-width:70%;padding:10px 14px;box-sizing:border-box;margin-bottom:4px;display:flex;flex-direction:column;${bubbleStyle}${resolvido ? 'opacity:.6' : ''}">
      ${senderHeader}
      ${r.texto ? `<div style="font-size:14px;word-break:break-word;line-height:1.4;${resolvido ? 'text-decoration:line-through;opacity:0.7' : ''}">${textoFormatado}</div>` : ''}
      ${anexoHtml}
      <div style="display:flex;justify-content:space-between;align-items:center;gap:16px;margin-top:6px;font-size:10px;color:var(--muted);border-top:1px solid rgba(255,255,255,0.03);padding-top:4px">
        <span>🕒 ${_fmtHoraCom(r.criado_em)} ${resolvido && r.resolvido_por ? ' · ✓ por ' + _escapeHtmlCom(r.resolvido_por) : ''}</span>
        <div style="display:flex;gap:6px">
          <span style="cursor:pointer;color:var(--success);font-weight:600" onclick="resolverRecado(${r.id}, ${resolvido ? 'false' : 'true'})">${resolvido ? 'Reabrir' : '✓ Resolvido'}</span>
          ${podeExcluir ? `· <span style="cursor:pointer;color:var(--danger);font-weight:600" onclick="excluirRecado(${r.id})">Excluir</span>` : ''}
        </div>
      </div>
    </div>
  `;
}

function selecionarUsuarioCom(uid, tipo) {
  comUsuarioAtivo = uid;
  comCanalAtivo = null;
  renderComLayout(comRecadosCache);
  _marcarConversaLida(comRecadosCache);
  _atualizarBadgeComMenu(comRecadosCache);
  setTimeout(_scrollListaComBottom, 50);
}

function selecionarCanalCom(canal) {
  comCanalAtivo = canal;
  comUsuarioAtivo = null;
  renderComLayout(comRecadosCache);
  _marcarConversaLida(comRecadosCache);
  _atualizarBadgeComMenu(comRecadosCache);
  setTimeout(_scrollListaComBottom, 50);
}

function filtrarConversasCom(busca) {
  comFiltroBusca = busca;
  renderSidebarCom(comRecadosCache);
}

async function enviarRecado() {
  const ta = document.getElementById('com-texto');
  const texto = ((ta && ta.value) || '').trim();
  if (!texto && !comArquivoSel) { showAlert('Escreva uma mensagem ou anexe um arquivo.', 'warn'); return; }

  const fd = new FormData();
  fd.append('texto', texto);
  
  if (comCanalAtivo) {
    fd.append('canal', comCanalAtivo);
  } else if (comUsuarioAtivo) {
    fd.append('usuario_id', String(comUsuarioAtivo));
  } else {
    showAlert('Selecione uma conversa.', 'warn');
    return;
  }

  if (comArquivoSel) fd.append('anexo', comArquivoSel);

  try {
    const resp = await fetch(API + '/comunicacao/', { method: 'POST', body: fd, credentials: 'same-origin' });
    if (!resp.ok) {
      let msg = 'Não foi possível enviar.';
      try { const d = await resp.json(); if (d && d.detail) msg = d.detail; } catch (e) {}
      throw new Error(msg);
    }
    if (ta) ta.value = '';
    comRemoverArquivo();
    await loadComunicacao();
    setTimeout(_scrollListaComBottom, 50);
  } catch (e) { showAlert(e.message, 'danger'); }
}

async function resolverRecado(id, marcar) {
  try {
    await api('/comunicacao/' + id + '/resolver', 'PUT', { resolvido: !!marcar });
    loadComunicacao();
  } catch (e) { showAlert(e.message, 'danger'); }
}

async function excluirRecado(id) {
  if (!confirm('Excluir esta mensagem definitivamente?')) return;
  try {
    await api('/comunicacao/' + id, 'DELETE');
    showAlert('Mensagem excluída.');
    loadComunicacao();
  } catch (e) { showAlert(e.message, 'danger'); }
}

async function limparConversaCom() {
  if (perfilAtual !== 'gestor' || !comUsuarioAtivo) return;
  const u = _conversasGestor(comRecadosCache).find(c => c.id === comUsuarioAtivo);
  const nome = u ? u.nome : 'este usuário';
  if (!confirm('Apagar TODAS as mensagens e arquivos da conversa com ' + nome + '? Essa ação é permanente.')) return;
  try {
    await api('/comunicacao/conversa-usuario/' + comUsuarioAtivo, 'DELETE');
    showAlert('Conversa limpa.');
    loadComunicacao();
  } catch (e) { showAlert(e.message, 'danger'); }
}

// ----- Gerenciar participantes (quem usa a Comunicação) -----
async function abrirParticipantesCom() {
  let config, usuarios;
  try {
    config = await api('/comunicacao/config');
    usuarios = await api('/comunicacao/usuarios-todos');
  } catch (e) {
    showAlert(e.message, 'danger');
    return;
  }

  let corpo = `
    <div style="margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid var(--border)">
      <label style="display:flex;justify-content:space-between;align-items:center;cursor:pointer">
        <span style="font-weight:600;font-size:13px;color:var(--text)">Permitir chat privado entre colaboradores</span>
        <input type="checkbox" id="com-p2p-global-chk" ${config.chat_p2p_permitido ? 'checked' : ''} onchange="toggleP2PGlobalCom(this.checked, this)" style="width:18px;height:18px;cursor:pointer">
      </label>
      <div style="font-size:11px;color:var(--muted);margin-top:4px">Se desativado, colaboradores comuns só podem falar no canal geral ou diretamente com o Administrador.</div>
    </div>
  `;

  ['producao', 'comercial', 'estoque', ''].forEach(setor => {
    const doSetor = usuarios.filter(u => (u.role || '') === setor);
    if (!doSetor.length) return;
    corpo += `<div style="font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);margin:12px 0 4px">${SETOR_ICONE_COM[setor] || ''} ${SETOR_LABEL_COM[setor] || 'Outros'}</div>`;
    doSetor.forEach(u => {
      corpo += `
        <div style="padding:10px 0;border-bottom:1px solid var(--border)">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <span style="font-weight:600;font-size:13px;color:var(--text)">${_escapeHtmlCom(u.nome)}</span>
            <label style="display:flex;align-items:center;cursor:pointer;font-size:12px;color:var(--muted)">
              <span style="margin-right:6px">Liberar Acesso</span>
              <input type="checkbox" ${u.participa ? 'checked' : ''} onchange="toggleParticipanteCom(${u.id}, this.checked, this)" style="width:18px;height:18px;cursor:pointer">
            </label>
          </div>
        </div>
      `;
    });
  });

  const old = document.getElementById('com-part-overlay');
  if (old) old.remove();
  const ov = document.createElement('div');
  ov.id = 'com-part-overlay';
  ov.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.6);display:flex;align-items:center;justify-content:center;z-index:9999;padding:16px';
  ov.onclick = fecharParticipantesCom;
  const box = document.createElement('div');
  box.style.cssText = 'background:var(--surface,#161922);border:1px solid var(--border,rgba(255,255,255,.12));border-radius:12px;max-width:480px;width:100%;max-height:80vh;display:flex;flex-direction:column;box-shadow:0 12px 48px rgba(0,0,0,.55)';
  box.onclick = function (e) { e.stopPropagation(); };
  box.innerHTML =
    `<div style="padding:18px 20px 12px;border-bottom:1px solid var(--border)">
       <div style="font-size:16px;font-weight:700;color:var(--text)">Configuração da Comunicação</div>
       <div style="font-size:12px;color:var(--muted);margin-top:3px">Gerencie quais colaboradores têm acesso ao chat interno e a permissão global de chat direto.</div>
     </div>
     <div style="padding:16px 20px;overflow-y:auto;flex:1">${corpo}</div>
     <div style="padding:14px 20px;text-align:right;border-top:1px solid var(--border)">
       <button class="btn btn-primary" onclick="fecharParticipantesCom()">Concluir</button>
     </div>`;
  ov.appendChild(box);
  document.body.appendChild(ov);
}

async function toggleParticipanteCom(uid, ativa, el) {
  try {
    await api('/comunicacao/usuarios/' + uid + '/participante', 'PUT', { ativa: !!ativa });
  } catch (e) {
    showAlert(e.message, 'danger');
    if (el) el.checked = !ativa;
  }
}

async function toggleP2PGlobalCom(permitido, el) {
  try {
    await api('/comunicacao/config', 'PUT', { p2p_permitido: !!permitido });
    showAlert('Configuração de chat privado atualizada.');
  } catch (e) {
    showAlert(e.message, 'danger');
    if (el) el.checked = !permitido;
  }
}

function fecharParticipantesCom() {
  const ov = document.getElementById('com-part-overlay');
  if (ov) ov.remove();
  loadComunicacao();   // atualiza a lista de conversas
}

// Bip de notificação gerado no navegador (sem arquivo de áudio)
function _playBeepCom() {
  try {
    if (!_comAudioCtx) _comAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const ctx = _comAudioCtx;
    if (ctx.state === 'suspended') ctx.resume();
    const tocar = (freq, inicio, dur) => {
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.type = 'sine';
      o.frequency.value = freq;
      g.gain.setValueAtTime(0.0001, ctx.currentTime + inicio);
      g.gain.exponentialRampToValueAtTime(0.25, ctx.currentTime + inicio + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + inicio + dur);
      o.connect(g); g.connect(ctx.destination);
      o.start(ctx.currentTime + inicio);
      o.stop(ctx.currentTime + inicio + dur);
    };
    tocar(880, 0, 0.18);
    tocar(1175, 0.16, 0.22);
  } catch (e) { /* silencioso se o navegador bloquear */ }
}

async function _pollComunicacao() {
  let recados;
  try { recados = await api('/comunicacao/'); } catch (e) { return; }
  comRecadosCache = recados;
  const maxId = _maxIdRecados(recados);
  const primeiraVez = (comUltimoId < 0);
  if (!primeiraVez && maxId > comUltimoId) _playBeepCom();
  comUltimoId = maxId;
  const pg = document.getElementById('page-comunicacao');
  if (pg && pg.classList.contains('active')) {
    renderComLayout(recados);
    _marcarConversaLida(recados);
  }
  _atualizarBadgeComMenu(recados);
}

function iniciarPollComunicacao() {
  if (comPollTimer) return;
  if (!paginasLiberadas.includes('comunicacao')) return;
  _pollComunicacao();
  comPollTimer = setInterval(_pollComunicacao, 12000);
}

// ----- não lidas por conversa (badge + pulso no menu) -----
function _isDirectMsg(r, myId, partnerId) {
  if (!r) return false;
  if (r.conversa_setor === 'p2p') {
    return (r.autor_id === myId && r.conversa_usuario_id === partnerId) || 
           (r.autor_id === partnerId && r.conversa_usuario_id === myId);
  }
  if (r.conversa_setor === null) {
    const isGestor = (perfilAtual === 'gestor');
    if (isGestor) {
      return r.conversa_usuario_id === partnerId;
    } else {
      const partner = (comUsuariosCache || []).find(u => u.id === partnerId);
      const partnerIsGestor = partner && (partner.role === 'gestor');
      if (partnerIsGestor) {
        return r.conversa_usuario_id === myId;
      }
    }
  }
  return false;
}
function _getSeenDirect(partnerId) {
  const newKey = 'com_seen_direct_' + partnerId;
  let val = localStorage.getItem(newKey);
  if (val !== null) return parseInt(val, 10) || 0;

  const isGestor = (perfilAtual === 'gestor');
  if (isGestor) {
    val = localStorage.getItem('com_seen_u_' + partnerId);
  } else {
    const partner = (comUsuariosCache || []).find(u => u.id === partnerId);
    if (partner && partner.role === 'gestor') {
      val = localStorage.getItem('com_seen_me');
    } else {
      val = localStorage.getItem('com_seen_p2p_' + partnerId);
    }
  }
  return val !== null ? (parseInt(val, 10) || 0) : 0;
}
function _setSeenDirect(partnerId, maxId) {
  localStorage.setItem('com_seen_direct_' + partnerId, String(maxId));
}
function _unreadDirect(recados, partnerId) {
  const myId = window.usuarioLogado ? window.usuarioLogado.id : 0;
  const seen = _getSeenDirect(partnerId);
  return (recados || []).filter(r => 
    _isDirectMsg(r, myId, partnerId) && 
    r.autor_id !== myId && 
    r.id > seen
  ).length;
}
function _unreadCanal(recados, canal) {
  const k = 'com_seen_c_' + canal;
  const seen = parseInt(localStorage.getItem(k) || '0', 10) || 0;
  return (recados || []).filter(r => r.conversa_setor === canal && r.conversa_usuario_id === null && r.autor_id !== (window.usuarioLogado ? window.usuarioLogado.id : 0) && r.id > seen).length;
}
function _marcarConversaLida(recados) {
  if (comCanalAtivo) {
    const maxId = _maxIdRecados((recados || []).filter(r => r.conversa_setor === comCanalAtivo && r.conversa_usuario_id === null));
    if (maxId) {
      localStorage.setItem('com_seen_c_' + comCanalAtivo, String(maxId));
    }
  } else if (comUsuarioAtivo) {
    const myId = window.usuarioLogado ? window.usuarioLogado.id : 0;
    const maxId = _maxIdRecados((recados || []).filter(r => _isDirectMsg(r, myId, comUsuarioAtivo)));
    if (maxId) {
      _setSeenDirect(comUsuarioAtivo, maxId);
    }
  }
}
function _atualizarBadgeComMenu(recados) {
  let total = 0;
  
  const canais = ['geral'];
  
  canais.forEach(c => {
    total += _unreadCanal(recados, c);
  });
  
  (comUsuariosCache || []).forEach(u => {
    if (window.usuarioLogado && u.id !== window.usuarioLogado.id) {
      total += _unreadDirect(recados, u.id);
    }
  });
  
  const b = document.getElementById('nav-comunicacao-badge');
  if (b) {
    if (total > 0) { b.textContent = total > 99 ? '99+' : String(total); b.style.display = ''; }
    else b.style.display = 'none';
  }
  const nav = document.querySelector('.nav-item[data-page="comunicacao"]');
  if (nav) nav.classList.toggle('com-pulse', total > 0);
}

// ----- Enter envia / Shift+Enter pula linha -----
function comTextoKeydown(ev) {
  if (ev.key === 'Enter' && !ev.shiftKey) {
    ev.preventDefault();
    enviarRecado();
  }
}

// ----- anexo (seleção/remoção antes de enviar) -----
function comSelecionarArquivo(input) {
  const f = input && input.files && input.files[0];
  comArquivoSel = f || null;
  const info = document.getElementById('com-anexo-info');
  if (!info) return;
  if (comArquivoSel) {
    info.innerHTML = '📎 ' + _escapeHtmlCom(comArquivoSel.name) +
      ' <a onclick="comRemoverArquivo()" style="cursor:pointer;color:var(--danger);margin-left:6px">remover</a>';
    info.style.display = '';
  } else {
    info.style.display = 'none';
  }
}
function comRemoverArquivo() {
  comArquivoSel = null;
  const input = document.getElementById('com-arquivo');
  if (input) input.value = '';
  const info = document.getElementById('com-anexo-info');
  if (info) { info.innerHTML = ''; info.style.display = 'none'; }
}

// ----- render do anexo na mensagem -----
function _anexoHtmlCom(r) {
  const url = API + '/comunicacao/anexo/' + r.id;
  const ehImg = (r.anexo_tipo || '').indexOf('image/') === 0;
  if (ehImg) {
    return `<div style="margin-top:8px"><a href="${url}" target="_blank" rel="noopener">` +
      `<img src="${url}" alt="${_escapeHtmlCom(r.anexo_nome)}" style="max-width:240px;max-height:240px;border-radius:8px;border:1px solid var(--border);display:block"></a></div>`;
  }
  return `<div style="margin-top:8px"><a href="${url}" target="_blank" rel="noopener" class="btn btn-sm btn-secondary" style="text-decoration:none">📎 ${_escapeHtmlCom(r.anexo_nome) || 'Baixar arquivo'}</a></div>`;
}

// ─── MODAL ───────────────────────────────────────────────────────────────────

function openModal(id) { document.getElementById(id).classList.add('open'); }
function closeModal(id) { document.getElementById(id).classList.remove('open'); }

document.querySelectorAll('.modal-overlay').forEach(m => {
  m.addEventListener('click', e => { if (e.target === m) m.classList.remove('open'); });
});

// ─── DASHBOARD ───────────────────────────────────────────────────────────────

async function loadDashboard(options = {}) {
  const mesEl = document.getElementById('dash-mes');
  if (!mesEl.value) mesEl.value = currentMonth();
  const mes = mesEl.value;
  document.getElementById('topbar-mes').textContent = mesLabel(mes);

  const cardsEl = document.getElementById('dash-cards');
  if (cardsEl && !(options.useCache && _cacheDashboardData && _cacheDashboardMes === mes)) {
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
    const useCache = options.useCache === true;
    let data;
    if (useCache && _cacheDashboardData && _cacheDashboardMes === mes) {
      data = _cacheDashboardData;
    } else {
      data = await api('/premiacao/dashboard/' + mes);
      _cacheDashboardData = data;
      _cacheDashboardMes = mes;
    }

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
      <div class="card" title="Percentual de dias no mês em que a produção atingiu ou superou a meta de ${fmtNum(META_GLOBAL)} peças">
        <div class="card-label">Aderência à Meta</div>
        <div class="card-value success">${data.aderencia_meta_percentual}%</div>
        <div class="card-sub">${data.dias_acima_meta || 0} de ${data.total_dias_trabalhados || 0} dias atingiram a meta</div>
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

    const colors = getChartThemeColors();

    // 2. GRAFICOS
    if (chartDashEvolucaoInstance) {
      chartDashEvolucaoInstance.destroy();
    }
    const canvasEvolucao = document.getElementById('chart-dash-evolucao');
    const ctxEvolucao = canvasEvolucao.getContext('2d');
    const labelsEvolucao = data.evolucao_diaria.map(item => {
      const partes = item.data.split('-');
      return `${partes[2]}/${partes[1]}`;
    });
    const producoes = data.evolucao_diaria.map(item => item.producao);
    const perdas = data.evolucao_diaria.map(item => item.perda);

    const prodGradient = ctxEvolucao.createLinearGradient(0, 0, 0, 300);
    prodGradient.addColorStop(0, hexToRgba('#3b82f6', 0.25));
    prodGradient.addColorStop(1, 'transparent');
    
    const lossGradient = ctxEvolucao.createLinearGradient(0, 0, 0, 300);
    lossGradient.addColorStop(0, hexToRgba('#ef4444', 0.20));
    lossGradient.addColorStop(1, 'transparent');

    chartDashEvolucaoInstance = new Chart(ctxEvolucao, {
      type: 'line',
      data: {
        labels: labelsEvolucao,
        datasets: [
          {
            label: 'Produção Real',
            data: producoes,
            borderColor: '#3b82f6',
            backgroundColor: prodGradient,
            borderWidth: 2,
            tension: 0.3,
            fill: true,
            pointRadius: 3
          },
          {
            label: 'Perdas (Desperdício)',
            data: perdas,
            borderColor: '#ef4444',
            backgroundColor: lossGradient,
            borderWidth: 2,
            tension: 0.3,
            fill: true,
            pointRadius: 3
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'top',
            labels: { color: colors.textColor, font: { family: 'DM Sans', size: 12 } }
          },
          tooltip: {
            mode: 'index',
            intersect: false,
            backgroundColor: colors.tooltipBg,
            titleColor: colors.tooltipText,
            bodyColor: colors.tooltipText,
            borderColor: colors.tooltipBorder,
            borderWidth: 1,
            padding: 10,
            boxPadding: 6,
            usePointStyle: true,
            titleFont: { family: 'DM Sans', size: 12, weight: '700' },
            bodyFont: { family: 'DM Sans', size: 11 }
          }
        },
        scales: {
          x: {
            grid: { color: colors.gridColor },
            ticks: { color: colors.textColor, font: { family: 'DM Sans', size: 11 } }
          },
          y: {
            grid: { color: colors.gridColor },
            ticks: { color: colors.textColor, font: { family: 'DM Sans', size: 11 } }
          }
        }
      }
    });

    if (chartDashPerdasTipoInstance) {
      chartDashPerdasTipoInstance.destroy();
    }
    const canvasPerdasTipo = document.getElementById('chart-dash-perdas-tipo');
    const ctxPerdasTipo = canvasPerdasTipo.getContext('2d');
    const labelsPerdasTipo = data.perdas_por_tipo.map(item => item.tipo_perda);
    const qtdsPerdasTipo = data.perdas_por_tipo.map(item => item.quantidade);

    const isLight = document.documentElement.getAttribute('data-theme') === 'light';

    chartDashPerdasTipoInstance = new Chart(ctxPerdasTipo, {
      type: 'doughnut',
      data: {
        labels: labelsPerdasTipo.length > 0 ? labelsPerdasTipo : ['Nenhuma perda registrada'],
        datasets: [{
          data: qtdsPerdasTipo.length > 0 ? qtdsPerdasTipo : [1],
          backgroundColor: qtdsPerdasTipo.length > 0
            ? ['#ef4444', '#f59e0b', '#3b82f6', '#10b981', '#a855f7', '#6b7280']
            : [colors.gridColor],
          borderWidth: 2,
          borderColor: isLight ? '#ffffff' : '#161920'
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '75%',
        plugins: {
          legend: {
            position: 'right',
            labels: { color: colors.textColor, font: { family: 'DM Sans', size: 11 } }
          },
          tooltip: {
            backgroundColor: colors.tooltipBg,
            titleColor: colors.tooltipText,
            bodyColor: colors.tooltipText,
            borderColor: colors.tooltipBorder,
            borderWidth: 1,
            padding: 10,
            boxPadding: 6,
            usePointStyle: true,
            titleFont: { family: 'DM Sans', size: 12, weight: '700' },
            bodyFont: { family: 'DM Sans', size: 11 }
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
            ${op.eh_lider
              ? `<div class="pill pill-info" style="font-size:11px">Líder · não concorre</div>`
              : op.elegivel
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
      <div class="card" style="border-left: 3px solid ${op.eh_lider ? 'var(--accent2)' : op.elegivel ? 'var(--success)' : 'var(--danger)'}">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
          <div style="font-family:var(--font-head);font-size:16px;font-weight:700">${op.colaborador}</div>
          ${op.eh_lider
            ? '<span class="pill pill-info">Líder · não concorre</span>'
            : op.elegivel
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
            <div style="font-family:var(--font-head);font-size:20px;font-weight:800;color:var(--muted)">${fmtNum(op.meta || META_GLOBAL)}</div>
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
              <strong>${item.colaborador_nome}</strong>
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
              <div style="font-size:11px; color:var(--muted)">${item.cliente_nome} &bull; Status: <span style="text-transform:capitalize">${item.status.replace('_', ' ')}</span></div>
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
    const cols = await api('/colaboradores/?contexto=producao');
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
    // Cards de resumo (a partir dos registros já carregados)
    const cardsEl = document.getElementById('prod-cards');
    if (cardsEl) {
      const totalProd = rows.reduce((s, r) => s + (+r.producao || 0), 0);
      const totalMeta = rows.reduce((s, r) => s + (+r.meta || 0), 0);
      const totalExc = rows.reduce((s, r) => s + (+r.excedente || 0), 0);
      const dias = new Set(rows.map(r => r.data)).size;
      cardsEl.innerHTML = `
        <div class="card">
          <div class="card-label">Total Produzido</div>
          <div class="card-value accent">${fmtNum(totalProd)}</div>
          <div class="card-sub">${mesLabel(mes)}</div>
        </div>
        <div class="card">
          <div class="card-label">Meta Acumulada</div>
          <div class="card-value info">${fmtNum(totalMeta)}</div>
          <div class="card-sub">no mês</div>
        </div>
        <div class="card">
          <div class="card-label">Excedente Acumulado</div>
          <div class="card-value ${totalExc >= 0 ? 'success' : 'negative'}">${totalExc >= 0 ? '+' : ''}${fmtNum(totalExc)}</div>
          <div class="card-sub">produção − meta</div>
        </div>
        <div class="card">
          <div class="card-label">Dias Trabalhados</div>
          <div class="card-value info">${dias}</div>
          <div class="card-sub">dias com produção</div>
        </div>`;
    }
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
          ${temPermissao('producao', 'editar') ? `<button class="btn btn-sm btn-secondary" onclick="editarProducao(${r.id}, ${r.colaborador_id}, ${r.maquina_id}, '${r.data}', ${r.meta}, ${r.producao}, ${r.produto_estoque_id || 'null'}, ${r.perda_quantidade || 0}, ${r.sobra_quantidade || 0}, '${r.pedido_numero || ''}')">✏️</button>` : ''}
          ${temPermissao('producao', 'deletar') ? `<button class="btn btn-sm btn-danger" onclick="deletarProducao(${r.id})">✕</button>` : ''}
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
let prodRevendaCache = [];
let revendaProdutos = [];
const TIPOS_PERDA_MOD = ['Quebra','Defeito','Contaminação','Mal formado','Rebarba','Fora de especificação','Outros'];

async function openModalProducao() {
  const [mqs, cols, prods, pedidos] = await Promise.all([
    api('/maquinas/'),
    api('/colaboradores/?contexto=producao'),
    api('/estoque/produtos').catch(()=>[]),
    api('/pedidos/').catch(()=>[])
  ]);
  // Revenda não é produzida: não aparece no registro de produção
  prodEstoqueCache = (prods || []).filter(p => p.categoria_tipo !== 'revenda');
  prodRevendaCache = (prods || []).filter(p => p.categoria_tipo === 'revenda');
  document.getElementById('prod-colaborador').innerHTML = cols.map(c => `<option value="${c.id}">${c.nome}</option>`).join('');
  document.getElementById('prod-maquina').innerHTML = mqs.filter(m=>m.ativa).map(m => `<option value="${m.id}">${m.nome}</option>`).join('');
  document.getElementById('prod-data').value = new Date().toISOString().split('T')[0];
  document.getElementById('prod-meta').value = META_GLOBAL;
  aplicarTravaMetaProd();
  document.getElementById('prod-edit-id').value = '';
  document.getElementById('prod-pedido-manual').value = '';
  document.getElementById('prod-pedido').innerHTML = '<option value="">— Sem pedido vinculado —</option>' +
    pedidos.filter(p => p.status !== 'entregue').map(p => `<option value="${p.id}">${p.numero_pedido} — ${p.cliente_nome}</option>`).join('');
  document.getElementById('modal-prod-title').textContent = 'Registrar Produção';
  document.getElementById('prod-save-btn').textContent = 'Salvar';

  // Modo de lançamento definido pelo Controle de Acesso (por perfil), não escolha do usuário.
  const toggleContainer = document.getElementById('prod-toggle-container');
  if (toggleContainer) toggleContainer.style.display = 'none';

  const checkbox = document.getElementById('prod-toggle-simplificado');
  if (checkbox) {
    checkbox.checked = modoSimplificadoPerfil;
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

function findBestStockMatch(desc, stockProducts) {
  if (!desc || !stockProducts || stockProducts.length === 0) return null;
  
  const cleanDesc = desc.toUpperCase();
  
  // 1. Tentar match exato normalizado
  const normDesc = cleanDesc.replace(/[^A-Z0-9]/g, '').replace(/ML$/, 'M');
  const exact = stockProducts.find(p => {
    const normP = p.nome.toUpperCase().replace(/[^A-Z0-9]/g, '').replace(/ML$/, 'M');
    return normP === normDesc;
  });
  if (exact) return exact.id;
  
  // 2. Token match para descrições com grafias diferentes
  const numbers = cleanDesc.match(/\d+/g) || [];
  
  let bestMatch = null;
  let bestScore = 0;
  
  for (const prod of stockProducts) {
    const cleanProd = prod.nome.toUpperCase();
    
    // Todos os números da descrição devem estar no nome do produto
    let hasAllNumbers = true;
    for (const num of numbers) {
      if (!cleanProd.includes(num)) {
        hasAllNumbers = false;
        break;
      }
    }
    if (!hasAllNumbers && numbers.length > 0) continue;
    
    let score = 0;
    
    // Dar peso para marca/característica
    if (cleanDesc.includes("CRISTAL") && (cleanProd.includes("CRISTAL") || cleanProd.includes("CTL"))) score += 6;
    if (cleanDesc.includes("COPO") && cleanProd.includes("COPO")) score += 2;
    if (cleanDesc.includes("PP") && cleanProd.includes("PP")) score += 2;
    if (cleanDesc.includes("TAMPA") && cleanProd.includes("TAMPA")) score += 3;
    
    // Match de substring normalizada
    const normP = cleanProd.replace(/[^A-Z0-9]/g, '');
    const normD = cleanDesc.replace(/[^A-Z0-9]/g, '');
    if (normP.includes(normD) || normD.includes(normP)) {
      score += 10;
    }
    
    if (score > bestScore) {
      bestScore = score;
      bestMatch = prod;
    }
  }
  
  return bestMatch && bestScore >= 3 ? bestMatch.id : null;
}

function _itemEhRevenda(i) {
  if (!i) return false;
  if (i.produto_id && prodRevendaCache.some(p => p.id === i.produto_id)) return true;
  if (!i.produto_id && i.descricao && findBestStockMatch(i.descricao, prodRevendaCache)) return true;
  return false;
}

async function buscarPedidoManual() {
  const inp = document.getElementById('prod-pedido-manual');
  const sel = document.getElementById('prod-pedido');
  const aviso = document.getElementById('prod-pedido-aviso');
  const num = ((inp && inp.value) || '').trim();
  if (aviso) { aviso.textContent = ''; }
  if (!num) { if (sel) sel.value = ''; return; }
  try {
    const lista = await api('/pedidos/');
    const achado = (lista || []).find(p => String(p.numero_pedido).trim() === num);
    if (achado) {
      if (sel.value === String(achado.id)) {
        if (aviso) { aviso.textContent = '✔ Pedido de ' + achado.cliente_nome; aviso.style.color = '#46d369'; }
        return;
      }
      if (![...sel.options].some(o => o.value === String(achado.id))) {
        const opt = document.createElement('option');
        opt.value = achado.id;
        opt.textContent = achado.numero_pedido + ' — ' + achado.cliente_nome;
        sel.appendChild(opt);
      }
      sel.value = String(achado.id);
      await onProdPedidoChange();
      if (aviso) { aviso.textContent = '✔ Pedido de ' + achado.cliente_nome; aviso.style.color = '#46d369'; }
    } else {
      if (sel) sel.value = '';
      if (aviso) { aviso.textContent = 'Pedido não encontrado — será salvo como número avulso'; aviso.style.color = 'var(--muted, #8b92a3)'; }
    }
  } catch (e) { if (aviso) aviso.textContent = ''; }
}

async function onProdPedidoChange() {
  const pedId = document.getElementById('prod-pedido').value;
  if (!pedId) {
    prodItens = [{ produto_id: null, producao: 0, perda: 0, sobra: 0, tipo_perda: 'Quebra' }];
    document.getElementById('prod-pedido-manual').value = '';
    renderProdItens();
    atualizarTotalProd();
    return;
  }
  
  try {
    const p = await api('/pedidos/' + pedId);
    
    // Auto-preencher o número manual para compatibilidade de visualização
    document.getElementById('prod-pedido-manual').value = p.numero_pedido;
    
    // Itens de revenda não são produzidos — não entram em "Produtos Produzidos"
    const itensProducao = (p.itens || []).filter(i => !_itemEhRevenda(i));
    // Mapear os itens (de produção) do pedido para prodItens
    prodItens = itensProducao.map(i => {
      const matchedProdId = i.produto_id || findBestStockMatch(i.descricao, prodEstoqueCache);
      
      const jaConcluido = (i.qtd_produzida || 0) >= i.quantidade || i.status === 'produzido' || i.status === 'entregue';
      
      return {
        pedido_item_id: i.id,
        pedido_item_desc: i.descricao,
        pedido_item_total: i.quantidade,
        pedido_item_atual: i.qtd_produzida || 0,
        produto_id: matchedProdId,
        producao: 0, // Inicia em 0 produzido hoje
        perda: 0,
        sobra: 0,
        tipo_perda: 'Quebra',
        concluido: jaConcluido
      };
    });
    
    if (!prodItens.length) prodItens = [{ produto_id: null, producao: 0, perda: 0, sobra: 0, tipo_perda: 'Quebra' }];

    renderProdItens();
    atualizarTotalProd();
  } catch (e) {
    showAlert('Erro ao buscar itens do pedido: ' + e.message, 'danger');
  }
}
window.onProdPedidoChange = onProdPedidoChange;

function toggleItemConcluido(idx, checked) {
  const item = prodItens[idx];
  if (checked) {
    const restante = Math.max(0, item.pedido_item_total - item.pedido_item_atual);
    item.producao = restante;
  } else {
    item.producao = 0;
  }
  
  const input = document.getElementById(`input-producao-${idx}`);
  if (input) input.value = item.producao || '';
  
  atualizarTotalProd();
}
window.toggleItemConcluido = toggleItemConcluido;

function renderProdItens() {
  const el = document.getElementById('prod-itens-list');
  if (!el) return;
  
  el.innerHTML = prodItens.map((item, idx) => {
    let productFieldHtml = '';
    if (item.pedido_item_id) {
      productFieldHtml = `
        <div class="prod-field-col prod-field-produto" style="min-width:0; display:flex; flex-direction:column; gap:4px; min-height:38px;">
          <div style="display:flex; align-items:center; gap:8px;">
            <input type="checkbox" id="chk-item-${idx}" ${item.concluido ? 'checked disabled' : ''} onchange="toggleItemConcluido(${idx}, this.checked)" style="width:16px; height:16px; accent-color:var(--accent); cursor:pointer">
            <div style="min-width:0; flex:1">
              <label for="chk-item-${idx}" style="cursor:pointer; font-weight:600; color:var(--text); display:block; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; font-size:13px; margin:0;" title="${item.pedido_item_desc}">
                ${item.pedido_item_desc}
              </label>
              <span style="color:var(--muted); font-size:11px; display:block; margin-top:1px;">
                Produzido: ${fmtNum(item.pedido_item_atual)} de ${fmtNum(item.pedido_item_total)} ${item.concluido ? '<strong style="color:var(--success)">[Concluído]</strong>' : ''}
              </span>
            </div>
          </div>
          <select onchange="prodItens[${idx}].produto_id=+this.value||null" ${item.concluido ? 'disabled' : ''} style="font-size:11px;padding:4px 6px;width:100%;min-width:0;margin-top:4px;">
            <option value="">— Sem baixar estoque (Não vinculado) —</option>
            ${prodEstoqueCache.map(p => `<option value="${p.id}" ${item.produto_id===p.id?'selected':''}>${_produtoLabel(p)} (${fmtNum(p.quantidade_atual)} ${p.unidade})</option>`).join('')}
          </select>
        </div>
      `;
    } else {
      productFieldHtml = `
        <div class="prod-field-col prod-field-produto" style="min-width:0">
          <label class="prod-field-label">Produto do Estoque</label>
          <select onchange="prodItens[${idx}].produto_id=+this.value||null" ${item.concluido ? 'disabled' : ''} style="font-size:13px;padding:8px 10px;width:100%;min-width:0">
            <option value="">— Sem produto —</option>
            ${prodEstoqueCache.map(p => `<option value="${p.id}" ${item.produto_id===p.id?'selected':''}>${_produtoLabel(p)} (${fmtNum(p.quantidade_atual)} ${p.unidade})</option>`).join('')}
          </select>
        </div>
      `;
    }

    let rowStyle = 'display:grid; grid-template-columns: 2.5fr 70px 70px 70px 1fr 28px; gap:6px; align-items:flex-end; margin-bottom:10px; border-bottom:1px solid rgba(255,255,255,0.05); padding-bottom:10px;';
    if (item.concluido) {
      rowStyle += ' opacity: 0.55; pointer-events: none; background: rgba(255,255,255,0.01); border-radius: 4px; padding: 4px;';
    }

    const isDeleteDisabled = item.concluido || item.pedido_item_id;

    return `
      <div class="prod-item-row" style="${rowStyle}">
        ${productFieldHtml}
        <div class="prod-field-col prod-field-producao" style="min-width:0">
          <label class="prod-field-label">Produção</label>
          <input type="number" id="input-producao-${idx}" value="${item.producao||''}" min="0" placeholder="0"
                 oninput="prodItens[${idx}].producao=+this.value; const restante = Math.max(0, prodItens[${idx}].pedido_item_total - prodItens[${idx}].pedido_item_atual); const chk = document.getElementById('chk-item-${idx}'); if (chk) { chk.checked = (+this.value === restante && restante > 0); }; atualizarTotalProd()"
                 ${item.concluido ? 'disabled' : ''}
                 style="font-size:12px;text-align:center;padding:6px 2px;width:100%;min-width:0">
        </div>
        <div class="prod-field-col prod-field-perda" style="min-width:0">
          <label class="prod-field-label">Perda</label>
          <input type="number" value="${item.perda||''}" min="0" placeholder="0"
                 oninput="prodItens[${idx}].perda=+this.value"
                 ${item.concluido ? 'disabled' : ''}
                 style="font-size:13px;text-align:center;padding:8px 4px;border-color:rgba(239,68,68,.35);width:100%;min-width:0">
        </div>
        <div class="prod-field-col prod-field-sobra" style="min-width:0">
          <label class="prod-field-label">Sobra</label>
          <input type="number" value="${item.sobra||''}" min="0" placeholder="0"
                 oninput="prodItens[${idx}].sobra=+this.value"
                 ${item.concluido ? 'disabled' : ''}
                 style="font-size:13px;text-align:center;padding:8px 4px;border-color:rgba(16,185,129,.35);width:100%;min-width:0">
        </div>
        <div class="prod-field-col prod-field-tipoperda" style="min-width:0">
          <label class="prod-field-label">Tipo Perda</label>
          <select onchange="prodItens[${idx}].tipo_perda=this.value" ${item.concluido ? 'disabled' : ''} style="font-size:12px;padding:8px 4px;width:100%;min-width:0">
            ${TIPOS_PERDA_MOD.map(t => `<option value="${t}" ${item.tipo_perda===t?'selected':''}>${t}</option>`).join('')}
          </select>
        </div>
        <div class="prod-field-col prod-field-acoes" style="min-width:0">
          <button class="btn btn-sm btn-danger" onclick="removeProdItem(${idx})" ${isDeleteDisabled?'disabled':''} style="padding:6px 8px;width:100%">✕</button>
        </div>
      </div>
    `;
  }).join('');
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

function aplicarTravaMetaProd() {
  const el = document.getElementById('prod-meta');
  if (!el) return;
  const isGestor = (window.usuarioLogado && window.usuarioLogado.role === 'gestor');
  el.readOnly = !isGestor;
  el.style.opacity = isGestor ? '' : '0.6';
  el.style.cursor = isGestor ? '' : 'not-allowed';
  el.title = isGestor ? '' : 'Meta global definida pelo gestor — nao editavel';
}
async function editarProducao(id, colId, maqId, data, meta, producao, produtoEstoqueId = null, perdaQtd = 0, sobraQtd = 0, pedidoNumero = '') {
  await openModalProducao();
  document.getElementById('prod-edit-id').value = id;
  document.getElementById('prod-colaborador').value = colId;
  document.getElementById('prod-maquina').value = maqId;
  document.getElementById('prod-data').value = data;
  document.getElementById('prod-meta').value = meta;
  aplicarTravaMetaProd();
  document.getElementById('prod-pedido-manual').value = pedidoNumero || '';
  document.getElementById('modal-prod-title').textContent = 'Editar Produção';
  document.getElementById('prod-save-btn').textContent = 'Atualizar';

  const isSimplificado = !produtoEstoqueId;
  const toggleContainerEdit = document.getElementById('prod-toggle-container');
  if (toggleContainerEdit) toggleContainerEdit.style.display = 'none';
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
      const itensValidos = prodItens.filter(i => (i.producao || 0) > 0 || (i.perda || 0) > 0 || (i.sobra || 0) > 0);
      if (!itensValidos.length) { showAlert('Informe pelo menos um item com produção ou perda', 'danger'); return; }

      const colNome = document.getElementById('prod-colaborador').selectedOptions[0]?.text || 'Operador';
      let res;

      if (itensValidos.length === 1) {
        // Apenas um item válido: o backend desconta do estoque de forma automática e registra a perda/sobra
        const primItem = itensValidos[0];
        res = await api('/producao/', 'POST', {
          colaborador_id: colId, maquina_id: maqId, data, meta,
          producao: totalProducao,
          produto_estoque_id: primItem.produto_id,
          perda_quantidade: primItem.perda || 0,
          perda_tipo: primItem.tipo_perda,
          sobra_quantidade: primItem.sobra || 0,
          pedido_numero: pedidoManual || null
        });
      } else {
        // Múltiplos produtos válidos:
        // 1. Registra a produção diária principal sem vincular a um produto estoque
        // (evitando que o backend dê baixa da soma total em um único produto)
        res = await api('/producao/', 'POST', {
          colaborador_id: colId, maquina_id: maqId, data, meta,
          producao: totalProducao,
          produto_estoque_id: null,
          perda_quantidade: 0,
          sobra_quantidade: 0,
          pedido_numero: pedidoManual || null
        });

        // 2. Faz as baixas/movimentações manuais no estoque para TODOS os itens válidos
        for (const item of itensValidos) {
          if (item.produto_id) {
            try {
              if (item.producao > 0) {
                await api('/estoque/movimentacoes', 'POST', {
                  produto_id: item.produto_id,
                  tipo: 'saida',
                  quantidade: item.producao,
                  motivo: 'Produção diária automática — Pedido ' + (pedidoManual || ''),
                  responsavel: colNome,
                  data
                });
              }
              if (item.perda > 0) {
                await api('/estoque/movimentacoes', 'POST', {
                  produto_id: item.produto_id,
                  tipo: 'perda',
                  quantidade: item.perda,
                  motivo: 'Perda na produção — Pedido ' + (pedidoManual || ''),
                  tipo_perda: item.tipo_perda || 'Quebra',
                  responsavel: colNome,
                  data
                });
              }
              if (item.sobra > 0) {
                await api('/estoque/movimentacoes', 'POST', {
                  produto_id: item.produto_id,
                  tipo: 'sobra',
                  quantidade: item.sobra,
                  motivo: 'Sobra de produção — Pedido ' + (pedidoManual || ''),
                  responsavel: colNome,
                  data
                });
              }
            } catch (err) {
              console.error('Erro ao processar movimentações de estoque para o produto ID ' + item.produto_id, err);
            }
          }
        }
      }

      // Atualizar o progresso de produção dos itens do pedido associado
      for (const item of itensValidos) {
        if (item.pedido_item_id && (item.producao > 0 || item.concluido)) {
          try {
            const novaQtd = item.pedido_item_atual + (item.producao || 0);
            let novoStatus = 'aberto';
            if (novaQtd >= item.pedido_item_total || item.concluido) {
              novoStatus = 'produzido';
            } else if (novaQtd > 0) {
              novoStatus = 'em_producao';
            }
            await api('/pedidos/itens/' + item.pedido_item_id + '/status', 'PUT', {
              status: novoStatus,
              qtd_produzida: Math.min(item.pedido_item_total, novaQtd),
              split_if_partial: true
            });
          } catch (err) {
            console.error('Erro ao atualizar status do item do pedido:', err);
          }
        }
      }

      showAlert('Produção registrada! Total: ' + fmtNum(totalProducao) + ' peças');
    }
    closeModal('modal-producao');
    // Atualizar seletor de mês para o mês do registro salvo
    const mesEl = document.getElementById('prod-mes');
    if (mesEl) mesEl.value = data.slice(0, 7);
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

    // Cálculos para o Painel de Análise
    const concorrentes = ops.filter(op => !op.eh_lider);
    const elegiveis = concorrentes.filter(op => op.elegivel);
    const totalPremioOps = elegiveis.reduce((sum, op) => sum + (op.valor_premio || 0), 0);
    const totalPremioAuxs = auxs.reduce((sum, a) => sum + (a.valor_bonus || 0), 0);
    const totalPremios = totalPremioOps + totalPremioAuxs;
    
    const pctMeta = concorrentes.length > 0 ? Math.round((elegiveis.length / concorrentes.length) * 100) : 0;
    const melhorOp = ops.length > 0 ? ops[0] : null;
    const mediaSetor = concorrentes.length > 0 ? Math.round(concorrentes.reduce((sum, op) => sum + (op.media_diaria || 0), 0) / concorrentes.length) : 0;

    const insightsEl = document.getElementById('prem-insights-cards');
    if (insightsEl) {
      insightsEl.innerHTML = `
        <div class="card" style="border-left: 3px solid var(--accent)">
          <div class="card-label">Total em Prêmios</div>
          <div class="card-value accent">${fmtBRL(totalPremios)}</div>
          <div style="font-size:11px;color:var(--muted)">${fmtBRL(totalPremioOps)} Op. | ${fmtBRL(totalPremioAuxs)} Aux.</div>
        </div>
        <div class="card" style="border-left: 3px solid var(--success)">
          <div class="card-label">Aderência à Meta</div>
          <div class="card-value success">${pctMeta}%</div>
          <div style="font-size:11px;color:var(--muted)">${elegiveis.length} de ${concorrentes.length} operadores atingiram a meta</div>
        </div>
        <div class="card" style="border-left: 3px solid var(--accent2)">
          <div class="card-label">Média do Setor</div>
          <div class="card-value info">${fmtNum(mediaSetor)}</div>
          <div style="font-size:11px;color:var(--muted)">peças/dia por operador</div>
        </div>
        <div class="card" style="border-left: 3px solid var(--success)">
          <div class="card-label">Destaque Operador</div>
          <div class="card-value success" style="font-size:18px; line-height: 1.4">${melhorOp ? melhorOp.colaborador : '—'}</div>
          <div style="font-size:11px;color:var(--muted)">${melhorOp ? `${fmtNum(melhorOp.total_producao)} peças no mês` : 'Nenhum lançamento'}</div>
        </div>
      `;
    }

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
            ${op.eh_lider
              ? `<span class="pill pill-info" style="font-size:11px">Líder · não concorre</span>`
              : op.elegivel
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
            ${temPermissao('premiacao', 'deletar') ? `<button class="btn btn-sm btn-danger" onclick="removerAuxiliar(${a.id})" style="margin-top:4px">✕</button>` : ''}
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
    <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;padding:8px 10px;border:1px solid var(--border);border-radius:8px;margin-bottom:6px;flex-wrap:wrap">
      <span class="pill ${pillTipoColaborador(t.nome)}">${formatTipoColaborador(t.nome)}</span>
      <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">
        <label style="display:flex;align-items:center;gap:5px;font-size:12px;color:var(--muted);cursor:pointer">
          <input type="checkbox" ${t.aparece_producao ? 'checked' : ''} onchange="toggleFlagTipo(${t.id},'aparece_producao',this.checked)"> Aparece na Produção
        </label>
        <label style="display:flex;align-items:center;gap:5px;font-size:12px;color:var(--muted);cursor:pointer">
          <input type="checkbox" ${t.concorre_premio ? 'checked' : ''} onchange="toggleFlagTipo(${t.id},'concorre_premio',this.checked)"> Concorre ao prêmio
        </label>
        ${['operador','auxiliar'].includes(t.nome) ? '' : (temPermissao('colaboradores', 'deletar') ? `<button class="btn btn-sm btn-danger" style="padding:2px 8px" onclick="deletarTipoColaborador(${t.id})">×</button>` : '')}
      </div>
    </div>
  `).join('') : '<span style="color:var(--muted)">Nenhum tipo cadastrado</span>';
}

async function toggleFlagTipo(id, campo, valor) {
  try {
    await api('/colaboradores/tipos/' + id + '/flags', 'PUT', { [campo]: valor ? 1 : 0 });
    showAlert('Configuração atualizada');
  } catch (e) {
    showAlert('Erro ao atualizar: ' + e.message, 'danger');
    renderTiposColaborador();
  }
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
        ${temPermissao('colaboradores', 'editar') ? `<button class="btn btn-sm btn-secondary" onclick="editColaborador(${c.id})">Editar</button>` : ''}
        ${temPermissao('colaboradores', 'deletar') ? `<button class="btn btn-sm btn-danger" onclick="deletarColaborador(${c.id})">Remover</button>` : ''}
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
        ${temPermissao('maquinas', 'editar') ? `<button class="btn btn-sm btn-secondary" onclick="editMaquina(${m.id})">Editar</button>` : ''}
        ${temPermissao('maquinas', 'deletar') ? `<button class="btn btn-sm btn-danger" onclick="deletarMaquina(${m.id})">Desativar</button>` : ''}
      </td>
    </tr>
  `).join('');
}

async function openModalMaquina() {
  document.getElementById('maq-id').value = '';
  document.getElementById('maq-nome').value = '';
  document.getElementById('maq-setor').value = '';
  document.getElementById('maq-meta').value = META_GLOBAL;
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
  const anaIniEl = document.getElementById('rel-ana-mes-ini');
  const anaFimEl = document.getElementById('rel-ana-mes-fim');
  if (mesIniEl && !mesIniEl.value) mesIniEl.value = mes;
  if (mesFimEl && !mesFimEl.value) mesFimEl.value = mes;
  if (premEl && !premEl.value) premEl.value = mes;
  if (anaIniEl && !anaIniEl.value) anaIniEl.value = mes;
  if (anaFimEl && !anaFimEl.value) anaFimEl.value = mes;
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

async function loadRelAnaliticos() {
  const mesIni = document.getElementById('rel-ana-mes-ini')?.value || new Date().toISOString().slice(0,7);
  const mesFim = document.getElementById('rel-ana-mes-fim')?.value || '';
  const tipoAna = document.getElementById('rel-ana-tipo')?.value || 'rendimento';
  
  let endpoint = '';
  if (tipoAna === 'rendimento') {
    endpoint = '/relatorios/rendimento-insumos?';
  } else if (tipoAna === 'evolucao') {
    endpoint = '/relatorios/evolucao-mensal?';
  } else if (tipoAna === 'ranking') {
    endpoint = '/relatorios/ranking-historico?';
  }
  
  if (mesIni) endpoint += 'mes_ini=' + mesIni;
  if (mesFim) endpoint += '&mes_fim=' + mesFim;
  
  try {
    const data = await api(endpoint);
    const titleEl = document.getElementById('rel-ana-title');
    const thead = document.getElementById('rel-ana-thead');
    const tbody = document.getElementById('rel-ana-tbody');
    const cardsEl = document.getElementById('rel-ana-cards');
    
    if (!tbody || !thead) return;
    
    if (tipoAna === 'rendimento') {
      if (titleEl) titleEl.textContent = 'Rendimento e Perdas de Insumos';
      thead.innerHTML = `
        <tr>
          <th>Código/ID</th>
          <th>Produto/Insumo</th>
          <th>Unidade</th>
          <th>Produção Real</th>
          <th>Perda Física</th>
          <th>Sobra</th>
          <th>Consumo Total</th>
          <th>Índice de Perda (%)</th>
          <th>Custo Médio</th>
          <th>Custo Desperdiçado</th>
        </tr>
      `;
      
      if (!data.length) {
        tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;color:var(--muted);padding:24px">Nenhum registro</td></tr>';
        if (cardsEl) cardsEl.innerHTML = `
          <div class="card"><div class="card-label">Total Produzido</div><div class="card-value info">0</div></div>
          <div class="card"><div class="card-label">Total Perdas</div><div class="card-value danger">0</div></div>
          <div class="card"><div class="card-label">Custo do Desperdício</div><div class="card-value danger">${fmtBRL(0)}</div></div>
        `;
        return;
      }
      
      const totalProduzido = data.reduce((s, r) => s + (r.total_produzido || 0), 0);
      const totalPerda = data.reduce((s, r) => s + (r.total_perda || 0), 0);
      const totalDesperdicio = data.reduce((s, r) => s + (r.custo_total_perda || 0), 0);
      
      if (cardsEl) cardsEl.innerHTML = `
        <div class="card"><div class="card-label">Total Produzido</div><div class="card-value info">${fmtNum(totalProduzido)}</div></div>
        <div class="card"><div class="card-label">Total Perdas</div><div class="card-value danger">${fmtNum(totalPerda)}</div></div>
        <div class="card"><div class="card-label">Custo do Desperdício</div><div class="card-value danger">${fmtBRL(totalDesperdicio)}</div></div>
      `;
      
      tbody.innerHTML = data.map(r => {
        const prod = r.total_produzido || 0;
        const perda = r.total_perda || 0;
        const sobra = r.total_sobra || 0;
        const consumo = r.total_consumido || 0;
        const idxPerda = r.indice_perda || 0;
        const custoMed = r.custo_medio || 0;
        const custoTotalPerda = r.custo_total_perda || 0;
        const unidade = r.unidade || '';
        
        return `<tr>
          <td>${r.produto_codigo ? `<strong>${r.produto_codigo}</strong>` : `ID: ${r.produto_id}`}</td>
          <td>${r.produto_nome}</td>
          <td>${unidade}</td>
          <td>${fmtNum(prod)}</td>
          <td class="danger">${fmtNum(perda)}</td>
          <td class="positive">${fmtNum(sobra)}</td>
          <td><strong>${fmtNum(consumo)}</strong></td>
          <td style="color:${idxPerda > 0 ? 'var(--danger)' : 'inherit'};font-weight:${idxPerda > 0 ? 'bold' : 'normal'}">${fmtNum(idxPerda)}%</td>
          <td>${fmtBRL(custoMed)}</td>
          <td class="danger" style="font-weight:bold">${fmtBRL(custoTotalPerda)}</td>
        </tr>`;
      }).join('');
      
    } else if (tipoAna === 'evolucao') {
      if (titleEl) titleEl.textContent = 'Evolução Mensal da Produção';
      thead.innerHTML = `
        <tr>
          <th>Mês</th>
          <th>Colaborador</th>
          <th>Dias Trabalhados</th>
          <th>Produção Total</th>
          <th>Média Diária</th>
          <th>Meta Média</th>
          <th>Excedente Acumulado</th>
          <th>Total Perdas</th>
          <th>Total Sobras</th>
        </tr>
      `;
      
      if (!data.length) {
        tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--muted);padding:24px">Nenhum registro</td></tr>';
        if (cardsEl) cardsEl.innerHTML = `
          <div class="card"><div class="card-label">Total Produzido</div><div class="card-value info">0</div></div>
          <div class="card"><div class="card-label">Dias Trabalhados</div><div class="card-value info">0</div></div>
          <div class="card"><div class="card-label">Total Perdas</div><div class="card-value danger">0</div></div>
        `;
        return;
      }
      
      const totalProduzido = data.reduce((s, r) => s + (r.total_producao || 0), 0);
      const totalPerda = data.reduce((s, r) => s + (r.total_perdas || 0), 0);
      const totalDias = data.reduce((s, r) => s + (r.dias_trabalhados || 0), 0);
      
      if (cardsEl) cardsEl.innerHTML = `
        <div class="card"><div class="card-label">Total Produzido</div><div class="card-value info">${fmtNum(totalProduzido)}</div></div>
        <div class="card"><div class="card-label">Lançamentos / Dias</div><div class="card-value info">${fmtNum(totalDias)}</div></div>
        <div class="card"><div class="card-label">Total Perdas</div><div class="card-value danger">${fmtNum(totalPerda)}</div></div>
      `;
      
      tbody.innerHTML = data.map(r => {
        const mes = r.mes_referencia;
        const col = r.colaborador;
        const dias = r.dias_trabalhados || 0;
        const prod = r.total_producao || 0;
        const med = r.media_diaria || 0;
        const meta = r.meta_media || 0;
        const exc = r.excedente_total || 0;
        const per = r.total_perdas || 0;
        const sob = r.total_sobras || 0;
        
        return `<tr>
          <td><strong>${mesLabel(mes)}</strong></td>
          <td><strong>${col}</strong></td>
          <td>${fmtNum(dias)}</td>
          <td>${fmtNum(prod)}</td>
          <td>${fmtNum(Math.round(med))}</td>
          <td>${fmtNum(Math.round(meta))}</td>
          <td class="${exc>=0?'positive':'negative'}">${exc>=0?'+':''}${fmtNum(Math.round(exc))}</td>
          <td class="danger">${per>0?fmtNum(per):'—'}</td>
          <td class="positive">${sob>0?fmtNum(sob):'—'}</td>
        </tr>`;
      }).join('');
      
    } else if (tipoAna === 'ranking') {
      if (titleEl) titleEl.textContent = 'Ranking Histórico de Operadores';
      thead.innerHTML = `
        <tr>
          <th>Operador</th>
          <th>Meses Ativos</th>
          <th>Total Produzido</th>
          <th>Média Geral</th>
          <th>Média da Meta</th>
          <th>Saldo Excedente</th>
          <th>Aderência à Meta</th>
          <th>Total Perdas</th>
          <th>Total Sobras</th>
          <th>Melhor Dia</th>
        </tr>
      `;
      
      if (!data.length) {
        tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;color:var(--muted);padding:24px">Nenhum registro</td></tr>';
        if (cardsEl) cardsEl.innerHTML = `
          <div class="card"><div class="card-label">Melhor Operador</div><div class="card-value success">—</div></div>
          <div class="card"><div class="card-label">Melhor Média</div><div class="card-value info">0</div></div>
          <div class="card"><div class="card-label">Total Geral</div><div class="card-value info">0</div></div>
        `;
        return;
      }
      
      const melhorOp = data[0]?.colaborador || '—';
      const melhorMed = data[0]?.media_geral || 0;
      const totalGeral = data.reduce((s, r) => s + (r.total_geral || 0), 0);
      
      if (cardsEl) cardsEl.innerHTML = `
        <div class="card" style="border-left:3px solid var(--success)"><div class="card-label">Melhor Operador</div><div class="card-value success" style="font-size:18px">${melhorOp}</div></div>
        <div class="card" style="border-left:3px solid var(--accent)"><div class="card-label">Melhor Média Geral</div><div class="card-value info">${fmtNum(Math.round(melhorMed))} pçs/dia</div></div>
        <div class="card" style="border-left:3px solid var(--accent2)"><div class="card-label">Total Geral Produzido</div><div class="card-value info">${fmtNum(totalGeral)}</div></div>
      `;
      
      tbody.innerHTML = data.map(r => {
        const col = r.colaborador;
        const meses = r.meses_trabalhados || 0;
        const total = r.total_geral || 0;
        const med = r.media_geral || 0;
        const meta = r.media_meta || 0;
        const exc = r.saldo_excedente || 0;
        const pct = r.pct_acima_meta || 0;
        const per = r.total_perdas || 0;
        const sob = r.total_sobras || 0;
        const melhor = r.melhor_dia || 0;
        
        return `<tr>
          <td><strong>${col}</strong></td>
          <td>${fmtNum(meses)}</td>
          <td><strong>${fmtNum(total)}</strong></td>
          <td>${fmtNum(Math.round(med))}</td>
          <td>${fmtNum(Math.round(meta))}</td>
          <td class="${exc>=0?'positive':'negative'}">${exc>=0?'+':''}${fmtNum(Math.round(exc))}</td>
          <td style="font-weight:bold;color:${pct>=80?'var(--success)':pct>=50?'var(--warn)':'var(--danger)'}">${fmtNum(pct)}%</td>
          <td class="danger">${per>0?fmtNum(per):'—'}</td>
          <td class="positive">${sob>0?fmtNum(sob):'—'}</td>
          <td class="positive"><strong>${fmtNum(melhor)}</strong></td>
        </tr>`;
      }).join('');
    }
  } catch (err) {
    showAlert('Erro ao carregar relatório analítico: ' + err.message, 'danger');
  }
}

function onChangeRelAnaTipo() {
  loadRelAnaliticos();
}

window.onChangeRelAnaTipo = onChangeRelAnaTipo;
window.loadRelAnaliticos = loadRelAnaliticos;


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
  ['producao','premiacao','estoque','pedidos','epi','analiticos'].forEach(t=>{
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
  if(tab==='analiticos') loadRelAnaliticos();
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
      <tbody>${ops.map((r,i)=>`<tr><td><strong>${i+1}º</strong></td><td>${r.colaborador}</td><td>${fmtNum(r.total_producao)}</td><td>${fmtNum(Math.round(r.media_diaria||0))}</td><td>${r.dias_trabalhados}</td><td><span class="pill ${r.eh_lider?'pill-info':(r.elegivel?'pill-success':'pill-danger')}">${r.eh_lider?'Líder':(r.elegivel?'✓':'✕')}</span></td><td>${fmtBRL(r.valor_premio)}</td></tr>`).join('')}</tbody>
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
    return `<tr><td><strong>${p.numero_pedido}</strong></td><td>${p.cliente_nome}</td><td>${p.vendedor || '—'}</td><td>${fmtDate(p.prazo_entrega)}</td><td style="color:${cor};font-weight:700">${dias<0?'Vencido':dias+'d'}</td><td>${p.itens_entregues}/${p.total_itens}</td><td><span class="pill ${SP[p.status]}">${SL[p.status]}</span></td></tr>`;
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

function _getEmpresaHeader(titulo) {
  const emp = window.empresaDados || {};
  const nome = emp.nome || 'PRATIC';
  const cnpj = emp.cnpj ? `CNPJ: ${emp.cnpj}` : '';
  const telefone = emp.telefone ? `Tel: ${emp.telefone}` : '';
  const email = emp.email ? `E-mail: ${emp.email}` : '';
  
  let endereco = '';
  if (emp.logradouro) {
    endereco = `${emp.logradouro}`;
    if (emp.numero) endereco += `, ${emp.numero}`;
    if (emp.complemento) endereco += ` - ${emp.complemento}`;
    if (emp.bairro) endereco += `, ${emp.bairro}`;
    if (emp.cep) endereco += ` - CEP: ${emp.cep}`;
    if (emp.cidade) {
      endereco += `, ${emp.cidade}`;
      if (emp.uf) endereco += `/${emp.uf.toUpperCase()}`;
    }
  }

  const logoHtml = emp.logo 
    ? `<img src="${emp.logo}" style="max-height: 70px; max-width: 200px; object-fit: contain; margin-right: 15px;">` 
    : '';

  const infoContato = [cnpj, telefone, email].filter(Boolean).join(' | ');

  return `
    <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 2px solid #333; padding-bottom: 12px; margin-bottom: 20px; font-family: sans-serif; color: #111;">
      <div style="display: flex; align-items: center;">
        ${logoHtml}
        <div>
          <div style="font-size: 20px; font-weight: bold; text-transform: uppercase;">${nome}</div>
          <div style="font-size: 11px; color: #555; margin-top: 4px;">${infoContato}</div>
          ${endereco ? `<div style="font-size: 11px; color: #555; margin-top: 2px;">${endereco}</div>` : ''}
        </div>
      </div>
      <div style="text-align: right;">
        <div style="font-size: 18px; font-weight: bold; color: #333;">${titulo}</div>
      </div>
    </div>
  `;
}

function _getPrintFooter() {
  return `
    <div class="print-footer">
      <span>Emitido em: ${new Date().toLocaleString('pt-BR')}</span>
      <span>Página <span class="page-number"></span></span>
    </div>
  `;
}

async function exportarRelatorio(tipo, formato) {
  if (formato==='pdf') {
    const maps={producao:'rel-prod-tbody',premiacao:'rel-prem-content',estoque:'rel-est-tbody',pedidos:'rel-ped-tbody',epi:'rel-epi-tbody',analiticos:'rel-ana-tbody'};
    const tits={producao:'Relatório de Produção',premiacao:'Relatório de Premiação',estoque:'Relatório de Estoque',pedidos:'Relatório de Pedidos',epi:'Relatório de EPI',analiticos:'Relatório Analítico de Insumos'};
    let tituloReport = tits[tipo];
    if (tipo === 'analiticos') {
      const elTit = document.getElementById('rel-ana-title');
      if (elTit) tituloReport = elTit.textContent;
    }
    const el=document.getElementById(maps[tipo]);
    const tabela=el?.closest('table')||el;
    const win=window.open('','_blank');
    win.document.write(`<html><head><title>${tituloReport}</title><style>@page{margin:0}body{font-family:Arial,sans-serif;margin:15mm 15mm 22mm 15mm;font-size:12px;counter-reset:page}table{width:100%;border-collapse:collapse}th{background:#333;color:#fff;padding:8px;text-align:left}td{padding:7px;border-bottom:1px solid #ddd}.print-footer{position:fixed;bottom:8mm;left:15mm;right:15mm;border-top:1px solid #ddd;padding-top:6px;display:flex;justify-content:space-between;font-size:10px;color:#777;font-family:Arial,sans-serif;counter-increment:page}.page-number::after{content:counter(page)}</style></head><body>${_getEmpresaHeader(tituloReport)}${tabela?.outerHTML||'<p>Sem dados</p>'}${_getPrintFooter()}</body></html>`);
    win.document.close();
    setTimeout(()=>win.print(),500);
  } else {
    const maps={producao:'rel-prod-tbody',estoque:'rel-est-tbody',pedidos:'rel-ped-tbody',epi:'rel-epi-tbody',analiticos:'rel-ana-tbody'};
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
    
    let downloadName = `pratic_${tipo}_${new Date().toISOString().slice(0,10)}.csv`;
    if (tipo === 'analiticos') {
      const tipoAna = document.getElementById('rel-ana-tipo')?.value || 'insumos';
      downloadName = `pratic_analiticos_${tipoAna}_${new Date().toISOString().slice(0,10)}.csv`;
    }
    
    a.download=downloadName;
    a.click();
  }
}

// ─── CONFIGURAÇÕES ────────────────────────────────────────────────────────────

async function loadConfiguracoes() {
  const configs = await api('/configuracoes/');
  const form = document.getElementById('config-form');
  if (!form) return;

  const byKey = {};
  (configs || []).forEach(c => { byKey[c.chave] = c; });
  const has = k => byKey[k] !== undefined;
  const val = k => has(k) ? byKey[k].valor : '';

  const field = (k, label, pre) => {
    if (!has(k)) return '';
    return `
      <div class="bonif-field">
        <label>${label}</label>
        <div class="bonif-input">
          ${pre ? `<span class="bonif-pre">${pre}</span>` : ''}
          <input type="number" id="cfg-${k}" value="${val(k)}" inputmode="numeric" min="0">
        </div>
      </div>`;
  };

  const card = (cls, em, titulo, nota, campos, btn) => {
    const keys = campos.filter(c => has(c[0])).map(c => c[0]);
    if (!keys.length) return '';
    const inner = campos.map(c => field(c[0], c[1], c[2])).join('');
    return `
      <div class="bonif-card ${cls}">
        <div class="bonif-head"><span class="bonif-em">${em}</span><h2>${titulo}</h2></div>
        ${nota ? `<p class="bonif-note">${nota}</p>` : ''}
        ${inner}
        <div class="bonif-foot">
          <button class="bonif-save" onclick='salvarCardBonif(${JSON.stringify(keys)}, this)'>${btn}</button>
        </div>
      </div>`;
  };

  form.innerHTML = `
    <style>
      #config-form .bonif-sub{color:var(--muted,#8b92a3);font-size:13.5px;margin:0 0 22px}
      #config-form .bonif-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;max-width:980px}
      #config-form .bonif-card{background:var(--surface,#161922);border:1px solid var(--border,rgba(255,255,255,.08));border-radius:14px;padding:20px 20px 18px;display:flex;flex-direction:column}
      #config-form .bonif-card.full{grid-column:1 / -1}
      #config-form .bonif-head{display:flex;align-items:center;gap:10px;margin-bottom:4px}
      #config-form .bonif-em{font-size:19px;width:34px;height:34px;display:grid;place-items:center;border-radius:9px;background:var(--surface-2,#1d2130);border:1px solid var(--border-soft,rgba(255,255,255,.06))}
      #config-form .bonif-head h2{font-size:15.5px;margin:0;font-weight:700;color:var(--text,#e6e9ef)}
      #config-form .bonif-note{color:var(--muted,#8b92a3);font-size:12.5px;margin:6px 0 16px;line-height:1.5}
      #config-form .bonif-field{margin-bottom:13px}
      #config-form .bonif-field label{display:block;font-size:12.5px;color:var(--muted,#8b92a3);margin-bottom:6px;font-weight:500}
      #config-form .bonif-input{display:flex;align-items:center;background:var(--surface-2,#1d2130);border:1px solid var(--border,rgba(255,255,255,.08));border-radius:9px;overflow:hidden;height:42px;max-width:280px}
      #config-form .bonif-input:focus-within{border-color:rgba(245,179,1,.55)}
      #config-form .bonif-pre{padding:0 11px;color:var(--muted,#6b7280);font-size:13.5px;font-weight:600;border-right:1px solid var(--border-soft,rgba(255,255,255,.06));align-self:stretch;display:flex;align-items:center}
      #config-form .bonif-input input{flex:1;background:transparent;border:0;outline:0;color:var(--text,#e6e9ef);font-size:15px;padding:0 12px;font-weight:600;min-width:0;-moz-appearance:textfield}
      #config-form .bonif-input input::-webkit-outer-spin-button,#config-form .bonif-input input::-webkit-inner-spin-button{-webkit-appearance:none;margin:0}
      #config-form .bonif-foot{margin-top:auto;display:flex;justify-content:flex-end;padding-top:14px;border-top:1px solid var(--border-soft,rgba(255,255,255,.06))}
      #config-form .bonif-save{background:#f5b301;color:#1a1400;border:0;border-radius:9px;padding:9px 20px;font-size:13.5px;font-weight:700;cursor:pointer;font-family:inherit}
      #config-form .bonif-save:hover{filter:brightness(1.07)}
      #config-form .bonif-save:disabled{opacity:.6;cursor:default}
      @media(max-width:680px){#config-form .bonif-grid{grid-template-columns:1fr}}
    </style>
    <p class="bonif-sub">Defina a meta de produ\u00e7\u00e3o e os valores de b\u00f4nus e pr\u00eamios da equipe.</p>
    <div class="bonif-grid">
      ${card('full','\ud83c\udfaf','Meta de Produ\u00e7\u00e3o',
        'M\u00ednimo que o operador deve produzir no dia. \u00c9 a <b>base</b> de quem entra na premia\u00e7\u00e3o \u2014 a partir dela \u00e9 calculada toda a bonifica\u00e7\u00e3o.',
        [['meta_padrao','Meta di\u00e1ria (pe\u00e7as)','']],
        'Salvar meta')}
      ${card('','\ud83c\udfc5','B\u00f4nus dos Auxiliares',
        'Valores pagos aos auxiliares destaque do m\u00eas.',
        [['qtd_auxiliares_premiados','Quantos auxiliares s\u00e3o premiados por m\u00eas',''],
         ['bonus_auxiliar_1','1\u00ba auxiliar destaque','R$'],
         ['bonus_auxiliar_2','2\u00ba auxiliar destaque','R$'],
         ['bonus_auxiliar_3','3\u00ba auxiliar destaque','R$']],
        'Salvar b\u00f4nus')}
      ${card('','\ud83c\udfc6','Pr\u00eamios dos Operadores',
        'Valores pagos aos operadores conforme o desempenho.',
        [['valor_premio_operador','Por bater a m\u00e9dia','R$'],
         ['valor_premio_operador_1','1\u00ba colocado','R$'],
         ['valor_premio_operador_2','2\u00ba colocado','R$']],
        'Salvar pr\u00eamios')}
    </div>`;
}

async function salvarCardBonif(keys, btn) {
  const original = btn ? btn.textContent : '';
  try {
    if (btn) { btn.disabled = true; btn.textContent = 'Salvando...'; }
    for (const k of keys) {
      const el = document.getElementById('cfg-' + k);
      if (!el) continue;
      await api('/configuracoes/' + k, 'PUT', { valor: el.value });
    }
    if (keys.includes('meta_padrao')) {
      const mv = document.getElementById('cfg-meta_padrao');
      if (mv && !isNaN(+mv.value)) META_GLOBAL = +mv.value;
    }
    showAlert('Bonifica\u00e7\u00f5es salvas!');
  } catch (e) {
    showAlert(e.message, 'danger');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = original; }
  }
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


async function openModalMovimentacao(prodId, nome, saldo) {
  const el = document.getElementById('mov-produto-id'); if(el) el.value = prodId;
  const sEl = document.getElementById('mov-saldo-atual-label'); if(sEl) sEl.textContent = fmtNum(saldo);
  const nEl = document.getElementById('mov-produto-nome'); if(nEl) nEl.textContent = nome;
  const qEl = document.getElementById('mov-quantidade-est'); if(qEl) qEl.value = '';
  const obsEl = document.getElementById('mov-obs-est'); if(obsEl) obsEl.value = '';
  const dtEl = document.getElementById('mov-data-est'); if(dtEl) dtEl.value = new Date().toISOString().split('T')[0];
  openModal('modal-movimentacao');
}


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
        ${temPermissao('epi', 'editar') ? `<button class="btn btn-sm btn-secondary" onclick="renovarEPI(${r.id},${r.colaborador_id},${r.epi_id})">🔄</button>` : ''}
        ${temPermissao('epi', 'deletar') ? `<button class="btn btn-sm btn-danger" onclick="deletarEntrega(${r.id})">✕</button>` : ''}
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
      ${temPermissao('epi', 'editar') ? `<button class="btn btn-sm btn-secondary" onclick="editEPI(${r.id},'${r.nome.replace(/'/g,"\\'")}','${r.categoria||''}','${r.descricao||''}')">✏️</button>` : ''}
      ${temPermissao('epi', 'deletar') ? `<button class="btn btn-sm btn-danger" onclick="deletarEPI(${r.id})">✕</button>` : ''}
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
    @page { size: A4; margin: 0; }
    * { box-sizing: border-box; }
    body { font-family: Arial, sans-serif; margin: 12mm; background: #fff; }
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
// Considera o item como produzido pela quantidade real, não só pelo campo status (evita divergência)
const _itemProduzido = i => (((i.qtd_produzida||0) >= i.quantidade) && i.quantidade>0) || i.status==='produzido' || i.status==='entregue';
const _itemStatusEf = i => i.status==='entregue' ? 'entregue' : (_itemProduzido(i) ? 'produzido' : ((i.qtd_produzida||0)>0 ? 'em_producao' : 'aberto'));

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
  try { const svd = await api('/estoque/saldo-vs-demanda'); checkSVDBadge(svd); } catch(e) {}
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

let todosProdutosCache = [];
async function _carregarRevendaProdutos() {
  try {
    const all = await api('/estoque/produtos');
    todosProdutosCache = all || [];
    revendaProdutos = todosProdutosCache.filter(p => p.categoria_tipo === 'revenda');
  } catch(e) { /* mantém o cache anterior */ }
}

// Casamento FORTE por descrição: só vale se o nome normalizado de um produto de
// revenda contém (ou está contido em) a descrição normalizada. Evita falsos
// positivos do findBestStockMatch (que casa frouxo, por token/limiar baixo).
function _descricaoCasaRevendaForte(desc) {
  if (!desc || !revendaProdutos.length) return false;
  const normD = desc.toUpperCase().replace(/[^A-Z0-9]/g, '').replace(/ML$/, 'M');
  if (normD.length < 6) return false; // descrição muito curta não decide nada
  return revendaProdutos.some(p => {
    const normP = (p.nome || '').toUpperCase().replace(/[^A-Z0-9]/g, '').replace(/ML$/, 'M');
    if (normP.length < 6) return false;
    return normP.includes(normD) || normD.includes(normP);
  });
}

// Reconhece item de revenda.
// - Item VINCULADO a um produto: a categoria do produto manda (não usa descrição).
// - Item SEM vínculo: acha o MELHOR produto correspondente entre TODOS os
//   produtos cadastrados; só é revenda se esse melhor match for de revenda.
//   (Assim um copo de produção casa com o produto de produção dele, não com um
//   produto de revenda por coincidência.)
function itemEhRevenda(i) {
  if (!i) return false;
  if (i.produto_id) {
    if (i.categoria_tipo === 'revenda') return true;
    if (revendaProdutos.some(p => p.id === i.produto_id)) return true;
    return false; // vinculado a categoria de produção => NÃO é revenda
  }
  if (i.categoria_tipo === 'revenda') return true;
  if (!i.descricao) return false;
  const bestId = findBestStockMatch(i.descricao, todosProdutosCache);
  if (bestId != null) return revendaProdutos.some(p => p.id === bestId);
  // sem nenhum produto cadastrado correspondente: cai no casamento forte só-revenda
  return _descricaoCasaRevendaForte(i.descricao);
}

async function loadFila() {
  const status=document.getElementById('ped-fila-status')?.value||'';
  let url='/pedidos/fila/producao';if(status) url+='?status='+status;
  await _carregarRevendaProdutos();
  const itens=(await api(url)).filter(i => !itemEhRevenda(i));
  const el=document.getElementById('ped-fila-cards');
  if(!el) return;

  // Banner de alertas
  try {
    const al=await api('/pedidos/alertas/resumo');
    const banner=document.getElementById('ped-alertas-banner');
    if(banner&&(al.vencidos+al.urgentes)>0){
      banner.innerHTML=`<div style="background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.3);border-radius:8px;padding:12px 16px;margin-bottom:16px;font-size:13px;color:var(--danger)">
        ⚠️ <strong>${al.vencidos} vencido(s)</strong> | <strong>${al.urgentes} urgente(s) em até 3 dias</strong>
      </div>`;
    } else if(banner) banner.innerHTML='';
  } catch(e){}

  if(!itens.length){
    el.innerHTML='<div class="table-wrap"><p style="padding:32px;text-align:center;color:var(--muted)">Nenhum item na fila de produção</p></div>';
    return;
  }

  // Agrupar por pedido e ordenar por prazo (mais urgente primeiro)
  const grupos={};
  itens.forEach(i=>{const k=i.pedido_id;if(!grupos[k])grupos[k]={pedido:i,itens:[]};grupos[k].itens.push(i);});
  const pedidosOrdenados = Object.values(grupos).sort((a,b) => {
    return (a.pedido.dias_restantes||99) - (b.pedido.dias_restantes||99);
  });

  // Contar totais para resumo
  const totalPedidos = pedidosOrdenados.length;
  const urgentes = pedidosOrdenados.filter(g => Math.round(g.pedido.dias_restantes) <= 3).length;

  el.innerHTML = `
    <!-- Resumo rápido -->
    <div style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap">
      <div style="background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:10px 16px;font-size:13px">
        📋 <strong>${totalPedidos}</strong> pedido(s) na fila
      </div>
      ${urgentes>0?`<div style="background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.3);border-radius:8px;padding:10px 16px;font-size:13px;color:var(--danger)">
        🔴 <strong>${urgentes}</strong> urgente(s) — prazo ≤ 3 dias
      </div>`:''}
      <button class="btn btn-sm btn-secondary" onclick="toggleTodasFilas(true)" style="margin-left:auto">↕ Expandir todos</button>
      <button class="btn btn-sm btn-secondary" onclick="toggleTodasFilas(false)">↕ Recolher todos</button>
    </div>

    <!-- Cards colapsáveis -->
    ${pedidosOrdenados.map(g => {
      const p=g.pedido;
      const dias=Math.round(p.dias_restantes);
      const diasCor=dias<0?'var(--danger)':dias<=3?'var(--danger)':dias<=7?'var(--warn)':'var(--success)';
      const diasLabel=dias<0?`⚠ Vencido há ${Math.abs(dias)}d`:dias===0?'⚠ Vence hoje!':`${dias}d restantes`;
      const urgente = dias <= 3;
      const produzidos = g.itens.filter(_itemProduzido).length;
      const totalItens = g.itens.length;
      const pctGeral = Math.round((produzidos/totalItens)*100);
      const cardId = 'fila-card-' + p.pedido_id;

      const itensList = g.itens.map(i=>{
        const pct=Math.min(100,Math.round((i.qtd_produzida/i.quantidade)*100));
        const stEf=_itemStatusEf(i);
        const prox=STATUS_NEXT_PED[stEf];
        return `<div style="padding:10px 0;border-bottom:1px solid var(--border)">
          <div class="flex items-center justify-between" style="margin-bottom:6px">
            <div style="flex:1;min-width:0">
              <span style="font-weight:600;font-size:13px">${i.descricao}</span>
              <span class="pill ${STATUS_PILL_PED[stEf]}" style="margin-left:8px;font-size:10px">${STATUS_LABEL_PED[stEf]}</span>
            </div>
            <div class="flex gap-2" style="flex-shrink:0;margin-left:8px">
              ${prox && temPermissao('producao', 'editar') ? `<button class="btn btn-sm btn-secondary" onclick="avancarItemStatus(${i.id},'${prox}',${i.quantidade})">${STATUS_NEXT_LABEL_PED[stEf]}</button>` : ''}
              ${temPermissao('producao', 'deletar') ? `<button class="btn btn-sm btn-danger" onclick="removerItemFila(${i.id})">✕</button>` : ''}
            </div>
          </div>
          <div style="font-size:12px;color:var(--muted);margin-bottom:5px">
            Qtd: <strong style="color:var(--text)">${fmtNum(i.qtd_produzida)} / ${fmtNum(i.quantidade)} ${i.unidade}</strong>
          </div>
          <div style="height:5px;background:var(--surface2);border-radius:3px;overflow:hidden">
            <div style="height:100%;width:${pct}%;background:${pct>=100?'var(--success)':'var(--accent)'};border-radius:3px;transition:width .3s"></div>
          </div>
        </div>`;
      }).join('');

      return `<div class="card fila-card" id="${cardId}" style="margin-bottom:12px;border-left:3px solid ${diasCor};${urgente?'box-shadow:0 0 0 1px rgba(239,68,68,.2)':''}">
        <!-- Cabeçalho clicável -->
        <div onclick="toggleFilaCard('${cardId}')" style="cursor:pointer;display:flex;align-items:center;justify-content:space-between;user-select:none">
          <div style="display:flex;align-items:center;gap:12px;flex:1;min-width:0">
            <div>
              <div style="font-family:var(--font-head);font-size:15px;font-weight:700">${p.numero_pedido}</div>
              <div style="font-size:12px;color:var(--muted);margin-top:2px">${p.cliente_nome}</div>
            </div>
            <!-- Progresso geral -->
            <div style="flex:1;max-width:140px">
              <div style="font-size:11px;color:var(--muted);margin-bottom:3px">${produzidos}/${totalItens} itens produzidos</div>
              <div style="height:5px;background:var(--surface2);border-radius:3px;overflow:hidden">
                <div style="height:100%;width:${pctGeral}%;background:${pctGeral>=100?'var(--success)':'var(--accent)'};border-radius:3px"></div>
              </div>
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:12px;flex-shrink:0">
            <div style="text-align:right">
              <div style="font-family:var(--font-head);font-weight:800;color:${diasCor};font-size:13px">${diasLabel}</div>
              <div style="font-size:11px;color:var(--muted)">${fmtDate(p.prazo_entrega)}</div>
            </div>
            <span class="fila-toggle-icon" style="color:var(--muted);font-size:16px;transition:transform .2s">${urgente?'▼':'▶'}</span>
          </div>
        </div>
        <!-- Itens (visível se urgente, colapsado se não) -->
        <div class="fila-itens" style="display:${urgente?'block':'none'};margin-top:12px;border-top:1px solid var(--border);padding-top:4px">
          ${itensList}
        </div>
      </div>`;
    }).join('')}
  `;
}

function toggleFilaCard(cardId) {
  const card = document.getElementById(cardId);
  if (!card) return;
  const itens = card.querySelector('.fila-itens');
  const icon = card.querySelector('.fila-toggle-icon');
  if (!itens) return;
  const aberto = itens.style.display !== 'none';
  itens.style.display = aberto ? 'none' : 'block';
  if (icon) icon.textContent = aberto ? '▶' : '▼';
}

function toggleTodasFilas(expandir) {
  document.querySelectorAll('.fila-card').forEach(card => {
    const itens = card.querySelector('.fila-itens');
    const icon = card.querySelector('.fila-toggle-icon');
    if (itens) itens.style.display = expandir ? 'block' : 'none';
    if (icon) icon.textContent = expandir ? '▼' : '▶';
  });
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

function _diasAtePrazo(prazoStr) {
  const s = String(prazoStr || '').slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return null;
  const [y, m, d] = s.split('-').map(Number);
  const alvo = new Date(y, m - 1, d); alvo.setHours(0, 0, 0, 0);
  const hoje = new Date(); hoje.setHours(0, 0, 0, 0);
  return Math.round((alvo - hoje) / 86400000);
}

function _popularFiltroMarcas(pedidos, selecionada) {
  const sel = document.getElementById('ped-marca-filtro');
  if (!sel) return;
  const marcas = new Set();
  (pedidos || []).forEach(p => {
    (p.marcas || '').split(',').forEach(m => { const t = m.trim(); if (t) marcas.add(t); });
  });
  const ordenadas = Array.from(marcas).sort((a, b) => a.localeCompare(b));
  sel.innerHTML = '<option value="">Todas as marcas</option>' +
    ordenadas.map(m => `<option value="${m.replace(/"/g, '&quot;')}" ${m === selecionada ? 'selected' : ''}>${m}</option>`).join('');
}

async function loadPedidos() {
  const sit = document.getElementById('ped-status-filtro')?.value ?? 'ativos';
  const prazoF = document.getElementById('ped-prazo-filtro')?.value || '';
  const marcaF = document.getElementById('ped-marca-filtro')?.value || '';
  let rows = await api('/pedidos/');
  const statusDe = p => p.status_efetivo || p.status;

  // Popula o filtro de marcas a partir de todos os pedidos (antes de filtrar)
  _popularFiltroMarcas(rows, marcaF);

  // Filtro de situação (usa o status real derivado da produção)
  if (sit === 'ativos') rows = rows.filter(p => statusDe(p) !== 'entregue');
  else if (sit) rows = rows.filter(p => statusDe(p) === sit);

  // Filtro de marca (marca dos produtos vinculados aos itens)
  if (marcaF) {
    rows = rows.filter(p => (p.marcas || '').split(',').map(s => s.trim()).filter(Boolean).includes(marcaF));
  }

  // Filtro de prazo
  if (prazoF) {
    const hoje = new Date();
    rows = rows.filter(p => {
      const dias = _diasAtePrazo(p.prazo_entrega);
      if (dias === null) return false;
      if (prazoF === 'hoje') return dias === 0;
      if (prazoF === 'semana') return dias >= 0 && dias <= 7;
      if (prazoF === 'atrasados') return dias < 0 && statusDe(p) !== 'entregue';
      if (prazoF === 'mes') {
        const s = String(p.prazo_entrega || '').slice(0, 10).split('-').map(Number);
        return s[0] === hoje.getFullYear() && (s[1] - 1) === hoje.getMonth();
      }
      return true;
    });
  }

  const tbody = document.getElementById('ped-tbody');
  if (!tbody) return;
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--muted);padding:24px">Nenhum pedido neste filtro</td></tr>';
    return;
  }
  tbody.innerHTML=rows.map(p=>{
    const dias=Math.round(p.dias_restantes);
    const diasCor=dias<0?'var(--danger)':dias<=3?'var(--warn)':'var(--success)';
    return `<tr>
      <td><strong>${p.numero_pedido}</strong></td>
      <td>${p.cliente_nome}</td>
      <td>${p.vendedor || '—'}</td>
      <td>${fmtDate(p.prazo_entrega)}</td>
      <td style="color:${diasCor};font-weight:700">${dias<0?'Vencido':dias+'d'}</td>
      <td>${p.itens_produzidos}/${p.total_itens}</td>
      <td><span class="pill ${STATUS_PILL_PED[p.status_efetivo||p.status]}">${STATUS_LABEL_PED[p.status_efetivo||p.status]}</span></td>
      <td class="flex gap-2">
        <button class="btn btn-sm btn-secondary" onclick="verDetalhesPedido(${p.id})">Ver</button>
        ${temPermissao('pedidos', 'editar') ? `<button class="btn btn-sm btn-secondary" onclick="editPedido(${p.id})">✏️</button>` : ''}
        ${temPermissao('pedidos', 'deletar') ? `<button class="btn btn-sm btn-danger" onclick="deletarPedido(${p.id})">✕</button>` : ''}
      </td>
    </tr>`;
  }).join('');
}


async function vincularProdutoItem(itemId, produtoIdAtual) {
  const prods = await api('/estoque/produtos');
  const sel = `<select id="sel-prod-${itemId}" style="font-size:12px;padding:4px 8px;min-width:180px" onchange="salvarVinculoProduto(${itemId}, this.value)">
    <option value="">— Sem vínculo —</option>
    ${prods.map(p=>`<option value="${p.id}" ${p.id==produtoIdAtual?'selected':''}>${p.nome}${p.marca?' '+p.marca:''}</option>`).join('')}
  </select>`;
  const cell = document.getElementById('cell-prod-'+itemId);
  if (cell) cell.innerHTML = sel;
}

async function salvarVinculoProduto(itemId, produtoId) {
  try {
    await api('/pedidos/itens/'+itemId+'/produto', 'PUT', { produto_id: produtoId ? +produtoId : null });
    showAlert('Produto vinculado!');
  } catch(e) { showAlert('Erro: '+e.message, 'danger'); }
}
async function marcarRevendaSeparado(pedidoId, itemId, qtd, marcar) {
  try {
    const r = await api('/pedidos/itens/'+itemId+'/separar-revenda','POST',{ marcar: !!marcar });
    if (marcar && r.sem_vinculo) {
      showAlert('Marcado, mas SEM baixa de estoque: vincule o item a um produto de revenda primeiro.', 'warn');
    } else if (marcar && r.saldo_insuficiente) {
      showAlert('Separado com baixa — atenção: faltaram '+fmtNum(r.faltou)+' un no estoque (saldo ficou '+fmtNum(r.saldo_atual)+').', 'warn');
    } else {
      showAlert(marcar ? 'Separado/Entregue — baixa registrada no estoque' : 'Desfeito — estoque estornado');
    }
    await verDetalhesPedido(pedidoId);
    loadPedidos();
  } catch(e){ showAlert(e.message,'danger'); }
}
window.marcarRevendaSeparado = marcarRevendaSeparado;

async function verDetalhesPedido(id) {
  const p=await api('/pedidos/'+id);
  await _carregarRevendaProdutos();
  const dias=Math.round(p.dias_restantes);
  const diasCor=dias<0?'var(--danger)':dias<=3?'var(--warn)':'var(--success)';
  document.getElementById('modal-ped-det-title').textContent='Pedido '+p.numero_pedido;
  document.getElementById('modal-ped-det-content').innerHTML=`
    <div class="cards-grid" style="margin-bottom:16px">
      <div class="card"><div class="card-label">Cliente</div><div style="font-weight:600">${p.cliente_nome}</div></div>
      <div class="card"><div class="card-label">Prazo</div><div style="font-family:var(--font-head);font-weight:800;color:${diasCor}">${fmtDate(p.prazo_entrega)}</div></div>
      <div class="card"><div class="card-label">Status</div><span class="pill ${STATUS_PILL_PED[p.status]}">${STATUS_LABEL_PED[p.status]}</span></div>
      ${p.vendedor ? `<div class="card"><div class="card-label">Vendedor</div><div style="font-weight:600">${p.vendedor}</div></div>` : ''}
    </div>
    <div class="table-wrap">
      <div class="table-head"><span class="table-head-title">Itens</span></div>
      <table><thead><tr><th>Descrição</th><th>Produto Estoque</th><th>Qtd</th><th>Produzido</th><th>Status</th><th></th></tr></thead>
      <tbody>${p.itens.map(i=>{
        if (itemEhRevenda(i)) {
          const feito = i.status === 'entregue' || i.status === 'produzido';
          return `<tr style="background:rgba(59,130,246,.05)">
            <td>${i.descricao} <span style="margin-left:6px;font-size:11px;padding:1px 7px;border-radius:9px;background:rgba(59,130,246,.15);color:#3b82f6">🛒 Revenda</span></td>
            <td>${fmtNum(i.quantidade)} ${i.unidade||''}</td>
            <td><span style="color:var(--muted);font-size:12px">Não produzido — separar do estoque</span></td>
            <td><span class="pill ${feito?STATUS_PILL_PED['entregue']:''}">${feito?'Separado / Entregue':'Pendente'}</span></td>
            <td>${feito
              ? `<button class="btn btn-sm btn-secondary" onclick="marcarRevendaSeparado(${p.id},${i.id},${i.quantidade},false)">Desfazer</button>`
              : `<button class="btn btn-sm btn-secondary" style="background:var(--success);border-color:var(--success);color:#fff" onclick="marcarRevendaSeparado(${p.id},${i.id},${i.quantidade},true)">✓ Separado/Entregue</button>`}</td>
          </tr>`;
        }
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


let pedidoArquivoSelecionado = null;
let pedidosArquivosSelecionados = [];

function selecionarPedidosArquivos(fileList, append = true) {
  const novos = Array.from(fileList || []);
  if (!novos.length) return;
  if (!append) pedidosArquivosSelecionados = [];
  const chave = f => f.name + '|' + f.size;
  const existentes = new Set(pedidosArquivosSelecionados.map(chave));
  novos.forEach(f => { if (!existentes.has(chave(f))) { pedidosArquivosSelecionados.push(f); existentes.add(chave(f)); } });
  pedidoArquivoSelecionado = pedidosArquivosSelecionados[0] || null;
  renderPedidosArquivosSelecionados();
}

function limparPedidosArquivos() {
  pedidosArquivosSelecionados = [];
  pedidoArquivoSelecionado = null;
  const input = document.getElementById('pedido-arquivo');
  if (input) input.value = '';
  renderPedidosArquivosSelecionados();
}

function renderPedidosArquivosSelecionados() {
  const files = pedidosArquivosSelecionados;
  const nome = document.getElementById('pedido-arquivo-nome');
  if (nome) {
    nome.textContent = !files.length ? 'Nenhum arquivo selecionado'
      : files.length === 1 ? `${files[0].name} — ${(files[0].size/1024/1024).toFixed(2)} MB`
      : `${files.length} arquivos selecionados`;
  }
  const preview = document.getElementById('pedido-import-preview');
  if (!preview) return;
  if (!files.length) { preview.style.display = 'none'; preview.innerHTML = ''; return; }
  preview.style.display = 'block';
  const lista = files.map(f => `• ${f.name}`).join('<br>');
  const dica = files.length === 1
    ? `Arraste mais arquivos para somar ao lote, ou use "Importar em lote" para criar direto.`
    : `Arraste mais arquivos para somar ao lote.`;
  preview.innerHTML = `<strong>${files.length} arquivo(s) prontos:</strong><br>${lista}`
    + `<br><span style="color:var(--muted)">${dica}</span>`
    + `<br><a href="#" onclick="limparPedidosArquivos();return false;" style="color:var(--accent)">Limpar seleção</a>`;
}

async function importarPedidosLote() {
  if (!pedidosArquivosSelecionados.length) { showAlert('Selecione um ou mais arquivos de pedido', 'danger'); return; }
  const btn = document.getElementById('btn-importar-pedido-lote');
  const preview = document.getElementById('pedido-import-preview');
  try {
    if (btn) { btn.disabled = true; btn.textContent = 'Importando...'; }
    const fd = new FormData();
    pedidosArquivosSelecionados.forEach(f => fd.append('files', f));
    let r = await fetch(API + '/pedidos/importar-arquivos-lote', { method: 'POST', body: fd });
    if (r.status === 401) {
      window.location.href = '/login?redirect=' + encodeURIComponent(window.location.pathname + window.location.search);
      return;
    }
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || 'Erro ao importar em lote');

    const rs = data.resumo || { criados: 0, duplicados: 0, erros: 0, total: 0 };
    const linhas = (data.resultados || []).map(it => {
      if (it.status === 'criado') {
        const falta = (it.faltando && it.faltando.length) ? ` <span style="color:#f4b400">(revisar: ${it.faltando.join(', ')})</span>` : '';
        return `<div style="color:#46d369">✅ Pedido ${it.numero_pedido} — ${it.cliente || 'cliente'} (${it.qtd_itens} item(ns))${falta}</div>`;
      }
      if (it.status === 'duplicado') {
        return `<div style="color:var(--muted)">↪️ Pedido ${it.numero_pedido} já existia — ignorado</div>`;
      }
      return `<div style="color:#ff6b6b">⚠️ ${it.arquivo}: ${it.motivo || 'não foi possível ler'}</div>`;
    }).join('');

    if (preview) {
      preview.style.display = 'block';
      const alertas = data.alertas_estoque || [];
      const blocoAlertas = alertas.length
        ? `<hr style="border-color:rgba(255,255,255,.1)"><div style="color:#f4b400;font-weight:600;margin:4px 0">⚠️ Estoque insuficiente para a demanda dos pedidos abertos:</div>`
          + alertas.map(a=>`<div style="color:#f4b400;font-size:13px">• ${a.produto}: saldo ${fmtNum(a.saldo)} ${a.unidade}, demanda ${fmtNum(a.demanda)} — faltam <strong>${fmtNum(a.falta)}</strong></div>`).join('')
        : '';
      preview.innerHTML = `<strong>Resumo:</strong> ${rs.criados} criado(s), ${rs.duplicados} duplicado(s), ${rs.erros} com erro — de ${rs.total} arquivo(s).<hr style="border-color:rgba(255,255,255,.1)">${linhas}${blocoAlertas}`;
    }
    showAlert(`Importação concluída: ${rs.criados} pedido(s) criado(s).`);
    const dups = (data.resultados || []).filter(it => it.status === 'duplicado').map(it => it.numero_pedido);
    const alertasEstoque = data.alertas_estoque || [];
    let avisoHtml = '';
    if (dups.length) {
      avisoHtml += `<div style="color:#f4b400;font-weight:600;margin-bottom:6px">${dups.length} pedido(s) já cadastrado(s) — não foram importados:</div>`
        + dups.map(n => `<div style="margin-left:4px">• Pedido <strong>${n}</strong></div>`).join('');
    }
    if (alertasEstoque.length) {
      if (avisoHtml) avisoHtml += `<hr style="border-color:rgba(255,255,255,.12);margin:12px 0">`;
      avisoHtml += `<div style="color:#f4b400;font-weight:600;margin-bottom:6px">Estoque insuficiente para a demanda dos pedidos abertos:</div>`
        + alertasEstoque.map(a => `<div style="margin-left:4px">• ${a.produto}: saldo ${fmtNum(a.saldo)} ${a.unidade}, demanda ${fmtNum(a.demanda)} — faltam <strong>${fmtNum(a.falta)}</strong></div>`).join('');
    }
    if (avisoHtml) showPopup('⚠️ Importação — atenção', avisoHtml);
    // Importação limpa (sem erros de leitura): fecha o modal sozinho
    if (rs.erros === 0) closeModal('modal-importar-pedido');
    if (typeof loadPedidos === 'function') { try { await loadPedidos(); } catch(e){} }
    pedidosArquivosSelecionados = [];
    const input = document.getElementById('pedido-arquivo');
    if (input) input.value = '';
  } catch (e) {
    showAlert(e.message || 'Erro ao importar em lote', 'danger');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Importar em lote'; }
  }
}
window.selecionarPedidosArquivos = selecionarPedidosArquivos;
window.importarPedidosLote = importarPedidosLote;
window.limparPedidosArquivos = limparPedidosArquivos;

function openModalImportarPedido() {
  pedidoArquivoSelecionado = null;
  pedidosArquivosSelecionados = [];
  const input = document.getElementById('pedido-arquivo');
  if (input) input.value = '';
  const nome = document.getElementById('pedido-arquivo-nome');
  if (nome) nome.textContent = 'Nenhum arquivo selecionado';
  const preview = document.getElementById('pedido-import-preview');
  if (preview) { preview.style.display = 'none'; preview.innerHTML = ''; }
  const btn = document.getElementById('btn-importar-pedido');
  if (btn) { btn.disabled = false; btn.textContent = 'Importar e Cadastrar'; }
  openModal('modal-importar-pedido');
}

function selecionarPedidoArquivo(file) {
  if (!file) return;
  pedidoArquivoSelecionado = file;
  const nome = document.getElementById('pedido-arquivo-nome');
  if (nome) nome.textContent = `${file.name} — ${(file.size/1024/1024).toFixed(2)} MB`;
  const preview = document.getElementById('pedido-import-preview');
  if (preview) {
    preview.style.display = 'block';
    preview.innerHTML = `<strong>Arquivo pronto para importação:</strong> ${file.name}<br><span>Após confirmar, o sistema criará o cliente caso ele ainda não exista e cadastrará os itens encontrados no pedido.</span>`;
  }
}

function handleDropPedidoArquivo(ev) {
  ev.preventDefault();
  const area = document.getElementById('pedido-drop-area');
  if (area) area.style.borderColor = 'rgba(255,255,255,.18)';
  const files = ev.dataTransfer?.files;
  if (files && files.length) selecionarPedidosArquivos(files);
}

async function importarPedidoArquivo() {
  if (!pedidoArquivoSelecionado) { showAlert('Selecione ou solte um arquivo do pedido', 'danger'); return; }
  const btn = document.getElementById('btn-importar-pedido');
  try {
    if (btn) { btn.disabled = true; btn.textContent = 'Analisando arquivo...'; }
    const fd = new FormData();
    fd.append('file', pedidoArquivoSelecionado);
    let r = await fetch(API.replace(/\/api$/, '/api/importar-pedido-arquivo'), { method: 'POST', body: fd });
    if (r.status === 404 || r.status === 405) {
      r = await fetch(API + '/pedidos/importar-arquivo', { method: 'POST', body: fd });
    }
    if (r.status === 401) {
      window.location.href = '/login?redirect=' + encodeURIComponent(window.location.pathname + window.location.search);
      return;
    }
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || 'Erro ao analisar arquivo');
    
    // Fechar modal de importação
    closeModal('modal-importar-pedido');
    
    // Preencher campos do modal-pedido
    document.getElementById('ped-id').value = '';
    document.getElementById('ped-numero').value = data.dados_extraidos.numero_pedido || '';
    document.getElementById('ped-prazo').value = data.dados_extraidos.prazo_entrega || '';
    document.getElementById('ped-vendedor').value = data.dados_extraidos.vendedor || '';
    
    let obsStr = data.dados_extraidos.observacoes || '';
    obsStr = (obsStr + `\nArquivo importado: ${pedidoArquivoSelecionado.name}`).trim();
    document.getElementById('ped-obs').value = obsStr;
    
    const clientes = await api('/pedidos/clientes');
    document.getElementById('ped-cliente').innerHTML = clientes.map(c => `<option value="${c.id}">${c.razao_social}${c.nome_fantasia ? ' — ' + c.nome_fantasia : ''}</option>`).join('');
    if (data.cliente_id) {
      document.getElementById('ped-cliente').value = data.cliente_id;
    }
    
    pedidoItens = (data.dados_extraidos.itens || []).map(i => ({
      descricao: i.descricao,
      quantidade: i.quantidade,
      unidade: i.unidade || 'unidade'
    }));
    
    await carregarProdutosEstoque();
    renderItensPedido();
    document.getElementById('modal-ped-title').textContent = 'Confirmar Pedido Importado';
    openModal('modal-pedido');
    
    showAlert('Arquivo de pedido analisado com sucesso! Revise os dados e clique em Salvar.');
  } catch (e) {
    showAlert(e.message || 'Erro ao importar arquivo', 'danger');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Importar e Cadastrar'; }
  }
}
// Funções expostas para o modal de importação de pedidos
window.openModalImportarPedido = openModalImportarPedido;
window.selecionarPedidoArquivo = selecionarPedidoArquivo;
window.handleDropPedidoArquivo = handleDropPedidoArquivo;
window.importarPedidoArquivo = importarPedidoArquivo;


let pedidoItens=[];
let produtosEstoque=[];

async function carregarProdutosEstoque() {
  try { produtosEstoque = await api('/estoque/produtos'); }
  catch(e) { produtosEstoque = []; }
  let dl = document.getElementById('produtos-datalist');
  if (!dl) { dl = document.createElement('datalist'); dl.id = 'produtos-datalist'; document.body.appendChild(dl); }
  const esc = s => String(s||'').replace(/"/g,'&quot;');
  dl.innerHTML = produtosEstoque.map(p => {
    const hint = [p.codigo, p.marca, p.categoria_nome].filter(Boolean).join(' · ');
    return `<option value="${esc(p.nome)}">${esc(hint)}</option>`;
  }).join('');
}

function selecionarProdutoPedidoItem(idx, valor) {
  if (!pedidoItens[idx]) return;
  pedidoItens[idx].descricao = valor;
  const alvo = String(valor||'').trim().toLowerCase();
  const matches = produtosEstoque.filter(p => String(p.nome||'').trim().toLowerCase() === alvo);
  if (matches.length === 1) {
    pedidoItens[idx].produto_id = matches[0].id;
    const u = matches[0].unidade;
    const opts = ['unidade','und','milheiro','kg','litro','metro','caixa','pacote'];
    if (u && opts.includes(u)) { pedidoItens[idx].unidade = u; renderItensPedido(); }
  } else {
    pedidoItens[idx].produto_id = null;
  }
}
window.selecionarProdutoPedidoItem = selecionarProdutoPedidoItem;
window.carregarProdutosEstoque = carregarProdutosEstoque;

async function openModalPedido() {
  pedidoItens=[];
  document.getElementById('ped-id').value='';
  document.getElementById('ped-numero').value='';
  document.getElementById('ped-prazo').value='';
  document.getElementById('ped-vendedor').value='';
  document.getElementById('ped-obs').value='';
  const clientes=await api('/pedidos/clientes');
  document.getElementById('ped-cliente').innerHTML=clientes.map(c=>`<option value="${c.id}">${c.razao_social}${c.nome_fantasia?' — '+c.nome_fantasia:''}</option>`).join('');
  await carregarProdutosEstoque();
  renderItensPedido();
  document.getElementById('modal-ped-title').textContent='Novo Pedido';
  openModal('modal-pedido');
}

// ── Seletor de produto por item do pedido (combobox com ranking por semelhança) ──
function _scoreProduto(query, prod) {
  const desc = (query || '').toUpperCase();
  const nome = (prod.nome || '').toUpperCase();
  if (!nome) return 0;
  const normD = desc.replace(/[^A-Z0-9]/g, '').replace(/ML$/, 'M');
  const normP = nome.replace(/[^A-Z0-9]/g, '').replace(/ML$/, 'M');
  let score = 0;
  if (normD && normP === normD) score += 100;
  const numbers = desc.match(/\d+/g) || [];
  let allNums = numbers.length > 0;
  for (const n of numbers) { if (!nome.includes(n)) { allNums = false; break; } }
  if (allNums && numbers.length > 0) score += 8;
  [['CRISTAL', 6], ['CTL', 4], ['COPO', 2], ['PP', 2], ['PS', 2], ['TAMPA', 3], ['BOLHA', 3], ['RETA', 3], ['FURO', 2]].forEach(([k, w]) => {
    if (desc.includes(k) && nome.includes(k)) score += w;
  });
  if (normD && (normP.includes(normD) || normD.includes(normP))) score += 10;
  const td = desc.split(/[^A-Z0-9]+/).filter(t => t.length >= 2);
  const tp = new Set(nome.split(/[^A-Z0-9]+/).filter(t => t.length >= 2));
  td.forEach(t => { if (tp.has(t)) score += 1; });
  if (prod.codigo && desc.includes(String(prod.codigo).toUpperCase())) score += 5;
  return score;
}

function _rankProdutos(query) {
  const arr = (produtosEstoque || []).map(p => ({ p, s: _scoreProduto(query, p) }));
  if (query && query.trim()) arr.sort((a, b) => b.s - a.s || (a.p.nome || '').localeCompare(b.p.nome || ''));
  else arr.sort((a, b) => (a.p.nome || '').localeCompare(b.p.nome || ''));
  return arr;
}

function abrirProdCombo(idx) {
  const drop = document.getElementById('ped-item-drop-' + idx);
  if (!drop) return;
  const q = pedidoItens[idx] ? (pedidoItens[idx].descricao || '') : '';
  const ranked = _rankProdutos(q).slice(0, 60);
  if (!ranked.length) {
    drop.innerHTML = '<div style="padding:10px;color:var(--muted);font-size:12px">Nenhum produto cadastrado no estoque</div>';
    drop.style.display = 'block';
    return;
  }
  const temQuery = !!(q && q.trim());
  drop.innerHTML = ranked.map(({ p, s }, i) => {
    const destaque = (temQuery && i === 0 && s > 0) ? 'border-left:3px solid var(--accent);' : 'border-left:3px solid transparent;';
    const label = _produtoLabel(p).replace(/"/g, '&quot;');
    return `<div onmousedown="event.preventDefault();selecionarProdComboItem(${idx}, ${p.id})" title="${label}"
      style="padding:7px 10px;cursor:pointer;font-size:12px;border-bottom:1px solid var(--border);${destaque}white-space:nowrap;overflow:hidden;text-overflow:ellipsis"
      onmouseover="this.style.background='var(--surface)'" onmouseout="this.style.background='transparent'">
      ${_produtoLabel(p)} <span style="color:var(--muted)">· ${fmtNum(p.quantidade_atual || 0)} ${p.unidade || ''}</span>
    </div>`;
  }).join('');
  drop.style.display = 'block';
}

function toggleProdCombo(idx) {
  const d = document.getElementById('ped-item-drop-' + idx);
  if (d && d.style.display === 'block') { d.style.display = 'none'; }
  else { abrirProdCombo(idx); const inp = document.getElementById('ped-item-input-' + idx); if (inp) inp.focus(); }
}

function fecharProdCombo(idx) { const d = document.getElementById('ped-item-drop-' + idx); if (d) d.style.display = 'none'; }
function fecharProdComboDelayed(idx) { setTimeout(() => fecharProdCombo(idx), 150); }

function selecionarProdComboItem(idx, prodId) {
  const p = (produtosEstoque || []).find(x => x.id === prodId);
  if (!p || !pedidoItens[idx]) return;
  pedidoItens[idx].descricao = p.nome;
  pedidoItens[idx].produto_id = p.id;
  const opts = ['unidade', 'und', 'milheiro', 'kg', 'litro', 'metro', 'caixa', 'pacote'];
  if (p.unidade && opts.includes(p.unidade)) pedidoItens[idx].unidade = p.unidade;
  fecharProdCombo(idx);
  renderItensPedido();
}
window.abrirProdCombo = abrirProdCombo;
window.toggleProdCombo = toggleProdCombo;
window.fecharProdComboDelayed = fecharProdComboDelayed;
window.selecionarProdComboItem = selecionarProdComboItem;

function renderItensPedido() {
  const el=document.getElementById('ped-itens-list');
  if(!el) return;
  if(!pedidoItens.length){el.innerHTML='<p style="color:var(--muted);font-size:13px;padding:8px 0">Nenhum item</p>';return;}
  el.innerHTML=pedidoItens.map((item,idx)=>`
    <div style="display:grid;grid-template-columns:1fr auto auto auto;gap:8px;align-items:center;margin-bottom:8px">
      <div style="position:relative;min-width:0">
        <input type="text" id="ped-item-input-${idx}" value="${(item.descricao||'').replace(/"/g,'&quot;')}" autocomplete="off"
          placeholder="Clique na seta ▼ para ver os produtos, ou digite *"
          oninput="pedidoItens[${idx}].descricao=this.value; abrirProdCombo(${idx})"
          onfocus="abrirProdCombo(${idx})" onblur="fecharProdComboDelayed(${idx})"
          style="font-size:13px;width:100%;padding-right:30px">
        <span onmousedown="event.preventDefault();toggleProdCombo(${idx})" title="Ver produtos do estoque"
          style="position:absolute;right:6px;top:50%;transform:translateY(-50%);cursor:pointer;color:var(--text);font-size:11px;padding:4px;user-select:none">▼</span>
        <div id="ped-item-drop-${idx}" style="display:none;position:absolute;z-index:60;left:0;right:0;top:calc(100% + 2px);background:var(--surface2);border:1px solid var(--border);border-radius:6px;max-height:240px;overflow-y:auto;box-shadow:0 8px 24px rgba(0,0,0,.45)"></div>
      </div>
      <input type="number" value="${item.quantidade}" min="1" placeholder="Qtd" oninput="pedidoItens[${idx}].quantidade=+this.value" style="width:80px;font-size:13px">
      <select onchange="pedidoItens[${idx}].unidade=this.value" style="font-size:13px">
        ${['unidade','und','milheiro','kg','litro','metro','caixa','pacote'].map(u=>`<option value="${u}" ${item.unidade===u?'selected':''}>${u}</option>`).join('')}
      </select>
      <button class="btn btn-sm btn-danger" onclick="pedidoItens.splice(${idx},1);renderItensPedido()">✕</button>
    </div>`).join('');
}

function addItemPedido(){pedidoItens.push({descricao:'',quantidade:1,unidade:'unidade'});renderItensPedido();}

async function editPedido(id) {
  const p = await api('/pedidos/' + id);
  document.getElementById('ped-id').value = p.id;
  document.getElementById('ped-numero').value = p.numero_pedido;
  document.getElementById('ped-prazo').value = p.prazo_entrega;
  
  const clientes = await api('/pedidos/clientes');
  document.getElementById('ped-cliente').innerHTML = clientes.map(c => `<option value="${c.id}">${c.razao_social}${c.nome_fantasia ? ' — ' + c.nome_fantasia : ''}</option>`).join('');
  document.getElementById('ped-cliente').value = p.cliente_id;
  
  document.getElementById('ped-vendedor').value = p.vendedor || '';
  document.getElementById('ped-obs').value = p.observacoes || '';
  
  pedidoItens = p.itens.map(i => ({
    descricao: i.descricao,
    quantidade: i.quantidade,
    unidade: i.unidade || 'unidade',
    produto_id: i.produto_id
  }));
  
  await carregarProdutosEstoque();
  renderItensPedido();
  document.getElementById('modal-ped-title').textContent = 'Editar Pedido';
  openModal('modal-pedido');
}
window.editPedido = editPedido;

async function salvarPedido() {
  const id = document.getElementById('ped-id').value;
  const body={numero_pedido:document.getElementById('ped-numero').value,cliente_id:+document.getElementById('ped-cliente').value,prazo_entrega:document.getElementById('ped-prazo').value,vendedor:document.getElementById('ped-vendedor').value,observacoes:document.getElementById('ped-obs').value,itens:pedidoItens.filter(i=>i.descricao.trim())};
  if(!body.numero_pedido){showAlert('Informe o número','danger');return;}
  if(!body.prazo_entrega){showAlert('Informe o prazo','danger');return;}
  if(!body.itens.length){showAlert('Adicione ao menos um item','danger');return;}
  try {
    if(id) {
      await api('/pedidos/' + id, 'PUT', body);
      showAlert('Pedido atualizado!');
    } else {
      const resp = await api('/pedidos/','POST',body);
      const alertas = (resp && resp.alertas_estoque) || [];
      if (alertas.length) {
        showAlert('Pedido salvo! ⚠️ Estoque insuficiente: '
          + alertas.map(a=>`${a.produto} (faltam ${fmtNum(a.falta)} ${a.unidade})`).join('; '), 'warn');
      } else {
        showAlert('Pedido salvo!');
      }
    }
    closeModal('modal-pedido');
    loadFila();
    loadPedidos();
    checkAlertasPedidos();
  } catch(e){ showPopup('⚠️ Não foi possível salvar', `<div style="color:#ff6b6b">${e.message}</div>`); }
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
      ${temPermissao('pedidos', 'editar') ? `<button class="btn btn-sm btn-secondary" onclick="editCliente(${c.id})">Editar</button>` : ''}
      ${temPermissao('pedidos', 'deletar') ? `<button class="btn btn-sm btn-danger" onclick="deletarCliente(${c.id})">✕</button>` : ''}
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

function _abreviarRazao(razao){
  if(!razao) return '';
  const suf=new Set(['LTDA','LTDA.','EIRELI','EPP','ME','MEI','SA','S/A','S.A','S.A.','CIA','CIA.','EI','INC','EIRL']);
  const out=[];
  razao.trim().split(/\s+/).forEach(t=>{
    const tu=t.toUpperCase().replace(/^[.,\-/]+|[.,\-/]+$/g,'');
    if(suf.has(tu)) return;
    if((t==='-'||t==='&'||t==='/')&&out.length===0) return;
    out.push(t);
  });
  let s=out.join(' ').replace(/^[\s\-,/&]+|[\s\-,/&]+$/g,'');
  if(!s) s=razao.trim();
  return s.slice(0,60).replace(/\s+$/,'');
}
window._abreviarRazao=_abreviarRazao;

async function buscarCNPJ() {
  const cnpj=document.getElementById('cli-cnpj')?.value.replace(/\D/g,'');
  if(cnpj?.length!==14){showAlert('CNPJ deve ter 14 dígitos','danger');return;}
  try {
    const d=await api('/pedidos/busca-cnpj/'+cnpj);
    const setV=(k,v)=>{const el=document.getElementById('cli-'+k);if(el)el.value=v||'';};
    setV('razao',d.razao_social);
    setV('fantasia', d.nome_fantasia || _abreviarRazao(d.razao_social));
    // E-mail e telefone NÃO são preenchidos pela Receita (costumam ser do contador) — preenchimento manual
    setV('cep',d.cep);setV('logradouro',d.logradouro);
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
  const fantasia = (getV('fantasia').trim()) || _abreviarRazao(getV('razao'));
  const body={cnpj:getV('cnpj').replace(/\D/g,''),razao_social:getV('razao'),nome_fantasia:fantasia,ie:getV('ie'),email:getV('email'),telefone:getV('telefone'),cep:getV('cep').replace(/\D/g,''),logradouro:getV('logradouro'),numero:getV('numero'),complemento:getV('complemento'),bairro:getV('bairro'),cidade:getV('cidade'),uf:getV('uf'),observacoes:getV('obs')};
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

    window.empresaDados = dados;

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
  const btn = document.querySelector('[onclick="salvarPermissoes()"]');
  const textoOriginal = btn?.innerHTML;
  if (btn) { btn.disabled = true; btn.innerHTML = '⏳ Salvando...'; }

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
    if (btn) { btn.innerHTML = '✅ Salvo!'; btn.style.background = 'var(--success)'; }
    setTimeout(() => {
      if (btn) { btn.disabled = false; btn.innerHTML = textoOriginal; btn.style.background = ''; }
    }, 2000);
    permissoesAtuais = body;
    showAlert(d.mensagem);
  } catch(e) {
    if (btn) { btn.disabled = false; btn.innerHTML = textoOriginal; btn.style.background = ''; }
    showAlert('Erro: '+e.message,'danger');
  }
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
  await carregarMetaGlobal();
  loadTopbarWidgets();
  const params = new URLSearchParams(window.location.search);
  const paginaSolicitada = params.get('page') || params.get('pagina');
  const paginaInicial = (paginaSolicitada && paginasLiberadas.includes(paginaSolicitada)) ? paginaSolicitada : (paginasLiberadas[0] || 'dashboard');
  showPage(paginaInicial);
});

// ─── GRÁFICOS ─────────────────────────────────────────────────────────────────

// Caches globais para evitar requisições repetidas ao alternar temas
let _cacheDashboardData = null;
let _cacheDashboardMes = null;

let _cacheGrafPeriodo = null;
let _cacheGrafData = null;
let _cacheAnualData = {};
let _cacheCompData = {};
let _cachePedidosData = null;
let _cacheEstoqueData = null;

const OP_COLORS = ['#3b82f6', '#8b5cf6', '#06b6d4', '#f97316', '#a855f7', '#ec4899', '#6366f1', '#14b8a6', '#f59e0b', '#0284c7'];

function getChartThemeColors() {
  const isLight = document.documentElement.getAttribute('data-theme') === 'light';
  return {
    gridColor: isLight ? '#cbd5e1' : '#2a2f3f',
    textColor: isLight ? '#475569' : '#94a3b8',
    accentColor: isLight ? '#ca8a04' : '#f0b429',
    successColor: isLight ? '#10b981' : '#10b981',
    dangerColor: isLight ? '#ef4444' : '#ef4444',
    infoColor: isLight ? '#3b82f6' : '#3b82f6',
    tooltipBg: isLight ? 'rgba(255, 255, 255, 0.96)' : 'rgba(22, 25, 32, 0.96)',
    tooltipText: isLight ? '#0f172a' : '#e8eaf0',
    tooltipBorder: isLight ? '#cbd5e1' : '#2a2f3f'
  };
}

function hexToRgba(hex, alpha) {
  if (typeof hex !== 'string') return hex;
  hex = hex.replace('#', '');
  if (hex.length === 3) {
    hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2];
  }
  const r = parseInt(hex.slice(0, 2), 16);
  const g = parseInt(hex.slice(2, 4), 16);
  const b = parseInt(hex.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function getGradientHelper(colorHex, alphaStart = 0.85, alphaEnd = 0.25) {
  return (context) => {
    const chart = context.chart;
    const { ctx, chartArea } = chart;
    if (!chartArea) return hexToRgba(colorHex, alphaStart);
    const gradient = ctx.createLinearGradient(0, chartArea.bottom, 0, chartArea.top);
    gradient.addColorStop(0, hexToRgba(colorHex, alphaEnd));
    gradient.addColorStop(1, hexToRgba(colorHex, alphaStart));
    return gradient;
  };
}

function getChartBaseOptions(colors) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        labels: {
          color: colors.textColor,
          font: { family: 'DM Sans', size: 12, weight: '500' }
        }
      },
      tooltip: {
        mode: 'index',
        intersect: false,
        backgroundColor: colors.tooltipBg,
        titleColor: colors.tooltipText,
        bodyColor: colors.tooltipText,
        borderColor: colors.tooltipBorder,
        borderWidth: 1,
        padding: 12,
        boxPadding: 8,
        usePointStyle: true,
        titleFont: { family: 'DM Sans', size: 13, weight: '700' },
        bodyFont: { family: 'DM Sans', size: 12 }
      },
      datalabels: {
        display: false
      }
    },
    scales: {
      x: {
        ticks: {
          color: colors.textColor,
          font: { family: 'DM Sans', size: 11 }
        },
        grid: {
          color: colors.gridColor
        }
      },
      y: {
        ticks: {
          color: colors.textColor,
          font: { family: 'DM Sans', size: 11 }
        },
        grid: {
          color: colors.gridColor
        }
      }
    }
  };
}

const grafCharts = {};
function destroyGrafChart(id) { if(grafCharts[id]){grafCharts[id].destroy();delete grafCharts[id];} }

// ── Helpers de melhoria dos Gráficos ─────────────────────────────────────────
let _grafPluginPronto = false;
function _hexLum(hex) {
  if (typeof hex !== 'string') return 0;
  hex = hex.replace('#','').slice(0,6);
  if (hex.length < 6) return 0;
  const r=parseInt(hex.slice(0,2),16), g=parseInt(hex.slice(2,4),16), b=parseInt(hex.slice(4,6),16);
  return (0.299*r + 0.587*g + 0.114*b) / 255;
}
function _dlBg(ctx) {
  let bg = ctx.dataset.backgroundColor;
  if (typeof bg === 'function') {
    bg = bg(ctx);
  }
  if (Array.isArray(bg)) bg = bg[ctx.dataIndex];
  return bg;
}
function _dlColor(ctx)  {
  const bg = _dlBg(ctx);
  if (typeof bg === 'string' && bg.startsWith('#')) {
    return _hexLum(bg) > 0.55 ? '#0f172a' : '#ffffff';
  }
  return '#ffffff';
}
function _dlStroke(ctx) { return _dlColor(ctx) === '#ffffff' ? '#0f172a' : '#ffffff'; }

function _grafInitPlugin() {
  if (_grafPluginPronto) return;
  try {
    if (window.Chart && window.ChartDataLabels) {
      Chart.register(window.ChartDataLabels);
      Chart.defaults.set('plugins.datalabels', { display: false });
    }
  } catch(e) {}
  _grafPluginPronto = true;
}

// Garante que o canvas esteja dentro de uma caixa de altura fixa e posição relativa,
// para que maintainAspectRatio:false respeite a altura (sem isso, o Chart.js estica).
function ensureChartBox(canvasId, altura) {
  const c = document.getElementById(canvasId);
  if (!c) return;
  let box = c.parentElement;
  if (!box || !box.classList || !box.classList.contains('graf-box')) {
    box = document.createElement('div');
    box.className = 'graf-box';
    box.style.position = 'relative';
    box.style.width = '100%';
    c.parentNode.insertBefore(box, c);
    box.appendChild(c);
  }
  box.style.height = altura + 'px';
  // remove eventual mensagem de vazio/erro anterior
  const msg = box.querySelector('.graf-msg');
  if (msg) msg.remove();
  c.style.display = '';
}

// Mostra mensagem (vazio ou erro) dentro da caixa do gráfico, escondendo o canvas.
function grafBoxMsg(canvasId, texto, isErro) {
  destroyGrafChart(canvasId.replace('chart-',''));
  const c = document.getElementById(canvasId);
  if (!c) return;
  const box = c.parentElement;
  if (!box) return;
  c.style.display = 'none';
  let msg = box.querySelector('.graf-msg');
  if (!msg) {
    msg = document.createElement('div');
    msg.className = 'graf-msg';
    msg.style.cssText = 'position:absolute;inset:0;display:flex;align-items:center;justify-content:center;text-align:center;font-size:13px;padding:12px';
    box.appendChild(msg);
  }
  msg.style.color = isErro ? 'var(--danger)' : 'var(--muted)';
  msg.textContent = texto;
}

// Overlay de carregamento sobre toda a área de gráficos.
function grafLoading(mostrar) {
  const cont = document.getElementById('graf-content');
  if (!cont) return;
  let ov = document.getElementById('graf-loading-overlay');
  if (mostrar) {
    if (!ov) {
      cont.style.position = cont.style.position || 'relative';
      ov = document.createElement('div');
      ov.id = 'graf-loading-overlay';
      ov.style.cssText = 'position:absolute;inset:0;background:rgba(10,12,18,.55);backdrop-filter:blur(1px);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;z-index:20;border-radius:12px';
      ov.innerHTML = '<div class="spinner"></div><div style="font-size:13px;color:var(--muted)">Carregando gráficos…</div>';
      cont.appendChild(ov);
    }
    ov.style.display = 'flex';
  } else if (ov) {
    ov.style.display = 'none';
  }
}


async function loadGraficoComparativo(options = {}) {
  const ano1El = document.getElementById('graf-comp-ano1');
  const ano2El = document.getElementById('graf-comp-ano2');
  if(!ano1El || !ano2El) return;
  const ano1 = ano1El.value;
  const ano2 = ano2El.value;
  
  const colors = getChartThemeColors();
  const MESES=['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];
  const DIAS_UTEIS=[22,20,21,22,21,21,23,22,21,23,21,21];
  try {
    const useCache = options.useCache === true;
    const cacheKey = `${ano1}_${ano2}`;
    let data;
    if (useCache && _cacheCompData[cacheKey]) {
      data = _cacheCompData[cacheKey];
    } else {
      const [dados1, dados2] = await Promise.all([
        api('/relatorios/resumo-anual/'+ano1),
        ano2!==ano1 ? api('/relatorios/resumo-anual/'+ano2) : Promise.resolve([])
      ]);
      data = [dados1, dados2];
      _cacheCompData[cacheKey] = data;
    }
    const [dados1, dados2] = data;
    const totais1=MESES.map((_,i)=>{const m=`${ano1}-${String(i+1).padStart(2,'0')}`;const r=dados1.find(d=>d.mes_referencia===m);return r?(r.total_producao||0):0;});
    const totais2=MESES.map((_,i)=>{const m=`${ano2}-${String(i+1).padStart(2,'0')}`;const r=dados2.find(d=>d.mes_referencia===m);return r?(r.total_producao||0):0;});
    const metas=DIAS_UTEIS.map(d=>8000*d);

    destroyGrafChart('comparativo-anual');
    const datasets=[{
      label:`${ano1}`,
      data:totais1,
      backgroundColor: getGradientHelper(colors.accentColor, 0.85, 0.25),
      borderColor: colors.accentColor,
      borderWidth: 1.5,
      borderRadius: 5
    }];
    if(ano2!==ano1) datasets.push({
      label:`${ano2}`,
      data:totais2,
      backgroundColor: getGradientHelper(colors.infoColor, 0.85, 0.25),
      borderColor: colors.infoColor,
      borderWidth: 1.5,
      borderRadius: 5
    });
    datasets.push({label:'Meta mensal',data:metas,type:'line',borderColor:colors.dangerColor,borderDash:[8,4],borderWidth:2.5,pointRadius:0,fill:false});

    const canvas = document.getElementById('chart-comparativo-anual');
    if(!canvas) return;
    _grafInitPlugin();
    ensureChartBox('chart-comparativo-anual', 320);
    
    const baseOpts = getChartBaseOptions(colors);
    grafCharts['comparativo-anual']=new Chart(canvas,{
      type:'bar',data:{labels:MESES,datasets},
      options:{
        ...baseOpts,
        plugins:{
          ...baseOpts.plugins,
          tooltip:{
            ...baseOpts.plugins.tooltip,
            callbacks:{label:ctx=>`${ctx.dataset.label}: ${fmtNum(ctx.raw)} peças`}
          },
          datalabels:{display:ctx=>ctx.dataset.type!=='line'&&(ctx.dataset.data[ctx.dataIndex]||0)>0,anchor:'center',align:'center',rotation:0,clamp:true,color:_dlColor,textStrokeColor:_dlStroke,textStrokeWidth:3,font:{family:'DM Sans',size:11,weight:'700'},formatter:v=>fmtNum(v)}
        },
        scales:{
          x:{
            ticks:{color:colors.textColor,font:{family:'DM Sans'}},
            grid:{color:colors.gridColor}
          },
          y:{
            ticks:{color:colors.textColor,callback:v=>fmtNum(v),font:{family:'DM Sans'}},
            grid:{color:colors.gridColor},
            title:{display:true,text:'Total de peças',color:colors.textColor,font:{family:'DM Sans',weight:'700'}}
          }
        }
      }
    });

    // Insights
    const total1=totais1.reduce((s,v)=>s+v,0);
    const total2=totais2.reduce((s,v)=>s+v,0);
    const cresc=total1>0&&ano2!==ano1?(((total2-total1)/total1)*100).toFixed(1):null;
    const melhorMes1=totais1.indexOf(Math.max(...totais1));
    const mesesAbaixo1=totais1.filter((v,i)=>v>0&&v<metas[i]).length;
    const mesesAbaixo2=ano2!==ano1?totais2.filter((v,i)=>v>0&&v<metas[i]).length:null;

    const insightsEl=document.getElementById('graf-comp-insights');
    if(insightsEl) insightsEl.innerHTML=`
      <div style="background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:14px">
        <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:6px">${cresc!==null?`📈 Variação ${ano1} → ${ano2}`:`📦 Total ${ano1}`}</div>
        ${cresc!==null
          ?`<div style="font-family:var(--font-head);font-size:22px;font-weight:800;color:${+cresc>=0?'var(--success)':'var(--danger)'}">${+cresc>=0?'+':''}${cresc}%</div><div style="font-size:12px;color:var(--muted);margin-top:4px">${fmtNum(total1)} → ${fmtNum(total2)} peças</div>`
          :`<div style="font-family:var(--font-head);font-size:22px;font-weight:800;color:var(--accent)">${fmtNum(total1)}</div><div style="font-size:12px;color:var(--muted);margin-top:4px">peças produzidas</div>`
        }
      </div>
      <div style="background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:14px">
        <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:6px">🏆 Melhor mês (${ano1})</div>
        <div style="font-family:var(--font-head);font-size:22px;font-weight:800;color:var(--accent)">${MESES[melhorMes1]}</div>
        <div style="font-size:12px;color:var(--muted);margin-top:4px">${fmtNum(totais1[melhorMes1])} peças</div>
      </div>
      <div style="background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:14px">
        <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:6px">⚠️ Meses abaixo da meta</div>
        <div style="font-family:var(--font-head);font-size:22px;font-weight:800;color:${mesesAbaixo1>0?'var(--danger)':'var(--success)'}">${mesesAbaixo1}${mesesAbaixo2!==null?' / '+mesesAbaixo2:''}</div>
        <div style="font-size:12px;color:var(--muted);margin-top:4px">${ano1}${mesesAbaixo2!==null?' / '+ano2:''}</div>
      </div>`;
  } catch(e){console.error('Erro comparativo anual:',e);}
}

async function loadGraficoAnual(options = {}) {
  const anoSel = document.getElementById('graf-ano');
  if(!anoSel) return;
  const ano = anoSel.value || new Date().getFullYear().toString();

  const colors = getChartThemeColors();
  try {
    const useCache = options.useCache === true;
    let dados;
    if (useCache && _cacheAnualData[ano]) {
      dados = _cacheAnualData[ano];
    } else {
      dados = await api('/relatorios/resumo-anual/'+ano);
      _cacheAnualData[ano] = dados;
    }
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

    destroyGrafChart('anual');
    _grafInitPlugin();
    ensureChartBox('chart-anual', 340);
    const baseOpts = getChartBaseOptions(colors);
    grafCharts['anual'] = new Chart(document.getElementById('chart-anual'), {
      type: 'bar',
      data: {
        labels: dados.map(r=>ml(r.mes_referencia)),
        datasets: [
          {
            label: 'Produção', data: dados.map(r=>r.total_producao||0),
            backgroundColor: getGradientHelper(colors.accentColor, 0.8, 0.2), borderColor: colors.accentColor, borderWidth: 1, borderRadius: 4,
            yAxisID: 'y'
          },
          {
            label: 'Perda', data: dados.map(r=>r.total_perda||0),
            backgroundColor: getGradientHelper(colors.dangerColor, 0.8, 0.2), borderColor: colors.dangerColor, borderWidth: 1, borderRadius: 4,
            yAxisID: 'y'
          },
          {
            label: 'Sobra', data: dados.map(r=>r.total_sobra||0),
            backgroundColor: getGradientHelper(colors.successColor, 0.8, 0.2), borderColor: colors.successColor, borderWidth: 1, borderRadius: 4,
            yAxisID: 'y'
          },
          {
            label: 'Média/dia', data: dados.map(r=>Math.round(r.media_diaria||0)),
            type: 'line', borderColor: colors.infoColor, backgroundColor: 'transparent',
            borderWidth: 2, pointRadius: 5, pointBackgroundColor: colors.infoColor,
            tension: 0.4, yAxisID: 'y2'
          }
        ]
      },
      options: {
        ...baseOpts,
        plugins: {
          ...baseOpts.plugins,
          tooltip: {
            ...baseOpts.plugins.tooltip,
            callbacks: { label: ctx => `${ctx.dataset.label}: ${fmtNum(ctx.raw)}` }
          }
        },
        scales: {
          x: { ticks: { color: colors.textColor, font:{family:'DM Sans'} }, grid: { color: colors.gridColor } },
          y: { ticks: { color: colors.textColor, callback: v=>fmtNum(v), font:{family:'DM Sans'} }, grid: { color: colors.gridColor }, title: { display: true, text: 'Peças', color: colors.textColor, font:{family:'DM Sans',weight:'700'} } },
          y2: { position: 'right', ticks: { color: colors.infoColor, callback: v=>fmtNum(v), font:{family:'DM Sans'} }, grid: { display: false }, title: { display: true, text: 'Média/dia', color: colors.infoColor, font:{family:'DM Sans',weight:'700'} } }
        }
      }
    });
  } catch(e) { console.error('Erro gráfico anual:', e); }
}

async function loadGraficos(options = {}) {
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

  const anoSel = document.getElementById('graf-ano');
  const comp1 = document.getElementById('graf-comp-ano1');
  const comp2 = document.getElementById('graf-comp-ano2');
  [anoSel, comp1, comp2].forEach((sel, idx) => {
    if(sel && sel.options.length===0) {
      for(let y=anoAtual; y>=anoAtual-4; y--) {
        const o=document.createElement('option');
        o.value=y; o.textContent=y;
        if(idx===2 ? y===anoAtual-1 : y===anoAtual) o.selected=true;
        sel.appendChild(o);
      }
    }
  });

  _grafInitPlugin();
  grafLoading(true);
  ensureChartBox('chart-total-mes', 360);
  ensureChartBox('chart-evol-producao', 280);
  ensureChartBox('chart-evol-saldo', 280);
  ensureChartBox('chart-evolucao-graf', 300);
  ensureChartBox('chart-comparativo', 300);
  ensureChartBox('chart-perda-idx', 280);
  ensureChartBox('chart-dias-meta', 280);
  ensureChartBox('chart-excedente', 280);
  ensureChartBox('chart-diario-graf', 340);
  ensureChartBox('chart-ranking-graf', 340);
  ensureChartBox('chart-pedidos-status', 280);
  ensureChartBox('chart-prazo', 280);
  ensureChartBox('chart-estoque-cat', 280);
  await Promise.all([loadGraficoAnual(options), loadGraficoComparativo(options)]);

  const colors = getChartThemeColors();
  const gc = colors.gridColor;
  const tc = colors.textColor;
  const ml = m => { const[y,mo]=m.split('-');return['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'][+mo-1]+'/'+y.slice(2); };

  try {
    const useCache = options.useCache === true;
    const cacheKey = `${mesIni}_${mesFim}_${mesAtual}`;
    let data;
    if (useCache && _cacheGrafPeriodo === cacheKey && _cacheGrafData) {
      data = _cacheGrafData;
    } else {
      data = await Promise.all([
        api('/relatorios/resumo-periodo'+periodoQS),
        api('/relatorios/evolucao-mensal'+periodoQS),
        api('/relatorios/ranking-historico'+periodoQS),
        api('/relatorios/producao-diaria/'+mesAtual)
      ]);
      _cacheGrafPeriodo = cacheKey;
      _cacheGrafData = data;
    }
    const [resumoPeriodo, evolucao, ranking, diario] = data;

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
    const baseOptsTotalMes = getChartBaseOptions(colors);
    grafCharts['total-mes'] = new Chart(document.getElementById('chart-total-mes'), {
      type:'bar',
      data:{ labels:meses.map(ml), datasets:ops.map((op,i)=>({
        label:op, data:meses.map(m=>{const r=evolucao.find(r=>r.colaborador===op&&r.mes_referencia===m);return r?r.total_producao:0;}),
        backgroundColor:hexToRgba(OP_COLORS[i%OP_COLORS.length], 0.85), borderColor:OP_COLORS[i%OP_COLORS.length], borderWidth:1, borderRadius:4
      }))},
      options:{
        ...baseOptsTotalMes,
        plugins:{
          ...baseOptsTotalMes.plugins,
          tooltip:{
            ...baseOptsTotalMes.plugins.tooltip,
            callbacks:{label:ctx=>`${ctx.dataset.label}: ${fmtNum(ctx.raw)} pçs`}
          }
        },
        scales:{
          x:{stacked:true,ticks:{color:tc,font:{family:'DM Sans'}},grid:{color:gc}},
          y:{stacked:true,ticks:{color:tc,callback:v=>fmtNum(v),font:{family:'DM Sans'}},grid:{color:gc}}
        }
      }
    });

    // 2. Evolução média diária (linha)
    destroyGrafChart('evolucao-graf');
    const baseOptsEvol = getChartBaseOptions(colors);
    grafCharts['evolucao-graf'] = new Chart(document.getElementById('chart-evolucao-graf'), {
      type:'line',
      data:{ labels:meses.map(ml), datasets:ops.map((op,i)=>({
        label:op, borderColor:OP_COLORS[i%OP_COLORS.length], backgroundColor:'transparent',
        data:meses.map(m=>{const r=evolucao.find(r=>r.colaborador===op&&r.mes_referencia===m);return r?Math.round(r.media_diaria||0):null;}),
        tension:0.4, fill:false, pointRadius:4, pointHoverRadius:7, spanGaps:true
      }))},
      options:{
        ...baseOptsEvol,
        scales:{
          x:{ticks:{color:tc,font:{family:'DM Sans'}},grid:{color:gc}},
          y:{ticks:{color:tc,callback:v=>fmtNum(v),font:{family:'DM Sans'}},grid:{color:gc}}
        }
      }
    });

    // 3. Comparativo média × meta (barras agrupadas)
    destroyGrafChart('comparativo');
    const baseOptsComp = getChartBaseOptions(colors);
    grafCharts['comparativo'] = new Chart(document.getElementById('chart-comparativo'), {
      type:'bar',
      data:{
        labels:ops,
        datasets:[
          {
            label:'Média Geral',
            data:ops.map(op=>{const r=ranking.find(r=>r.colaborador===op);return Math.round(r?.media_geral||0);}),
            backgroundColor:ops.map((_,i)=>hexToRgba(OP_COLORS[i%OP_COLORS.length], 0.85)),
            borderColor:ops.map((_,i)=>OP_COLORS[i%OP_COLORS.length]),
            borderWidth:1,
            borderRadius:6,
            datalabels:{display:true,anchor:'center',align:'center',rotation:0,clamp:true,color:_dlColor,textStrokeColor:_dlStroke,textStrokeWidth:3,font:{family:'DM Sans',size:11,weight:'700'},formatter:v=>v>0?fmtNum(v):''}
          },
          {label:'Meta média', data:ops.map(op=>{const r=ranking.find(r=>r.colaborador===op);return Math.round(r?.media_meta||0);}), type:'line', borderColor:colors.dangerColor, borderDash:[6,3], borderWidth:2, pointRadius:4, fill:false}
        ]
      },
      options:{
        ...baseOptsComp,
        scales:{
          x:{ticks:{color:tc,font:{family:'DM Sans'}},grid:{color:gc}},
          y:{ticks:{color:tc,callback:v=>fmtNum(v),font:{family:'DM Sans'}},grid:{color:gc}}
        }
      }
    });

    // 4. Índice de perda por mês (linha)
    destroyGrafChart('perda-idx');
    const baseOptsPerda = getChartBaseOptions(colors);
    grafCharts['perda-idx'] = new Chart(document.getElementById('chart-perda-idx'), {
      type:'line',
      data:{ labels:meses.map(ml), datasets:ops.map((op,i)=>{
        const dados = meses.map(m=>{
          const r=evolucao.find(r=>r.colaborador===op&&r.mes_referencia===m);
          if(!r||!r.total_producao) return 0;
          return +((r.total_perdas||0)/r.total_producao*100).toFixed(2);
        });
        return {label:op, borderColor:OP_COLORS[i%OP_COLORS.length], backgroundColor:'transparent', data:dados, tension:0.3, pointRadius:4, spanGaps:true};
      })},
      options:{
        ...baseOptsPerda,
        scales:{
          x:{ticks:{color:tc,font:{family:'DM Sans'}},grid:{color:gc}},
          y:{ticks:{color:tc,callback:v=>v+'%',font:{family:'DM Sans'}},grid:{color:gc},title:{display:true,text:'% perda',color:tc,font:{family:'DM Sans',weight:'700'}}}
        }
      }
    });

    // 5. Dias abaixo da meta (barras agrupadas)
    destroyGrafChart('dias-meta');
    const baseOptsDiasMeta = getChartBaseOptions(colors);
    grafCharts['dias-meta'] = new Chart(document.getElementById('chart-dias-meta'), {
      type:'bar',
      data:{ labels:meses.map(ml), datasets:ops.map((op,i)=>({
        label:op,
        data:meses.map(m=>{const r=evolucao.find(r=>r.colaborador===op&&r.mes_referencia===m);
          if(!r) return 0;
          return r.dias_abaixo_meta || Math.max(0,(r.dias_trabalhados||0)-(r.dias_acima_meta||0));
        }),
        backgroundColor:hexToRgba(OP_COLORS[i%OP_COLORS.length], 0.8), borderColor:OP_COLORS[i%OP_COLORS.length], borderWidth:1, borderRadius:4
      }))},
      options:{
        ...baseOptsDiasMeta,
        scales:{
          x:{ticks:{color:tc,font:{family:'DM Sans'}},grid:{color:gc}},
          y:{ticks:{color:tc,font:{family:'DM Sans'}},grid:{color:gc},title:{display:true,text:'dias',color:tc,font:{family:'DM Sans',weight:'700'}}}
        }
      }
    });

    // 6. Excedente acumulado (barras + linha zero)
    destroyGrafChart('excedente');
    const baseOptsExcedente = getChartBaseOptions(colors);
    grafCharts['excedente'] = new Chart(document.getElementById('chart-excedente'), {
      type:'bar',
      data:{ labels:meses.map(ml), datasets:ops.map((op,i)=>({
        label:op,
        data:meses.map(m=>{const r=evolucao.find(r=>r.colaborador===op&&r.mes_referencia===m);return Math.round((r?.excedente_total ?? ((r?.excedente_positivo||0)+(r?.excedente_negativo||0))) || 0);}),
        backgroundColor:meses.map(m=>{
          const r=evolucao.find(r=>r.colaborador===op&&r.mes_referencia===m);
          const val = (r?.excedente_total ?? ((r?.excedente_positivo||0)+(r?.excedente_negativo||0))) || 0;
          return val >= 0 ? hexToRgba(colors.successColor, 0.75) : hexToRgba(colors.dangerColor, 0.75);
        }),
        borderColor:meses.map(m=>{
          const r=evolucao.find(r=>r.colaborador===op&&r.mes_referencia===m);
          const val = (r?.excedente_total ?? ((r?.excedente_positivo||0)+(r?.excedente_negativo||0))) || 0;
          return val >= 0 ? colors.successColor : colors.dangerColor;
        }),
        borderWidth:1, borderRadius:3
      }))},
      options:{
        ...baseOptsExcedente,
        scales:{
          x:{ticks:{color:tc,font:{family:'DM Sans'}},grid:{color:gc}},
          y:{ticks:{color:tc,callback:v=>fmtNum(v),font:{family:'DM Sans'}},grid:{color:gc}}
        }
      }
    });

    // 6b. Evolução mensal — barras simples coloridas + rótulo em cima
    const prodPorMes = meses.map(m => Math.round(evolucao.filter(r=>r.mes_referencia===m).reduce((s,r)=>s+(r.total_producao||0),0)));
    const varProdPct = prodPorMes.map((v,i)=> (i===0 || !(prodPorMes[i-1]>0)) ? null : ((v-prodPorMes[i-1])/prodPorMes[i-1]*100));

    // Saldo (excedente) vem dos lançamentos — mesma base de meta usada no resto do sistema.
    // A meta de cada mês é derivada disso (produção − saldo). Os DOIS gráficos usam esta meta, então batem entre ci.
    const saldoPorMes = meses.map(m => Math.round(evolucao.filter(r=>r.mes_referencia===m).reduce((s,r)=>s+((r.excedente_total ?? ((r.excedente_positivo||0)+(r.excedente_negativo||0)))||0),0)));
    const metaPorMes = prodPorMes.map((v,i)=> Math.max(0, v - saldoPorMes[i]));
    const bateuMeta = saldoPorMes.map(s => s >= 0);
    const devMeta = prodPorMes.map((v,i)=> (metaPorMes[i]>0) ? (saldoPorMes[i]/metaPorMes[i]*100) : null);

    // Gráfico 1: Produção — verde/vermelho pela meta · em cima: % vs meta
    destroyGrafChart('evol-producao');
    grafCharts['evol-producao'] = new Chart(document.getElementById('chart-evol-producao'), {
      type:'bar',
      data:{ labels:meses.map(ml), datasets:[
        { label:'Produção', data:prodPorMes,
          backgroundColor: (context) => {
            const ok = bateuMeta[context.dataIndex];
            const colorHex = ok ? colors.successColor : colors.dangerColor;
            return getGradientHelper(colorHex, 0.85, 0.25)(context);
          },
          borderColor: bateuMeta.map(ok=>ok?colors.successColor:colors.dangerColor), borderWidth:1, borderRadius:6,
          datalabels:{
            display: true,
            anchor: 'end',
            align: 'end',
            offset: 4,
            font: { size: 11, weight: '700', family: 'DM Sans' },
            color: ctx => {
              const d = devMeta[ctx.dataIndex];
              return d == null ? colors.textColor : (d >= 0 ? colors.successColor : colors.dangerColor);
            },
            textStrokeColor: _dlStroke,
            textStrokeWidth: 3,
            formatter: (v, ctx) => {
              const d = devMeta[ctx.dataIndex];
              return d == null ? '' : (d >= 0 ? '+' : '') + Math.abs(d).toFixed(0) + '%';
            }
          }
        }
      ]},
      options:{responsive:true,maintainAspectRatio:false, layout:{padding:{top:24, bottom:8}},
        plugins:{
          legend:{display:false}, 
          tooltip:{
            backgroundColor: colors.tooltipBg,
            titleColor: colors.tooltipText,
            bodyColor: colors.tooltipText,
            borderColor: colors.tooltipBorder,
            borderWidth: 1,
            padding: 10,
            callbacks:{
              label: ctx => {
                const idx = ctx.dataIndex;
                const prod = prodPorMes[idx];
                const meta = metaPorMes[idx];
                const dev = devMeta[idx];
                const varMes = varProdPct[idx];
                
                const lines = [
                  `Produção: ${fmtNum(prod)} pçs`
                ];
                if (meta > 0) {
                  lines.push(`Meta: ${fmtNum(meta)} pçs`);
                  lines.push(`Vs Meta: ${dev >= 0 ? '+' : ''}${dev.toFixed(1)}%`);
                }
                if (varMes !== null) {
                  lines.push(`Vs Mês Ant.: ${varMes >= 0 ? '+' : ''}${varMes.toFixed(1)}%`);
                }
                return lines;
              }
            }
          }
        },
        scales:{ x:{ticks:{color:colors.textColor, font:{family:'DM Sans'}},grid:{color:colors.gridColor}}, y:{beginAtZero:true,ticks:{color:colors.textColor,callback:v=>fmtNum(v), font:{family:'DM Sans'}},grid:{color:colors.gridColor}} }}
    });

    // Gráfico 2: Saldo vs meta — verde se positivo, vermelho se negativo · valor do mês em cima
    destroyGrafChart('evol-saldo');
    grafCharts['evol-saldo'] = new Chart(document.getElementById('chart-evol-saldo'), {
      type:'bar',
      data:{ labels:meses.map(ml), datasets:[
        { label:'Saldo vs meta', data:saldoPorMes,
          backgroundColor: (context) => {
            const val = context.dataset.data[context.dataIndex];
            const colorHex = val >= 0 ? colors.successColor : colors.dangerColor;
            return getGradientHelper(colorHex, 0.85, 0.25)(context);
          },
          borderColor: saldoPorMes.map(v=>v>=0?colors.successColor:colors.dangerColor), borderWidth:1, borderRadius:6,
          datalabels:{ display:true, anchor:'end', align:'end', offset:2, font:{size:11,weight:'700', family:'DM Sans'},
            color:ctx=>{const v=ctx.dataset.data[ctx.dataIndex]; return v>=0?colors.successColor:colors.dangerColor;},
            textStrokeColor:_dlStroke, textStrokeWidth:3,
            formatter:v=>(v>=0?'+':'')+fmtNum(Math.round(v)) } }
      ]},
      options:{responsive:true,maintainAspectRatio:false, layout:{padding:{top:24,bottom:8}},
        plugins:{legend:{display:false}, 
          tooltip:{
            backgroundColor:colors.tooltipBg,
            titleColor:colors.tooltipText,
            bodyColor:colors.tooltipText,
            borderColor:colors.tooltipBorder,
            borderWidth: 1,
            padding: 10,
            callbacks:{label:ctx=>'Saldo: '+(ctx.raw>=0?'+':'')+fmtNum(ctx.raw)+' pçs'}
          }
        },
        scales:{ x:{ticks:{color:colors.textColor, font:{family:'DM Sans'}},grid:{color:colors.gridColor}}, y:{ticks:{color:colors.textColor,callback:v=>fmtNum(v), font:{family:'DM Sans'}},grid:{color:colors.gridColor}} }}
    });

    // 7. Produção diária do mês (stacked!)
    const dias=[...new Set(diario.map(r=>r.data))].sort();
    const opsD=[...new Set(diario.map(r=>r.colaborador))];
    const metaDia=diario[0]?.meta||8000;
    destroyGrafChart('diario-graf');
    const baseOptsDiario = getChartBaseOptions(colors);
    const dsets=opsD.map((op,i)=>({
      label:op,
      data:dias.map(d=>{const r=diario.find(r=>r.colaborador===op&&r.data===d);return r?r.producao:0;}),
      backgroundColor:hexToRgba(OP_COLORS[i%OP_COLORS.length], 0.85),
      borderColor:OP_COLORS[i%OP_COLORS.length],
      borderWidth:1,
      borderRadius:3
    }));
    dsets.push({
      label:`Meta (${fmtNum(metaDia)})`,
      data:dias.map(()=>metaDia),
      type:'line',
      borderColor:colors.dangerColor,
      borderDash:[6,3],
      borderWidth:2.5,
      pointRadius:0,
      fill:false
    });
    grafCharts['diario-graf'] = new Chart(document.getElementById('chart-diario-graf'), {
      type:'bar',
      data:{labels:dias.map(fmtDate),datasets:dsets},
      options:{
        ...baseOptsDiario,
        plugins:{
          ...baseOptsDiario.plugins,
          tooltip:{
            ...baseOptsDiario.plugins.tooltip,
            callbacks:{label:ctx=>`${ctx.dataset.label}: ${fmtNum(ctx.raw)} pçs`}
          }
        },
        scales:{
          x:{stacked:true,ticks:{color:tc,maxRotation:0,font:{family:'DM Sans'}},grid:{color:gc}},
          y:{stacked:true,ticks:{color:tc,callback:v=>fmtNum(v),font:{family:'DM Sans'}},grid:{color:gc}}
        }
      }
    });

    // 8. Ranking histórico horizontal
    destroyGrafChart('ranking-graf');
    const baseOptsRanking = getChartBaseOptions(colors);
    grafCharts['ranking-graf'] = new Chart(document.getElementById('chart-ranking-graf'), {
      type:'bar',
      data:{
        labels:ranking.map(r=>r.colaborador),
        datasets:[{
          label:'Média (pçs/dia)',
          data:ranking.map(r=>Math.round(r.media_geral||0)),
          backgroundColor:ranking.map((_,i)=>hexToRgba(OP_COLORS[i%OP_COLORS.length], 0.85)),
          borderColor:ranking.map((_,i)=>OP_COLORS[i%OP_COLORS.length]),
          borderWidth:1,
          borderRadius:6
        }]
      },
      options:{
        ...baseOptsRanking,
        indexAxis:'y',
        plugins:{
          ...baseOptsRanking.plugins,
          legend:{display:false},
          datalabels:{
            display:true,
            anchor:'center',
            align:'center',
            rotation:0,
            clamp:true,
            color:_dlColor,
            textStrokeColor:_dlStroke,
            textStrokeWidth:3,
            font:{family:'DM Sans',size:12,weight:'700'},
            formatter:v=>v>0?fmtNum(v):''
          }
        },
        scales:{
          x:{ticks:{color:tc,callback:v=>fmtNum(v),font:{family:'DM Sans'}},grid:{color:gc}},
          y:{ticks:{color:tc,font:{family:'DM Sans'}},grid:{color:gc}}
        }
      }
    });

    // Estado "sem dados" — substitui gráficos vazios por mensagem
    if (evolucao.length === 0) ['chart-total-mes','chart-evol-producao','chart-evol-saldo','chart-evolucao-graf','chart-comparativo','chart-perda-idx','chart-dias-meta','chart-excedente'].forEach(id=>grafBoxMsg(id,'Sem dados de produção no período selecionado'));
    if (diario.length === 0) grafBoxMsg('chart-diario-graf','Sem lançamentos neste mês');
    if (ranking.length === 0) grafBoxMsg('chart-ranking-graf','Sem dados para o ranking');

    // 9. Pedidos por status (rosca)
    try {
      let pedidos;
      if (useCache && _cachePedidosData) {
        pedidos = _cachePedidosData;
      } else {
        pedidos = await api('/pedidos/');
        _cachePedidosData = pedidos;
      }
      const sc={aberto:0,em_producao:0,produzido:0,entregue:0};
      pedidos.forEach(p=>{if(sc[p.status]!==undefined)sc[p.status]++;});
      const dlRosca={display:ctx=>(ctx.dataset.data[ctx.dataIndex]||0)>0,color:_dlColor,textStrokeColor:_dlStroke,textStrokeWidth:3,font:{weight:'700',size:13},formatter:v=>v>0?v:''};
      if (pedidos.length === 0) {
        grafBoxMsg('chart-pedidos-status','Nenhum pedido cadastrado');
        grafBoxMsg('chart-prazo','Nenhum pedido cadastrado');
      } else {
        destroyGrafChart('pedidos-status');
        const baseOptsPedidos = getChartBaseOptions(colors);
        grafCharts['pedidos-status'] = new Chart(document.getElementById('chart-pedidos-status'), {
          type:'doughnut',
          data:{labels:['Aberto','Em produção','Produzido','Entregue'], datasets:[{data:Object.values(sc), backgroundColor:[hexToRgba(colors.infoColor,0.85), hexToRgba(colors.accentColor,0.85), hexToRgba(colors.successColor,0.85), hexToRgba(colors.textColor,0.6)], borderWidth:0}]},
          options:{
            ...baseOptsPedidos,
            cutout: '75%',
            plugins:{
              ...baseOptsPedidos.plugins,
              legend:{labels:{color:tc,font:{family:'DM Sans'}},position:'bottom'},
              datalabels:dlRosca
            }
          }
        });

        // 10. Prazo: no prazo vs atrasados
        const noPrazo=pedidos.filter(p=>p.status!=='entregue'&&Math.round(p.dias_restantes)>=0).length;
        const atrasados=pedidos.filter(p=>p.status!=='entregue'&&Math.round(p.dias_restantes)<0).length;
        const entregues=pedidos.filter(p=>p.status==='entregue').length;
        destroyGrafChart('prazo');
        const baseOptsPrazo = getChartBaseOptions(colors);
        grafCharts['prazo'] = new Chart(document.getElementById('chart-prazo'), {
          type:'doughnut',
          data:{labels:['No prazo','Atrasados','Entregues'], datasets:[{data:[noPrazo,atrasados,entregues], backgroundColor:[hexToRgba(colors.successColor,0.85), hexToRgba(colors.dangerColor,0.85), hexToRgba(colors.textColor,0.6)], borderWidth:0}]},
          options:{
            ...baseOptsPrazo,
            cutout: '75%',
            plugins:{
              ...baseOptsPrazo.plugins,
              legend:{labels:{color:tc,font:{family:'DM Sans'}},position:'bottom'},
              datalabels:dlRosca
            }
          }
        });
      }
    } catch(e){
      grafBoxMsg('chart-pedidos-status','Erro ao carregar pedidos',true);
      grafBoxMsg('chart-prazo','Erro ao carregar pedidos',true);
    }

    // 11. Estoque por categoria
    try {
      let prods;
      if (useCache && _cacheEstoqueData) {
        prods = _cacheEstoqueData;
      } else {
        prods = await api('/estoque/produtos');
        _cacheEstoqueData = prods;
      }
      const cm={};
      prods.forEach(p=>{const c=p.categoria_nome||'Sem categoria';if(!cm[c])cm[c]=0;cm[c]+=p.quantidade_atual||0;});
      if (Object.keys(cm).length === 0) {
        grafBoxMsg('chart-estoque-cat','Nenhum produto em estoque');
      } else {
        destroyGrafChart('estoque-cat');
        const baseOptsEstoque = getChartBaseOptions(colors);
        grafCharts['estoque-cat'] = new Chart(document.getElementById('chart-estoque-cat'), {
          type:'bar',
          data:{labels:Object.keys(cm), datasets:[{label:'Saldo', data:Object.values(cm), backgroundColor:getGradientHelper(colors.infoColor, 0.85, 0.25), borderColor:colors.infoColor, borderWidth:1, borderRadius:4}]},
           options:{
             ...baseOptsEstoque,
             plugins:{
               ...baseOptsEstoque.plugins,
               legend:{display:false},
               datalabels:{display:true,anchor:'center',align:'center',rotation:0,clamp:true,color:_dlColor,textStrokeColor:_dlStroke,textStrokeWidth:3,font:{family:'DM Sans',size:11,weight:'700'},formatter:v=>v>0?fmtNum(v):''}
             },
             scales:{
               x:{ticks:{color:tc,font:{family:'DM Sans'}},grid:{color:gc}},
               y:{ticks:{color:tc,callback:v=>fmtNum(v),font:{family:'DM Sans'}},grid:{color:gc}}
             }
           }
        });
      }
    } catch(e){
      grafBoxMsg('chart-estoque-cat','Erro ao carregar estoque',true);
    }

  } catch(e) { showAlert('Erro ao carregar gráficos: '+e.message,'danger'); }
  finally { grafLoading(false); }
}

function exportarGraficoPDF() {
  const win=window.open('','_blank');
  const canvases=document.getElementById('graf-content')?.querySelectorAll('canvas')||[];
  let imgs='';
  canvases.forEach(c=>{try{imgs+=`<img src="${c.toDataURL()}" style="width:48%;margin:1%">`;}catch(e){}});
  win.document.write(`<html><head><title>Análise PRATIC</title><style>@page{margin:0}body{font-family:Arial;margin:15mm 15mm 22mm 15mm;counter-reset:page}h2{font-size:16px;color:#333}img{display:inline-block;vertical-align:top}.print-footer{position:fixed;bottom:8mm;left:15mm;right:15mm;border-top:1px solid #ddd;padding-top:6px;display:flex;justify-content:space-between;font-size:10px;color:#777;font-family:Arial,sans-serif;counter-increment:page}.page-number::after{content:counter(page)}</style></head><body>${_getEmpresaHeader('Análise Gráfica')}${imgs}${_getPrintFooter()}</body></html>`);
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

let _produtosBuscaTimer = null;

function loadProdutosDebounced() {
  clearTimeout(_produtosBuscaTimer);
  _produtosBuscaTimer = setTimeout(() => loadProdutos(), 180);
}

function _normBuscaProduto(v) {
  return String(v || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim();
}

function limparFiltrosProdutos() {
  _setVal('est-busca-produto', '');
  _setVal('est-filtro-cat', '');
  _setVal('est-filtro-marca', '');
  _setVal('est-filtro-status', '');
  loadProdutos();
}

function _statusProduto(p) {
  const qtd = Number(p.quantidade_atual || 0);
  const min = Number(p.estoque_minimo || 0);
  if (qtd <= 0) return { texto: 'Falta', classe: 'pill-danger' };
  if (min > 0 && qtd <= min) return { texto: 'Baixo', classe: 'pill-danger' };
  return { texto: 'OK', classe: 'pill-success' };
}

function _filtrarProdutosEstoque(prods) {
  const busca = _normBuscaProduto(_getVal('est-busca-produto'));
  const status = _getVal('est-filtro-status');
  const marca = _getVal('est-filtro-marca');

  return prods.filter(p => {
    const qtd = Number(p.quantidade_atual || 0);
    const min = Number(p.estoque_minimo || 0);

    if (busca) {
      const alvo = _normBuscaProduto([p.codigo, p.nome, p.marca, p.categoria_nome, p.unidade].join(' '));
      if (!alvo.includes(busca)) return false;
    }

    if (marca && String(p.marca || '').trim() !== marca) return false;

    if (status === 'falta' && qtd > 0) return false;
    if (status === 'baixo' && !(min > 0 && qtd > 0 && qtd <= min)) return false;
    if (status === 'ok' && !(qtd > 0 && (min <= 0 || qtd > min))) return false;
    if (status === 'positivo' && !(qtd > 0)) return false;
    if (status === 'sem_minimo' && !(min <= 0)) return false;

    return true;
  });
}

function _popularFiltroMarcasEstoque(prods) {
  const sel = document.getElementById('est-filtro-marca');
  if (!sel) return;
  const atual = sel.value || '';
  const marcas = new Set();
  (prods || []).forEach(p => { const m = String(p.marca || '').trim(); if (m) marcas.add(m); });
  const ordenadas = Array.from(marcas).sort((a, b) => a.localeCompare(b));
  sel.innerHTML = '<option value="">Todas as marcas</option>' +
    ordenadas.map(m => `<option value="${m.replace(/"/g, '&quot;')}" ${m === atual ? 'selected' : ''}>${m}</option>`).join('');
}

function _atualizarSugestoesProdutos(prods) {
  const dl = document.getElementById('est-busca-produtos-list');
  if (!dl) return;
  const opts = [];
  const seen = new Set();
  prods.forEach(p => {
    [p.codigo, p.nome, p.marca, p.categoria_nome].forEach(v => {
      v = String(v || '').trim();
      if (v && !seen.has(v.toLowerCase())) {
        seen.add(v.toLowerCase());
        opts.push(`<option value="${v.replace(/"/g, '&quot;')}"></option>`);
      }
    });
  });
  dl.innerHTML = opts.slice(0, 120).join('');
}

async function loadProdutos() {
  const catId = _getVal('est-filtro-cat');
  let url = '/estoque/produtos';
  if (catId) url += '?categoria_id=' + encodeURIComponent(catId);

  const todos = await api(url);
  _atualizarSugestoesProdutos(todos);
  _popularFiltroMarcasEstoque(todos);

  const prods = _filtrarProdutosEstoque(todos);
  const tbody = document.getElementById('est-produtos-tbody');
  const resumo = document.getElementById('est-produtos-resumo');
  if (!tbody) return;

  const total = todos.length;
  const exibindo = prods.length;
  const falta = todos.filter(p => Number(p.quantidade_atual || 0) <= 0).length;
  const baixo = todos.filter(p => {
    const qtd = Number(p.quantidade_atual || 0);
    const min = Number(p.estoque_minimo || 0);
    return min > 0 && qtd > 0 && qtd <= min;
  }).length;
  if (resumo) resumo.innerHTML = `Exibindo <strong>${exibindo}</strong> de <strong>${total}</strong> produto(s) • Falta: <strong>${falta}</strong> • Estoque baixo: <strong>${baixo}</strong>`;

  if (!prods.length) {
    tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--muted);padding:28px">Nenhum produto encontrado com os filtros selecionados</td></tr>';
    return;
  }

  tbody.innerHTML = prods.map(p => {
    const st = _statusProduto(p);
    return `
    <tr>
      <td><strong>${p.codigo || '—'}</strong></td>
      <td><strong>${p.nome || ''}</strong></td>
      <td>${p.categoria_nome || '—'}</td>
      <td>${p.marca || '—'}</td>
      <td>${p.unidade || 'unidade'}</td>
      <td style="font-weight:700;color:${st.classe==='pill-danger'?'var(--danger)':'var(--text)'}">${fmtNum(p.quantidade_atual || 0)}</td>
      <td>${fmtNum(p.estoque_minimo || 0)}</td>
      <td><span class="pill ${st.classe}">${st.texto}</span></td>
      <td class="flex gap-2">
        ${temPermissao('estoque', 'movimentar') ? `<button class="btn btn-sm btn-secondary" onclick="openModalMovimentacao(${p.id})">📦 Mov.</button>` : ''}
        ${temPermissao('estoque', 'editar') ? `<button class="btn btn-sm btn-secondary" onclick="editProduto(${p.id})">✏️</button>` : ''}
        ${temPermissao('estoque', 'deletar') ? `<button class="btn btn-sm btn-danger" onclick="deletarProduto(${p.id})">✕</button>` : ''}
      </td>
    </tr>`;
  }).join('');
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
  const dataInicio = _getVal('est-filtro-data-ini');
  const dataFim = _getVal('est-filtro-data-fim');
  
  let url = '/estoque/movimentacoes';
  const params = [];
  if (tipo) params.push('tipo=' + encodeURIComponent(tipo));
  if (dataInicio) params.push('data_inicio=' + encodeURIComponent(dataInicio));
  if (dataFim) params.push('data_fim=' + encodeURIComponent(dataFim));
  
  if (params.length) {
    url += '?' + params.join('&');
  }
  
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
      <td>${temPermissao('estoque', 'deletar') ? `<button class="btn btn-sm btn-danger" onclick="deletarMovimentacao(${m.id})">✕</button>` : ''}</td>
    </tr>`).join('');
}

function setFiltroPeriodoMovimentacoes(periodo) {
  const hoje = new Date();
  const formatLocal = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  let ini = '';
  let fim = '';
  
  if (periodo === 'hoje') {
    const formatted = formatLocal(hoje);
    ini = formatted;
    fim = formatted;
  } else if (periodo === 'ontem') {
    const ontem = new Date();
    ontem.setDate(hoje.getDate() - 1);
    const formatted = formatLocal(ontem);
    ini = formatted;
    fim = formatted;
  } else if (periodo === 'mes') {
    const y = hoje.getFullYear();
    const m = hoje.getMonth();
    ini = formatLocal(new Date(y, m, 1));
    fim = formatLocal(hoje);
  }
  
  _setVal('est-filtro-data-ini', ini);
  _setVal('est-filtro-data-fim', fim);
  loadMovimentacoes();
}

function gerarRelatorioMovimentacoes() {
  const tipo = _getVal('est-filtro-tipo');
  const dataInicio = _getVal('est-filtro-data-ini');
  const dataFim = _getVal('est-filtro-data-fim');
  
  const tipoLabel = {
    '': 'Todos os tipos',
    'entrada': 'Entradas',
    'saida': 'Saídas',
    'perda': 'Perdas',
    'ajuste': 'Ajustes',
    'sobra': 'Sobras'
  }[tipo || ''] || 'Todos os tipos';
  
  let periodoStr = 'Todo o período';
  if (dataInicio && dataFim) {
    periodoStr = `Período: ${fmtDate(dataInicio)} até ${fmtDate(dataFim)}`;
  } else if (dataInicio) {
    periodoStr = `A partir de: ${fmtDate(dataInicio)}`;
  } else if (dataFim) {
    periodoStr = `Até: ${fmtDate(dataFim)}`;
  }
  
  const tituloReport = `Relatório de Movimentações (${tipoLabel})`;
  const tbody = document.getElementById('est-movs-tbody');
  if (!tbody || tbody.rows.length === 0 || tbody.rows[0].cells[0].textContent.includes('Nenhuma movimentação')) {
    showAlert('Não há dados para gerar o relatório com os filtros atuais.', 'warning');
    return;
  }
  
  let rowsHtml = '';
  Array.from(tbody.rows).forEach(row => {
    let cellsHtml = '';
    const cells = Array.from(row.cells);
    for (let i = 0; i < cells.length - 1; i++) {
      cellsHtml += `<td style="padding:7px;border-bottom:1px solid #ddd;font-family:Arial,sans-serif;">${cells[i].innerHTML}</td>`;
    }
    rowsHtml += `<tr>${cellsHtml}</tr>`;
  });

  const tableHtml = `
    <div style="font-family:Arial,sans-serif;margin-bottom:12px;font-size:13px;color:#333;"><strong>${periodoStr}</strong></div>
    <table style="width:100%;border-collapse:collapse;margin-top:10px;">
      <thead>
        <tr style="background:#333;color:#fff;">
          <th style="padding:8px;text-align:left;font-family:Arial,sans-serif;">Data</th>
          <th style="padding:8px;text-align:left;font-family:Arial,sans-serif;">Código/ID</th>
          <th style="padding:8px;text-align:left;font-family:Arial,sans-serif;">Produto</th>
          <th style="padding:8px;text-align:left;font-family:Arial,sans-serif;">Tipo</th>
          <th style="padding:8px;text-align:left;font-family:Arial,sans-serif;">Quantidade</th>
          <th style="padding:8px;text-align:left;font-family:Arial,sans-serif;">Saldo Anterior</th>
          <th style="padding:8px;text-align:left;font-family:Arial,sans-serif;">Saldo Atual</th>
          <th style="padding:8px;text-align:left;font-family:Arial,sans-serif;">Responsável</th>
        </tr>
      </thead>
      <tbody>
        ${rowsHtml}
      </tbody>
    </table>
  `;

  const win = window.open('', '_blank');
  win.document.write(`<html><head><title>${tituloReport}</title><style>@page{margin:0}body{font-family:Arial,sans-serif;margin:15mm 15mm 22mm 15mm;font-size:12px;counter-reset:page}.print-footer{position:fixed;bottom:8mm;left:15mm;right:15mm;border-top:1px solid #ddd;padding-top:6px;display:flex;justify-content:space-between;font-size:10px;color:#777;font-family:Arial,sans-serif;counter-increment:page}.page-number::after{content:counter(page)}span.pill{background:#e2e8f0;padding:2px 6px;border-radius:4px;font-size:11px;font-weight:bold;color:#475569;text-transform:uppercase;}</style></head><body>${_getEmpresaHeader(tituloReport)}${tableHtml}${_getPrintFooter()}</body></html>`);
  win.document.close();
  setTimeout(() => win.print(), 500);
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
      <td><strong>${c.nome || ''}</strong> ${c.tipo === 'revenda' ? '<span style="margin-left:8px;font-size:11px;padding:2px 8px;border-radius:10px;background:rgba(59,130,246,.15);color:#3b82f6">🛒 Revenda</span>' : '<span style="margin-left:8px;font-size:11px;padding:2px 8px;border-radius:10px;background:var(--surface2);color:var(--muted)">Produção</span>'}</td>
      <td>${c.descricao || '—'}</td>
      <td class="flex gap-2">
        ${temPermissao('estoque', 'editar') ? `<button class="btn btn-sm btn-secondary" onclick="editCategoria(${c.id})">✏️</button>` : ''}
        ${temPermissao('estoque', 'deletar') ? `<button class="btn btn-sm btn-danger" onclick="deletarCategoria(${c.id})">✕</button>` : ''}
      </td>
    </tr>`).join('');
}

function _ensureCatTipoField() {
  if (document.getElementById('est-cat-tipo')) return;
  const grid = document.querySelector('#modal-categoria .form-grid');
  if (!grid) return;
  const g = document.createElement('div');
  g.className = 'form-group';
  g.style.gridColumn = '1/-1';
  g.innerHTML = '<label>Tipo da categoria</label>'
    + '<select id="est-cat-tipo">'
    + '<option value="producao">Produção (fabricado pela empresa)</option>'
    + '<option value="revenda">Revenda (não produzido — comprado pronto)</option>'
    + '</select>';
  grid.appendChild(g);
}

async function openModalCategoria() {
  _setVal('est-cat-id', '');
  _setVal('est-cat-nome', '');
  _setVal('est-cat-desc', '');
  _ensureCatTipoField();
  _setVal('est-cat-tipo', 'producao');
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
  _ensureCatTipoField();
  _setVal('est-cat-tipo', c.tipo || 'producao');
  const ti = document.getElementById('modal-cat-title'); if (ti) ti.textContent = 'Editar Categoria';
  openModal('modal-categoria');
}

async function salvarCategoria() {
  const id = _getVal('est-cat-id');
  const body = { nome: _getVal('est-cat-nome').trim(), descricao: _getVal('est-cat-desc').trim(), tipo: _getVal('est-cat-tipo') || 'producao' };
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
  const raw = String(el.value || '').replace(/\D/g, '');
  let v = raw.slice(0, 14);
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

  // Busca automática de CNPJ ao atingir 14 dígitos
  if (raw.length === 14) {
    if (el.dataset.lastSearched !== raw) {
      el.dataset.lastSearched = raw;
      buscarCNPJ();
    }
  } else {
    delete el.dataset.lastSearched;
  }
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
  ['config','usuarios','permissoes-usr'].forEach(t => {
    const el = document.getElementById('perm-content-' + t);
    const btn = document.getElementById('perm-tab-' + t);
    if (el) el.style.display = t === tab ? '' : 'none';
    if (btn) {
      btn.style.borderColor = t === tab ? 'var(--accent)' : '';
      btn.style.color = t === tab ? 'var(--accent)' : '';
    }
  });
  if (tab === 'usuarios') loadUsuarios();
  if (tab === 'permissoes-usr') loadPermUsuarios();
  if (tab === 'config') loadPermissoes();
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

// ─── SALDO VS DEMANDA ────────────────────────────────────────────────────────

let svdDados = [];

const SVD_CONFIG = {
  critico:     { label: '🔴 Crítico',     pill: 'pill-danger',  cor: 'var(--danger)'  },
  atencao:     { label: '🟡 Atenção',     pill: 'pill-warn',    cor: 'var(--warn)'    },
  ok:          { label: '🟢 OK',          pill: 'pill-success', cor: 'var(--success)' },
  sem_demanda: { label: '⚫ Sem demanda', pill: 'pill-info',    cor: 'var(--muted)'   },
};

async function loadSaldoDemanda() {
  // Popular filtro de categorias
  try {
    const cats = await api('/estoque/categorias');
    const sel = document.getElementById('svd-filtro-cat');
    if (sel && sel.options.length <= 1) {
      cats.forEach(c => {
        const o = document.createElement('option');
        o.value = c.id; o.textContent = c.nome;
        sel.appendChild(o);
      });
    }
  } catch(e) {}

  const catId = document.getElementById('svd-filtro-cat')?.value || '';
  let url = '/estoque/saldo-vs-demanda';
  if (catId) url += '?categoria_id=' + catId;

  try {
    svdDados = await api(url);

    // Filtrar pelas categorias ocultadas (persistidas no backend)
    const ocultas = await _getSvdCategoriasOcultas();
    svdDados = svdDados.filter(r => {
      const catIdStr = r.categoria_id === null || r.categoria_id === undefined ? "null" : String(r.categoria_id);
      return !ocultas.includes(catIdStr);
    });

    // Popular filtro de marcas dinamicamente
    const marcaSel = document.getElementById('svd-filtro-marca');
    if (marcaSel && marcaSel.options.length <= 1) {
      const marcas = [...new Set(svdDados.map(r => r.marca).filter(Boolean))].sort();
      marcas.forEach(m => {
        const o = document.createElement('option');
        o.value = m; o.textContent = m;
        marcaSel.appendChild(o);
      });
    }

    const sit = document.getElementById('svd-filtro-sit')?.value || '';
    const marca = document.getElementById('svd-filtro-marca')?.value || '';
    let filtrado = svdDados;
    if (sit) filtrado = filtrado.filter(r => r.situacao === sit);
    if (marca) filtrado = filtrado.filter(r => r.marca === marca);

    renderSVDKPIs(svdDados);
    renderSVDTabela(filtrado);
    renderSVDAlerta(svdDados);
    checkSVDBadge(svdDados);

    const el = document.getElementById('svd-ultima-atualizacao');
    if (el) el.textContent = '🕐 Atualizado em: ' + new Date().toLocaleString('pt-BR');
  } catch(e) { showAlert('Erro ao carregar Saldo vs Demanda: ' + e.message, 'danger'); }
}

function renderSVDKPIs(dados) {
  const criticos = dados.filter(r => r.situacao === 'critico').length;
  const atencao  = dados.filter(r => r.situacao === 'atencao').length;
  const ok       = dados.filter(r => r.situacao === 'ok').length;
  const total    = dados.filter(r => r.situacao !== 'sem_demanda').length;

  const el = document.getElementById('svd-kpi-cards');
  if (!el) return;
  el.innerHTML = `
    <div class="card" style="border-left:3px solid var(--muted)">
      <div class="card-label">Produtos Monitorados</div>
      <div class="card-value" style="color:var(--text)">${total}</div>
      <div style="font-size:11px;color:var(--muted)">com demanda ativa</div>
    </div>
    <div class="card" style="border-left:3px solid var(--danger)">
      <div class="card-label">🔴 Crítico</div>
      <div class="card-value danger">${criticos}</div>
      <div style="font-size:11px;color:var(--muted)">cobertura &lt; 20% ou negativo</div>
    </div>
    <div class="card" style="border-left:3px solid var(--warn)">
      <div class="card-label">🟡 Atenção</div>
      <div class="card-value" style="color:var(--warn)">${atencao}</div>
      <div style="font-size:11px;color:var(--muted)">cobertura entre 20% e 50%</div>
    </div>
    <div class="card" style="border-left:3px solid var(--success)">
      <div class="card-label">🟢 OK</div>
      <div class="card-value success">${ok}</div>
      <div style="font-size:11px;color:var(--muted)">cobertura acima de 50%</div>
    </div>`;
}

function renderSVDAlerta(dados) {
  const criticos = dados.filter(r => r.situacao === 'critico');
  const banner = document.getElementById('svd-alerta-banner');
  if (!banner) return;
  if (!criticos.length) { banner.innerHTML = ''; return; }
  const lista = criticos.slice(0,5).map(r =>
    `<strong>${r.nome}</strong>: ${fmtNum(r.saldo_projetado)} ${r.unidade}`
  ).join(' &nbsp;|&nbsp; ');
  banner.innerHTML = `
    <div style="background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.3);border-radius:8px;padding:12px 16px;margin-bottom:16px;font-size:13px">
      ⚠️ <strong style="color:var(--danger)">${criticos.length} produto(s) em situação crítica:</strong>
      <span style="color:var(--muted);margin-left:8px">${lista}</span>
    </div>`;
}

function checkSVDBadge(dados) {
  const badge = document.getElementById('nav-svd-badge');
  const criticos = dados.filter(r => r.situacao === 'critico').length;
  if (badge) {
    badge.style.display = criticos > 0 ? 'inline' : 'none';
    badge.textContent = criticos;
  }
  // Badge no dashboard
  const dashEl = document.getElementById('dash-alerta-svd');
  if (dashEl && criticos > 0) {
    const nomes = dados.filter(r=>r.situacao==='critico').slice(0,3).map(r=>r.nome).join(', ');
    dashEl.innerHTML = `
      <div style="background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.3);border-radius:10px;padding:14px 18px;margin-bottom:20px;display:flex;align-items:center;gap:14px">
        <span style="font-size:22px">📊</span>
        <div style="flex:1">
          <div style="font-family:var(--font-head);font-weight:700;color:var(--danger);margin-bottom:4px">${criticos} produto(s) com estoque crítico</div>
          <div style="font-size:13px;color:var(--muted)">${nomes}${criticos>3?' e mais...':''}</div>
        </div>
        <button class="btn btn-sm btn-secondary" onclick="showPage('saldo-demanda')">Ver →</button>
      </div>`;
  } else if (dashEl) dashEl.innerHTML = '';
}

function renderSVDTabela(dados) {
  const tbody = document.getElementById('svd-tbody');
  if (!tbody) return;
  if (!dados.length) {
    tbody.innerHTML = '<tr><td colspan="11" style="text-align:center;color:var(--muted);padding:32px">Nenhum produto encontrado</td></tr>';
    return;
  }
  tbody.innerHTML = dados.map(r => {
    const cfg = SVD_CONFIG[r.situacao] || SVD_CONFIG.ok;
    const pct = Math.min(100, Math.max(0, r.cobertura));
    const barCor = r.situacao === 'critico' ? 'var(--danger)' : r.situacao === 'atencao' ? 'var(--warn)' : 'var(--success)';
    const projCor = r.saldo_projetado < 0 ? 'var(--danger)' : r.saldo_projetado === 0 ? 'var(--warn)' : 'var(--text)';

    return `<tr>
      <td>
        <div style="font-weight:600">${r.nome}${r.marca ? ' <span style="color:var(--muted);font-weight:400">'+r.marca+'</span>' : ''}${r.categoria_tipo === 'revenda' ? ' <span style="font-size:11px;padding:1px 7px;border-radius:9px;background:rgba(59,130,246,.15);color:#3b82f6">🛒 Revenda</span>' : ''}</div>
        ${r.codigo ? `<div style="font-size:11px;color:var(--muted)">${r.codigo}</div>` : ''}
      </td>
      <td style="color:var(--muted)">${r.categoria}</td>
      <td style="font-weight:700">${fmtNum(r.saldo_atual)} <span style="color:var(--muted);font-weight:400;font-size:11px">${r.unidade}</span></td>
      <td style="color:var(--accent2)">${r.qtd_aberto > 0 ? fmtNum(r.qtd_aberto) : '—'}</td>
      <td style="color:var(--warn)">${r.qtd_em_producao > 0 ? fmtNum(r.qtd_em_producao) : '—'}</td>
      <td style="font-weight:600">${r.total_demanda > 0 ? fmtNum(r.total_demanda) : '—'}</td>
      <td style="font-weight:700;color:${projCor}">${r.saldo_projetado < 0 ? '−' : ''}${fmtNum(Math.abs(r.saldo_projetado))}</td>
      <td style="min-width:100px">
        <div style="display:flex;align-items:center;gap:6px">
          <div style="flex:1;height:8px;background:var(--surface2);border-radius:4px;overflow:hidden">
            <div style="height:100%;width:${pct}%;background:${barCor};border-radius:4px;transition:width .3s"></div>
          </div>
          <span style="font-size:12px;font-weight:600;color:${barCor};min-width:36px">${r.situacao==='sem_demanda'?'—':pct.toFixed(0)+'%'}</span>
        </div>
      </td>
      <td>
        ${r.dias_urgente === null || r.dias_urgente === undefined
          ? '<span style="color:var(--muted)">—</span>'
          : r.dias_urgente < 0
            ? `<span style="color:var(--danger);font-weight:700">🔴 Vencido há ${Math.abs(r.dias_urgente)}d</span>`
            : r.dias_urgente === 0
              ? `<span style="color:var(--danger);font-weight:700">🔴 Vence hoje!</span>`
              : r.dias_urgente <= 3
                ? `<span style="color:var(--danger);font-weight:700">🔴 Vence em ${r.dias_urgente}d</span>`
                : r.dias_urgente <= 7
                  ? `<span style="color:var(--warn);font-weight:700">🟡 Vence em ${r.dias_urgente}d</span>`
                  : r.dias_urgente <= 15
                    ? `<span style="color:var(--warn)">🟡 Vence em ${r.dias_urgente}d</span>`
                    : `<span style="color:var(--success)">🟢 Vence em ${r.dias_urgente}d</span>`
        }
      </td>
      <td><span class="pill ${cfg.pill}">${cfg.label}</span></td>
      <td>
        ${r.categoria_tipo === 'revenda' && r.saldo_projetado < 0
          ? `<div style="font-size:11px;font-weight:700;color:#3b82f6;margin-bottom:4px">🛒 Comprar ${fmtNum(Math.abs(r.saldo_projetado))} ${r.unidade}</div>`
          : ''}
        ${r.total_demanda > 0 ? `<button class="btn btn-sm btn-secondary" onclick="verDetalhesSVD(${r.id},'${r.nome.replace(/'/g,"\\'")}')">🔍 Pedidos</button>` : ''}
      </td>
    </tr>`;
  }).join('');
}

async function verDetalhesSVD(prodId, nome) {
  document.getElementById('modal-svd-title').textContent = `📦 ${nome} — Pedidos em Aberto`;
  document.getElementById('modal-svd-content').innerHTML = '<div style="padding:20px;text-align:center;color:var(--muted)">Carregando...</div>';
  openModal('modal-svd-detalhe');

  try {
    const rows = await api(`/estoque/saldo-vs-demanda/${prodId}/pedidos`);
    const STATUS_PILL = { aberto:'pill-info', em_producao:'pill-warn' };
    const STATUS_LABEL = { aberto:'📋 Aberto', em_producao:'🏭 Em produção' };

    document.getElementById('modal-svd-content').innerHTML = rows.length ? `
      <div class="table-wrap">
        <table>
          <thead><tr><th>Nº Pedido</th><th>Cliente</th><th>Item</th><th>Qtd Pedida</th><th>Produzido</th><th>Saldo</th><th>Prazo</th><th>Dias</th><th>Status</th></tr></thead>
          <tbody>${rows.map(r => {
            const cor = r.dias_restantes < 0 ? 'var(--danger)' : r.dias_restantes <= 3 ? 'var(--warn)' : 'var(--success)';
            return `<tr>
              <td><strong>${r.numero_pedido}</strong></td>
              <td>${r.cliente || '—'}</td>
              <td style="color:var(--muted)">${r.descricao}</td>
              <td>${fmtNum(r.quantidade)} ${r.unidade}</td>
              <td>${fmtNum(r.qtd_produzida)}</td>
              <td style="font-weight:700;color:var(--danger)">${fmtNum(r.saldo_item)}</td>
              <td>${fmtDate(r.prazo_entrega)}</td>
              <td style="color:${cor};font-weight:700">${r.dias_restantes < 0 ? 'Vencido' : r.dias_restantes + 'd'}</td>
              <td><span class="pill ${STATUS_PILL[r.status]||'pill-info'}">${STATUS_LABEL[r.status]||r.status}</span></td>
            </tr>`;
          }).join('')}</tbody>
        </table>
      </div>` : '<p style="padding:20px;color:var(--muted);text-align:center">Nenhum pedido em aberto para este produto.</p>';
  } catch(e) {
    document.getElementById('modal-svd-content').innerHTML = `<p style="color:var(--danger);padding:20px">Erro: ${e.message}</p>`;
  }
}

function gerarListaCompras() {
  const criticos = svdDados.filter(r => r.situacao === 'critico' || r.situacao === 'atencao');
  if (!criticos.length) { showAlert('Nenhum produto crítico ou em atenção no momento!'); return; }

  document.getElementById('modal-lista-compras-content').innerHTML = `
    <p style="color:var(--muted);font-size:13px;margin-bottom:16px">
      Produtos que precisam de reposição para atender a demanda atual dos pedidos em aberto.
    </p>
    <div class="table-wrap">
      <table id="lista-compras-table">
        <thead><tr><th>Produto</th><th>Categoria</th><th>Saldo Atual</th><th>Demanda Total</th><th>Déficit</th><th>Sugestão de Compra</th><th>Situação</th></tr></thead>
        <tbody>${criticos.map(r => {
          const deficit = Math.max(0, r.total_demanda - r.saldo_atual);
          const sugestao = deficit + Math.max(r.estoque_minimo || 0, Math.round(r.total_demanda * 0.2));
          const cfg = SVD_CONFIG[r.situacao];
          return `<tr>
            <td><strong>${r.nome}</strong>${r.marca?'<br><span style="font-size:11px;color:var(--muted)">'+r.marca+'</span>':''}</td>
            <td>${r.categoria}</td>
            <td>${fmtNum(r.saldo_atual)} ${r.unidade}</td>
            <td>${fmtNum(r.total_demanda)} ${r.unidade}</td>
            <td style="color:var(--danger);font-weight:700">${deficit > 0 ? fmtNum(deficit) : '—'} ${r.unidade}</td>
            <td style="color:var(--success);font-weight:700">${fmtNum(sugestao)} ${r.unidade}</td>
            <td><span class="pill ${cfg.pill}">${cfg.label}</span></td>
          </tr>`;
        }).join('')}</tbody>
      </table>
    </div>`;
  openModal('modal-lista-compras');
}

function exportarListaCompras(formato) {
  const table = document.getElementById('lista-compras-table');
  if (!table) return;
  if (formato === 'pdf') {
    const win = window.open('','_blank');
    win.document.write(`<html><head><title>Lista de Compras PRATIC</title>
      <style>@page{margin:0}body{font-family:Arial,sans-serif;margin:15mm 15mm 22mm 15mm;font-size:12px;counter-reset:page}table{width:100%;border-collapse:collapse}th{background:#333;color:#fff;padding:8px;text-align:left}td{padding:7px;border-bottom:1px solid #ddd}.print-footer{position:fixed;bottom:8mm;left:15mm;right:15mm;border-top:1px solid #ddd;padding-top:6px;display:flex;justify-content:space-between;font-size:10px;color:#777;font-family:Arial,sans-serif;counter-increment:page}.page-number::after{content:counter(page)}</style>
      </head><body>
      ${_getEmpresaHeader('Lista de Compras')}
      ${table.outerHTML}
      ${_getPrintFooter()}
      </body></html>`);
    win.document.close();
    setTimeout(() => win.print(), 500);
  } else {
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
    a.download = `lista_compras_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
  }
}

function exportarSVD(formato) {
  const table = document.getElementById('svd-table');
  if (!table) return;
  if (formato === 'pdf') {
    const win = window.open('','_blank');
    win.document.write(`<html><head><title>Saldo vs Demanda PRATIC</title>
      <style>@page{margin:0}body{font-family:Arial,sans-serif;margin:15mm 15mm 22mm 15mm;font-size:11px;counter-reset:page}table{width:100%;border-collapse:collapse}th{background:#333;color:#fff;padding:6px;text-align:left}td{padding:5px;border-bottom:1px solid #ddd}.print-footer{position:fixed;bottom:8mm;left:15mm;right:15mm;border-top:1px solid #ddd;padding-top:6px;display:flex;justify-content:space-between;font-size:10px;color:#777;font-family:Arial,sans-serif;counter-increment:page}.page-number::after{content:counter(page)}</style>
      </head><body>
      ${_getEmpresaHeader('Saldo vs Demanda')}
      ${table.outerHTML}
      ${_getPrintFooter()}
      </body></html>`);
    win.document.close();
    setTimeout(() => win.print(), 500);
  } else {
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
    a.download = `saldo_demanda_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
  }
}

async function _getSvdCategoriasOcultas() {
  // Fonte de verdade: backend (persiste entre cargas de página e dispositivos).
  // Salva a lista de categorias desmarcadas/ocultadas.
  // Assim, novas categorias criadas aparecem ativas por padrão.
  try {
    const cfg = await api('/configuracoes/svd_categorias_ocultas');
    if (cfg && cfg.valor) {
      try {
        const arr = JSON.parse(cfg.valor);
        localStorage.setItem('svd_categorias_ocultas', cfg.valor);
        return arr;
      } catch (e) {}
    } else {
      // Tenta migrar da chave antiga svd_categorias_visiveis se existir
      const cfgAntiga = await api('/configuracoes/svd_categorias_visiveis');
      if (cfgAntiga && cfgAntiga.valor) {
        try {
          const visiveis = JSON.parse(cfgAntiga.valor);
          const cats = await api('/estoque/categorias');
          const ocultas = [];
          if (!visiveis.includes('null')) ocultas.push('null');
          cats.forEach(c => {
            if (!visiveis.includes(String(c.id))) {
              ocultas.push(String(c.id));
            }
          });
          const valor = JSON.stringify(ocultas);
          await api('/configuracoes/svd_categorias_ocultas', 'PUT', { valor });
          localStorage.setItem('svd_categorias_ocultas', valor);
          return ocultas;
        } catch (e) {}
      }
      // Se não houver nada no servidor, usa cache local
      const local = localStorage.getItem('svd_categorias_ocultas');
      if (local) { try { return JSON.parse(local); } catch (e) {} }
    }
  } catch (e) {
    const local = localStorage.getItem('svd_categorias_ocultas');
    if (local) { try { return JSON.parse(local); } catch (e2) {} }
  }
  return []; // Por padrão, nenhuma categoria é oculta
}

async function abrirConfigCategoriasSVD() {
  const container = document.getElementById('modal-svd-categorias-content');
  if (!container) return;
  container.innerHTML = '<div style="color:var(--muted);text-align:center;padding:12px">Carregando...</div>';
  openModal('modal-svd-categorias');

  try {
    const cats = await api('/estoque/categorias');
    const ocultas = await _getSvdCategoriasOcultas();

    let html = '';
    
    // Opção "Sem Categoria"
    const semCatChecked = !ocultas.includes('null');
    html += `
      <label style="display:flex;align-items:center;gap:8px;padding:6px 8px;border-radius:4px;cursor:pointer;background:var(--surface2)">
        <input type="checkbox" class="svd-cat-checkbox" value="null" ${semCatChecked ? 'checked' : ''}>
        <span style="font-weight:600;color:var(--text)">📁 Sem Categoria</span>
      </label>
    `;

    // Categorias cadastradas
    cats.forEach(c => {
      const isChecked = !ocultas.includes(String(c.id));
      html += `
        <label style="display:flex;align-items:center;gap:8px;padding:6px 8px;border-radius:4px;cursor:pointer;background:var(--surface2)">
          <input type="checkbox" class="svd-cat-checkbox" value="${c.id}" ${isChecked ? 'checked' : ''}>
          <span>${c.nome}</span>
        </label>
      `;
    });

    container.innerHTML = html;
  } catch (e) {
    container.innerHTML = `<div style="color:var(--danger);padding:12px">Erro ao carregar categorias: ${e.message}</div>`;
  }
}

function marcarTodasCategoriasSVD(marcar) {
  const checkboxes = document.querySelectorAll('.svd-cat-checkbox');
  checkboxes.forEach(cb => cb.checked = marcar);
}

async function aplicarCategoriasSVD() {
  const checkboxes = document.querySelectorAll('.svd-cat-checkbox');
  const ocultas = [];
  checkboxes.forEach(cb => {
    if (!cb.checked) {
      ocultas.push(cb.value);
    }
  });
  const valor = JSON.stringify(ocultas);
  localStorage.setItem('svd_categorias_ocultas', valor);
  try {
    await api('/configuracoes/svd_categorias_ocultas', 'PUT', { valor });
  } catch (e) {
    showAlert('Salvo localmente, mas não foi possível gravar no servidor: ' + e.message, 'danger');
  }
  closeModal('modal-svd-categorias');
  loadSaldoDemanda();
}

// ─── LIMPAR DADOS ─────────────────────────────────────────────────────────────

async function limparDados(tipo) {
  const msgs = {
    producao:    'Isso vai remover TODA a produção diária e premiações. Confirma?',
    pedidos:     'Isso vai remover TODOS os pedidos e itens. Confirma?',
    estoque_mov: 'Isso vai remover todas as movimentações e zerar os saldos. Confirma?',
    tudo:        '⚠️ ATENÇÃO: Isso vai remover TODOS os dados operacionais (produção, pedidos, estoque, EPI). Os cadastros (colaboradores, máquinas, produtos) serão mantidos.\n\nTem CERTEZA?'
  };
  if (!confirm(msgs[tipo])) return;
  if (tipo === 'tudo' && !confirm('Última confirmação: apagar TUDO mesmo?')) return;

  const alertEl = document.getElementById('limpar-alert');
  try {
    const r = await api('/configuracoes/limpar/' + tipo, 'POST', {});
    if (alertEl) {
      alertEl.innerHTML = `<div class="alert alert-success" style="margin-top:8px">✅ ${r.mensagem}</div>`;
      setTimeout(() => alertEl.innerHTML = '', 5000);
    }
    showAlert(r.mensagem);
  } catch(e) {
    if (alertEl) alertEl.innerHTML = `<div class="alert alert-danger">${e.message}</div>`;
    showAlert('Erro: ' + e.message, 'danger');
  }
}

// ─── PERMISSÕES POR USUÁRIO ───────────────────────────────────────────────────

const MODULOS_CONFIG = {
  dashboard:      { label:'📊 Dashboard',         acoes:['ver'] },
  producao:       { label:'🏭 Produção Diária',    acoes:['ver','criar','editar','deletar'] },
  premiacao:      { label:'🏆 Premiação',          acoes:['ver','criar','editar','deletar'] },
  colaboradores:  { label:'👥 Colaboradores',      acoes:['ver','criar','editar','deletar'] },
  maquinas:       { label:'⚙️ Máquinas',           acoes:['ver','criar','editar','deletar'] },
  pedidos:        { label:'🧾 Pedidos',            acoes:['ver','criar','editar','deletar','importar'] },
  estoque:        { label:'📦 Estoque',            acoes:['ver','criar','editar','deletar','movimentar'] },
  epi:            { label:'🦺 EPI',               acoes:['ver','criar','editar','deletar'] },
  'saldo-demanda':{ label:'📊 Saldo vs Demanda',  acoes:['ver'] },
  graficos:       { label:'📈 Gráficos',          acoes:['ver'] },
  relatorios:     { label:'📋 Relatórios',        acoes:['ver','exportar'] },
  configuracoes:  { label:'🔧 Configurações',     acoes:['ver','editar'] },
  backup:         { label:'💾 Backup',            acoes:['backup','restaurar','limpar'] },
  permissoes:     { label:'🔐 Controle de Acesso',acoes:['ver','editar'] },
  empresa:        { label:'🏢 Dados da Empresa',  acoes:['ver','editar'] },
};

const ACAO_LABEL = {
  ver:'Ver', criar:'Criar', editar:'Editar', deletar:'Deletar',
  importar:'Importar', movimentar:'Movimentar', exportar:'Exportar',
  backup:'Backup', restaurar:'Restaurar', limpar:'Limpar'
};

let permUsuarioAtual = {};

async function loadPermUsuarios() {
  try {
    const users = await api('/auth/usuarios');
    const sel = document.getElementById('perm-usr-select');
    if (!sel) return;
    // Resetar para recarregar sempre
    sel.innerHTML = '<option value="">— Selecione um usuário —</option>' +
      users.map(u =>
        `<option value="${u.id}">${u.nome} (${u.username}) — ${u.role}</option>`
      ).join('');
  } catch(e) { console.error('Erro ao carregar usuários:', e); }
}

async function loadPermissoesUsuario() {
  const id = document.getElementById('perm-usr-select')?.value;
  const tabela = document.getElementById('perm-usr-tabela');
  const infoEl = document.getElementById('perm-usr-info');
  if (!id) { if(tabela) tabela.style.display='none'; return; }

  try {
    const [users, perms] = await Promise.all([
      api('/auth/usuarios'),
      api('/auth/usuarios/' + id + '/permissoes')
    ]);
    const usr = users.find(u => u.id == id);
    if (infoEl && usr) infoEl.textContent = `Perfil: ${usr.role} | ${usr.ativo ? 'Ativo' : 'Inativo'}`;
    permUsuarioAtual = perms;
    renderPermUsuarioGrid(perms);
    if (tabela) tabela.style.display = 'block';
  } catch(e) { showAlert('Erro ao carregar permissões: ' + e.message, 'danger'); }
}

function renderPermUsuarioGrid(perms) {
  const el = document.getElementById('perm-usr-grid');
  if (!el) return;

  // Todas as ações possíveis para montar colunas fixas
  const todasAcoes = ['ver','criar','editar','deletar','importar','movimentar','exportar','backup','restaurar','limpar'];

  // Cabeçalho
  let html = `
    <div style="display:grid;grid-template-columns:220px repeat(${todasAcoes.length},1fr);gap:6px;padding:10px 0;border-bottom:2px solid var(--border);margin-bottom:4px">
      <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;font-weight:700">Módulo</div>
      ${todasAcoes.map(a=>`<div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;text-align:center">${ACAO_LABEL[a]||a}</div>`).join('')}
    </div>`;

  html += Object.entries(MODULOS_CONFIG).map(([modulo, cfg]) => {
    const cols = todasAcoes.map(acao => {
      const temAcao = cfg.acoes.includes(acao);
      if (!temAcao) return `<div></div>`;
      const ativo = perms[modulo]?.[acao] ?? false;
      return `<div style="display:flex;justify-content:center;align-items:center">
        <label class="toggle-switch" style="cursor:pointer;position:relative;display:inline-block;width:40px;height:22px">
          <input type="checkbox" id="perm_${modulo}_${acao}" ${ativo?'checked':''}
            onchange="permToggleChanged('${modulo}','${acao}',this.checked)"
            style="opacity:0;width:0;height:0;position:absolute">
          <span id="span_${modulo}_${acao}" style="position:absolute;top:0;left:0;right:0;bottom:0;background:${ativo?'var(--accent)':'var(--surface2)'};border:1px solid ${ativo?'var(--accent)':'var(--border)'};border-radius:22px;transition:.3s;pointer-events:none">
            <span style="position:absolute;height:16px;width:16px;left:${ativo?'20':'2'}px;bottom:2px;background:white;border-radius:50%;transition:.3s"></span>
          </span>
        </label>
      </div>`;
    }).join('');

    return `<div style="display:grid;grid-template-columns:220px repeat(${todasAcoes.length},1fr);gap:6px;align-items:center;padding:10px 0;border-bottom:1px solid var(--border)">
      <div style="font-size:13px;font-weight:500">${cfg.label}</div>
      ${cols}
    </div>`;
  }).join('');

  el.innerHTML = html;
}

function permToggleChanged(modulo, acao, checked) {
  if (!permUsuarioAtual[modulo]) permUsuarioAtual[modulo] = {};
  permUsuarioAtual[modulo][acao] = checked;
  const span = document.getElementById(`span_${modulo}_${acao}`);
  if (span) {
    span.style.background = checked ? 'var(--accent)' : 'var(--surface2)';
    span.style.borderColor = checked ? 'var(--accent)' : 'var(--border)';
    const dot = span.querySelector('span');
    if (dot) dot.style.left = checked ? '20px' : '2px';
  }
}

function permUsuarioTodos(liberar) {
  Object.entries(MODULOS_CONFIG).forEach(([modulo, cfg]) => {
    cfg.acoes.forEach(acao => {
      const cb = document.getElementById(`perm_${modulo}_${acao}`);
      const span = document.getElementById(`span_${modulo}_${acao}`);
      if (cb) cb.checked = liberar;
      if (span) {
        span.style.background = liberar ? 'var(--accent)' : 'var(--surface2)';
        span.style.borderColor = liberar ? 'var(--accent)' : 'var(--border)';
        const dot = span.querySelector('span');
        if (dot) dot.style.left = liberar ? '20px' : '2px';
      }
      if (!permUsuarioAtual[modulo]) permUsuarioAtual[modulo] = {};
      permUsuarioAtual[modulo][acao] = liberar;
    });
  });
}

async function salvarPermissoesUsuario() {
  const id = document.getElementById('perm-usr-select')?.value;
  if (!id) { showAlert('Selecione um usuário', 'danger'); return; }

  // Feedback visual no botão
  const btn = document.querySelector('[onclick="salvarPermissoesUsuario()"]');
  const textoOriginal = btn?.innerHTML;
  if (btn) { btn.disabled = true; btn.innerHTML = '⏳ Salvando...'; }

  // Coletar estado dos toggles
  const body = {};
  Object.entries(MODULOS_CONFIG).forEach(([modulo, cfg]) => {
    body[modulo] = {};
    cfg.acoes.forEach(acao => {
      const el = document.getElementById(`perm_${modulo}_${acao}`);
      body[modulo][acao] = el ? el.checked : false;
    });
  });

  try {
    await api('/auth/usuarios/' + id + '/permissoes', 'PUT', body);
    if (btn) { btn.innerHTML = '✅ Salvo!'; btn.style.background = 'var(--success)'; }
    setTimeout(() => {
      if (btn) { btn.disabled = false; btn.innerHTML = textoOriginal; btn.style.background = ''; }
    }, 2000);
    showAlert('Permissões salvas com sucesso!');
  } catch(e) {
    if (btn) { btn.disabled = false; btn.innerHTML = textoOriginal; btn.style.background = ''; }
    showAlert('Erro: ' + e.message, 'danger');
  }
}

// ─── CARREGAR PERMISSÕES DO USUÁRIO LOGADO ────────────────────────────────────

let minhasPermissoes = null;

async function carregarMinhasPermissoes() {
  try {
    minhasPermissoes = await api('/auth/me/permissoes');
  } catch(e) {
    minhasPermissoes = null;
  }
}

function temPermissao(modulo, acao) {
  if (!minhasPermissoes) return true; // Se não carregou, libera (segurança no backend)
  return minhasPermissoes[modulo]?.[acao] ?? false;
}

function aplicarPermissoesUI() {
  if (!minhasPermissoes) return;
  // Ocultar botões de criar
  document.querySelectorAll('[data-perm-criar]').forEach(el => {
    const modulo = el.getAttribute('data-perm-criar');
    if (!temPermissao(modulo, 'criar')) el.style.display = 'none';
  });
  // Ocultar botões de editar
  document.querySelectorAll('[data-perm-editar]').forEach(el => {
    const modulo = el.getAttribute('data-perm-editar');
    if (!temPermissao(modulo, 'editar')) el.style.display = 'none';
  });
  // Ocultar botões de deletar
  document.querySelectorAll('[data-perm-deletar]').forEach(el => {
    const modulo = el.getAttribute('data-perm-deletar');
    if (!temPermissao(modulo, 'deletar')) el.style.display = 'none';
  });
  // Ocultar botões de importar
  document.querySelectorAll('[data-perm-importar]').forEach(el => {
    const modulo = el.getAttribute('data-perm-importar');
    if (!temPermissao(modulo, 'importar')) el.style.display = 'none';
  });
  // Ocultar botões de movimentar
  document.querySelectorAll('[data-perm-movimentar]').forEach(el => {
    const modulo = el.getAttribute('data-perm-movimentar');
    if (!temPermissao(modulo, 'movimentar')) el.style.display = 'none';
  });
}
