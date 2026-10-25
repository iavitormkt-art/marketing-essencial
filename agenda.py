# Agenda de publicações: o robô publica no Instagram e no Facebook de cada
# cliente na data e hora marcadas, sem ninguém logado.
#
# Tudo fica CRIPTOGRAFADO no repositório (o repositório é público):
#   agenda/<cliente>.enc.json        lista de posts (data, redes, legenda, status)
#   agenda/<cliente>/<id>.enc        arte de cada post
#
# Uso (no computador do Vitor; depois: git pull antes, git push depois):
#   python agenda.py <cliente> adicionar <arte.png> "2026-10-27 18:00" <legenda.txt> [--redes instagram,facebook]
#   python agenda.py <cliente> adicionar <pasta-do-carrossel> "2026-10-27 18:00" <legenda.txt>   (até 10 .png, em ordem de nome)
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
    """arte = um .png (post simples) ou uma pasta com os .png do carrossel, em ordem de nome."""
    data = datetime.strptime(quando, "%Y-%m-%d %H:%M").replace(tzinfo=FUSO)
    artes = sorted(Path(arte).glob("*.png")) if Path(arte).is_dir() else [Path(arte)]
    if not 1 <= len(artes) <= 10:
        sys.exit("O Instagram aceita de 1 a 10 imagens por post")
    posts = ler(cliente)
    pid = data.strftime("%Y%m%d-%H%M") + f"-{len(posts) + 1:02d}"
    _, pasta = caminhos(cliente)
    pasta.mkdir(parents=True, exist_ok=True)
    for i, a in enumerate(artes, 1):
        (pasta / f"{pid}-{i:02d}.enc").write_text(json.dumps(cofre.cifrar(cliente, a.read_bytes())), encoding="utf-8")
    posts.append({
        "id": pid, "quando": data.isoformat(), "redes": redes, "artes": [a.name for a in artes],
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
    for f in pasta.glob(f"{pid}-*.enc"):
        f.unlink()
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


def esperar_pronto(criacao):
    """O Instagram processa cada imagem antes de deixar publicar."""
    for _ in range(30):
        if api(criacao, fields="status_code").get("status_code") == "FINISHED":
            return
        time.sleep(4)
    raise RuntimeError(f"O Instagram não terminou de processar a mídia {criacao}")


def publicar_post(cliente, p):
    ig = ENV.get(f"IG_{cliente.upper()}")
    pagina = ENV.get(f"FB_{cliente.upper()}")
    _, pasta = caminhos(cliente)
    artes = p.get("artes") or [p["arte"]]
    token_pagina = token_da_pagina(pagina)
    no_facebook = "facebook" in p["redes"]
    links = {}

    # As fotos sobem primeiro na página do Facebook sem publicar: o post do Facebook
    # junta todas, e o Instagram busca cada imagem por um endereço da própria Meta
    fotos = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, nome in enumerate(artes, 1):
            arquivo = pasta / f"{p['id']}-{i:02d}.enc"
            if not arquivo.exists():  # posts agendados antes do carrossel: um arquivo só
                arquivo = pasta / f"{p['id']}.enc"
            arte = Path(tmp) / nome
            arte.write_bytes(cofre.decifrar(cliente, json.loads(arquivo.read_text(encoding="utf-8"))))
            with arte.open("rb") as f:
                fotos.append(post(f"{pagina}/photos", token_pagina, arquivos={"source": (nome, f, "image/png")},
                                  published="false")["id"])

    if no_facebook:
        anexos = {f"attached_media[{i}]": json.dumps({"media_fbid": f}) for i, f in enumerate(fotos)}
        feito = post(f"{pagina}/feed", token_pagina, message=p["legenda"], **anexos)
        links["facebook"] = f"https://www.facebook.com/{feito['id']}"

    if "instagram" in p["redes"]:
        urls = [api(f, token=token_pagina, fields="images")["images"][0]["source"] for f in fotos]
        if len(urls) == 1:
            criacao = post(f"{ig}/media", ENV["META_TOKEN"], image_url=urls[0], caption=p["legenda"])["id"]
        else:
            filhos = []
            for u in urls:
                filho = post(f"{ig}/media", ENV["META_TOKEN"], image_url=u, is_carousel_item="true")["id"]
                esperar_pronto(filho)
                filhos.append(filho)
            criacao = post(f"{ig}/media", ENV["META_TOKEN"], media_type="CAROUSEL",
                           children=",".join(filhos), caption=p["legenda"])["id"]
        esperar_pronto(criacao)
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
