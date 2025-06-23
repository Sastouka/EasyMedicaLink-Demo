# activation.py – gestion licences & activation
from __future__ import annotations
import os, json, uuid, hashlib, socket, requests, calendar
from datetime import date, timedelta
from typing import Optional, Dict
from flask import (
    request, render_template_string, redirect, url_for,
    flash, session, Blueprint # Import Blueprint
)

# ─────────────────────────────────────────────────────────────
# 1. Imports internes
# ─────────────────────────────────────────────────────────────
import theme, utils
import login # Import the entire login module to access _set_login_paths and load_users/save_users

# ─────────────────────────────────────────────────────────────
# 2. Configuration
# ─────────────────────────────────────────────────────────────
TRIAL_DAYS  = 7
SECRET_SALT = "S2!eUrltaMnSecet25lrao"
# MEDICALINK_FILES is no longer static; it's managed by utils.DYNAMIC_BASE_DIR.
# The USERS_FILE from login will implicitly handle this.

# ─────────────────────────────────────────────────────────────
# 3. Générateur de clé
# ─────────────────────────────────────────────────────────────
def _week_of_month(d: date) -> int:
    return ((d.day + calendar.monthrange(d.year, d.month)[0] - 1) // 7) + 1

def get_hardware_id() -> str:
    return hashlib.sha256(str(uuid.getnode()).encode()).hexdigest()[:16]

def generate_activation_key_for_user(
    hwid: str, plan: str, ref: Optional[date] = None
) -> str:
    ref     = ref or date.today()
    mmYYYY  = ref.strftime("%m%Y")
    suffix  = str(_week_of_month(ref)) if plan.lower().startswith("essai") else "" # Modifié pour inclure "essai_Xjours"
    payload = f"{hwid}{SECRET_SALT}{plan.lower().strip()}{mmYYYY}{suffix}"
    digest  = hashlib.sha256(payload.encode()).hexdigest().upper()[:16]
    return "-".join(digest[i:i+4] for i in range(0, 16, 4))

# ─────────────────────────────────────────────────────────────
# 4. Accès users.json
# ─────────────────────────────────────────────────────────────
def _user() -> Optional[dict]:
    # Ensure login paths are set for the current session's admin_email before loading users
    current_admin_email = session.get("admin_email")
    if current_admin_email:
        login._set_login_paths(current_admin_email)
    else:
        # Fallback if admin_email is not in session (e.g., initial access before login)
        login._set_login_paths() 
    return login.load_users().get(session.get("email"))

def _save_user(u: dict):
    # Ensure login paths are set for the current session's admin_email before saving users
    current_admin_email = session.get("admin_email")
    if current_admin_email:
        login._set_login_paths(current_admin_email)
    else:
        login._set_login_paths() 

    users = login.load_users()
    users[session["email"]] = u
    login.save_users(users)
        
def _ensure_placeholder(u: dict):
    if "activation" not in u:
        u["activation"] = {
            "plan": f"essai_{TRIAL_DAYS}jours", # Initialisation du plan d'essai
            "activation_date": date.today().isoformat(),
            "activation_code": "0000-0000-0000-0000" # Clé par défaut pour l'essai
        }
        _save_user(u)
        
def _admin_activation_record() -> Optional[dict]:
    """
    Retourne le dictionnaire d’activation du 1ᵉʳ compte admin trouvé,
    ou None si aucun admin enregistré.
    
    WARNING: This function might be problematic in a multi-admin setup
    with dynamic directories if it needs to find a specific admin's data.
    It currently iterates through all users loaded from the *current*
    dynamic path. If the current dynamic path is for a different admin,
    it won't find other admin's records.
    For cross-admin checks, a dedicated mechanism might be needed.
    """
    # Ensure login paths are set before loading users to find admin record
    # This might need to be 'default_admin@example.com' or a known central admin if multi-admin data is segregated.
    login._set_login_paths(session.get('admin_email', 'default_admin@example.com')) # Use current or default admin context

    for u in login.load_users().values():
        if u.get("role") == "admin" and "activation" in u:
            return u["activation"]
    return None        

# ─────────────────────────────────────────────────────────────
# 5. Validation licences
# ─────────────────────────────────────────────────────────────
def _add_month(d: date) -> date:
    nxt_mo = d.month % 12 + 1
    nxt_yr = d.year + d.month // 12
    try:                return d.replace(year=nxt_yr, month=nxt_mo)
    except ValueError:  return (d.replace(day=1, year=nxt_yr, month=nxt_mo)
                                - timedelta(days=1))

def check_activation() -> bool:
    """
    • Pour l’admin : contrôle normal sur son propre enregistrement.
    • Pour les médecins / assistantes : on valide si ET SEULEMENT SI
      l’activation de l’admin est valable.
    """
    u = _user()
    if not u:               # utilisateur non connecté
        return True

    role = u.get("role", "admin").lower()

    # ----- cas ADMIN : inchangé -----
    if role == "admin":
        _ensure_placeholder(u)
        act = u["activation"]
        plan = act["plan"].lower()
        act_date = date.fromisoformat(act["activation_date"])
        today = date.today()

        # NOUVEAU : Gérer la clé d'essai par défaut "0000-0000-0000-0000"
        if plan.startswith("essai") and act.get("activation_code") == "0000-0000-0000-0000":
            # Pour cette clé spécifique, la validité est basée sur la date uniquement
            return today <= act_date + timedelta(days=TRIAL_DAYS)
        
        # Logique existante pour les autres clés (y compris les clés d'essai générées par le système)
        # Note: Si generate_activation_key_for_user est modifiée pour toujours générer la clé 0000-0000-0000-0000
        # pour les plans d'essai, cette ligne est redondante mais peut rester pour d'autres types de clés d'essai.
        exp_code = generate_activation_key_for_user(get_hardware_id(), plan, act_date)
        if act.get("activation_code") != exp_code:
            return False

        if plan.startswith("essai"):
            return today <= act_date + timedelta(days=TRIAL_DAYS)
        if plan == "1 mois":
            return today <= _add_month(act_date)
        if plan == "1 an":
            try:
                lim = act_date.replace(year=act_date.year + 1)
            except ValueError:
                lim = act_date + timedelta(days=365)
            return today <= lim
        if plan == "illimité":
            return True
        return False

    # ----- cas Médecin / Assistante -----
    admin_act = _admin_activation_record()
    if not admin_act:
        return False                     # aucun admin activé ⇒ bloqué

    # Réutilise la même routine de validation sur l’enregistrement admin
    tmp_user = {"activation": admin_act}
    session_backup = session.get("email")          # sauvegarde
    session["email"] = "___admin_dummy___"         # clé fictive pour _ensure_placeholder
    
    # Appel récursif à check_activation pour vérifier le plan de l'administrateur
    # avec la clé "0000-0000-0000-0000" pour les plans d'essai
    res = check_activation.__wrapped__(tmp_user) # Utilise __wrapped__ pour appeler la fonction originale sans le décorateur
                                                 # qui pourrait créer une récursion infinie si check_activation était un décorateur.
    
    # S'assurer que le code de l'administrateur est vérifié correctement
    # Cette partie vérifie si le code d'activation de l'admin correspond
    # à celui généré pour son plan, en excluant la clé "0000-0000-0000-0000"
    # qui est traitée spécifiquement ci-dessus.
    if admin_act.get("activation_code") != "0000-0000-0000-0000":
        res = res and (admin_act.get("activation_code") ==
                       generate_activation_key_for_user(get_hardware_id(),
                                                        admin_act["plan"],
                                                        date.fromisoformat(admin_act["activation_date"])))
    
    session["email"] = session_backup               # restaure
    return res

def update_activation(plan: str, code: str):
    u = _user()
    if not u: return
    u["activation"] = {
        "plan": plan,
        "activation_date": date.today().isoformat(),
        "activation_code": code
    }
    _save_user(u)

update_activation_after_payment = update_activation  # compat
# ──────────────────────────
# 6. PayPal
# ──────────────────────────
PAYPAL_CLIENT_ID  = os.environ.get("PAYPAL_CLIENT_ID") or "AYPizBBNq1vp8WyvzvTHITGq9KoUUTXmzE0DBA7D_lWl5Ir6wEwVCB-gorvd1jgyX35ZqyURK6SMvps5"
PAYPAL_SECRET     = os.environ.get("PAYPAL_SECRET")    or "EKSvwa_yK7ZYTuq45VP60dbRMzChbrko90EnhQsRzrMNZhqU2mHLti4_UTYV60ytY9uVZiAg7BoBlNno"
PAYPAL_OAUTH_URL  = "https://api-m.paypal.com/v1/oauth2/token"
PAYPAL_ORDER_API  = "https://api-m.paypal.com/v2/checkout/orders"

def get_paypal_access_token() -> str:
    r = requests.post(PAYPAL_OAUTH_URL,
        auth=(PAYPAL_CLIENT_ID, PAYPAL_SECRET),
        data={"grant_type":"client_credentials"})
    if r.ok: return r.json()["access_token"]
    raise RuntimeError(r.text)

def create_paypal_order(amount, return_url, cancel_url):
    token = get_paypal_access_token()
    hdr   = {"Authorization":f"Bearer {token}", "Content-Type":"application/json"}
    body  = {
        "intent":"CAPTURE",
        "purchase_units":[{"amount":{"currency_code":"USD","value":amount}}],
        "application_context":{"return_url":return_url,"cancel_url":cancel_url}
    }
    r = requests.post(PAYPAL_ORDER_API, json=body, headers=hdr)
    if r.ok:
        j = r.json()
        return j["id"], next(l["href"] for l in j["links"] if l["rel"]=="approve")
    raise RuntimeError(r.text)

def capture_paypal_order(oid):
    token = get_paypal_access_token()
    r = requests.post(f"{PAYPAL_ORDER_API}/{oid}/capture",
        headers={"Authorization":f"Bearer {token}"})
    return r.ok and r.json().get("status") == "COMPLETED"

# ─────────────────────────────────────────────────────────────
# 7. Templates (HTML condensé)
# ─────────────────────────────────────────────────────────────
activation_template = """
<!DOCTYPE html><html lang='fr'>
{{ pwa_head()|safe }}
<head>
<meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Activation</title>
<link rel='stylesheet' href='https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css'>
<link rel='stylesheet' href='https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css'>
<style>
body{background:#f8f9fa; display: flex; align-items: center; justify-content: center; min-height: 100vh;}
.card{border-radius:1rem;box-shadow:0 4px 20px rgba(0,0,0,.1); width: 100%; max-width: 500px;}
.btn-primary{background:linear-gradient(45deg,#0069d9,#6610f2);border:none}
.contact-info {margin-top: 20px; padding-top: 15px; border-top: 1px solid #eee; text-align: center;}
.contact-info a {margin: 0 10px;}
</style>
</head><body><div class='container'>
<div class='row justify-content-center'><div class='col-md-6'>
<div class='card p-4'><h3 class='card-title text-center mb-3'><i class='fas fa-key'></i> Activation</h3>
<p class='small text-center'>Mois/année : <b>{{ month_year }}</b> • Semaine #<b>{{ week_rank }}</b></p>
<form method='POST'><input type='hidden' name='choix' id='planField'>
<div class='mb-3'><label class='form-label'><i class='fas fa-desktop'></i> ID machine :</label>
<input class='form-control' readonly value='{{ machine_id }}'></div>
<div class='mb-3'><label class='form-label'><i class='fas fa-code'></i> Clé (optionnelle)</label>
<input name='activation_code' class='form-control' placeholder='XXXX-XXXX-XXXX-XXXX'></div>
<div class='d-grid gap-2 mb-3'>
<button type='submit' class='btn btn-primary' onclick="setPlan('essai')"
    {% if current_plan_is_expired_default_trial %}disabled{% endif %}>
<i class='fas fa-hourglass-start'></i> Essai {{ TRIAL_DAYS }} jours</button>
<button type='submit' class='btn btn-success' onclick="setPlan('1 mois')">
<i class='fas fa-calendar-day'></i> 1 mois (25 $)</button>
<button type='submit' class='btn btn-success' onclick="setPlan('1 an')">
<i class='fas fa-calendar-alt'></i> 1 an (50 $)</button>
<button type='submit' class='btn btn-success' onclick="setPlan('illimité')">
<i class='fas fa-infinity'></i> Illimité (120 $)</button></div>
{% with m = get_flashed_messages(with_categories=true) %}
  {% for c,msg in m %}<div class='alert alert-{{c}}'>{{msg}}</div>{% endfor %}{% endwith %}
</form>
<div class='contact-info'>
    <p>Pour toute question concernant l'activation, le paiement ou le support technique, contactez-nous. Vous pouvez nous joindre par email à sastoukadigital@gmail.com pour des requêtes détaillées, ou via WhatsApp au +212652084735 pour une assistance rapide et directe.</p>
    <a href='mailto:sastoukadigital@gmail.com' class='btn btn-outline-info'><i class='fas fa-envelope'></i> Email</a>
    <a href='https://wa.me/212652084735' class='btn btn-outline-success' target='_blank'><i class='fab fa-whatsapp'></i> WhatsApp</a>
</div>
</div></div></div></div>
<script>
function setPlan(p){document.getElementById('planField').value=p;}
</script></body></html>"""

failed_activation_template = """<html>
{{ pwa_head()|safe }}
<head><meta http-equiv='refresh' content='5;url={{ url_for("activation.activation") }}'> # Corrected url_for reference
<title>Échec</title><link rel='stylesheet'
href='https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css'></head>
<body class='vh-100 d-flex align-items-center justify-content-center'>
<div class='alert alert-danger text-center'>Activation invalide – contactez le support.</div></body></html>"""

# Define the Blueprint for activation
activation_bp = Blueprint("activation", __name__) # Define the Blueprint here

# ─────────────────────────────────────────────────────────────
# 8. Routes (now using activation_bp)
# ─────────────────────────────────────────────────────────────
# Removed `def register_routes(app):` wrapper as blueprint is registered directly in app.py

orders: Dict[str, tuple[str,str]] = {} # This must be outside of any function to maintain state

@activation_bp.route("/", methods=["GET","POST"]) # Use activation_bp.route
def activation():
    # Ensure utils's dynamic base directory and login's paths are set
    # This is crucial because check_activation and _user/save_user depend on it.
    admin_email_from_session = session.get('admin_email', 'default_admin@example.com')
    utils.set_dynamic_base_dir(admin_email_from_session)
    login._set_login_paths(admin_email_from_session)

    # ── NOUVEAUTÉ : si licence déjà valide → accueil directement
    if check_activation():
        return redirect(url_for("accueil.accueil"))

    hwid, today = get_hardware_id(), date.today()
    ctx = dict(machine_id=hwid,
               week_rank=_week_of_month(today),
               month_year=today.strftime("%m/%Y"),
               TRIAL_DAYS=TRIAL_DAYS)

    # Récupérer l'état actuel de l'activation de l'utilisateur pour le template
    current_user_data = _user()
    current_activation = current_user_data.get("activation", {})
    current_plan_is_expired_default_trial = (
        current_activation.get("plan", "").startswith("essai") and
        current_activation.get("activation_code") == "0000-0000-0000-0000" and
        not (date.today() <= date.fromisoformat(current_activation.get("activation_date", date.today().isoformat())) + timedelta(days=TRIAL_DAYS))
    )
    # Ajouter la variable au contexte pour le template
    ctx['current_plan_is_expired_default_trial'] = current_plan_is_expired_default_trial


    if request.method == "POST":
        plan = request.form["choix"]            # 'essai', '1 an', …
        code = request.form.get("activation_code","").strip().upper()
        
        # ─── Essai (clé obligatoirement "0000-0000-0000-0000")
        if plan.startswith("essai"):
            if code == "0000-0000-0000-0000": # Vérification explicite de la clé requise pour l'essai
                if current_plan_is_expired_default_trial:
                    flash("Votre période d'essai gratuite avec cette clé est terminée. Veuillez choisir un plan payant.", "danger")
                    return render_template_string(activation_template, **ctx)
                else:
                    update_activation(plan, code)
                    flash("Essai activé !","success")
                    return redirect(url_for("accueil.accueil"))
            else:
                # Message d'erreur si la clé d'essai n'est pas la bonne
                flash("Clé essai incorrecte. Pour le plan d'essai, la clé doit être '0000-0000-0000-0000'.","danger")
                return render_template_string(activation_template, **ctx)

        # ─── Plans payants
        tariffs = {"1 mois":"25.00","1 an":"50.00","illimité":"120.00"}
        if plan in tariffs:
            # Pour les plans payants, générer la clé attendue basée sur l'ID matériel
            expected_paid_code = generate_activation_key_for_user(hwid, plan, today)
            if code and code == expected_paid_code: # Vérifier si le code fourni correspond à celui généré
                update_activation(plan, code)
                flash("Plan activé par clé !","success")
                return redirect(url_for("accueil.accueil"))
            try: # Tenter PayPal si aucune clé manuelle valide ou si la clé manuelle est incorrecte
                oid, url = create_paypal_order(
                    tariffs[plan],
                    return_url=url_for("activation.paypal_success", _external=True), # Use blueprint name
                    cancel_url=url_for("activation.paypal_cancel",  _external=True)  # Use blueprint name
                )
                orders[oid] = (plan, expected_paid_code) # Stocker le code attendu pour la vérification
                return redirect(url)
            except Exception as e:
                flash(f"PayPal error : {e}","danger")
            return render_template_string(activation_template, **ctx)

    return render_template_string(activation_template, **ctx)

@activation_bp.route("/paypal_success") # Use activation_bp.route
def paypal_success():
    # Ensure utils's dynamic base directory and login's paths are set
    admin_email_from_session = session.get('admin_email', 'default_admin@example.com')
    utils.set_dynamic_base_dir(admin_email_from_session)
    login._set_login_paths(admin_email_from_session)

    oid = request.args.get("token")
    if oid and oid in orders and capture_paypal_order(oid):
        plan, code = orders.pop(oid)
        update_activation(plan, code)
        flash("Paiement validé – licence activée !","success")
        return redirect(url_for("accueil.accueil"))
    return render_template_string(failed_activation_template)

@activation_bp.route("/paypal_cancel") # Use activation_bp.route
def paypal_cancel():
    # Ensure utils's dynamic base directory and login's paths are set
    admin_email_from_session = session.get('admin_email', 'default_admin@example.com')
    utils.set_dynamic_base_dir(admin_email_from_session)
    login._set_login_paths(admin_email_from_session)

    flash("Paiement annulé.","warning")
    return redirect(url_for("activation.activation")) # Use blueprint name for redirect

# ─────────────────────────────────────────────────────────────
# 9. Middleware blocage
# ─────────────────────────────────────────────────────────────
def init_app(app):
    # This init_app will register the blueprint.
    # The blueprint is ALREADY registered in create_app in app.py.
    # So, we remove app.register_blueprint(activation_bp) from here.
    # app.register_blueprint(activation_bp) # REMOVED from here

    @app.before_request
    def _guard():
        # Ensure utils's dynamic base directory and login's paths are set
        # This needs to run on every request before other checks
        admin_email_from_session = session.get('admin_email', 'default_admin@example.com')
        utils.set_dynamic_base_dir(admin_email_from_session)
        login._set_login_paths(admin_email_from_session)

        # Médecin et assistante contournent le contrôle d’activation
        role = session.get("role")
        if role in ("medecin", "assistante"):
            return

        # Mode développeur toujours libre
        if session.get("is_developpeur"):
            return
        if request.blueprint == "developpeur_bp":
            return

        # Routes exemptées de login/activation
        exempt = {
            "login.login", "login.register",
            "login.forgot_password", "login.reset_password",
            "static", "activation.activation", "activation.paypal_success", "activation.paypal_cancel" # Use blueprint name for endpoints
        }
        if request.endpoint in exempt or "email" not in session:
            return

        # Pour tous les autres, on vérifie l’activation
        if not check_activation():
            return redirect(url_for("activation.activation")) # Use blueprint name
