import os
import webbrowser
from flask import Flask, session, redirect, url_for, request, render_template, render_template_string

# ───────────── 1. Création de l’application
app = Flask(
    __name__,
    static_folder='static',
    static_url_path='/static',
    template_folder='templates'
)
# Utiliser une clé secrète depuis les variables d'environnement
app.secret_key = os.environ.get("SECRET_KEY", "dev")

# ───────────── 2. Thèmes
import theme
theme.init_theme(app)

@app.context_processor
def inject_theme_names():
    return {"theme_names": list(theme.THEMES.keys())}

# ───────────── 3. Injection des paramètres globaux dans tous les templates
import utils
@app.context_processor
def inject_config_values():
    cfg = utils.load_config()
    return {
        'app_name':             cfg.get('app_name', 'EasyMedicalink'),
        'theme':                cfg.get('theme', 'clair'),
        'logo_path':            cfg.get('logo_path', '/static/logo.png'),
        'background_file_path': cfg.get('background_file_path', '')
    }

# ───────────── 4. Initialisation des utils (Excel, PDF…)
utils.init_app(app)
from utils import load_config, background_file as _default_bg
cfg = load_config()
app.background_path = cfg.get("background_file_path") or _default_bg
import utils as _u; _u.background_file = app.background_path  # synchronisation

# ───────────── 5. Activation (middleware + routes)
from activation import init_app as init_activation, register_routes as register_activation_routes
init_activation(app)
register_activation_routes(app)

# ───────────── 6. Enregistrement des Blueprints
from pwa import pwa_bp
from login import login_bp
from accueil import accueil_bp
from administrateur import administrateur_bp
from rdv import rdv_bp
from facturation import facturation_bp
from statistique import statistique_bp
from developpeur import developpeur_bp
from routes import register_routes

# PWA en premier
app.register_blueprint(pwa_bp)
app.register_blueprint(login_bp)
app.register_blueprint(accueil_bp)
app.register_blueprint(administrateur_bp)
app.register_blueprint(developpeur_bp)
app.register_blueprint(rdv_bp, url_prefix="/rdv")
app.register_blueprint(facturation_bp)
app.register_blueprint(statistique_bp, url_prefix="/statistique")

# ───────────── 7. Route racine
@app.route("/", methods=["GET"])
def root():
    # Si non connecté, redirige vers login ; sinon vers accueil
    return redirect(url_for("login.login")) if "email" not in session else redirect(url_for("accueil.accueil"))

# ───────────── 8. Sécurisation des routes
@app.before_request
def require_login():
    allowed = {
        # PWA assets
        "pwa_bp.manifest", "pwa_bp.sw", "pwa_bp.pwa_icon",
        # Public / auth
        "root", "static",
        "login.login", "login.register", "login.forgot_password", "login.reset_password",
        # Activation & PayPal
        "activation", "trial_expired", "paypal_success", "paypal_cancel", "purchase_plan", "admin",
        # Accueil
        "accueil.accueil",
        # Admin module
        "administrateur_bp.dashboard", "administrateur_bp.create_user",
        "administrateur_bp.toggle_active", "administrateur_bp.delete_user",
        # Développeur
        "developpeur_bp.dashboard", "developpeur_bp.create_admin",
        "developpeur_bp.toggle_active", "developpeur_bp.delete_admin", "developpeur_bp.gen_custom",
        # RDV
        "rdv.rdv_home", "rdv.delete_rdv", "rdv.consult_rdv", "rdv.pdf_today",
        # Facturation
        "facturation.facturation_home", "facturation.download_invoice",
        "facturation.generate_invoice", "facturation.delete_invoice", "facturation.generate_report",
        # Statistique
        "statistique.stats_home",
        # Page hors-ligne
        "offline"
    }
    if request.endpoint not in allowed and "email" not in session:
        return redirect(url_for("login.login"))

# ───────────── 9. Autres petites routes
register_routes(app)

# ───────────── 10. Configuration PWA hors-ligne
with app.app_context():
    offline_urls = [
        rule.rule for rule in app.url_map.iter_rules()
        if "GET" in rule.methods and "<" not in rule.rule and not rule.rule.startswith("/static")
    ]
    offline_urls.append('/offline')
    app.config['PWA_OFFLINE_URLS'] = offline_urls

# ───────────── 11. Page de secours hors-ligne
@app.route("/offline")
def offline():
    return render_template_string("""
<!DOCTYPE html>
<html lang="fr">
  {{ pwa_head()|safe }}
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Hors-ligne</title>
  <style>
    body { display:flex;flex-direction:column;justify-content:center;align-items:center;height:100vh;margin:0;font-family:sans-serif;background:#f0f0f0;color:#333; }
    h1{font-size:2.5rem;margin-bottom:0.5rem;} p{font-size:1.1rem;}
  </style>
</head>
<body>
  <h1>Vous êtes hors-ligne</h1>
  <p>Vérifiez votre connexion et réessayez plus tard.</p>
</body>
</html>
"""), 200

# ───────────── 12. Lancement
if __name__ == "__main__":
    try:
        webbrowser.open("http://127.0.0.1:3000/login")
    except:
        pass
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 3000)))