// Busca os avisos no painel local e entrega ao mascote nas abas do Clinus. Nada sai do computador.
const PORTA = 8765;
const ID_SCRIPT = "maestro-clinus";

async function cfg() {
  return chrome.storage.local.get({ token: "", perfil: "lucas", origem: "" });
}

async function buscar() {
  const { token, perfil } = await cfg();
  if (!token) return { erro: "Falta o código do Maestro (abra as opções da extensão)." };
  try {
    const r = await fetch(`http://127.0.0.1:${PORTA}/api/estado?perfil=${perfil}&canal=ext`, { headers: { "X-Token": token } });
    if (!r.ok) return { erro: "Código do Maestro recusado." };
    const e = await r.json();
    if (e.sem_backup) return { erro: "Maestro sem backup do Clinus." };
    return { resumo: e.resumo, avisos: e.avisos, tarefas: e.tarefas.slice(0, 5), saudacao: e.saudacao };
  } catch {
    return { erro: "Maestro desligado. Abra o painel (abrir_maestro.bat)." };
  }
}

async function concluir(id, nota) {
  const { token, perfil } = await cfg();
  const r = await fetch(`http://127.0.0.1:${PORTA}/api/concluir?`, {
    method: "POST", headers: { "X-Token": token, "Content-Type": "application/json" },
    body: JSON.stringify({ id, perfil, nota })
  });
  return (await r.json()).ok;
}

async function registrar() {
  const { origem } = await cfg();
  try { await chrome.scripting.unregisterContentScripts({ ids: [ID_SCRIPT] }); } catch {}
  if (!origem) return;
  await chrome.scripting.registerContentScripts([{
    id: ID_SCRIPT, matches: [origem], js: ["content.js"], css: ["content.css"], runAt: "document_idle", allFrames: false
  }]);
}

chrome.runtime.onMessage.addListener((m, _s, resp) => {
  if (m.tipo === "estado") buscar().then(resp);
  else if (m.tipo === "concluir") concluir(m.id, m.nota || "feito (marcado no balão)").then((ok) => resp({ ok }));
  else if (m.tipo === "registrar") registrar().then(() => resp({ ok: true }));
  return true;
});
chrome.runtime.onInstalled.addListener(registrar);
chrome.runtime.onStartup.addListener(registrar);
