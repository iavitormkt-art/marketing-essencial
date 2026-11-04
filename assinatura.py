# Dados da assinatura do cliente, mostrados no app em Configurações → Minha assinatura
# (e usados no cálculo do cancelamento, Cláusula 12 do contrato). Grava no cofre criptografado.
#
# Uso:
#   python assinatura.py <cliente> definir --plano "Essencial+" --mensal 1197 --prazo 12 --forma mensal --inicio 2026-11-05
#       --forma: pix | cartao (parcelado) | mensal (cartão mês a mês)
#       opcionais: --implantacao 497   (valor de tabela; isenta nos contratos de 6 e 12 meses)
#                  --pago 12209        (valor pago no Pix ou no parcelado; sem isso, calcula pela tabela)
#                  --captacao 800      (valor da captação bônus do contrato de 12 meses)
#                  --sem-garantia      (o CNPJ/CPF já usou a garantia de 30 dias)
#   python assinatura.py <cliente> captacao-feita     (marca a captação bônus como feita)
#   python assinatura.py <cliente> ver

import json
import sys

import cofre

DESCONTO_PIX = {3: 0.05, 6: 0.10, 12: 0.15}


def opcao(args, nome, padrao=None):
    return args[args.index(nome) + 1] if nome in args else padrao


def main():
    if len(sys.argv) < 3 or sys.argv[2] not in ("definir", "captacao-feita", "ver"):
        print(__doc__ or open(__file__, encoding="utf-8").read().split("\n\n")[0])
        sys.exit(1)
    cliente, acao, args = sys.argv[1], sys.argv[2], sys.argv[3:]
    conteudo = cofre.abrir(cliente)
    a = conteudo.get("assinatura")
    if acao == "definir":
        mensal, prazo, forma = float(opcao(args, "--mensal")), int(opcao(args, "--prazo")), opcao(args, "--forma")
        assert forma in ("pix", "cartao", "mensal"), "--forma deve ser pix, cartao ou mensal"
        assert prazo in (3, 6, 12), "--prazo deve ser 3, 6 ou 12"
        assert not (forma == "mensal" and prazo == 3), "cartão mês a mês só nos contratos de 6 e 12 meses"
        pago = opcao(args, "--pago")
        if pago is None and forma != "mensal":
            pago = round(mensal * prazo * (1 - DESCONTO_PIX[prazo])) if forma == "pix" else mensal * prazo
        a = {
            "plano": opcao(args, "--plano"), "mensal": mensal, "prazo": prazo, "forma": forma,
            "inicio": opcao(args, "--inicio"), "implantacao": float(opcao(args, "--implantacao", 497)),
            "pago": float(pago) if pago is not None else None,
            "captacao": float(opcao(args, "--captacao", 0)), "captacaoFeita": False,
            "garantia": "--sem-garantia" not in args,
        }
    elif acao == "captacao-feita":
        assert a, "assinatura ainda não definida"
        a["captacaoFeita"] = True
    if acao != "ver":
        conteudo["assinatura"] = a
        cofre.fechar(cliente, conteudo)
    print(json.dumps(a, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
