"""Ledger de evidências simulado: hash-chain + assinatura Ed25519, gravado em disco (simula S3 WORM)."""
import base64
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

GENESIS = "0" * 64


def _canonico(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


class LedgerManager:
    def __init__(self, pasta: Path, chave: Ed25519PrivateKey | None = None):
        self.pasta = Path(pasta)
        self.pasta.mkdir(parents=True, exist_ok=True)
        # SIMULAÇÃO: em produção a chave privada fica no dispositivo do utilizador.
        self._chave = chave or Ed25519PrivateKey.generate()
        pub = self._chave.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.chave_id = base64.b64encode(pub).decode()
        self._ultimo = self._ler_ultimo()

    def _ler_ultimo(self) -> dict | None:
        ficheiros = sorted(self.pasta.glob("*.json"))
        return json.loads(ficheiros[-1].read_text(encoding="utf-8")) if ficheiros else None

    def registar(self, *, pop_id, ator, acao, resultado="sucesso", entrada=None, saida=None, privacidade) -> dict:
        seq = (self._ultimo["sequence"] + 1) if self._ultimo else 1
        evento = {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sequence": seq,
            "pop_id": pop_id,
            "actor": ator,
            "acao": acao,
            "resultado": resultado,
            "entrada": entrada or {},
            "saida": saida or {},
            "privacidade": privacidade,
            "hash_anterior": self._ultimo["hash_evento"] if self._ultimo else GENESIS,
        }
        evento["hash_evento"] = hashlib.sha256(_canonico(evento)).hexdigest()
        evento["assinatura"] = {
            "algoritmo": "Ed25519",
            "chave_id": self.chave_id,
            "valor": base64.b64encode(self._chave.sign(evento["hash_evento"].encode())).decode(),
        }
        destino = self.pasta / f"{seq:010d}.json"
        with open(destino, "x", encoding="utf-8", newline="\n") as f:  # "x": nunca sobrescreve (imutabilidade simulada)
            json.dump(evento, f, ensure_ascii=False, indent=2)
        self._ultimo = evento
        return evento

    def verificar(self) -> bool:
        anterior = GENESIS
        for f in sorted(self.pasta.glob("*.json")):
            ev = json.loads(f.read_text(encoding="utf-8"))
            sig = ev.pop("assinatura")
            if ev["hash_anterior"] != anterior:
                return False
            if hashlib.sha256(_canonico({k: v for k, v in ev.items() if k != "hash_evento"})).hexdigest() != ev["hash_evento"]:
                return False
            pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(sig["chave_id"]))
            try:
                pub.verify(base64.b64decode(sig["valor"]), ev["hash_evento"].encode())
            except InvalidSignature:
                return False
            anterior = ev["hash_evento"]
        return True

