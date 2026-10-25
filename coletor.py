# Coletor diário do app de acompanhamento (Marketing Essencial).
#
# Lê, pela API oficial da Meta, os números do dia do Instagram (conta
# profissional) e da página do Facebook de um cliente e grava o histórico que o
# app mostra:
#   dados/<cliente>.json  ->  [{ "data": "2026-10-24", "instagram": {...}, "facebook": {...} }, ...]
#
# Só leitura: nada é publicado, respondido ou alterado nas contas.
#
# Uso:  python coletor.py <cliente>              (ex.: python coletor.py studio)
#       python coletor.py <cliente> 2026-10-20   (um dia específico)
#       python coletor.py <cliente> --dias 30    (refaz os últimos 30 dias + hoje)
#       python coletor.py <cliente> --contas     (lista páginas e Instagrams que a chave enxerga)
#
# Configuração em .env (mesma pasta; nunca vai para o GitHub nem para o app):
#   META_TOKEN=...            chave de acesso de longa duração (só leitura)
#   IG_<CLIENTE>=1784...      id da conta do Instagram desse cliente (o --contas mostra)
#   FB_<CLIENTE>=5769...      id da página do Facebook desse cliente (opcional)
#   META_VERSAO=v26.0         opcional
#
# Regra do serviço: não inventar dados. Métrica que a API não devolver fica
# null (o app mostra "—"), nunca um número estimado.

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PASTA = Path(__file__).parent
FUSO = timezone(timedelta(hours=-3))  # Brasília


def ler_env():
    env = {}
    arquivo = PASTA / ".env"
    if arquivo.exists():
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            if "=" in linha and not linha.strip().startswith("#"):
                k, v = linha.split("=", 1)
                env[k.strip()] = v.strip()
    # No robô do GitHub não há .env: as chaves vêm dos segredos, como variáveis de ambiente
    env.update({k: v for k, v in os.environ.items() if k.split("_")[0] in ("META", "IG", "FB", "SENHA") and v})
    return env


ENV = ler_env()
VERSAO = ENV.get("META_VERSAO", "v26.0")


def api(caminho, token=None, **params):
    params["access_token"] = token or ENV["META_TOKEN"]
    url = f"https://graph.facebook.com/{VERSAO}/{caminho}?{urllib.parse.urlencode(params)}"
    for tentativa in range(2):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            erro = json.loads(e.read() or b"{}").get("error", {})
            # A Meta às vezes devolve "unexpected error" passageiro: tenta mais uma vez
            if tentativa == 0 and erro.get("code") in (1, 2):
                continue
            # A mensagem da Meta não contém a chave; mesmo assim, não imprimimos a URL
            raise RuntimeError(f"Meta API {e.code}: {erro.get('message', 'erro')} ({caminho})") from None


def paginas(caminho, limite=200, token=None, **params):
    """Percorre uma lista paginada da API."""
    itens, dados = [], api(caminho, token=token, **params)
    while True:
        itens += dados.get("data", [])
        prox = dados.get("paging", {}).get("next")
        if not prox or len(itens) >= limite:
            return itens
        with urllib.request.urlopen(prox, timeout=30) as r:
            dados = json.load(r)


def quando(texto):
    return datetime.fromisoformat(texto.replace("+0000", "+00:00"))


def listar_contas():
    for p in paginas("me/accounts", fields="id,name,instagram_business_account{id,username,followers_count}"):
        ig = p.get("instagram_business_account")
        print(f"Página: {p['name']} (id {p['id']})")
        print(f"  Instagram: @{ig['username']} id {ig['id']} ({ig.get('followers_count')} seguidores)" if ig
              else "  Instagram: nenhum ligado a esta página")


# ---------------------------------------------------------------- Instagram

def metrica_ig(ig, nome, dia):
    """Total do dia (fuso de Brasília) de uma métrica da conta; None se a API não der."""
    ini = datetime.combine(dia, datetime.min.time(), FUSO)
    try:
        r = api(f"{ig}/insights", metric=nome, period="day", metric_type="total_value",
                since=int(ini.timestamp()), until=int((ini + timedelta(days=1)).timestamp()))
        return r["data"][0]["total_value"]["value"]
    except (RuntimeError, KeyError, IndexError):
        return None


def insights_post_ig(midia):
    tipo = midia.get("media_product_type")
    nomes = "reach,saved,views,shares" if tipo != "STORY" else "reach,views"
    try:
        r = api(f"{midia['id']}/insights", metric=nomes)
        return {m["name"]: m["values"][0]["value"] for m in r.get("data", [])}
    except RuntimeError:
        return {}


def coletar_instagram(ig, dia):
    conta = api(ig, fields="username,name,followers_count,profile_picture_url")
    usuario = conta["username"]

    ini = datetime.combine(dia, datetime.min.time(), FUSO)
    fim = ini + timedelta(days=1)
    posts, comentarios = [], []
    # Posts do dia e comentários do dia (em posts de até 30 dias, onde a conversa acontece)
    for m in paginas(f"{ig}/media", limite=60,
                     fields="id,caption,media_type,media_product_type,timestamp,permalink,"
                            "like_count,comments_count,thumbnail_url,media_url"):
        q = quando(m["timestamp"])
        if q < ini - timedelta(days=30):
            break
        if ini <= q < fim:
            ins = insights_post_ig(m)
            posts.append({
                "id": m["id"],
                "tipo": {"REELS": "Reels", "STORY": "Story"}.get(m.get("media_product_type"), "Feed"),
                "legenda": (m.get("caption") or "").strip()[:220],
                "link": m.get("permalink"),
                "imagem": m.get("thumbnail_url") or m.get("media_url"),
                "curtidas": m.get("like_count"),
                "comentarios": m.get("comments_count"),
                "salvamentos": ins.get("saved"),
                "compartilhamentos": ins.get("shares"),
                "alcance": ins.get("reach"),
                "visualizacoes": ins.get("views"),
                "hora": q.astimezone(FUSO).strftime("%H:%M"),
            })
        if m.get("comments_count"):
            for c in paginas(f"{m['id']}/comments", limite=100,
                             fields="id,text,timestamp,username,replies{username}"):
                cq = quando(c["timestamp"])
                if not (ini <= cq < fim) or c.get("username") == usuario:
                    continue
                respostas = c.get("replies", {}).get("data", [])
                comentarios.append({
                    "texto": c.get("text", ""),
                    # O app não mostra o @ de quem comentou
                    "quem": "cliente",
                    "respondido": any(r.get("username") == usuario for r in respostas),
                    "post": m.get("permalink"),
                    "hora": cq.astimezone(FUSO).strftime("%H:%M"),
                })

    return {
        "perfil": usuario,
        "nome": conta.get("name"),
        "foto": conta.get("profile_picture_url"),
        "seguidores": conta.get("followers_count"),
        "alcance": metrica_ig(ig, "reach", dia),
        "visitas": metrica_ig(ig, "profile_views", dia),
        "cliquesLink": metrica_ig(ig, "website_clicks", dia),
        "contasEngajadas": metrica_ig(ig, "accounts_engaged", dia),
        "posts": posts,
        "comentarios": comentarios,
    }


# ---------------------------------------------------------------- Facebook

def token_da_pagina(pagina):
    """Os dados da página pedem a chave da própria página, derivada da chave do .env."""
    for p in paginas("me/accounts", fields="id,access_token"):
        if p["id"] == pagina:
            return p["access_token"]
    raise RuntimeError(f"A chave não enxerga a página {pagina} (confira com --contas)")


def metricas_fb(pagina, token, nomes, dia):
    """Valores do dia de várias métricas da página; None nas que a API não der.
    Os dias da página seguem o fuso da Meta (Califórnia), não o de Brasília."""
    try:
        r = api(f"{pagina}/insights", token=token, metric=",".join(nomes), period="day",
                since=dia.isoformat(), until=(dia + timedelta(days=1)).isoformat())
        dados = {d["name"]: d["values"][-1]["value"] for d in r.get("data", []) if d.get("values")}
    except RuntimeError:
        dados = {}
    return {n: dados.get(n) for n in nomes}


def insights_post_fb(post, token):
    try:
        r = api(f"{post}/insights", token=token, metric="post_media_view,post_total_media_view_unique",
                period="lifetime")
        return {m["name"]: m["values"][0]["value"] for m in r.get("data", [])}
    except (RuntimeError, KeyError, IndexError):
        return {}


def coletar_facebook(pagina, dia):
    token = token_da_pagina(pagina)
    conta = api(pagina, token=token, fields="name,followers_count,picture.width(200).height(200){url}")
    m = metricas_fb(pagina, token, ["page_total_media_view_unique", "page_views_total",
                                    "page_post_engagements", "page_daily_follows_unique"], dia)

    ini = datetime.combine(dia, datetime.min.time(), FUSO)
    fim = ini + timedelta(days=1)
    posts, comentarios = [], []
    for p in paginas(f"{pagina}/posts", limite=60, token=token,
                     fields="id,created_time,message,permalink_url,full_picture,shares,"
                            "reactions.summary(true).limit(0),comments.summary(true).limit(0)"):
        q = quando(p["created_time"])
        if q < ini - timedelta(days=30):
            break
        total_coment = p.get("comments", {}).get("summary", {}).get("total_count")
        if ini <= q < fim:
            ins = insights_post_fb(p["id"], token)
            posts.append({
                "id": p["id"],
                "tipo": "Post",
                "legenda": (p.get("message") or "").strip()[:220],
                "link": p.get("permalink_url"),
                "imagem": p.get("full_picture"),
                "curtidas": p.get("reactions", {}).get("summary", {}).get("total_count"),
                "comentarios": total_coment,
                "compartilhamentos": p.get("shares", {}).get("count", 0),
                "alcance": ins.get("post_total_media_view_unique"),
                "visualizacoes": ins.get("post_media_view"),
                "hora": q.astimezone(FUSO).strftime("%H:%M"),
            })
        if total_coment:
            for c in paginas(f"{p['id']}/comments", limite=100, token=token,
                             fields="id,message,created_time,from{id},comments{from{id}}"):
                cq = quando(c["created_time"])
                if not (ini <= cq < fim) or c.get("from", {}).get("id") == pagina:
                    continue
                respostas = c.get("comments", {}).get("data", [])
                comentarios.append({
                    "texto": c.get("message", ""),
                    "quem": "cliente",
                    "respondido": any(r.get("from", {}).get("id") == pagina for r in respostas),
                    "post": p.get("permalink_url"),
                    "hora": cq.astimezone(FUSO).strftime("%H:%M"),
                })

    return {
        "nome": conta.get("name"),
        "foto": conta.get("picture", {}).get("data", {}).get("url"),
        "seguidores": conta.get("followers_count"),
        "alcance": m["page_total_media_view_unique"],
        "visitas": m["page_views_total"],
        "engajamento": m["page_post_engagements"],
        "novos": m["page_daily_follows_unique"],
        "posts": posts,
        "comentarios": comentarios,
    }


# ---------------------------------------------------------------- histórico

def coletar(cliente, dia):
    registro = {"data": dia.isoformat()}
    ig = ENV.get(f"IG_{cliente.upper()}")
    fb = ENV.get(f"FB_{cliente.upper()}")
    if ig:
        registro["instagram"] = coletar_instagram(ig, dia)
    if fb:
        registro["facebook"] = coletar_facebook(fb, dia)
    registro["coletadoEm"] = datetime.now(FUSO).isoformat(timespec="minutes")
    return registro


def gravar(cliente, registros):
    destino = PASTA / "dados" / f"{cliente}.json"
    destino.parent.mkdir(exist_ok=True)
    historico = json.loads(destino.read_text(encoding="utf-8")) if destino.exists() else []
    novas = {r["data"] for r in registros}
    # Registros no formato antigo (só Instagram, sem a chave "instagram") são descartados
    historico = [d for d in historico if d["data"] not in novas and ("instagram" in d or "facebook" in d)]
    historico = sorted(historico + registros, key=lambda d: d["data"])
    # Instagram: novos seguidores = diferença para o dia anterior registrado
    for a, b in zip(historico, historico[1:]):
        ia, ib = a.get("instagram"), b.get("instagram")
        if ib:
            ib["novos"] = (ib["seguidores"] - ia["seguidores"]) if ia and None not in (
                ia["seguidores"], ib["seguidores"]) else None
    destino.write_text(json.dumps(historico, ensure_ascii=False, indent=1), encoding="utf-8")
    return destino


def main():
    if len(sys.argv) < 2 or "META_TOKEN" not in ENV:
        print(__doc__ if len(sys.argv) < 2 else "Falta META_TOKEN no .env")
        sys.exit(1)
    if "--contas" in sys.argv:
        listar_contas()
        return
    cliente = sys.argv[1]
    hoje = datetime.now(FUSO).date()
    if "--dias" in sys.argv:
        n = int(sys.argv[sys.argv.index("--dias") + 1])
        dias = [hoje - timedelta(days=i) for i in range(n, -1, -1)]
    else:
        dias = [date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else hoje]

    registros = []
    for dia in dias:
        r = coletar(cliente, dia)
        registros.append(r)
        resumo = [f"{rede}: {len(r[rede]['posts'])} posts, {len(r[rede]['comentarios'])} comentários, "
                  f"{r[rede]['seguidores']} seguidores" for rede in ("instagram", "facebook") if rede in r]
        print(f"{cliente} {r['data']} | " + " | ".join(resumo))
    destino = gravar(cliente, registros)
    print(f"-> {destino.name}")


if __name__ == "__main__":
    main()
