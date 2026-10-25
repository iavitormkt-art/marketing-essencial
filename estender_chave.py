# Troca a chave curta do .env (META_TOKEN, gerada no Explorador da Graph API)
# pela chave de longa duração (~60 dias) e grava de volta no .env.
#
# Alternativa ao botão "Estender token de acesso" do Depurador, quando ele falha.
#
# Uso:  python estender_chave.py            (estende e grava)
#       python estender_chave.py --validade (só mostra até quando a chave atual vale)
#
# Precisa no .env (mesma pasta):
#   META_APP_ID=1159290556441760
#   META_APP_SECRET=...   chave secreta do app (Configurações do app > Básico)
#
# Nunca imprime a chave nem o segredo: só a validade.

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from coletor import ENV, PASTA, VERSAO, FUSO


def chamar(caminho, **params):
    url = f"https://graph.facebook.com/{VERSAO}/{caminho}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        erro = json.loads(e.read() or b"{}").get("error", {})
        sys.exit(f"Meta API {e.code}: {erro.get('message', 'erro')} ({caminho})")


def validade(chave):
    info = chamar("debug_token", input_token=chave, access_token=chave)["data"]
    if not info.get("is_valid"):
        return "chave inválida ou expirada"
    expira = info.get("expires_at") or 0
    return ("não expira" if not expira
            else "vale até " + datetime.fromtimestamp(expira, FUSO).strftime("%d/%m/%Y %H:%M"))


def main():
    if "--validade" in sys.argv:
        print("Chave atual:", validade(ENV["META_TOKEN"]))
        return
    if not ENV.get("META_APP_SECRET"):
        sys.exit("Falta META_APP_SECRET no .env")
    nova = chamar("oauth/access_token", grant_type="fb_exchange_token",
                  client_id=ENV.get("META_APP_ID", "1159290556441760"),
                  client_secret=ENV["META_APP_SECRET"],
                  fb_exchange_token=ENV["META_TOKEN"])["access_token"]

    arquivo = PASTA / ".env"
    texto = arquivo.read_text(encoding="utf-8")
    texto = re.sub(r"(?m)^META_TOKEN=.*$", lambda _: f"META_TOKEN={nova}", texto)
    arquivo.write_text(texto, encoding="utf-8")
    print("Chave nova gravada no .env:", validade(nova))


if __name__ == "__main__":
    main()
