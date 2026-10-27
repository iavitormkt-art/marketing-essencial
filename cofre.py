# Cofre do app: os dados de cada cliente vão para a internet CRIPTOGRAFADOS.
#
# O site é público (GitHub Pages), mas o arquivo dados/<cliente>.enc.json só
# abre com a senha do cliente (AES-256-GCM, chave derivada da senha com
# PBKDF2-SHA256). O app pede a senha uma vez e lembra no aparelho.
#
# Conteúdo do cofre: {"historico": [...registros do coletor...], "notas": {"feitos": [...], "passos": [...]}}
#
# Uso:
#   python cofre.py fechar <cliente>   dados/<cliente>.json (+ notas) -> dados/<cliente>.enc.json
#   python cofre.py abrir <cliente>    dados/<cliente>.enc.json -> dados/<cliente>.json (para o coletor)
#   python cofre.py senha <cliente>    cria a senha do cliente no .env (SENHA_<CLIENTE>), se não existir
#
# A senha vem de SENHA_<CLIENTE> (no .env local ou nos segredos do GitHub). Nunca é impressa.
#
# Acessos extras (equipe, quem ajuda a testar): ACESSOS_<CLIENTE>=usuario:senha,outro:senha
# Cada um ganha uma cópia do cofre em dados/<cliente>.<usuario>.enc.json, com a
# própria senha, e entra pelo link app?cliente=<cliente>&equipe (pede usuário e senha).
# Para tirar um acesso: apagar do ACESSOS_ e o arquivo dele.

import base64
import json
import os
import secrets
import sys

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from coletor import ENV, PASTA

ITERACOES = 600_000
b64 = lambda b: base64.b64encode(b).decode()


def chave(senha, sal):
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=sal, iterations=ITERACOES)
    # Igual ao app: sem espaços nas pontas e sem diferença de maiúsculas
    return kdf.derive(senha.strip().lower().encode("utf-8"))


def senha_de(cliente):
    senha = ENV.get(f"SENHA_{cliente.upper()}")
    if not senha:
        sys.exit(f"Falta SENHA_{cliente.upper()} no .env (ou nos segredos do GitHub)")
    return senha


def arquivos(cliente):
    d = PASTA / "dados"
    return d / f"{cliente}.json", d / f"{cliente}.notas.json", d / f"{cliente}.enc.json"


def acessos(cliente):
    """ACESSOS_<CLIENTE>=usuario:senha,... -> {usuario: senha} (usuário em minúsculas)."""
    texto = ENV.get(f"ACESSOS_{cliente.upper()}", "")
    pares = (item.split(":", 1) for item in texto.split(",") if ":" in item)
    return {u.strip().lower(): s.strip() for u, s in pares if u.strip() and s.strip()}


def cifrar(cliente, dados, sal=None, senha=None):
    """bytes -> envelope {v, iteracoes, sal, iv, dados} (o que vai para o repositório)."""
    sal = sal or secrets.token_bytes(16)
    iv = secrets.token_bytes(12)
    cifrado = AESGCM(chave(senha or senha_de(cliente), sal)).encrypt(iv, dados, None)
    return {"v": 1, "iteracoes": ITERACOES, "sal": b64(sal), "iv": b64(iv), "dados": b64(cifrado)}


def decifrar(cliente, envelope):
    k = chave(senha_de(cliente), base64.b64decode(envelope["sal"]))
    return AESGCM(k).decrypt(base64.b64decode(envelope["iv"]), base64.b64decode(envelope["dados"]), None)


def abrir(cliente):
    """Devolve o conteúdo do cofre (ou vazio se ainda não existe)."""
    _, _, enc = arquivos(cliente)
    if not enc.exists():
        return {"historico": [], "notas": {"feitos": [], "passos": []}}
    return json.loads(decifrar(cliente, json.loads(enc.read_text(encoding="utf-8"))))


def fechar(cliente, conteudo):
    _, _, enc = arquivos(cliente)
    texto = json.dumps(conteudo, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    enc.parent.mkdir(exist_ok=True)
    gravar_envelope(cliente, enc, texto)
    for usuario, senha in acessos(cliente).items():
        gravar_envelope(cliente, enc.with_name(f"{cliente}.{usuario}.enc.json"), texto, senha)


def gravar_envelope(cliente, arquivo, texto, senha=None):
    # Mantém o sal do cofre anterior: assim a chave lembrada nos aparelhos continua valendo
    sal = base64.b64decode(json.loads(arquivo.read_text(encoding="utf-8"))["sal"]) if arquivo.exists() else None
    arquivo.write_text(json.dumps(cifrar(cliente, texto, sal, senha)), encoding="utf-8")


def ler_json(caminho, padrao):
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else padrao


def criar_senha(cliente):
    nome = f"SENHA_{cliente.upper()}"
    if ENV.get(nome):
        print(f"{nome} já existe no .env")
        return
    # 4 palavras + 2 dígitos: fácil de digitar no celular, difícil de adivinhar
    palavras = ("abacaxi acerola agenda alecrim amora anzol arara areia aroeira astro aurora avela azeite "
                "bambu banana baunilha bicicleta biscoito bolacha bolota bosque brisa buriti cacau caderno caju "
                "camelo canela canoa capim caqui carambola castanha cebola cedro cereja chave chuva cidade "
                "cipreste cobre coco coelho cometa coral corda coruja cravo cristal damasco duna escada esfera "
                "estrela farol feijao figo floresta folha fonte formiga framboesa gaivota garoa girassol goiaba "
                "granito grilo guarana horta ilha ipe jabuti jambo janela jasmim jaca jardim jequitiba jiboia "
                "lagoa laranja lareira lima limao lince lontra lua maca macaxeira manga maracuja mel melancia "
                "menta mirante montanha morango musgo nevoa noz oceano oliva onda orquidea ouro palmeira papel "
                "pequi pera peteca pimenta pinha pipa planeta pomar ponte quiabo quintal raposa rio romã rosa "
                "sabia salvia semente serra sol tamarindo tatu telha tigre tomate trilha trovao tucano uva vale "
                "vela veleiro vento violeta vulcao xicara").replace("ã", "a").split()
    senha = "-".join(secrets.choice(palavras) for _ in range(4)) + f"-{secrets.randbelow(90) + 10}"
    arquivo = PASTA / ".env"
    with arquivo.open("a", encoding="utf-8") as f:
        f.write(f"\n# Senha do app do cliente {cliente} (dar ao cliente; também vai nos segredos do GitHub)\n{nome}={senha}\n")
    print(f"{nome} criada no .env")


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("fechar", "abrir", "senha"):
        print(__doc__)
        sys.exit(1)
    acao, cliente = sys.argv[1], sys.argv[2]
    historico, notas, _ = arquivos(cliente)
    if acao == "senha":
        criar_senha(cliente)
    elif acao == "abrir":
        conteudo = abrir(cliente)
        historico.parent.mkdir(exist_ok=True)
        historico.write_text(json.dumps(conteudo["historico"], ensure_ascii=False, indent=1), encoding="utf-8")
        notas.write_text(json.dumps(conteudo["notas"], ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{cliente}: cofre aberto ({len(conteudo['historico'])} dias)")
    else:
        conteudo = {"historico": ler_json(historico, []), "notas": ler_json(notas, {"feitos": [], "passos": []})}
        fechar(cliente, conteudo)
        print(f"{cliente}: cofre fechado ({len(conteudo['historico'])} dias, "
              f"{len(conteudo['notas']['feitos'])} anotações)")


if __name__ == "__main__":
    main()
