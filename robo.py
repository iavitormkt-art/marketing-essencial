# Robô diário (GitHub Actions, todo dia às 23h de Brasília): abre o cofre do
# cliente, coleta ontem e hoje (ontem de novo porque a Meta fecha os números
# do dia com atraso) e fecha o cofre com o histórico atualizado.
#
# Uso:  python robo.py <cliente> [<cliente> ...]

import sys
from datetime import datetime, timedelta

import cofre
from coletor import FUSO, coletar, gravar


def rodar(cliente):
    conteudo = cofre.abrir(cliente)
    historico, _, _ = cofre.arquivos(cliente)
    historico.parent.mkdir(exist_ok=True)
    historico.write_text(cofre.json.dumps(conteudo["historico"], ensure_ascii=False), encoding="utf-8")

    hoje = datetime.now(FUSO).date()
    registros = [coletar(cliente, d) for d in (hoje - timedelta(days=1), hoje)]
    gravar(cliente, registros)

    conteudo["historico"] = cofre.ler_json(historico, [])
    cofre.fechar(cliente, conteudo)
    print(f"{cliente}: {len(conteudo['historico'])} dias no cofre (último {conteudo['historico'][-1]['data']})")


if __name__ == "__main__":
    for c in sys.argv[1:]:
        rodar(c)
