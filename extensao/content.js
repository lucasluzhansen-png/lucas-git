// Mascote do Maestro dentro do Clinus: canto inferior, arrastável, com balão e botões.
(() => {
  if (document.getElementById("maestro-hansen")) return;
  const ADIAR_MIN = 30;
  const raiz = document.createElement("div");
  raiz.id = "maestro-hansen";
  raiz.innerHTML = '<div class="mh-balao" hidden><div class="mh-texto"></div><div class="mh-botoes"></div></div><div class="mh-mascote" title="Maestro (arraste para mover)"><svg viewBox="0 0 80 80" width="56" height="56" role="img" aria-label="Maestro"><path d="M26 10c-9 0-14 9-12 20 1 8 4 16 7 25 1 4 5 4 6 0l4-14c1-3 6-3 7 0l4 14c1 4 5 4 6 0 3-9 6-17 7-25 2-11-3-20-12-20-5 0-7 2-10 2s-5-2-10-2z" fill="#fff" stroke="#0E5E63" stroke-width="3" stroke-linejoin="round"/><circle cx="31" cy="26" r="2.4" fill="#0E5E63"/><circle cx="45" cy="26" r="2.4" fill="#0E5E63"/><path d="M32 34q6 6 12 0" fill="none" stroke="#0E5E63" stroke-width="2.6" stroke-linecap="round"/><path d="M58 30l16-18" stroke="#c28a2c" stroke-width="3.5" stroke-linecap="round"/><circle cx="75" cy="11" r="3" fill="#c28a2c"/></svg><span class="mh-ponto" hidden></span></div>';
  document.documentElement.appendChild(raiz);
  const balao = raiz.querySelector(".mh-balao"), texto = raiz.querySelector(".mh-texto");
  const botoes = raiz.querySelector(".mh-botoes"), ponto = raiz.querySelector(".mh-ponto"), mascote = raiz.querySelector(".mh-mascote");

  const ler = (k, d) => new Promise((r) => { try { chrome.storage.local.get({ [k]: d }, (v) => r(v[k])); } catch { r(d); } });
  const gravar = (k, v) => { try { chrome.storage.local.set({ [k]: v }); } catch {} };
  const botao = (rotulo, fn) => { const b = document.createElement("button"); b.textContent = rotulo; b.onclick = fn; botoes.appendChild(b); };

  let adiadoAte = 0, atual = null;
  function mostrar(titulo, corpo, acoes) {
    texto.replaceChildren();
    if (titulo) { const t = document.createElement("b"); t.textContent = titulo; texto.append(t, document.createElement("br")); }
    texto.append(corpo);
    botoes.replaceChildren();
    acoes.forEach(([r, f]) => botao(r, f));
    balao.hidden = false;
  }
  const fechar = () => { balao.hidden = true; };

  async function ciclo() {
    let e;
    try { e = await chrome.runtime.sendMessage({ tipo: "estado" }); } catch { return; }
    if (!e) return;
    raiz.classList.toggle("mh-erro", !!e.erro);
    const n = e.erro ? 0 : (e.resumo?.tarefas || 0);
    ponto.hidden = !n; ponto.textContent = n > 9 ? "9+" : n;
    if (e.erro) { atual = { erro: e.erro }; return; }
    atual = e;
    if (Date.now() < adiadoAte) return;
    const aviso = (e.avisos || [])[0];
    if (aviso) mostrar(aviso.titulo, aviso.texto, [
      ["Ver", () => { mostrarLista(); }],
      ["Adiar " + ADIAR_MIN + " min", () => { adiadoAte = Date.now() + ADIAR_MIN * 60000; fechar(); }]
    ]);
  }

  function mostrarLista() {
    if (!atual) return;
    if (atual.erro) return mostrar("Maestro", atual.erro, [["Fechar", fechar]]);
    const ul = document.createElement("div");
    ul.className = "mh-lista";
    if (!(atual.tarefas || []).length) ul.textContent = "Nada pendente. Bom trabalho.";
    (atual.tarefas || []).forEach((t) => {
      const l = document.createElement("div"); l.className = "mh-item" + (t.urgente ? " mh-urg" : "");
      const s = document.createElement("span"); s.textContent = t.titulo;
      const b = document.createElement("button"); b.textContent = "Feito";
      b.onclick = async () => { b.disabled = true; const r = await chrome.runtime.sendMessage({ tipo: "concluir", id: t.id }); if (r?.ok) l.remove(); else b.disabled = false; };
      l.append(s, b); ul.appendChild(l);
    });
    mostrar("Pendências", ul, [["Fechar", fechar]]);
  }

  // clicar no mascote abre/fecha a lista; arrastar move
  let arr = null;
  mascote.addEventListener("pointerdown", (ev) => { arr = { x: ev.clientX, y: ev.clientY, l: raiz.offsetLeft, t: raiz.offsetTop, mov: false }; mascote.setPointerCapture(ev.pointerId); });
  mascote.addEventListener("pointermove", (ev) => {
    if (!arr) return;
    const dx = ev.clientX - arr.x, dy = ev.clientY - arr.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) arr.mov = true;
    if (arr.mov) { raiz.style.left = Math.max(0, Math.min(innerWidth - 70, arr.l + dx)) + "px"; raiz.style.top = Math.max(0, Math.min(innerHeight - 70, arr.t + dy)) + "px"; raiz.style.right = raiz.style.bottom = "auto"; }
  });
  mascote.addEventListener("pointerup", () => {
    if (!arr) return;
    if (arr.mov) gravar("mh_pos", { l: raiz.offsetLeft, t: raiz.offsetTop });
    else if (balao.hidden) mostrarLista(); else fechar();
    arr = null;
  });

  ler("mh_pos", null).then((p) => { if (p) { raiz.style.left = Math.min(p.l, innerWidth - 70) + "px"; raiz.style.top = Math.min(p.t, innerHeight - 70) + "px"; raiz.style.right = raiz.style.bottom = "auto"; } });
  ciclo(); setInterval(ciclo, 60000);
})();
