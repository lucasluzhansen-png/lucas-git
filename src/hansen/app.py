"""Maestro Painel: programa LOCAL com botões (sem PowerShell). Abre numa aba do navegador, atualiza sozinho, mostra as tarefas,
tem o botão "Feito", avisa na própria tela e aceita o arquivo de backup arrastado. Só responde neste computador (127.0.0.1) e exige um código secreto."""
import hmac
import json
import re
import secrets
import sys
import threading
import traceback
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from hansen import hoje
from hansen.tarefas import _ler_json_ou_isolar
from hansen.caminhos import pasta_saida
from hansen.cobrador import categoria, decidir
from hansen.maestro_vivo import achar_backup, carregar_config
from hansen.painel_comercial import TIPOS, TIPOS_FINANCEIRO, cartoes
from hansen.tarefas import escrever_atomico, ler_tarefas
from hansen.yaml_parser import carregar_todos

PORTA = 8765
PAGINA = Path(__file__).parent / "web" / "painel.html"
LIMITE_UPLOAD = 100 * 1024 * 1024
TITULO = re.compile(r"^(?P<t>.*?)(?: \[[^\]]*\])?\. (?P<d>.*)$", re.S)


class Servico:
    """Estado e regras do painel (sem HTTP): fácil de testar."""

    def __init__(self, base: Path, pastas: list[Path], agora=datetime.now, intervalo_min: int = 60):
        self.base, self.pastas, self.agora, self.intervalo = Path(base), [Path(p) for p in pastas], agora, intervalo_min
        self.lock = threading.RLock()
        self.m = self.dados = self.backup = self.ultima = self.ref = None
        self.msgs: list[dict] = []
        self.erro = ""
        self.pops = carregar_todos()
        (self.base / "estado").mkdir(parents=True, exist_ok=True)

    def atualizar(self, forcar: bool = False) -> bool:
        with self.lock:
            b = achar_backup(self.pastas + [self.base / "manual"])
            if not b:
                self.erro = "Nenhum backup do Clinus encontrado."
                return False
            ref = f"{b.name}|{b.stat().st_mtime}"
            velho = not self.ultima or (self.agora() - self.ultima).total_seconds() >= self.intervalo * 60
            if not forcar and self.m is not None and ref == self.ref and not velho:
                return False
            try:
                _, m, dados, msgs = hoje.executar_completo(b, self.agora(), self.base)
            except (ValueError, KeyError, OSError) as e:
                self.erro = f"Não consegui ler o backup {b.name} ({type(e).__name__})."
                return False
            self.m, self.dados, self.msgs, self.backup, self.ref, self.ultima, self.erro = m, dados, msgs, b, ref, self.agora(), ""
            return True

    def salvar_backup_manual(self, conteudo: str) -> str:
        """Backup arrastado para a página. Devolve '' se deu certo ou a mensagem de erro."""
        try:
            dado = json.loads(conteudo)
        except ValueError:
            return "Esse arquivo não é um backup do Clinus (não é JSON)."
        if not isinstance(dado, dict) or dado.get("versao") != "hrpg_v1":
            return "Esse arquivo não parece um backup do Clinus (use Dados e backup → Exportar JSON)."
        pasta = self.base / "manual"
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / "clinus-backup-manual.json").write_text(conteudo, encoding="utf-8")
        self.atualizar(forcar=True)
        return self.erro

    def estado(self, perfil: str, canal: str = "web") -> dict:
        with self.lock:
            if self.m is None:
                self.atualizar()
            if self.m is None:
                return {"sem_backup": True, "erro": self.erro}
            agora = self.agora()
            tarefas = ler_tarefas(self.base / "estado" / "tarefas.json")
            minhas = [t for t in tarefas if t.estado in ("aberta", "escalada") and t.responsavel == perfil]
            quem, tipos = ("contato_comercial", TIPOS) if perfil == "lucas" else ("financeiro", TIPOS_FINANCEIRO)
            cards = cartoes(self.m, self.dados, quem, tipos)
            em_cartao = {c["tarefa"] for c in cards}

            def dias(t):
                c = t.criada_em.astimezone().replace(tzinfo=None) if t.criada_em.tzinfo else t.criada_em
                return max(0, (agora.date() - c.date()).days)

            def item(t):
                mt = TITULO.match(t.titulo)
                return {"id": t.id, "titulo": mt["t"] if mt else t.titulo, "detalhe": mt["d"] if mt else "",
                        "urgente": t.prioridade in ("amarela", "vermelha"), "dias": dias(t), "categoria": categoria(t.titulo)}

            idade = (agora - datetime.fromtimestamp(self.backup.stat().st_mtime)).total_seconds() / 3600
            arq = self.base / "estado" / f"cobrador_{canal}_{perfil}.json"
            est = _ler_json_ou_isolar(arq, {}) if arq.exists() else {}
            avisos = decidir(self.pops["MA-01"], tarefas, perfil, agora, est, idade)
            escrever_atomico(arq, json.dumps(est))
            urgentes = sum(1 for t in minhas if t.prioridade in ("amarela", "vermelha"))
            return {
                "sem_backup": False, "perfil": perfil, "agora": agora.strftime("%H:%M"),
                "saudacao": hoje.saudacao(agora, len(minhas) + (len(self.msgs) if perfil == "recepcao" else 0), urgentes),
                "backup": {"nome": self.backup.name, "horas": round(idade, 1), "antigo": idade >= 24},
                "resumo": {"tarefas": len(minhas), "urgentes": urgentes},
                "cartoes": [{**c, "dias": c["dias"]} for c in cards],
                "tarefas": [item(t) for t in minhas if t.id not in em_cartao],
                "mensagens": self.msgs if perfil == "recepcao" else [],
                "avisos": [{"titulo": a.titulo, "texto": a.texto} for a in avisos],
                "erro": self.erro,
            }

    def concluir(self, tarefa_id: int, perfil: str, nota: str = "") -> bool:
        with self.lock:
            if self.m is None:
                return False
            self.m.tarefas.tarefas.clear()
            self.m.tarefas._carregar()  # sincroniza com o arquivo (outras rotinas podem ter mexido)
            if tarefa_id not in self.m.tarefas.tarefas:
                return False
            return self.m.tarefas.fechar(tarefa_id, perfil, (nota or "feito (marcado no painel)").strip()[:200])


def ler_ou_criar_token(base: Path) -> str:
    arq = Path(base) / "estado" / "app_token.txt"
    if arq.exists():
        return arq.read_text(encoding="utf-8").strip()
    arq.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(18)
    arq.write_text(token, encoding="utf-8")
    return token


def criar_servidor(servico: Servico, token: str, porta: int = PORTA) -> ThreadingHTTPServer:
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _responder(self, corpo: bytes, tipo: str, codigo: int = 200):
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(corpo)

        def _json(self, obj, codigo: int = 200):
            self._responder(json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", codigo)

        def _permitido(self, qs) -> bool:
            host = self.headers.get("Host", "").split(":")[0]  # evita ataque de "DNS rebinding"
            k = (qs.get("k") or [self.headers.get("X-Token", "")])[0]
            return host in ("127.0.0.1", "localhost") and hmac.compare_digest(str(k), token)

        def do_GET(self):
            url = urlparse(self.path)
            qs = parse_qs(url.query)
            if not self._permitido(qs):
                return self._responder("Acesso negado. Abra pelo atalho do Maestro.".encode("utf-8"), "text/plain; charset=utf-8", 403)
            if url.path == "/":
                return self._responder(PAGINA.read_bytes(), "text/html; charset=utf-8")
            if url.path == "/api/estado":
                perfil = (qs.get("perfil") or ["lucas"])[0]
                canal = "ext" if (qs.get("canal") or [""])[0] == "ext" else "web"  # extensão do navegador cobra no seu próprio ritmo
                return self._json(servico.estado(perfil if perfil in ("lucas", "recepcao") else "lucas", canal))
            self._responder(b"nao encontrado", "text/plain", 404)

        def do_POST(self):
            url = urlparse(self.path)
            qs = parse_qs(url.query)
            if not self._permitido(qs):
                return self._responder(b"acesso negado", "text/plain", 403)
            n = int(self.headers.get("Content-Length") or 0)
            if n > LIMITE_UPLOAD:
                return self._json({"ok": False, "erro": "Arquivo grande demais."}, 413)
            try:
                corpo = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._json({"ok": False, "erro": "Pedido inválido."}, 400)
            perfil = corpo.get("perfil") if corpo.get("perfil") in ("lucas", "recepcao") else "lucas"
            if url.path == "/api/concluir":
                try:
                    tid = int(corpo.get("id", -1))
                except (TypeError, ValueError):
                    return self._json({"ok": False, "erro": "Pedido inválido."}, 400)
                return self._json({"ok": servico.concluir(tid, perfil, str(corpo.get("nota", "")))})
            if url.path == "/api/atualizar":
                servico.atualizar(forcar=True)
                return self._json({"ok": True, "erro": servico.erro})
            if url.path == "/api/backup":
                erro = servico.salvar_backup_manual(str(corpo.get("conteudo", "")))
                return self._json({"ok": not erro, "erro": erro})
            if url.path == "/api/sair":
                self._json({"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            self._responder(b"nao encontrado", "text/plain", 404)

    return ThreadingHTTPServer(("127.0.0.1", porta), H)


def _loop_atualizacao(servico: Servico, parar: threading.Event, cada_s: int = 300):
    while not parar.wait(cada_s):
        try:
            servico.atualizar()
        except Exception:  # nunca derruba o painel
            pass


def main(abrir_navegador: bool = True) -> int:
    base = pasta_saida() / "hoje"
    base.mkdir(parents=True, exist_ok=True)
    try:
        cfg = carregar_config()
        token = ler_ou_criar_token(base)
        url = f"http://127.0.0.1:{PORTA}/?k={token}"
        servico = Servico(base, [Path(p) for p in cfg["pastas_backup"]])
        try:
            srv = criar_servidor(servico, token)
        except OSError:  # porta ocupada: o Maestro já está aberto; só abre a aba
            if abrir_navegador:
                webbrowser.open(url)
            return 0
        servico.atualizar()
        parar = threading.Event()
        threading.Thread(target=_loop_atualizacao, args=(servico, parar), daemon=True).start()
        if abrir_navegador:
            webbrowser.open(url)
        try:
            srv.serve_forever()
        finally:
            parar.set()
        return 0
    except Exception:
        (base / "app.log").write_text(traceback.format_exc(), encoding="utf-8")
        return 1


if __name__ == "__main__":
    sys.exit(main("--sem-navegador" not in sys.argv))
