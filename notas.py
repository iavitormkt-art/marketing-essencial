# Anotações do gestor que aparecem no app ("O que fizemos" e "Próximos passos").
# Grava direto no cofre criptografado do cliente.
#
# Uso:
#   python notas.py <cliente> fiz "Ativamos a resposta automática do Instagram"   (data de hoje)
#   python notas.py <cliente> fiz "texto" --data 2026-10-20
#   python notas.py <cliente> passos "Calendário de novembro" "Responder em até 2 h"   (substitui a lista)
#   python notas.py <cliente> apagar-fiz <número>   (número mostrado no listar)
#   python notas.py <cliente> listar

import sys
from datetime import datetime

import cofre
from coletor import FUSO


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    cliente, acao, args = sys.argv[1], sys.argv[2], sys.argv[3:]
    conteudo = cofre.abrir(cliente)
    notas = conteudo["notas"]
    if acao == "fiz":
        data = args[args.index("--data") + 1] if "--data" in args else datetime.now(FUSO).date().isoformat()
        texto = args[0]
        notas["feitos"].insert(0, {"data": data, "texto": texto})
        notas["feitos"].sort(key=lambda n: n["data"], reverse=True)
    elif acao == "passos":
        notas["passos"] = list(args)
    elif acao == "apagar-fiz":
        notas["feitos"].pop(int(args[0]) - 1)
    if acao != "listar":
        cofre.fechar(cliente, conteudo)
    for i, n in enumerate(notas["feitos"], 1):
        print(f"{i}. {n['data']}  {n['texto']}")
    for p in notas["passos"]:
        print(f"   -> {p}")


if __name__ == "__main__":
    main()
