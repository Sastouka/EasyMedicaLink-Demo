# administrateur.py
# ──────────────────────────────────────────────────────────────────────────────
#  Version mise à jour :
#    • _current_plan() lit désormais le plan dans users.json (bloc 'activation').
#    • Plus aucune référence à utils.ACTIVATION_FILE.
#    • Boutons de téléchargement toujours affichés en bas.
#    • Aucune autre ligne d’origine perdue ; filtres propriétaire + rôles inchangés.
#    • Ajout d'un bouton pour télécharger toutes les données Excel dans un seul fichier.
#    • Ajout d'un bouton pour importer une base de données Excel (fichiers multiples en feuilles).
#    • Amélioration de l'esthétique des boutons d'export/import avec icônes et gestion du chargement.
#    • Réorganisation de l'affichage des boutons : Excel en haut, exécutables en bas.
#    • NOUVEAU : Vérification d'unicité globale de l'email pour la création de comptes.
#    • NOUVEAU : Convention d'e-mail pour les médecins/assistantes : prenom.nom@<admin_prefix>.eml.com
# ──────────────────────────────────────────────────────────────────────────────

from flask import Blueprint, render_template_string, request, redirect, url_for, flash, session, abort, send_file, jsonify, current_app
from datetime import datetime
import json
from pathlib import Path
import theme
import utils
import login
import io
import pandas as pd
import os
import re # Importation ajoutée pour l'extraction du préfixe d'e-mail de l'admin
from werkzeug.utils import secure_filename

# Importez la fonction _load_all_excels depuis statistique.py
# Assurez-vous que statistique.py est accessible dans le même répertoire
# ou dans un chemin d'importation Python.
try:
    from statistique import _load_all_excels
except ImportError:
    # Fallback si statistique.py n'est pas directement importable,
    # vous pouvez copier la fonction ici ou gérer l'erreur.
    print("ATTENTION: Impossible d'importer _load_all_excels de statistique.py. Assurez-vous que le fichier est présent et accessible.")
    # Définition d'une version minimale pour éviter les erreurs si l'import échoue
    def _load_all_excels(folder: str) -> dict:
        print(f"AVERTISSEMENT: _load_all_excels n'est pas disponible. Le téléchargement/importation Excel ne fonctionnera pas.")
        return {}

# Import de la nouvelle fonction de vérification d'unicité globale
from login import _is_email_globally_unique

# Récupération de TRIAL_DAYS pour l’affichage
try:
    from activation import TRIAL_DAYS
except ImportError:
    TRIAL_DAYS = 7

administrateur_bp = Blueprint('administrateur_bp', __name__, url_prefix='/administrateur')

# ──────────────────────────────────────────────────────────────────────────────
# Helper plan
# ──────────────────────────────────────────────────────────────────────────────
def _current_plan() -> str:
    """
    Renvoie le plan de licence de l’administrateur connecté (lecture users.json).
    """
    mapping = {
        f"essai_{TRIAL_DAYS}jours": f"Essai ({TRIAL_DAYS} jours)",
        "1 an":     "1 an",
        "illimité": "Illimité",
    }
    user = login.load_users().get(session.get("email"))
    plan_raw = (
        user.get("activation", {}).get("plan", "").lower()
        if user else ""
    )
    return mapping.get(plan_raw, plan_raw.capitalize() or "Inconnu")

# ──────────────────────────────────────────────────────────────────────────────
# NOUVELLE ROUTE : Importer Arrière-plan (ajoutée ici)
# ──────────────────────────────────────────────────────────────────────────────
@administrateur_bp.route("/import_background", methods=["POST"])
def import_background():
    # Ensure utils.BACKGROUND_FOLDER is set (it should be via app.before_request in a full app context)
    if utils.BACKGROUND_FOLDER is None:
        return jsonify({"status": "error", "message": "Erreur: Le chemin du dossier d'arrière-plan n'est pas défini."}), 500

    if "background_file" not in request.files or request.files["background_file"].filename == "":
        flash("Aucun fichier sélectionné pour l'arrière-plan.", "warning")
        return jsonify({"status": "warning", "message": "Aucun fichier sélectionné."})

    f = request.files["background_file"]
    filename = secure_filename(f.filename) # Use secure_filename
    path = os.path.join(utils.BACKGROUND_FOLDER, filename)
    
    try:
        f.save(path)
        ext = os.path.splitext(filename)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".pdf"):
            os.remove(path) # Delete unsupported file
            flash("Format non supporté (seuls PNG, JPG, JPEG, GIF, BMP, PDF sont acceptés).", "warning")
            return jsonify({"status": "warning", "message": "Format non supporté (seuls PNG, JPG, JPEG, GIF, BMP, PDF sont acceptés)."})

        # Load, update, and save config
        cfg = utils.load_config()
        cfg["background_file_path"] = filename # Store only the filename
        utils.save_config(cfg)
        
        # Update the global background_file in utils for immediate effect
        utils.init_app(current_app._get_current_object()) # Pass the real app object

        flash(f"Arrière plan importé : {filename}", "success")
        return jsonify({"status": "success", "message": f"Arrière plan importé : {filename}"})
    except Exception as e:
        flash(f"Erreur lors de l'importation de l'arrière-plan : {e}", "danger")
        return jsonify({"status": "error", "message": f"Erreur : {e}"})

@administrateur_bp.route('/', methods=['GET'])
def dashboard():
    if 'email' not in session:
        return redirect(url_for('login.login'))

    # Debugging : afficher le chemin du dossier static et son contenu
    import os
    from flask import current_app
    static_folder = current_app.static_folder
    print("Static folder =", static_folder)
    try:
        contents = os.listdir(static_folder)
        print("Contenu de static/ =", contents)
    except Exception as e:
        print("Erreur lors de la lecture du dossier static :", e)

    # Détection robuste des exécutables, même si Windows a ajouté « .exe.exe »
    win64_filename = next(
        (f for f in contents if f.startswith('EasyMedicaLink-Win64.exe')),
        None
    )
    win32_filename = next(
        (f for f in contents if f.startswith('EasyMedicaLink-Win32.exe')),
        None
    )

    admin_email  = session['email']
    full_users   = login.load_users()
    
    # Préparez les utilisateurs pour le tableau en s'assurant que toutes les clés sont présentes
    users_for_table = []
    for e, u in full_users.items():
        if u.get('role') in ('medecin', 'assistante') and u.get('owner') == admin_email:
            # Assurez-vous que toutes les clés nécessaires pour le template sont présentes, avec des valeurs par défaut
            user_info = {
                'email': e,
                'nom': u.get('nom', ''),
                'prenom': u.get('prenom', ''),
                'role': u.get('role', ''),
                'active': u.get('active', False), # Default to False if not specified
                'phone': u.get('phone', ''), # Ensure phone is present for WhatsApp link
            }
            users_for_table.append(user_info)

    config       = utils.load_config()
    current_date = datetime.now().strftime("%Y-%m-%d")

    # Get available background files for settings form
    backgrounds_folder = utils.BACKGROUND_FOLDER
    backgrounds = []
    if os.path.exists(backgrounds_folder):
        backgrounds = [f for f in os.listdir(backgrounds_folder) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.pdf'))]


    return render_template_string(
        administrateur_template,
        users=users_for_table, # Passez la liste préparée
        config=config,
        current_date=current_date,
        theme_vars=theme.current_theme(),
        theme_names=list(theme.THEMES.keys()),
        plan=_current_plan(),
        admin_email=admin_email,
        win64_filename=win64_filename,
        win32_filename=win32_filename,
        backgrounds=backgrounds # Pass backgrounds to the template
    )

@administrateur_bp.route('/get_user/<user_email>')
def get_user(user_email):
    u = login.load_users().get(user_email)
    if not u:
        return {}, 404
    # S'assurer que les clés sont présentes pour la réponse JSON
    return {
        'nom': u.get('nom', ''),
        'prenom': u.get('prenom', ''),
        'role': u.get('role', '')
    }

@administrateur_bp.route('/create_user', methods=['POST'])
def create_user():
    if 'email' not in session:
        return redirect(url_for('login.login'))
    
    admin_email = session['email']
    data        = request.form
    
    # Extraire le préfixe de l'e-mail de l'administrateur (partie avant le '@')
    admin_email_prefix = admin_email.split('@')[0]
    
    # Construire l'e-mail du nouvel utilisateur avec la convention souhaitée
    # Ex: prenom.nom@admin_prefix.eml.com
    key = f"{data['prenom'].lower()}.{data['nom'].lower()}@{admin_email_prefix}.eml.com"

    # NOUVEAU: Vérification d'unicité globale de l'email
    # On utilise la fonction de login pour vérifier dans TOUS les dossiers d'admins
    if not _is_email_globally_unique(key):
        flash(f"L'e-mail '{key}' est déjà utilisé par un autre compte (médecin, assistante ou administrateur).", "danger")
        return redirect(url_for('administrateur_bp.dashboard'))

    users = login.load_users() # Charge les utilisateurs du dossier de l'administrateur courant

    # Vérification d'unicité locale (au cas où, bien que la globale soit plus forte)
    if key in users:
        flash("Un utilisateur avec cet e-mail existe déjà sous votre compte administrateur.", "warning")
    else:
        users[key] = {
            'nom':      data['nom'],
            'prenom':   data['prenom'],
            'role':     data['role'],
            'password': login.hash_password(data['password']),
            'active':   True,
            'owner':    admin_email # L'administrateur qui crée ce compte est le propriétaire
        }
        login.save_users(users)
        flash("Compte créé avec succès !", "success")
    
    return redirect(url_for('administrateur_bp.dashboard'))

@administrateur_bp.route('/edit_user', methods=['POST'])
def edit_user():
    data      = request.form
    old_email = data['email']
    new_email = data.get('new_email', old_email).strip().lower()
    users     = login.load_users()
    if old_email not in users or users[old_email].get('owner') != session.get('email'):
        flash("Action non autorisée.", "error")
        return redirect(url_for('administrateur_bp.dashboard'))
    user = users.pop(old_email)

    # NOUVEAU: Vérification d'unicité globale si l'email change
    if new_email != old_email and not _is_email_globally_unique(new_email):
        flash(f"Le nouvel e-mail '{new_email}' est déjà utilisé par un autre compte dans le système.", "danger")
        # Remettre l'utilisateur sous l'ancien email avant de rediriger pour éviter de le perdre
        users[old_email] = user
        login.save_users(users) # Sauvegarder l'état original
        return redirect(url_for('administrateur_bp.dashboard'))


    user.update({'nom': data['nom'], 'prenom': data['prenom'], 'role': data['role']})
    new_pwd = data.get('new_password', '').strip()
    if new_pwd:
        user['password'] = login.hash_password(new_pwd)
    users[new_email] = user
    login.save_users(users)
    flash("Données mises à jour.", "success")
    return redirect(url_for('administrateur_bp.dashboard'))

@administrateur_bp.route('/toggle_active/<user_email>')
def toggle_active(user_email):
    users = login.load_users()
    if user_email in users and users[user_email].get('owner') == session.get('email'):
        users[user_email]['active'] = not users[user_email]['active']
        login.save_users(users)
    return redirect(url_for('administrateur_bp.dashboard'))

@administrateur_bp.route('/delete_user/<user_email>')
def delete_user(user_email):
    users = login.load_users()
    if user_email in users and users[user_email].get('owner') == session.get('email'):
        users.pop(user_email)
        login.save_users(users)
    return redirect(url_for('administrateur_bp.dashboard'))

@administrateur_bp.route("/download_all_excels")
def download_all_excels():
    # Vérification des autorisations (seuls les administrateurs peuvent télécharger)
    if session.get("role") != "admin":
        flash("Accès réservé aux administrateurs.", "danger")
        return redirect(url_for("accueil.accueil")) # Rediriger vers l'accueil ou login

    try:
        # Charger tous les DataFrames depuis le dossier Excel
        df_map = _load_all_excels(utils.EXCEL_FOLDER)

        if not df_map:
            flash("Aucun fichier Excel trouvé pour l'export.", "warning")
            return redirect(url_for("administrateur_bp.dashboard"))

        # Créer un buffer en mémoire pour le fichier Excel
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            for filename, df in df_map.items():
                # Nettoyer le nom de la feuille (max 31 caractères, pas de caractères invalides)
                sheet_name = filename.replace(".xlsx", "").replace(".xls", "")
                # Supprimer les caractères non autorisés dans les noms de feuille Excel
                sheet_name = "".join(c for c in sheet_name if c.isalnum() or c in [' ', '_', '-'])
                sheet_name = sheet_name[:31] # Limite de 31 caractères pour les noms de feuille Excel
                
                # Écrire le DataFrame dans une feuille du fichier Excel
                df.to_excel(writer, sheet_name=sheet_name, index=False)
        buffer.seek(0) # Remettre le curseur au début du buffer

        # Préparer le nom du fichier de téléchargement
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"EasyMedicaLink_Donnees_Excel_{timestamp}.xlsx"

        return send_file(
            buffer,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        # Gérer les erreurs et flasher un message
        flash(f"Erreur lors de la génération du fichier Excel : {e}", "danger")
        return redirect(url_for("administrateur_bp.dashboard"))

@administrateur_bp.route("/upload_excel_database", methods=["POST"])
def upload_excel_database():
    # Vérification des autorisations (seuls les administrateurs peuvent importer)
    if session.get("role") != "admin":
        flash("Accès réservé aux administrateurs.", "danger")
        return redirect(url_for("accueil.accueil"))
        
    if 'excel_file' not in request.files:
        flash("Aucun fichier n'a été sélectionné.", "warning")
        return redirect(url_for("administrateur_bp.dashboard"))

    file = request.files['excel_file']

    if file.filename == '':
        flash("Aucun fichier n'a été sélectionné.", "warning")
        return redirect(url_for("administrateur_bp.dashboard"))

    if file and (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
        try:
            # Lire toutes les feuilles du fichier Excel importé
            # sheet_name=None retourne un dictionnaire de DataFrames
            imported_dfs = pd.read_excel(file.stream, sheet_name=None)

            # Parcourir les fichiers Excel existants dans le dossier utils.EXCEL_FOLDER
            updated_count = 0
            for original_filename in os.listdir(utils.EXCEL_FOLDER):
                if original_filename.lower().endswith(('.xlsx', '.xls')):
                    # Nettoyer le nom du fichier pour le faire correspondre aux noms de feuille
                    # C'est l'inverse du nettoyage fait lors de l'exportation
                    cleaned_sheet_name = original_filename.replace(".xlsx", "").replace(".xls", "")
                    cleaned_sheet_name = "".join(c for c in cleaned_sheet_name if c.isalnum() or c in [' ', '_', '-'])
                    cleaned_sheet_name = cleaned_sheet_name[:31] # S'assurer que ça correspond à la logique d'export

                    if cleaned_sheet_name in imported_dfs:
                        df_to_save = imported_dfs[cleaned_sheet_name]
                        original_file_path = os.path.join(utils.EXCEL_FOLDER, original_filename)
                        
                        # Sauvegarder le DataFrame importé à l'emplacement du fichier original
                        df_to_save.to_excel(original_file_path, index=False)
                        updated_count += 1
            
            if updated_count > 0:
                flash(f"{updated_count} fichier(s) Excel mis à jour avec succès.", "success")
            else:
                flash("Aucun fichier Excel correspondant n'a été trouvé ou mis à jour.", "warning")

        except Exception as e:
            flash(f"Erreur lors de l'importation du fichier Excel : {e}", "danger")
    else:
        flash("Type de fichier non autorisé. Veuillez importer un fichier .xlsx ou .xls.", "danger")

    return redirect(url_for("administrateur_bp.dashboard"))
  
# ──────────────────────────────────────────────────────────────────────────────
# TEMPLATE HTML (le contenu de cette variable est maintenant mis à jour)
# ──────────────────────────────────────────────────────────────────────────────
administrateur_template = """
<!DOCTYPE html>
<html lang="fr">
{{ pwa_head()|safe }}
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
  <title>Administration - {{ config.nom_clinique or 'EasyMedicaLink' }}</title>

  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.datatables.net/1.13.1/css/dataTables.bootstrap5.min.css" rel="stylesheet">
  <link href="https://cdn.datatables.net/responsive/2.4.1/css/responsive.bootstrap5.min.css" rel="stylesheet">

  <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700&family=Great+Vibes&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>

  <style>
    :root {
      {% for var, val in theme_vars.items() %}
      --{{ var }}: {{ val }};
      {% endfor %}
      --font-primary: 'Poppins', sans-serif;
      --font-secondary: 'Great Vibes', cursive;
      --gradient-main: linear-gradient(45deg, var(--primary-color) 0%, var(--secondary-color) 100%);
      --shadow-light: 0 5px 15px rgba(0, 0, 0, 0.1);
      --shadow-medium: 0 8px 25px rgba(0, 0, 0, 0.2);
      --border-radius-lg: 1rem;
      --border-radius-md: 0.75rem;
      --border-radius-sm: 0.5rem;
    }

    body {
      font-family: var(--font-primary);
      background: var(--bg-color);
      color: var(--text-color);
      padding-top: 56px;
      transition: background 0.3s ease, color 0.3s ease;
    }

    .navbar {
      background: var(--gradient-main) !important;
      box-shadow: var(--shadow-medium);
    }
    .navbar-brand {
      font-family: var(--font-secondary);
      font-size: 2.0rem !important;
      color: white !important;
      display: flex;
      align-items: center;
      transition: transform 0.3s ease;
    }
    .navbar-brand:hover {
      transform: scale(1.05);
    }
    .navbar-toggler {
      border: none;
      outline: none;
    }
    .navbar-toggler i {
      color: white;
      font-size: 1.5rem;
    }

    .offcanvas-header {
      background: var(--gradient-main) !important;
      color: white;
    }
    .offcanvas-body {
      background: var(--card-bg) !important;
      color: var(--text-color) !important;
    }
    .offcanvas-title {
      font-weight: 600;
    }

    .card {
      border-radius: var(--border-radius-lg);
      box-shadow: var(--shadow-light);
      background: var(--card-bg) !important;
      color: var(--text-color) !important;
      border: none;
      transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .card:hover {
      box-shadow: var(--shadow-medium);
    }

    .card-header {
      background: var(--primary-color) !important;
      color: var(--button-text) !important;
      border-top-left-radius: var(--border-radius-lg);
      border-top-right-radius: var(--border-radius-lg);
      padding: 1.5rem;
      position: relative;
      overflow: hidden;
    }
    .card-header::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(255, 255, 255, 0.1);
      transform: skewY(-5deg);
      transform-origin: top left;
      z-index: 0;
    }
    .card-header h1, .card-header .header-item, .card-header p {
      position: relative;
      z-index: 1;
      font-size: 1.8rem !important;
      font-weight: 700;
    }
    .card-header i {
      font-size: 1.8rem !important;
      margin-right: 0.5rem;
    }
    .header-item {
      font-size: 1.2rem !important;
      font-weight: 400;
    }

    /* Floating Labels */
    .floating-label {
      position: relative;
      margin-bottom: 1rem;
    }
    .floating-label input,
    .floating-label select,
    .floating-label textarea {
      padding: 1rem 0.75rem 0.5rem;
      height: auto;
      border-radius: var(--border-radius-sm);
      border: 1px solid var(--secondary-color);
      background-color: var(--card-bg);
      color: var(--text-color);
      transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }
    .floating-label input:focus,
    .floating-label select:focus,
    .floating-label textarea:focus {
      border-color: var(--primary-color);
      box-shadow: 0 0 0 0.25rem rgba(var(--primary-color-rgb), 0.25);
      background-color: var(--card-bg);
      color: var(--text-color);
    }
    .floating-label label {
      position: absolute;
      top: 0.75rem;
      left: 0.75rem;
      font-size: 1rem;
      color: var(--text-color-light);
      transition: all 0.2s ease;
      pointer-events: none;
    }
    .floating-label input:focus + label,
    .floating-label input:not(:placeholder-shown) + label,
    .floating-label select:focus + label,
    .floating-label select:not([value=""]) + label,
    .floating-label textarea:focus + label,
    .floating-label textarea:not(:placeholder-shown) + label {
      top: 0.25rem;
      left: 0.75rem;
      font-size: 0.75rem;
      color: var(--primary-color);
      background-color: var(--card-bg);
      padding: 0 0.25rem;
      transform: translateX(-0.25rem);
    }
    .floating-label input[type="date"]:not([value=""])::-webkit-datetime-edit-text,
    .floating-label input[type="date"]:not([value=""])::-webkit-datetime-edit-month-field,
    .floating-label input[type="date"]:not([value=""])::-webkit-datetime-edit-day-field,
    .floating-label input[type="date"]:not([value=""])::-webkit-datetime-edit-year-field {
      color: var(--text-color);
    }
    .floating-label input[type="date"]::-webkit-calendar-picker-indicator {
      filter: {% if session.theme == 'dark' %}invert(1){% else %}none{% endif %};
    }

    /* Buttons */
    .btn {
      border-radius: var(--border-radius-md);
      font-weight: 600;
      transition: all 0.3s ease;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 0.75rem 1.25rem;
    }
    .btn i {
      margin-right: 0.5rem;
    }
    .btn-primary {
      background: var(--gradient-main);
      border: none;
      color: var(--button-text);
      box-shadow: var(--shadow-light);
    }
    .btn-primary:hover {
      box-shadow: var(--shadow-medium);
      background: var(--gradient-main);
      opacity: 0.9;
    }
    .btn-success {
      background-color: var(--success-color);
      border-color: var(--success-color);
      color: white;
      box-shadow: var(--shadow-light); /* Added for consistency */
    }
    .btn-success:hover {
      background-color: var(--success-color-dark);
      border-color: var(--success-color-dark);
      box-shadow: var(--shadow-medium);
    }
    .btn-warning {
      background-color: var(--warning-color);
      border-color: var(--warning-color);
      color: white;
    }
    .btn-warning:hover {
      background-color: var(--warning-color-dark);
      border-color: var(--warning-color-dark);
      box-shadow: var(--shadow-medium);
    }
    .btn-danger {
      background-color: var(--danger-color);
      border-color: var(--danger-color);
      color: white;
    }
    .btn-danger:hover {
      background-color: var(--danger-color-dark);
      border-color: var(--danger-color-dark);
      box-shadow: var(--shadow-medium);
    }
    .btn-info { /* WhatsApp button */
      background-color: #25D366;
      border-color: #25D366;
      color: white;
      box-shadow: var(--shadow-light); /* Added for consistency */
    }
    .btn-info:hover {
      background-color: #1DA851;
      border-color: #1DA851;
      box-shadow: var(--shadow-medium);
    }
    .btn-outline-secondary {
      border-color: var(--secondary-color);
      color: var(--text-color);
      background-color: transparent;
    }
    .btn-outline-secondary:hover {
      background-color: var(--secondary-color);
      color: white;
      box-shadow: var(--shadow-light);
    }
    .btn-secondary {
      background-color: var(--secondary-color);
      border-color: var(--secondary-color);
      color: var(--button-text);
    }
    .btn-secondary:hover {
      background-color: var(--secondary-color-dark);
      border-color: var(--secondary-color-dark);
      box-shadow: var(--shadow-medium);
    }
    .btn-sm {
      padding: 0.5rem 0.8rem;
      font-size: 0.875rem;
    }

    /* Icon Cards */
    .icon-card {
      flex: 1 1 170px;
      max-width: 180px;
      color: var(--primary-color);
      padding: 0.5rem;
      text-decoration: none;
      transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .icon-card:hover {
      transform: translateY(-5px);
      box-shadow: var(--shadow-medium);
    }
    .icon-card i {
      font-size: 40px !important;
      margin-bottom: 0.5rem;
    }
    .icon-card span {
      font-size: 1.1rem !important;
      font-weight: 600;
      color: var(--text-color);
    }
    .icon-card .border {
      border-radius: var(--border-radius-lg);
      border: 1px solid var(--border-color) !important;
      background-color: var(--card-bg);
      box-shadow: var(--shadow-light);
      transition: all 0.2s ease;
    }
    .icon-card:hover .border {
      border-color: var(--primary-color) !important;
    }

    /* DataTables */
    #usersTable_wrapper .dataTables_filter input,
    #usersTable_wrapper .dataTables_length select {
      border-radius: var(--border-radius-sm);
      border: 1px solid var(--secondary-color);
      padding: 0.5rem 0.75rem;
      background-color: var(--card-bg);
      color: var(--text-color);
    }
    #usersTable_wrapper .dataTables_filter input:focus,
    #usersTable_wrapper .dataTables_length select:focus {
      border-color: var(--primary-color);
      box-shadow: 0 0 0 0.25rem rgba(var(--primary-color-rgb), 0.25);
    }
    /* Hide the dropdown arrow for DataTables length select */
    #usersTable_wrapper .dataTables_length select {
      -webkit-appearance: none;
      -moz-appearance: none;
      appearance: none;
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath fill='none' stroke='%23333' stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M2 5l6 6 6-6'/%3E%3Csvg%3E");
      background-repeat: no-repeat;
      background-position: right 0.75rem center;
      background-size: 0.65em auto;
      padding-right: 2rem;
    }
    body.dark-theme #usersTable_wrapper .dataTables_length select {
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath fill='none' stroke='%23fff' stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M2 5l6 6 6-6'/%3E%3Csvg%3E");
    }

    #usersTable_wrapper .dataTables_paginate .pagination .page-item .page-link {
      border-radius: var(--border-radius-sm);
      margin: 0 0.2rem;
      background-color: var(--card-bg);
      color: var(--text-color);
      border: 1px solid var(--secondary-color);
    }
    #usersTable_wrapper .dataTables_paginate .pagination .page-item.active .page-link {
      background: var(--gradient-main);
      border-color: var(--primary-color);
      color: var(--button-text);
    }
    #usersTable_wrapper .dataTables_paginate .pagination .page-item .page-link:hover {
      background-color: rgba(var(--primary-color-rgb), 0.1);
      color: var(--primary-color);
    }
    .table {
      --bs-table-bg: var(--card-bg);
      --bs-table-color: var(--text-color);
      --bs-table-striped-bg: var(--table-striped-bg);
      --bs-table-striped-color: var(--text-color);
      --bs-table-border-color: var(--border-color);
    }
    .table thead th {
      background-color: var(--primary-color);
      color: var(--button-text);
      border-color: var(--primary-color);
    }
    .table tbody tr {
      transition: background-color 0.2s ease;
    }
    .table tbody tr:hover {
      background-color: rgba(var(--primary-color-rgb), 0.05) !important;
    }

    /* Flash messages */
    .alert {
      border-radius: var(--border-radius-md);
      font-weight: 600;
      position: fixed;
      top: 70px;
      left: 50%;
      transform: translateX(-50%);
      z-index: 1060;
      width: 90%;
      max-width: 500px;
      box-shadow: var(--shadow-medium);
      animation: fadeInOut 5s forwards;
    }

    @keyframes fadeInOut {
      0% { opacity: 0; transform: translateX(-50%) translateY(-20px); }
      10% { opacity: 1; transform: translateX(-50%) translateY(0); }
      90% { opacity: 1; transform: translateX(-50%) translateY(0); }
      100% { opacity: 0; transform: translateX(-50%) translateY(-20px); }
    }

    /* Footer */
    footer {
      background: var(--gradient-main);
      color: white;
      font-weight: 300;
      box-shadow: 0 -5px 15px rgba(0, 0, 0, 0.1);
      padding-top: 0.75rem;
      padding-bottom: 0.75rem;
    }
    footer p {
      margin-bottom: 0.25rem;
    }

    /* Modals */
    .modal-content {
      background-color: var(--card-bg);
      color: var(--text-color);
      border-radius: var(--border-radius-lg);
      box-shadow: var(--shadow-medium);
    }
    .modal-header {
      background: var(--gradient-main);
      color: var(--button-text);
      border-top-left-radius: var(--border-radius-lg);
      border-top-right-radius: var(--border-radius-lg);
    }
    .modal-title {
      color: var(--button-text);
    }
    .btn-close {
      filter: invert(1);
    }

    /* Responsive adjustments */
    @media (max-width: 768px) {
      .card-header h1 {
        font-size: 1.5rem !important;
      }
      .card-header .header-item {
        font-size: 1rem !important;
      }
      .card-header i {
        font-size: 1.5rem !important;
      }
      .icon-card {
        flex: 1 1 140px;
        max-width: 160px;
      }
      .icon-card i {
        font-size: 32px !important;
      }
      .icon-card span {
        font-size: 20px !important;
      }
      .btn {
        width: 100%;
        margin-bottom: 0.5rem;
      }
      .d-flex.gap-2 {
        flex-direction: column;
      }
      .dataTables_filter, .dataTables_length {
        text-align: center !important;
      }
      .dataTables_filter input, .dataTables_length select {
        width: 100%;
        margin-bottom: 0.5rem;
      }

      /* Responsive for export/import buttons */
      .excel-buttons .btn {
          padding: 0.6rem 1rem; /* Smaller padding */
          font-size: 0.9rem; /* Smaller font */
      }
      .excel-buttons .btn .full-text {
          display: none; /* Hide full text on small screens */
      }
      .excel-buttons .btn .abbr-text {
          display: inline; /* Show abbreviation on small screens */
      }
      .executable-buttons .btn {
          padding: 0.6rem 1rem; /* Smaller padding */
          font-size: 0.9rem; /* Smaller font */
      }
      .executable-buttons .btn .full-text {
          display: none; /* Hide full text on small screens */
      }
      .executable-buttons .btn .abbr-text {
          display: inline; /* Show abbreviation on small screens */
      }
    }

    @media (min-width: 769px) {
        .excel-buttons .btn .full-text {
            display: inline; /* Show full text on larger screens */
        }
        .excel-buttons .btn .abbr-text {
            display: none; /* Hide abbreviation on larger screens */
        }
        .executable-buttons .btn .full-text {
            display: inline; /* Show full text on larger screens */
        }
        .executable-buttons .btn .abbr-text {
            display: none; /* Hide abbreviation on larger screens */
        }
    }
  </style>
</head>
<body>
  <nav class="navbar navbar-dark fixed-top">
    <div class="container-fluid d-flex align-items-center">
      <button class="navbar-toggler" type="button" data-bs-toggle="offcanvas" data-bs-target="#settingsOffcanvas">
        <i class="fas fa-bars"></i>
      </button>
      <a class="navbar-brand ms-auto d-flex align-items-center"
         href="{{ url_for('accueil.accueil') }}">
        <i class="fas fa-home me-2"></i>
        <i class="fas fa-heartbeat me-2"></i>EasyMedicaLink
      </a>
    </div>
  </nav>

<div class="offcanvas offcanvas-start" tabindex="-1" id="settingsOffcanvas">
  <div class="offcanvas-header text-white">
    <h5 class="offcanvas-title"><i class="fas fa-cog me-2"></i>Paramètres</h5>
    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="offcanvas"></button>
  </div>
  <div class="offcanvas-body">
    <div class="d-flex gap-2 mb-4">
      <a href="{{ url_for('login.change_password') }}" class="btn btn-outline-secondary flex-fill">
        <i class="fas fa-key me-2"></i>Modifier passe
      </a>
      <a href="{{ url_for('login.logout') }}" class="btn btn-outline-secondary flex-fill">
        <i class="fas fa-sign-out-alt me-2"></i>Déconnexion
      </a>
    </div>
    <form id="settingsForm" action="{{ url_for('settings') }}" method="POST">
      <div class="mb-3 floating-label">
        <input type="text" class="form-control" name="nom_clinique" id="nom_clinique"
               value="{{ config.nom_clinique | default('') }}" placeholder=" ">
        <label for="nom_clinique">Nom Clinique / Cabinet</label>
      </div>
      <div class="mb-3 floating-label">
        <input type="text" class="form-control" name="centre_medecin" id="centre_medecin"
               value="{{ config.centre_medical | default('') }}" placeholder=" ">
        <label for="centre_medecin">Centre Médical</label>
      </div>
      <div class="mb-3 floating-label">
        <input type="text" class="form-control" name="nom_medecin" id="nom_medecin"
               value="{{ config.doctor_name | default('') }}" placeholder=" ">
        <label for="nom_medecin">Nom Médecin</label>
      </div>
      <div class="mb-3 floating-label">
        <input type="text" class="form-control" name="lieu" id="lieu"
               value="{{ config.location | default('') }}" placeholder=" ">
        <label for="lieu">Lieu</label>
      </div>
      <div class="mb-3 floating-label">
        <select id="theme" name="theme" class="form-select" placeholder=" ">
          {% for t in theme_names %}
            <option value="{{ t }}" {% if config.theme == t %}selected{% endif %}>{{ t.capitalize() }}</option>
          {% endfor %}
        </select>
        <label for="theme">Thème</label>
      </div>
      <div class="mb-3 floating-label">
        <textarea class="form-control" name="liste_medicaments" id="liste_medicaments" rows="4" placeholder=" ">{% if config.medications_options %}{{ config.medications_options|join('\\n') }}{% endif %}</textarea>
        <label for="liste_medicaments">Liste des Médicaments</label>
      </div>
      <div class="mb-3 floating-label">
        <textarea class="form-control" name="liste_analyses" id="liste_analyses" rows="4" placeholder=" ">{% if config.analyses_options %}{{ config.analyses_options|join('\\n') }}{% endif %}</textarea>
        <label for="liste_analyses">Liste des Analyses</label>
      </div>
      <div class="mb-3 floating-label">
        <textarea class="form-control" name="liste_radiologies" id="liste_radiologies" rows="4" placeholder=" ">{% if config.radiologies_options %}{{ config.radiologies_options|join('\\n') }}{% endif %}</textarea>
        <label for="liste_radiologies">Liste des Radiologies</label>
      </div>
      <button type="submit" class="btn btn-success w-100">
        <i class="fas fa-save me-2"></i>Enregistrer
      </button>
    </form>
  </div>
</div>

  <script>
    document.getElementById('adminSettingsForm').addEventListener('submit',e=>{
      e.preventDefault();
      fetch(e.target.action,{method:'POST',body:new FormData(e.target),credentials:'same-origin'})
        .then(r=>{
          if(!r.ok) {
            Swal.fire({icon:'error',title:'Erreur',text:'Échec de la sauvegarde.'});
            throw new Error('Network response was not ok.');
          }
          return r.json(); // Assuming the settings endpoint returns JSON
        })
        .then(data => {
          Swal.fire({icon:'success',title:'Enregistré',text:'Paramètres sauvegardés.'}).then(() => {
            location.reload();
          });
        })
        .catch(error => {
          console.error('Error:', error);
          if (!error.message.includes('Network response was not ok.')) {
            Swal.fire({icon:'error',title:'Erreur',text:'Une erreur inattendue est survenue.'});
          }
        });
    });
  </script>

  <div class="container-fluid my-4">
    <div class="row justify-content-center">
      <div class="col-12">
        <div class="card shadow-lg">
          <div class="card-header py-3 text-center">
            <h1 class="mb-2 header-item"><i class="fas fa-hospital me-2"></i>{{ config.nom_clinique or 'NOM CLINIQUE/CABINET' }}</h1>
            <div class="d-flex justify-content-center gap-4 flex-wrap">
              <div class="d-flex align-items-center header-item"><i class="fas fa-user-md me-2"></i><span>{{ config.doctor_name or 'NOM MEDECIN' }}</span></div>
              <div class="d-flex align-items-center header-item"><i class="fas fa-map-marker-alt me-2"></i><span>{{ config.location or 'LIEU' }}</span></div>
            </div>
            <p class="mt-2 header-item"><i class="fas fa-calendar-day me-2"></i>{{ current_date }}</p>
          </div>

          <div class="card-body">
            <div class="mb-3 text-center">
              <h6 class="fw-bold"><i class="fas fa-id-badge me-2"></i>Informations de licence</h6>
              <p class="mb-1"><strong>Plan :</strong> {{ plan }}</p>
              <p class="mb-4"><strong>Administrateur :</strong> {{ admin_email }}</p>
            </div>

            <div class="d-flex justify-content-around flex-wrap gap-3">
              <a href="{{ url_for('rdv.rdv_home') }}" class="icon-card text-center">
                <div class="border rounded h-100 p-3 d-flex flex-column justify-content-center align-items-center">
                  <i class="fas fa-calendar-check mb-2"></i><span>RDV</span>
                </div>
              </a>
              <a href="{{ url_for('index') }}" class="icon-card text-center">
                <div class="border rounded h-100 p-3 d-flex flex-column justify-content-center align-items-center">
                  <i class="fas fa-stethoscope mb-2"></i><span>Consultations</span>
                </div>
              </a>
              <a href="{{ url_for('facturation.facturation_home') }}" class="icon-card text-center">
                <div class="border rounded h-100 p-3 d-flex flex-column justify-content-center align-items-center">
                  <i class="fas fa-file-invoice-dollar mb-2"></i><span>Factures</span>
                </div>
              </a>
              <a href="{{ url_for('statistique.stats_home') }}" class="icon-card text-center">
                <div class="border rounded h-100 p-3 d-flex flex-column justify-content-center align-items-center">
                  <i class="fas fa-chart-pie mb-2"></i><span>Statistiques</span>
                </div>
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
  
  <div class="d-flex justify-content-center flex-wrap gap-3 my-4">
    <button type="button" class="btn btn-primary" data-bs-toggle="modal" data-bs-target="#importBackgroundModal">
      <i class="fas fa-image me-2"></i>Importer Logo/Arrière-plan
    </button>
  </div>
  
  <div class="container-fluid my-4">
    <div class="row justify-content-center">
      <div class="col-12">
        <div class="card">
          <div class="card-header text-center"><h2 class="header-item">Administration des comptes</h2></div>
          <div class="card-body">
            <form class="row g-3 mb-4" method="POST" action="{{ url_for('administrateur_bp.create_user') }}">
              <div class="col-12 col-md-2 floating-label">
                <input name="nom" id="createNom" class="form-control" placeholder=" " required>
                <label for="createNom">Nom</label>
              </div>
              <div class="col-12 col-md-2 floating-label">
                <input name="prenom" id="createPrenom" class="form-control" placeholder=" " required>
                <label for="createPrenom">Prénom</label>
              </div>
              <div class="col-12 col-md-2 floating-label">
                <select name="role" id="createRole" class="form-select" placeholder=" " required>
                  <option value="medecin">Médecin</option>
                  <option value="assistante">Assistante</option>
                </select>
                <label for="createRole">Rôle</label>
              </div>
              <div class="col-12 col-md-2 floating-label">
                <input name="password" id="createPassword" type="password" class="form-control" placeholder=" " required>
                <label for="createPassword">Mot de passe</label>
              </div>
              <div class="col-12 col-md-2">
                <button class="btn btn-primary w-100" type="submit"><i class="fas fa-user-plus me-1"></i>Créer</button>
              </div>
            </form>

            <div class="table-responsive">
              <table id="usersTable" class="table table-striped table-hover nowrap" style="width:100%">
                <thead><tr><th>Nom</th><th>Prénom</th><th>Email</th><th>Rôle</th><th>Actif</th><th>Actions</th></tr></thead>
                <tbody>
                  {% for user_info in users %}
                  <tr>
                    <td>{{ user_info.nom }}</td>
                    <td>{{ user_info.prenom }}</td>
                    <td>{{ user_info.email }}</td>
                    <td>{{ user_info.role }}</td>
                    <td>{{ 'Oui' if user_info.active else 'Non' }}</td>
                    <td>
                      <a href="#" class="btn btn-sm btn-warning me-1 editBtn" data-email="{{ user_info.email }}" title="Modifier"><i class="fas fa-edit"></i></a>
                      <a href="{{ url_for('administrateur_bp.toggle_active', user_email=user_info.email) }}" class="btn btn-sm btn-outline-secondary me-1" title="Activer/Désactiver">
                        {% if user_info.active %}<i class="fas fa-user-slash"></i>{% else %}<i class="fas fa-user-check"></i>{% endif %}
                      </a>
                      <a href="#" onclick="confirmDeleteUser('{{ user_info.email }}')" class="btn btn-sm btn-danger" title="Supprimer"><i class="fas fa-trash"></i></a>
                    </td>
                  </tr>
                  {% endfor %}
                </tbody>
              </table>
            </div>

          </div>
        </div>
      </div>
    </div>
  </div>

  <div class="container-fluid my-4 mb-5">
    <div class="d-flex justify-content-center gap-3 flex-wrap excel-buttons">
      <a href="{{ url_for('administrateur_bp.download_all_excels') }}" class="btn btn-success">
        <i class="fas fa-file-excel me-2"></i><span class="full-text">Télécharger votre base de données</span><span class="abbr-text">Export DB</span>
      </a>
      <form action="{{ url_for('administrateur_bp.upload_excel_database') }}" method="POST" enctype="multipart/form-data" id="uploadExcelForm">
          <input type="file" name="excel_file" id="excel_file_upload" accept=".xlsx,.xls" class="d-none">
          <label for="excel_file_upload" class="btn btn-info">
              <i class="fas fa-upload me-2"></i><span class="full-text">Importer votre base de données</span><span class="abbr-text">Import DB</span>
          </label>
          <button type="submit" class="btn btn-info" id="upload_button" style="display:none;">
              <span id="upload_button_text"><i class="fas fa-arrow-up me-2"></i>Confirmer l'importation</span>
              <span id="upload_spinner" class="spinner-border spinner-border-sm" role="status" aria-hidden="true" style="display:none;"></span>
          </button>
      </form>
    </div>
    <div class="d-flex justify-content-center gap-3 flex-wrap mt-3 executable-buttons">
      {% if win64_filename %}
      <a href="{{ url_for('static', filename=win64_filename) }}" class="btn btn-primary">
        <i class="fas fa-download me-2"></i><span class="full-text">Télécharger EasyMedicalLink Win64</span><span class="abbr-text">Win64</span>
      </a>
      {% endif %}
      {% if win32_filename %}
      <a href="{{ url_for('static', filename=win32_filename) }}" class="btn btn-primary">
        <i class="fas fa-download me-2"></i><span class="full-text">Télécharger EasyMedicalLink Win32</span><span class="abbr-text">Win32</span>
      </a>
      {% endif %}
    </div>
  </div>

  <div class="modal fade" id="editModal" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog">
      <form id="editForm" method="POST" class="modal-content" action="{{ url_for('administrateur_bp.edit_user') }}">
        <div class="modal-header"><h5 class="modal-title">Modifier l'utilisateur</h5><button class="btn-close btn-close-white" type="button" data-bs-dismiss="modal"></button></div>
        <div class="modal-body">
          <input type="hidden" name="email" id="editEmail">
          <div class="mb-3 floating-label">
            <input id="newEmail" name="new_email" type="email" class="form-control" placeholder=" " required>
            <label for="newEmail">Adresse email</label>
          </div>
          <div class="mb-3 floating-label">
            <input id="newPassword" name="new_password" type="password" class="form-control" placeholder=" ">
            <label for="newPassword">Nouveau mot de passe</label>
          </div>
          <div class="mb-3 floating-label">
            <input id="editNom" name="nom" class="form-control" placeholder=" " required>
            <label for="editNom">Nom</label>
          </div>
          <div class="mb-3 floating-label">
            <input id="editPrenom" name="prenom" class="form-control" placeholder=" " required>
            <label for="editPrenom">Prénom</label>
          </div>
          <div class="mb-3 floating-label">
            <select id="editRole" name="role" class="form-select" placeholder=" " required>
              <option value="medecin">Médecin</option><option value="assistante">Assistante</option>
            </select>
            <label for="editRole">Rôle</label>
          </div>
        </div>
        <div class="modal-footer"><button class="btn btn-primary" type="submit">Enregistrer</button></div>
      </form>
    </div>
  </div>

  <footer class="text-center py-3">
    <p class="small mb-1" style="color: white;">
      <i class="fas fa-heartbeat me-1"></i>
      SASTOUKA DIGITAL © 2025 • sastoukadigital@gmail.com tel +212652084735
    </p>
  </footer>

  <div class="modal fade" id="importBackgroundModal" tabindex="-1">
    <div class="modal-dialog">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title"><i class="fas fa-image me-2"></i>Importer Arrière-plan</h5>
          <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
        </div>
        <div class="modal-body">
          <form id="importBackgroundFormAdmin" onsubmit="return ajaxFileUpload('importBackgroundFormAdmin','{{ url_for('administrateur_bp.import_background') }}')">
            <div class="mb-3">
              <label for="background_file_admin" class="form-label"><i class="fas fa-file-image me-2"></i>Fichier</label>
              <input type="file" class="form-control" name="background_file" id="background_file_admin" required>
            </div>
            <div class="modal-footer">
              <button type="submit" class="btn btn-primary"><i class="fas fa-upload me-2"></i>Importer</button>
              <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Annuler</button>
            </div>
          </form>
        </div>
      </div>
    </div>
  </div>

  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
  <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
  <script src="https://cdn.datatables.net/1.13.1/js/jquery.dataTables.min.js"></script>
  <script src="https://cdn.datatables.net/1.13.1/js/dataTables.bootstrap5.min.js"></script>
  <script src="https://cdn.datatables.net/responsive/2.4.1/js/dataTables.responsive.min.js"></script>
  <script src="https://cdn.datatables.net/responsive/2.4.1/js/responsive.bootstrap5.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
  <script>
    document.addEventListener('DOMContentLoaded',()=>{
      new DataTable('#usersTable',{
        responsive:true,
        lengthChange:true, /* Re-enabled length change */
        language:{url:"//cdn.datatables.net/plug-ins/1.13.1/i18n/fr-FR.json"}
      });
    });
    document.querySelectorAll('.editBtn').forEach(btn=>{
      btn.addEventListener('click',e=>{
        e.preventDefault();
        const email=btn.dataset.email;
        fetch(`/administrateur/get_user/${encodeURIComponent(email)}`).then(r=>r.json()).then(u=>{
          document.getElementById('editEmail').value=email;
          document.getElementById('newEmail').value=email;
          document.getElementById('editNom').value=u.nom;
          document.getElementById('editPrenom').value=u.prenom;
          document.getElementById('editRole').value=u.role;
          new bootstrap.Modal(document.getElementById('editModal')).show();
        });
      });
    });
    document.getElementById('editForm').addEventListener('submit',e=>{
      e.preventDefault();
      fetch(e.target.action,{method:'POST',body:new FormData(e.target),credentials:'same-origin'})
        .then(r=>{
          if(!r.ok) {
            Swal.fire({icon:'error',title:'Erreur',text:'Échec de la sauvegarde.'});
            throw new Error('Network response was not ok.');
          }
          return r.text(); // Assuming it returns text or redirects
        })
        .then(()=>location.reload())
        .catch(error => {
          console.error('Error:', error);
          if (!error.message.includes('Network response was not ok.')) {
            Swal.fire({icon:'error',title:'Erreur',text:'Une erreur inattendue est survenue.'});
          }
        });
    });

    // SweetAlert for delete user confirmation
    function confirmDeleteUser(email) {
        Swal.fire({
            title: 'Êtes-vous sûr?',
            text: `Vous êtes sur le point de supprimer l'utilisateur ${email}. Cette action est irréversible!`,
            icon: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#d33',
            cancelButtonColor: '#3085d6',
            confirmButtonText: 'Oui, supprimer!',
            cancelButtonText: 'Annuler'
        }).then((result) => {
            if (result.isConfirmed) {
                window.location.href = `{{ url_for('administrateur_bp.delete_user', user_email='') }}${encodeURIComponent(email)}`;
            }
        });
    }

    // Gérer l'affichage du bouton de confirmation d'importation et l'indicateur de chargement
    document.getElementById('excel_file_upload').addEventListener('change', function() {
        const uploadButton = document.getElementById('upload_button');
        if (this.files.length > 0) {
            uploadButton.style.display = 'inline-flex';
        } else {
            uploadButton.style.display = 'none';
        }
    });

    document.getElementById('uploadExcelForm').addEventListener('submit', function() {
        const uploadButton = document.getElementById('upload_button');
        const uploadButtonText = document.getElementById('upload_button_text');
        const uploadSpinner = document.getElementById('upload_spinner');

        // Afficher le spinner et désactiver le bouton
        uploadButtonText.style.display = 'none';
        uploadSpinner.style.display = 'inline-block';
        uploadButton.disabled = true;
        uploadButton.classList.add('no-pointer-events'); // Prevent further clicks
    });

    // NOUVEAU : Fonction de téléchargement de fichiers AJAX (réutilisée depuis main_template)
    window.ajaxFileUpload = function(formId, endpoint) {
      var form = document.getElementById(formId);
      var formData = new FormData(form);
      fetch(endpoint, {
          method: "POST",
          body: formData
      })
      .then(response => response.json())
      .then(data => {
          Swal.fire({
              icon: data.status,
              title: data.status === "success" ? "Succès" : "Attention",
              text: data.message,
              timer: 2000,
              showConfirmButton: false
          });
          if (data.status === "success") {
              // Masquer le modal après un téléchargement réussi
              const modalElement = document.getElementById('importBackgroundModal');
              if (modalElement) {
                  bootstrap.Modal.getInstance(modalElement).hide();
              }
              setTimeout(() => window.location.reload(), 2100);
          }
      })
      .catch(error => {
          Swal.fire({
              icon: "error",
              title: "Erreur",
              text: error,
              timer: 2000,
              showConfirmButton: false
          });
      });
      return false; // Empêcher la soumission de formulaire par défaut
    };

  </script>
</body>
</html>
"""
