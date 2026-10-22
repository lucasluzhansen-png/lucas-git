const $ = (i) => document.getElementById(i);
chrome.storage.local.get({ token: "", perfil: "lucas", origem: "" }, (v) => { $("token").value = v.token; $("perfil").value = v.perfil; $("origem").value = v.origem.replace(/\/\*$/, ""); });
$("salvar").onclick = async () => {
  try {
    const u = new URL($("origem").value.trim());
    const arquivo = u.protocol === "file:";  // Clinus aberto como arquivo local
    const padrao = arquivo ? "file:///*" : `${u.protocol}//${u.host}/*`;
    if (!arquivo && !(await chrome.permissions.request({ origins: [padrao] }))) { $("msg").textContent = "Permissão negada."; return; }
    await chrome.storage.local.set({ token: $("token").value.trim(), perfil: $("perfil").value, origem: padrao });
    await chrome.runtime.sendMessage({ tipo: "registrar" });
    $("msg").textContent = "Salvo. Recarregue o Clinus.";
  } catch { $("msg").textContent = "Endereço inválido."; }
};
