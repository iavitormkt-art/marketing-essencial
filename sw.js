// Guarda as telas do app para abrir rápido (e sem internet, com os últimos dados)
const CACHE = "me-v10";
const ARQUIVOS = ["./", "index.html", "manifest.webmanifest", "icone-192.png", "icone-180.png", "marca/logo-vc-96.png"];
self.addEventListener("install", (e) => e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ARQUIVOS))));
self.addEventListener("activate", (e) =>
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))),
);
// Rede primeiro (dados sempre frescos); se cair, usa a cópia guardada
self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET") return;
  if (new URL(e.request.url).origin !== location.origin) return; // servidor do chat e outros: direto da rede
  e.respondWith(
    fetch(e.request)
      .then((r) => {
        const copia = r.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copia));
        return r;
      })
      .catch(() => caches.match(e.request)),
  );
});

// Aviso de mensagem nova na Conversa (Web Push enviado pelo servidor do Studio)
self.addEventListener("push", (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch { d = { corpo: e.data?.text() }; }
  e.waitUntil(self.registration.showNotification(d.titulo || "Marketing Essencial", {
    body: d.corpo || "Mensagem nova", icon: "icone-192.png", badge: "icone-192.png", tag: "conversa", renotify: true,
    data: { url: new URL(d.url || "./?aba=chat", self.registration.scope).href },
  }));
});
self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const alvo = e.notification.data?.url || self.registration.scope;
  e.waitUntil(clients.matchAll({ type: "window", includeUncontrolled: true }).then((lista) => {
    for (const c of lista) if ("focus" in c) { c.navigate(alvo).catch(() => {}); return c.focus(); }
    return clients.openWindow(alvo);
  }));
});
