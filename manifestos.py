# Gera um manifesto por cliente (manifest-<id>.webmanifest e manifest-<id>-equipe.webmanifest),
# para o app instalado na tela do celular abrir direto no cliente certo.
# Uso: python manifestos.py studio moranguinho
import json
import os
import sys

# Clientes com marca própria no app instalado (ícones icone-<id>-*.png gerados da logo)
MARCAS = {"moranguinho": ("Moranguinho · Marketing Essencial", "Moranguinho", "#FED7D2")}

BASE = json.load(open("manifest.webmanifest", encoding="utf-8"))
for cliente in sys.argv[1:]:
    for equipe in (False, True):
        inicio = f"./?cliente={cliente}" + ("&equipe" if equipe else "")
        m = {**BASE, "id": inicio, "start_url": inicio + "&app=1", "scope": "./"}  # app=1: aberto pelo ícone
        if cliente in MARCAS and os.path.exists(f"icone-{cliente}-512.png"):
            nome_longo, curto, cor = MARCAS[cliente]
            m.update(name=nome_longo, short_name=curto, background_color=cor, icons=[
                {"src": "icone-vazio-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
                {"src": "icone-vazio-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
                {"src": f"icone-{cliente}-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}])
        nome = f"manifest-{cliente}" + ("-equipe" if equipe else "") + ".webmanifest"
        with open(nome, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False, indent=2)
        print("ok", nome)
