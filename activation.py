# activation.py  – gestion licences & activation
from __future__ import annotations
import os, json, uuid, hashlib, socket, requests, calendar
from datetime import date, timedelta
from typing import Optional, Dict
from flask import (
    request, render_template_string, redirect, url_for,
    flash, session
)

# ─────────────────────────────────────────────────────────────
# 1. Imports internes
# ─────────────────────────────────────────────────────────────
import theme, utils
from login import load_users, save_users, USERS_FILE

# ─────────────────────────────────────────────────────────────
# 2. Configuration
# ─────────────────────────────────────────────────────────────
TRIAL_DAYS  = 7
SECRET_SALT = "S2!eUrltaMnSecet25lrao"
MEDICALINK_FILES = USERS_FILE.parent

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
    suffix  = str(_week_of_month(ref)) if plan.lower() == "essai" else ""
    payload = f"{hwid}{SECRET_SALT}{plan.lower().strip()}{mmYYYY}{suffix}"
    digest  = hashlib.sha256(payload.encode()).hexdigest().upper()[:16]
    return "-".join(digest[i:i+4] for i in range(0, 16, 4))

# ─────────────────────────────────────────────────────────────
# 4. Accès users.json
# ─────────────────────────────────────────────────────────────
def _user() -> Optional[dict]:
    return load_users().get(session.get("email"))

def _save_user(u: dict):
    users = load_users(); users[session["email"]] = u; save_users(users)

def _ensure_placeholder(u: dict):
    if "activation" not in u:
        u["activation"] = {
            "plan": "essai_en_attente",
            "activation_date": date.today().isoformat(),
            "activation_code": ""
        }
        _save_user(u)
        
def _admin_activation_record() -> Optional[dict]:
    """
    Retourne le dictionnaire d’activation du 1ᵉʳ compte admin trouvé,
    ou None si aucun admin enregistré.
    """
    for u in load_users().values():
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
        exp_code = generate_activation_key_for_user(get_hardware_id(), plan, act_date)
        if act.get("activation_code") != exp_code:
            return False

        today = date.today()
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
    res = (
        admin_act.get("activation_code") ==
        generate_activation_key_for_user(get_hardware_id(),
                                         admin_act["plan"],
                                         date.fromisoformat(admin_act["activation_date"]))
        and  check_activation.__wrapped__(tmp_user)   # recursion sur l'admin
    )
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
<style>body{background:#f8f9fa}.card{border-radius:1rem;box-shadow:0 4px 20px rgba(0,0,0,.1)}
.btn-primary{background:linear-gradient(45deg,#0069d9,#6610f2);border:none}</style>
</head><body class='vh-100 d-flex align-items-center'><div class='container'>
<div class='row justify-content-center'><div class='col-md-6'>
<div class='card p-4'><h3 class='card-title text-center mb-3'><i class='fas fa-key'></i> Activation</h3>
<p class='small text-center'>Mois/année : <b>{{ month_year }}</b> • Semaine #<b>{{ week_rank }}</b></p>
<form method='POST'><input type='hidden' name='choix' id='planField'>
<div class='mb-3'><label class='form-label'><i class='fas fa-desktop'></i> ID machine :</label>
<input class='form-control' readonly value='{{ machine_id }}'></div>
<div class='mb-3'><label class='form-label'><i class='fas fa-code'></i> Clé (optionnelle)</label>
<input name='activation_code' class='form-control' placeholder='XXXX-XXXX-XXXX-XXXX'></div>
<div class='d-grid gap-2 mb-3'>
<button type='submit' class='btn btn-primary' onclick="setPlan('essai')">
<i class='fas fa-hourglass-start'></i> Essai {{ TRIAL_DAYS }} jours</button>
<button type='submit' class='btn btn-success' onclick="setPlan('1 mois')">
<i class='fas fa-calendar-day'></i> 1 mois (25 $)</button>
<button type='submit' class='btn btn-success' onclick="setPlan('1 an')">
<i class='fas fa-calendar-alt'></i> 1 an (50 $)</button>
<button type='submit' class='btn btn-success' onclick="setPlan('illimité')">
<i class='fas fa-infinity'></i> Illimité (120 $)</button></div>
{% with m = get_flashed_messages(with_categories=true) %}
  {% for c,msg in m %}<div class='alert alert-{{c}}'>{{msg}}</div>{% endfor %}{% endwith %}
</form></div></div></div></div>
<script>
function setPlan(p){document.getElementById('planField').value=p;}
</script></body></html>"""

failed_activation_template = """<html>
{{ pwa_head()|safe }}
<head><meta http-equiv='refresh' content='5;url={{ url_for("activation") }}'>
<title>Échec</title><link rel='stylesheet'
href='https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css'></head>
<body class='vh-100 d-flex align-items-center justify-content-center'>
<div class='alert alert-danger text-center'>Activation invalide – contactez le support.</div></body></html>"""

# ─────────────────────────────────────────────────────────────
# 8. Routes
# ─────────────────────────────────────────────────────────────
def register_routes(app):
    orders: Dict[str, tuple[str,str]] = {}

    @app.route("/activation", methods=["GET","POST"])
    def activation():
        # ── NOUVEAUTÉ : si licence déjà valide → accueil directement
        if check_activation():
            return redirect(url_for("accueil.accueil"))

        hwid, today = get_hardware_id(), date.today()
        ctx = dict(machine_id=hwid,
                   week_rank=_week_of_month(today),
                   month_year=today.strftime("%m/%Y"),
                   TRIAL_DAYS=TRIAL_DAYS)

        if request.method == "POST":
            plan = request.form["choix"]            # 'essai', '1 an', …
            code = request.form.get("activation_code","").strip().upper()
            expected = generate_activation_key_for_user(hwid, plan, today)

            # ─── Essai (clé requise)
            if plan == "essai":
                if code == expected:
                    update_activation("essai", code)
                    flash("Essai activé !","success")
                    return redirect(url_for("accueil.accueil"))
                flash("Clé essai incorrecte.","danger")
                return render_template_string(activation_template, **ctx)

            # ─── Plans payants
            tariffs = {"1 mois":"25.00","1 an":"50.00","illimité":"120.00"}
            if plan in tariffs:
                if code and code == expected:                 # clé manuelle OK
                    update_activation(plan, code)
                    flash("Plan activé par clé !","success")
                    return redirect(url_for("accueil.accueil"))
                try:                                          # déclencher PayPal
                    oid, url = create_paypal_order(
                        tariffs[plan],
                        return_url=url_for("paypal_success", _external=True),
                        cancel_url=url_for("paypal_cancel",  _external=True)
                    )
                    orders[oid] = (plan, expected)
                    return redirect(url)
                except Exception as e:
                    flash(f"PayPal error : {e}","danger")
                return render_template_string(activation_template, **ctx)

        return render_template_string(activation_template, **ctx)

    @app.route("/paypal_success")
    def paypal_success():
        oid = request.args.get("token")
        if oid and oid in orders and capture_paypal_order(oid):
            plan, code = orders.pop(oid)
            update_activation(plan, code)
            flash("Paiement validé – licence activée !","success")
            return redirect(url_for("accueil.accueil"))
        return render_template_string(failed_activation_template)

    @app.route("/paypal_cancel")
    def paypal_cancel():
        flash("Paiement annulé.","warning")
        return redirect(url_for("activation"))

# ─────────────────────────────────────────────────────────────
# 9. Middleware blocage
# ─────────────────────────────────────────────────────────────
def init_app(app):
    @app.before_request
    def _guard():
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
            "static", "activation", "paypal_success", "paypal_cancel"
        }
        if request.endpoint in exempt or "email" not in session:
            return

        # Pour tous les autres, on vérifie l’activation
        if not check_activation():
            return redirect(url_for("activation"))
