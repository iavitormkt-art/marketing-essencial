# Gera um manifesto por cliente (manifest-<id>.webmanifest e manifest-<id>-equipe.webmanifest),
# para o app instalado na tela do celular abrir direto no cliente certo.
# Uso: python manifestos.py studio moranguinho
import json
import sys

BASE = json.load(open("manifest.webmanifest", encoding="utf-8"))
for cliente in sys.argv[1:]:
    for equipe in (False, True):
        inicio = f"./?cliente={cliente}" + ("&equipe" if equipe else "")
        m = {**BASE, "id": inicio, "start_url": inicio, "scope": "./"}
        nome = f"manifest-{cliente}" + ("-equipe" if equipe else "") + ".webmanifest"
        with open(nome, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False, indent=2)
        print("ok", nome)
