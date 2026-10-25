# Agenda de publicações: o robô publica no Instagram e no Facebook de cada
# cliente na data e hora marcadas, sem ninguém logado.
#
# Tudo fica CRIPTOGRAFADO no repositório (o repositório é público):
#   agenda/<cliente>.enc.json        lista de posts (data, redes, legenda, status)
#   agenda/<cliente>/<id>.enc        arte de cada post
#
# Uso (no computador do Vitor; depois: git pull antes, git push depois):
#   python agenda.py <cliente> adicionar <arte.png> "2026-10-27 18:00" <legenda.txt> [--redes instagram,facebook]
#   python agenda.py <cliente> listar
#   python agenda.py <cliente> remover <id>
#   python agenda.py <cliente> publicar     (o robô roda isso a cada 15 min: publica o que já passou da hora)
#
# Só publica com o post AGENDADO aqui, ou seja, depois da aprovação do Vitor (e do cliente).
# Chave com permissão de publicar: META_TOKEN (instagram_content_publish e pages_manage_posts).

import json
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import requests

import cofre
from coletor import ENV, FUSO, PASTA, VERSAO, api, token_da_pagina

GRAPH = f"https://graph.facebook.com/{VERSAO}"


def caminhos(cliente):
    return PASTA / "agenda" / f"{cliente}.enc.json", PASTA / "agenda" / cliente


def ler(cliente):
    lista, _ = caminhos(cliente)
    if not lista.exists():
        return []
    return json.loads(cofre.decifrar(cliente, json.loads(lista.read_text(encoding="utf-8"))))


def gravar(cliente, posts):
    lista, _ = caminhos(cliente)
    lista.parent.mkdir(exist_ok=True)
    texto = json.dumps(posts, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    lista.write_text(json.dumps(cofre.cifrar(cliente, texto)), encoding="utf-8")


def adicionar(cliente, arte, quando, legenda, redes):
    data = datetime.strptime(quando, "%Y-%m-%d %H:%M").replace(tzinfo=FUSO)
    posts = ler(cliente)
    pid = data.strftime("%Y%m%d-%H%M") + f"-{len(posts) + 1:02d}"
    _, pasta = caminhos(cliente)
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / f"{pid}.enc").write_text(json.dumps(cofre.cifrar(cliente, Path(arte).read_bytes())), encoding="utf-8")
    posts.append({
        "id": pid, "quando": data.isoformat(), "redes": redes, "arte": Path(arte).name,
        "legenda": Path(legenda).read_text(encoding="utf-8").strip(), "status": "agendado",
    })
    posts.sort(key=lambda p: p["quando"])
    gravar(cliente, posts)
    print(f"Agendado {pid}: {data:%d/%m/%Y %H:%M} em {', '.join(redes)}")


def listar(cliente):
    for p in ler(cliente):
        extra = p.get("links") or p.get("erro") or ""
        print(f"{p['id']}  {p['quando'][:16].replace('T', ' ')}  {p['status']:<10} {'+'.join(p['redes']):<18} "
              f"{p['legenda'][:50].replace(chr(10), ' ')}  {extra}")


def remover(cliente, pid):
    posts = ler(cliente)
    _, pasta = caminhos(cliente)
    (pasta / f"{pid}.enc").unlink(missing_ok=True)
    gravar(cliente, [p for p in posts if p["id"] != pid])
    print(f"Removido {pid}")


# ---------------------------------------------------------------- publicação

def post(caminho, token, **dados):
    arquivos = dados.pop("arquivos", None)
    r = requests.post(f"{GRAPH}/{caminho}", data={**dados, "access_token": token}, files=arquivos, timeout=120)
    resposta = r.json()
    if "error" in resposta:
        # A mensagem da Meta não contém a chave
        raise RuntimeError(f"Meta API: {resposta['error'].get('message')} ({caminho})")
    return resposta


def publicar_post(cliente, p):
    ig = ENV.get(f"IG_{cliente.upper()}")
    pagina = ENV.get(f"FB_{cliente.upper()}")
    _, pasta = caminhos(cliente)
    imagem = cofre.decifrar(cliente, json.loads((pasta / f"{p['id']}.enc").read_text(encoding="utf-8")))
    links = {}

    with tempfile.TemporaryDirectory() as tmp:
        arte = Path(tmp) / p["arte"]
        arte.write_bytes(imagem)
        # A foto sobe primeiro na página do Facebook: publicada (se o post é para o Facebook)
        # ou só guardada, para o Instagram buscar a imagem por um endereço da própria Meta
        token_pagina = token_da_pagina(pagina)
        no_facebook = "facebook" in p["redes"]
        with arte.open("rb") as f:
            foto = post(f"{pagina}/photos", token_pagina, arquivos={"source": (arte.name, f, "image/png")},
                        message=p["legenda"] if no_facebook else "", published="true" if no_facebook else "false")
        if no_facebook:
            links["facebook"] = f"https://www.facebook.com/{foto.get('post_id', foto['id'])}"

    if "instagram" in p["redes"]:
        url = api(foto["id"], token=token_pagina, fields="images")["images"][0]["source"]
        criacao = post(f"{ig}/media", ENV["META_TOKEN"], image_url=url, caption=p["legenda"])["id"]
        for _ in range(30):  # o Instagram processa a imagem antes de deixar publicar
            if api(criacao, fields="status_code").get("status_code") == "FINISHED":
                break
            time.sleep(4)
        midia = post(f"{ig}/media_publish", ENV["META_TOKEN"], creation_id=criacao)["id"]
        links["instagram"] = api(midia, fields="permalink").get("permalink")
    return links


def publicar(cliente):
    posts = ler(cliente)
    agora = datetime.now(FUSO)
    mudou = False
    for p in posts:
        if p["status"] != "agendado" or datetime.fromisoformat(p["quando"]) > agora:
            continue
        try:
            p["links"] = publicar_post(cliente, p)
            p["status"] = "publicado"
        except Exception as e:  # registra o erro e não tenta de novo sozinho (evita post duplicado)
            p["status"], p["erro"] = "erro", str(e)[:300]
        p["publicadoEm"] = datetime.now(FUSO).isoformat(timespec="minutes")
        mudou = True
        print(f"{cliente} {p['id']}: {p['status']} {p.get('links') or p.get('erro')}")
    if mudou:
        gravar(cliente, posts)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    cliente, acao, args = sys.argv[1], sys.argv[2], sys.argv[3:]
    if acao == "adicionar":
        redes = args[args.index("--redes") + 1].split(",") if "--redes" in args else ["instagram", "facebook"]
        adicionar(cliente, args[0], args[1], args[2], redes)
    elif acao == "listar":
        listar(cliente)
    elif acao == "remover":
        remover(cliente, args[0])
    elif acao == "publicar":
        publicar(cliente)


if __name__ == "__main__":
    main()
