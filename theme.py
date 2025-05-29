# theme.py
# Module de gestion de thèmes pour l'application Flask
# Permet de définir jusqu'à 10 thèmes personnalisables

from flask import session, current_app

# Définition des thèmes :
# Chaque thème est un dict de variables CSS (--var-name : valeur).
THEMES = {    "turquoise": {
        # These colors are from the login_template's .btn-gradient for a strong turquoise feel
        "gradient-start-color": "#1a73e8", # A blueish start from login.py
        "gradient-end-color": "#0d9488",   # The prominent turquoise/teal from login.py
        "text-color": "#0b3c5d",           # A dark blue, similar to your light theme text
        "primary-color": "#0d9488",        # Main turquoise for elements
        "secondary-color": "#1a73e8",      # Secondary blue for links/accents
        "button-bg": "#0d9488",            # Button background, can also be a gradient
        "button-text": "#ffffff",
        "card-bg": "#ffffff",
        "card-shadow": "rgba(0, 60, 100, 0.1)", # Similar to light theme shadow
    },    "deep_ocean": {
        "bg-color": "#e0f2f7",
        "text-color": "#001a33",
        "primary-color": "#000080",
        "secondary-color": "#4682B4",
        "button-bg": "#000080",
        "button-text": "#ffffff",
        "card-bg": "#ffffff",
        "card-shadow": "rgba(0, 0, 128, 0.2)",
    },    "rose": {
        "bg-color": "#fdf2f8",
        "text-color": "#831843",
        "primary-color": "#db2777",
        "secondary-color": "#be185d",
        "button-bg": "#db2777",
        "button-text": "#ffffff",
        "card-bg": "#ffffff",
        "card-shadow": "rgba(219, 39, 119, 0.2)",
    },    "warm_sunset": {
        "bg-color": "#fff3e0",
        "text-color": "#8b4513",
        "primary-color": "#FF7F50",
        "secondary-color": "#FFD700",
        "button-bg": "#FF7F50",
        "button-text": "#ffffff",
        "card-bg": "#ffffff",
        "card-shadow": "rgba(255, 127, 80, 0.2)",
    },
    "light": {
        "bg-color":      "#f5f9ff",      # Fond clair, hygiène et propreté
        "text-color":    "#0b3c5d",      # Bleu marine confortable
        "primary-color": "#1e81b0",      # Bleu calme et professionnel
        "secondary-color":"#a7c5eb",     # Bleu pastel apaisant
        "button-bg":     "#1e81b0",
        "button-text":   "#ffffff",
        "card-bg":       "#ffffff",
        "card-shadow":   "rgba(0, 60, 100, 0.1)",
    },
    "dark": {
        "bg-color":      "#0b3c5d",      # Bleu marine profond
        "text-color":    "#ffffff",      # Texte blanc pour contraste
        "primary-color": "#3da5d9",      # Cyan vif, moderne
        "secondary-color":"#6ebfea",     # Bleu clair
        "button-bg":     "#3da5d9",
        "button-text":   "#ffffff",
        "card-bg":       "#1f2833",      # Gris bleuté sombre
        "card-shadow":   "rgba(61, 165, 217, 0.2)",
    },
    "ocean": {
        "bg-color":      "#e0f7fa",      # Aqua doux, rappel d'eau stérile
        "text-color":    "#004d40",      # Teal sombre
        "primary-color": "#00796b",      # Teal professionnel
        "secondary-color":"#b2dfdb",     # Teal clair
        "button-bg":     "#00796b",
        "button-text":   "#ffffff",
        "card-bg":       "#ffffff",
        "card-shadow":   "rgba(0, 121, 107, 0.2)",
    },
    "sunset": {
        "bg-color":      "#fff8e1",      # Jaune pâle, chaleureux
        "text-color":    "#bf360c",      # Rouge profond
        "primary-color": "#e65100",      # Orange prononcé
        "secondary-color":"#ffab40",     # Orange doux
        "button-bg":     "#e65100",
        "button-text":   "#ffffff",
        "card-bg":       "#ffffff",
        "card-shadow":   "rgba(230, 81, 0, 0.2)",
    },
    "forest": {
        "bg-color":      "#e8f5e9",      # Vert menthe, frais
        "text-color":    "#1b5e20",      # Vert foncé
        "primary-color": "#2e7d32",      # Vert médecine
        "secondary-color":"#a5d6a7",     # Vert clair
        "button-bg":     "#2e7d32",
        "button-text":   "#ffffff",
        "card-bg":       "#ffffff",
        "card-shadow":   "rgba(46, 125, 50, 0.2)",
    },
    "slate": {
        "bg-color": "#f8fafc",
        "text-color": "#0f172a",
        "primary-color": "#64748b",
        "secondary-color": "#475569",
        "button-bg": "#64748b",
        "button-text": "#ffffff",
        "card-bg": "#ffffff",
        "card-shadow": "rgba(71, 84, 105, 0.1)",
    },
    "sunrise": {
        "bg-color": "#fffbeb",
        "text-color": "#78350f",
        "primary-color": "#f59e0b",
        "secondary-color": "#d97706",
        "button-bg": "#f59e0b",
        "button-text": "#ffffff",
        "card-bg": "#ffffff",
        "card-shadow": "rgba(245, 158, 11, 0.2)",
    },
    "violet": {
        "bg-color": "#f5f3ff",
        "text-color": "#3730a3",
        "primary-color": "#7c3aed",
        "secondary-color": "#6d28d9",
        "button-bg": "#7c3aed",
        "button-text": "#ffffff",
        "card-bg": "#ffffff",
        "card-shadow": "rgba(124, 58, 237, 0.2)",
    },
    "emerald": {
        "bg-color": "#ecfdf5",
        "text-color": "#065f46",
        "primary-color": "#10b981",
        "secondary-color": "#047857",
        "button-bg": "#10b981",
        "button-text": "#ffffff",
        "card-bg": "#ffffff",
        "card-shadow": "rgba(16, 185, 129, 0.2)",
    },
    "royal_blue": {
        "bg-color": "#e6f0ff",
        "text-color": "#002060",
        "primary-color": "#4169E1",
        "secondary-color": "#87CEEB",
        "button-bg": "#4169E1",
        "button-text": "#ffffff",
        "card-bg": "#ffffff",
        "card-shadow": "rgba(65, 105, 225, 0.2)",
    },
}

# Valeur par défaut
DEFAULT_THEME = "turquoise"

def get_theme(name: str) -> dict:
    """Retourne le dict de variables CSS pour un thème donné."""
    return THEMES.get(name, THEMES[DEFAULT_THEME])

def current_theme() -> dict:
    """Récupère le thème courant depuis la session Flask."""
    theme_name = session.get('theme', DEFAULT_THEME)
    return get_theme(theme_name)

def init_theme(app):
    """Enregistre le context_processor pour injecter les variables de thème dans les templates."""
    @app.context_processor
    def inject_theme_vars():
        return {'theme_vars': current_theme()}

    # Endpoint pour changer de thème
    @app.route('/set_theme/<name>')
    def set_theme(name):
        if name in THEMES:
            session['theme'] = name
        return ('', 204)