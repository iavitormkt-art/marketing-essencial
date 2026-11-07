# Cria uma aprovação no app do cliente (fotos ou peças de campanha).
# Aparece em destaque no Resumo ("📷/📣 <chamada>") até o cliente enviar a escolha pela Conversa.
#
# Uso:
#   python aprovacao.py <cliente> <id> "<título>" <pasta-com-imagens> [--chamada "Texto do destaque"] [--textos textos.json]
#   python aprovacao.py <cliente> --listar
#   python aprovacao.py <cliente> --remover <id>
#
# Subpastas da pasta viram grupos. textos.json (opcional): {"nome-do-arquivo.jpg": "legenda/texto do post", ...}
# As imagens são reduzidas para tela de celular (1080 px) e vão para galeria/<cliente>/<id>/<n>.jpg.
# Depois: commit + push.

import json
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageOps

PASTA = Path(__file__).parent


def carregar(cliente):
    arq = PASTA / "galeria" / f"{cliente}.json"
    if not arq.exists():
        return arq, {"aprovacoes": []}
    j = json.loads(arq.read_text(encoding="utf-8"))
    if "aprovacoes" not in j:  # formato antigo (só fotos)
        j = {"aprovacoes": [{"id": "fotos", "titulo": j.get("titulo", "Fotos para as redes"), "chamada": "Fotos para aprovar",
                             "itens": j.get("itens", []), "antiga": True}]}
    return arq, j


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(1)
    cliente = a[0]
    arq, j = carregar(cliente)
    if "--listar" in a:
        for ap in j["aprovacoes"]:
            print(ap["id"], "|", ap["titulo"], "|", len(ap["itens"]), "itens")
        return
    if "--remover" in a:
        alvo = a[a.index("--remover") + 1]
        j["aprovacoes"] = [x for x in j["aprovacoes"] if x["id"] != alvo]
        shutil.rmtree(PASTA / "galeria" / cliente / alvo, ignore_errors=True)
        arq.write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")
        print("removida", alvo); return
    ident, titulo, origem = a[1], a[2], Path(a[3])
    chamada = a[a.index("--chamada") + 1] if "--chamada" in a else titulo
    textos = json.loads(Path(a[a.index("--textos") + 1]).read_text(encoding="utf-8")) if "--textos" in a else {}
    destino = PASTA / "galeria" / cliente / ident
    shutil.rmtree(destino, ignore_errors=True); destino.mkdir(parents=True)
    itens, n = [], 0
    arquivos = sorted(p for p in origem.rglob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))
    for p in arquivos:
        n += 1
        im = ImageOps.exif_transpose(Image.open(p))
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA"); fundo = Image.new("RGB", im.size, (245, 240, 238)); fundo.paste(im, mask=im.split()[-1]); im = fundo
        im = im.convert("RGB"); im.thumbnail((1080, 1080))
        im.save(destino / f"{n:03d}.jpg", quality=82, optimize=True, progressive=True)
        grupo = p.parent.name if p.parent != origem else ""
        item = {"n": n, "grupo": grupo}
        if textos.get(p.name):
            item["texto"] = textos[p.name]
        itens.append(item)
    j["aprovacoes"] = [x for x in j["aprovacoes"] if x["id"] != ident] + [{"id": ident, "titulo": titulo, "chamada": chamada, "itens": itens}]
    arq.write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")
    # número -> arquivo original (fica na pasta do cliente, fora do site publicado)
    mapa = PASTA.parent / "clientes" / cliente / "aprovacoes" / f"{ident}.json"
    mapa.parent.mkdir(parents=True, exist_ok=True)
    mapa.write_text(json.dumps({str(i + 1): str(p) for i, p in enumerate(arquivos)}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{ident}: {n} itens em galeria/{cliente}/{ident}/ (falta commit + push)")


if __name__ == "__main__":
    main()
