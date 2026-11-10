# Robô de coleta (GitHub Actions): abre o cofre do cliente, coleta e fecha o
# cofre com o histórico atualizado.
#   - Completa (23h de Brasília): ontem e hoje (ontem de novo porque a Meta
#     fecha os números do dia com atraso).
#   - Rápida (--hoje, a cada 15 min): só o dia de hoje, para o app ter movimento
#     durante o dia em vez de mostrar os números da madrugada.
#
# Uso:  python robo.py [--hoje] <cliente> [<cliente> ...]

import sys
from datetime import datetime, timedelta

import cofre
from coletor import FUSO, coletar, gravar


def rodar(cliente, so_hoje=False):
    conteudo = cofre.abrir(cliente)
    historico, _, _ = cofre.arquivos(cliente)
    historico.parent.mkdir(exist_ok=True)
    historico.write_text(cofre.json.dumps(conteudo["historico"], ensure_ascii=False), encoding="utf-8")

    hoje = datetime.now(FUSO).date()
    registros = [coletar(cliente, d) for d in ((hoje,) if so_hoje else (hoje - timedelta(days=1), hoje))]
    gravar(cliente, registros)

    conteudo["historico"] = cofre.ler_json(historico, [])
    cofre.fechar(cliente, conteudo)
    print(f"{cliente}: {len(conteudo['historico'])} dias no cofre (último {conteudo['historico'][-1]['data']})")


if __name__ == "__main__":
    so_hoje = "--hoje" in sys.argv
    for c in [a for a in sys.argv[1:] if not a.startswith("--")]:
        rodar(c, so_hoje)
