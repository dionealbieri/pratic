/* Botões coloridos: dá uma cor a cada botão secundário conforme a ação (pelo texto/ícone).
   Funciona em todas as telas, inclusive nas montadas depois (observa o DOM).
   Para um botão ficar sem cor automática: data-cor="nenhuma". Para forçar: data-cor="azul|verde|..." */
(function () {
  const REGRAS = [
    ['verm',    /🗑|excluir|remover|apagar|cancelar (a |o )?(cota|remessa|pedido|lan)|↩ ?cancelar|desfazer|\bpdf\b/i],
    ['cinza',   /^\W*(fechar|cancelar|voltar|limpar|anterior|próxima|proxima|ocultar|mostrar|sair)\b|^[\s←→◀▶×✕]+$/i],
    ['turq',    /🏷|estoque do cliente|imprimir|🖨|nota fiscal|🧾|\bnf\b/i],
    ['verde',   /✅|✓|entregue|confirm|autoriz|retira|🙋|💾|salvar|concluir|liberar|visto|marcar/i],
    ['roxo',    /✏|editar|alterar|trocar|parcial|✂|corrigir|🔁|acertar|⚙/i],
    ['laranja', /⚠|separar|revenda|🧹|limpeza|📐|embalagem|pendente/i],
    ['azul',    /👁|\bver\b|caixa|📦|cota|detalhe|copiar|📋|busca|🔍|importar|📥|anexar|📎|baixar|⬇|hist[oó]rico|ficha|\+|➕|novo|nova|adicionar|lançar/i],
  ];
  const CORES = ['azul', 'verde', 'roxo', 'laranja', 'turq', 'verm', 'cinza'];
  const PULAR = /\b(btn-primary|btn-neon|btn-full-primary|mp-b-[a-z]+|mp-card)\b/;
  // Variantes antigas viram o mesmo padrão (mesma cor de sempre, novo acabamento)
  const FIXAS = [['btn-danger', 'verm'], ['btn-success', 'verde'], ['btn-info', 'azul'], ['btn-warning', 'laranja']];

  function corDe(b) {
    const forc = b.dataset.cor;
    if (forc) return forc === 'nenhuma' ? null : forc;
    for (const [cls, cor] of FIXAS) if (b.classList.contains(cls)) return cor;
    const t = (b.textContent || '').trim() + ' ' + (b.title || '') + ' ' + (b.getAttribute('aria-label') || '');
    for (const [cor, re] of REGRAS) if (re.test(t)) return cor;
    return 'cinza';
  }
  function pintar(b) {
    if (PULAR.test(b.className)) return;
    if (b.closest('#cot-tipo, .mp-cards')) return;
    if (b.style && b.style.background) return;            // já tem cor própria no código
    const txt = (b.textContent || '').trim();
    if (b.dataset.btTxt === txt && b.classList.contains('bt')) return;
    b.dataset.btTxt = txt;
    const cor = corDe(b);
    CORES.forEach(c => b.classList.remove('bt-' + c));
    if (!cor) { b.classList.remove('bt'); return; }
    b.classList.add('bt', 'bt-' + cor);
  }
  function varrer(raiz) {
    // secundários, variantes antigas (danger/success/info/warning) e .btn sem variante
    (raiz || document).querySelectorAll('.btn.btn-secondary, .btn.btn-danger, .btn.btn-success, .btn.btn-info, .btn.btn-warning, .btn:not(.btn-primary):not(.btn-secondary):not(.btn-danger):not(.btn-success):not(.btn-info):not(.btn-warning):not(.btn-neon)').forEach(pintar);
  }
  let agendado = false;
  function agendar() {
    if (agendado) return;
    agendado = true;
    requestAnimationFrame(() => { agendado = false; varrer(); });
  }
  function iniciar() {
    varrer();
    new MutationObserver(agendar).observe(document.body, { childList: true, subtree: true, characterData: true });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
  window.pintarBotoes = varrer;
})();
