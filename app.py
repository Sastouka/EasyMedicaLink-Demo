import os
import webbrowser
from flask import Flask, session, redirect, url_for, request, render_template_string
from datetime import timedelta

# ───────────── 1. Création de l’application
def create_app():
    app = Flask(
        __name__,
        static_folder='static',
        static_url_path='/static',
        template_folder='templates'
    )
    # Utiliser une clé secrète depuis les variables d'environnement
    app.secret_key = os.environ.get("SECRET_KEY", "dev")
    app.permanent_session_lifetime = timedelta(days=7) # Les sessions durent 7 jours

    # ───────────── 2. Thèmes
    import theme
    theme.init_theme(app)

    @app.context_processor
    def inject_theme_names():
        return {"theme_names": list(theme.THEMES.keys())}

    # ───────────── Injection des paramètres globaux dans tous les templates
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

    # ───────────── Enregistrement des Blueprints
    import pwa
    import login
    import accueil
    import administrateur
    import rdv
    import facturation
    import statistique
    import developpeur
    import routes # Importe le module contenant la fonction register_routes
    import activation # Importe le module activation pour accéder à son blueprint

    # Enregistrer les Blueprints en premier
    app.register_blueprint(pwa.pwa_bp)
    app.register_blueprint(login.login_bp)
    app.register_blueprint(accueil.accueil_bp)
    app.register_blueprint(administrateur.administrateur_bp)
    app.register_blueprint(developpeur.developpeur_bp)
    app.register_blueprint(rdv.rdv_bp, url_prefix="/rdv")
    app.register_blueprint(facturation.facturation_bp)
    app.register_blueprint(statistique.statistique_bp, url_prefix="/statistique")
    # Enregistrer le blueprint d'activation après les autres blueprints
    app.register_blueprint(activation.activation_bp) # Déplacé ici

    # Initialisation du middleware d'activation
    activation.init_app(app) # Cet init_app va maintenant seulement enregistrer le before_request

    # ───────────── 7. Route racine
    @app.route("/", methods=["GET"])
    def root():
        # Si non connecté, redirige vers login ; sinon vers accueil
        return redirect(url_for("login.login")) if "email" not in session else redirect(url_for("accueil.accueil"))

    # ───────────── 8. Sécurisation des routes et initialisation dynamique des chemins
    @app.before_request
    def setup_dynamic_paths(): # Renommée de require_login pour être plus explicite sur sa fonction
        # Définir le répertoire de base dynamique basé sur l'e-mail de l'administrateur de la session actuelle.
        # Ceci doit s'exécuter avant toute autre logique qui dépend des chemins de fichiers.
        # L'e-mail de l'administrateur DOIT être correctement défini dans session['admin_email']
        # lors du processus de connexion (dans votre blueprint 'login').
        admin_email = session.get('admin_email', 'default_admin@example.com')

        # Ligne de débogage : Affiche l'e-mail utilisé pour les chemins de données
        print(f"DEBUG: L'application utilise le répertoire de données pour : {admin_email}")

        utils.set_dynamic_base_dir(admin_email)
        # Réinitialiser les utilitaires avec l'instance de l'application après que le chemin dynamique soit défini
        utils.init_app(app)
        # Charger les données du patient, ceci utilise maintenant les chemins définis dynamiquement
        utils.load_patient_data()

        # Définir les points d'accès autorisés (devraient idéalement être gérés de manière plus évolutive si nombreux)
        # Par simplicité, listés ici.
        allowed_endpoints = {
            # Actifs PWA
            "pwa_bp.manifest", "pwa_bp.sw", "pwa_bp.pwa_icon",
            # Public / authentification
            "root", "static",
            "login.login", "login.register", "login.forgot_password", "login.reset_password",
            "login.change_password", "login.logout",
            # Activation & PayPal (maintenant correctement référencé avec le nom du blueprint)
            "activation.activation", "activation.paypal_success", "activation.paypal_cancel",
            # Autres routes publiques ou points d'accès API qui ne nécessitent pas encore de connexion
            "theme.set_theme", # Permettre les changements de thème sans connexion
            "offline" # Page hors ligne
        }

        # Vérifier si le point d'accès de la requête actuelle nécessite une connexion
        # Cette logique devrait généralement être après la configuration des chemins spécifiques à l'URL
        if request.endpoint not in allowed_endpoints and "email" not in session:
            # Pour le débogage, afficher le point d'accès qui a causé la redirection
            print(f"DEBUG: Redirection vers la connexion. Point d'accès : {request.endpoint}, Email de session : {'email' in session}")
            return redirect(url_for("login.login"))

    # ───────────── 9. Autres petites routes
    # Appeler routes.register_routes(app) ici, APRÈS que @app.before_request soit enregistré.
    # Cela garantit que lorsque register_routes est exécuté, le contexte de l'application (et donc la session)
    # est correctement configuré pour toute logique dépendante de la session dans les définitions de route de routes.py.
    routes.register_routes(app)

    # ───────────── 10. Configuration PWA hors-ligne
    with app.app_context():
        # Utiliser app.test_request_context() pour construire des URLs en dehors d'une vraie requête.
        # Ceci est à des fins de mise en cache PWA, pas pour la gestion des requêtes à l'exécution.
        with app.test_request_context('/'): # Créer un contexte de requête factice pour url_for
            offline_urls = []
            for rule in app.url_map.iter_rules():
                if "GET" in rule.methods and not ("<" in rule.rule or rule.rule.startswith("/static")):
                    try:
                        # Tenter de construire l'URL ; ignorer si elle nécessite des arguments non fournis
                        # ou si c'est une route dynamique non destinée à la mise en cache générale.
                        url = url_for(rule.endpoint)
                        offline_urls.append(url)
                    except Exception as e:
                        # print(f"Ignorer l'URL pour le cache hors ligne PWA ({rule.endpoint}) : {e}")
                        pass # Ignorer les règles qui ne peuvent pas être construites sans paramètres

            offline_urls.append('/offline')
            app.config['PWA_OFFLINE_URLS'] = list(set(offline_urls)) # Supprimer les doublons
            print(f"URLs hors ligne PWA définies : {app.config['PWA_OFFLINE_URLS']}")


    # ───────────── 11. Page de secours hors-ligne
    @app.route("/offline")
    def offline():
        # Le contenu de cette route est un HTML autonome
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

    print("Application Flask démarrée et Blueprints enregistrés.")
    return app

# ───────────── Initialisation de l'application pour Gunicorn
# Cette ligne est déplacée ici pour que 'app' soit disponible au niveau du module
app = create_app()

# ───────────── 12. Lancement pour le développement local
if __name__ == '__main__':
    try:
        # Ouvrir dans le navigateur web seulement si pas dans un environnement conteneurisé (comme replit)
        # Ceci est une heuristique ; le déploiement réel pourrait différer.
        if os.environ.get("FLASK_ENV") != "production" and not os.environ.get("REPL_SLUG"):
             webbrowser.open("http://127.0.0.1:3000/login")
    except Exception as e:
        print(f"Impossible d'ouvrir le navigateur web : {e}")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 3000)))