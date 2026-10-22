"""Notificação do Windows (toast) via PowerShell, sem instalar nada. Fora do Windows, apenas registra em arquivo.
IMPORTANTE: não foi possível testar em Windows real neste ambiente; use `python -m hansen.notificacao` para conferir."""
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from hansen.caminhos import pasta_saida

PS = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$t = $xml.GetElementsByTagName('text')
$t.Item(0).AppendChild($xml.CreateTextNode($env:MAESTRO_TITULO)) | Out-Null
$t.Item(1).AppendChild($xml.CreateTextNode($env:MAESTRO_TEXTO)) | Out-Null
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
# identificador do próprio Windows PowerShell: o Windows aceita toasts dele sem registrar um aplicativo
$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show($toast)
"""


def registrar_log(titulo: str, texto: str, pasta: Path | None = None) -> None:
    pasta = pasta or pasta_saida() / "hoje"
    pasta.mkdir(parents=True, exist_ok=True)
    with open(pasta / "avisos.log", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M} | {titulo} | {texto}\n")


def notificar_windows(titulo: str, texto: str) -> bool:
    """True se o Windows aceitou a notificação. Sempre deixa o aviso também no log (avisos.log)."""
    registrar_log(titulo, texto)
    if os.name != "nt":
        return False
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", PS],
                           env={**os.environ, "MAESTRO_TITULO": titulo, "MAESTRO_TEXTO": texto}, capture_output=True, timeout=20)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


if __name__ == "__main__":  # python -m hansen.notificacao  → manda um aviso de teste
    print("Pasta dos arquivos do Maestro:", (pasta_saida() / "hoje").resolve())
    ok = notificar_windows("Maestro Hansen", "Teste: se você está vendo isto, os avisos funcionam. 🦷")
    print("Aviso enviado ao Windows." if ok else "O Windows não aceitou o aviso (ou não é Windows). O texto ficou em avisos.log dentro da pasta de saída (veja o caminho acima).")
    sys.exit(0 if ok else 1)
