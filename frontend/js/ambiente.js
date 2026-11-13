/* Mostra em que servidor o usuário está. Controlado pela variável PRATIC_AMBIENTE
   no Coolify: "treinamento" (faixa laranja), "teste" (faixa roxa) ou vazio/"producao"
   (nada aparece). Evita lançar pedido real no treino — ou o contrário. */
(function () {
  var CORES = {
    treinamento: { bg: '#f97316', txt: '🎓 AMBIENTE DE TREINAMENTO — nada do que é feito aqui vale de verdade', tit: '🎓 TREINO · ' },
    teste:       { bg: '#7c3aed', txt: '🧪 SERVIDOR DE TESTE — não é o sistema oficial', tit: '🧪 TESTE · ' }
  };
  function aplicar(amb) {
    var c = CORES[amb];
    if (!c || document.getElementById('pratic-ambiente-faixa')) return;
    var f = document.createElement('div');
    f.id = 'pratic-ambiente-faixa';
    f.setAttribute('role', 'status');
    f.textContent = c.txt;
    f.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:2147483000;background:' + c.bg +
      ';color:#fff;font:700 13px/1.2 Arial,Helvetica,sans-serif;text-align:center;padding:7px 10px;' +
      'letter-spacing:.3px;box-shadow:0 -2px 10px rgba(0,0,0,.35);pointer-events:none';
    document.body.appendChild(f);
    document.body.style.paddingBottom = '34px';
    // borda colorida em volta da tela inteira: dá para perceber mesmo sem ler a faixa
    var b = document.createElement('div');
    b.style.cssText = 'position:fixed;inset:0;border:4px solid ' + c.bg + ';pointer-events:none;z-index:2147482999';
    document.body.appendChild(b);
    if (document.title.indexOf(c.tit) !== 0) document.title = c.tit + document.title;
    var obs = new MutationObserver(function () { if (document.title.indexOf(c.tit) !== 0) document.title = c.tit + document.title; });
    var t = document.querySelector('title'); if (t) obs.observe(t, { childList: true });
    window.PRATIC_AMBIENTE = amb;
  }
  function iniciar() {
    fetch('/api/ambiente', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { if (d && d.ambiente) aplicar(String(d.ambiente).toLowerCase()); })
      .catch(function () {});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar); else iniciar();
})();
