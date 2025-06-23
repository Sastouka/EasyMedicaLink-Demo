# --- pwa.py (mis à jour) ---
# Ajout d'un alias pour service-worker.js afin de résoudre le 404
from flask import (
    Blueprint, url_for, make_response,
    send_from_directory, current_app
)
import json, pathlib

# Blueprint PWA
pwa_bp = Blueprint(
    "pwa_bp", __name__,
    static_folder="static",
    url_prefix=""
)

# BASE_DIR for PWA assets remains static as PWA assets are globally accessible
# and not specific to an admin's dynamic folder.
BASE_DIR = pathlib.Path(__file__).resolve().parent
ICON_DIR = BASE_DIR / "static" / "pwa"
ICON_DIR.mkdir(parents=True, exist_ok=True)

# Manifest dynamique
def _manifest():
    return {
        "name":             "EasyMedicalink",
        "short_name":       "EML",
        "start_url":        "/login",
        "scope":            "/",
        "display":          "standalone",
        "theme_color":      "#1a73e8",
        "background_color": "#ffffff",
        "icons": [
            {
                "src":   url_for("pwa_bp.pwa_icon", filename="icon-192.png"),
                "sizes": "192x192",
                "type":  "image/png"
            },
            {
                "src":   url_for("pwa_bp.pwa_icon", filename="icon-512.png"),
                "sizes": "512x512",
                "type":  "image/png"
            }
        ]
    }

@pwa_bp.route("/manifest.webmanifest")
def manifest():
    resp = make_response(
        json.dumps(_manifest(), ensure_ascii=False, separators=(",", ":"))
    )
    resp.headers["Content-Type"] = "application/manifest+json"
    resp.cache_control.max_age = 86400
    return resp

@pwa_bp.route("/sw.js")
def sw():
    # PWA service worker URLs, typically static and don't depend on dynamic user folders
    urls = [
        url_for("pwa_bp.manifest"),
        url_for("pwa_bp.sw"),
        url_for("pwa_bp.pwa_icon", filename="icon-192.png"),
        url_for("pwa_bp.pwa_icon", filename="icon-512.png"),
        "/",
        "/login"
    ]
    urls.extend(current_app.config.get("PWA_OFFLINE_URLS", []))

    sw_code = f"""
const CACHE_NAME = 'em-cache-v2';
const PRECACHE_URLS = {json.dumps(urls)};

self.addEventListener('install', event => {{
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
}});

self.addEventListener('activate', event => {{
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(key => key !== CACHE_NAME)
            .map(key => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
}});

self.addEventListener('fetch', event => {{
  if (event.request.method !== 'GET') return;
  event.respondWith(
    caches.match(event.request).then(cachedResponse => {{
      return cachedResponse || fetch(event.request).then(networkResponse => {{
        if (networkResponse && networkResponse.ok) {{
          caches.open(CACHE_NAME)
                .then(cache => cache.put(event.request, networkResponse.clone()));
        }}
        return networkResponse;
      }});
    }});
  );
}});
"""
    resp = make_response(sw_code, 200)
    resp.headers["Content-Type"] = "text/javascript"
    resp.cache_control.no_cache = True
    return resp

# Alias pour service-worker.js
@pwa_bp.route("/service-worker.js")
def service_worker():
    return sw()

@pwa_bp.route("/icon/<path:filename>")
def pwa_icon(filename):
    return send_from_directory(ICON_DIR, filename)

@pwa_bp.app_context_processor
def inject_pwa():
    def pwa_head():
        return f"""
<link rel="manifest" href="{url_for('pwa_bp.manifest')}">
<link rel="apple-touch-icon" sizes="192x192"
      href="{url_for('pwa_bp.pwa_icon', filename='icon-192.png')}">
<meta name="theme-color" content="#1a73e8">
<meta name="apple-mobile-web-app-capable" content="yes">
<script>
  if ('serviceWorker' in navigator) {{
    navigator.serviceWorker.register('{url_for('pwa_bp.sw')}', {{ scope: '/' }})
      .then(() => console.log('Service Worker enregistré'))
      .catch(err => console.error('Erreur d’enregistrement SW:', err));
  }}
</script>
"""
    return dict(pwa_head=pwa_head)
