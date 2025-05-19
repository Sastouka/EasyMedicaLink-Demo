# login.py — rôle Admin visible partout, mais création/reset ouverts à tous
import os
import sys
import json
import hmac
import hashlib
import ctypes
import platform
import socket
import uuid
import pathlib
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from flask import (
    Blueprint,
    request,
    render_template_string,
    redirect,
    url_for,
    flash,
    session,
)

def generate_reset_token(length: int = 32) -> str:
    """
    Génère un token URL-safe pour la réinitialisation de mot de passe.
    """
    return secrets.token_urlsafe(length)

# ── Chemin caché du fichier utilisateurs ────────────────────────────────────
if getattr(sys, "frozen", False):
    base = Path(sys.executable).parent
else:
    base = Path(__file__).resolve().parent

hidden_dir = base / "MEDICALINK_FILES"
hidden_dir.mkdir(parents=True, exist_ok=True)
# Windows : attribuer l’attribut caché au dossier
if platform.system() == "Windows":
    ctypes.windll.kernel32.SetFileAttributesW(str(hidden_dir), 0x02)

USERS_FILE = hidden_dir / ".users.json"       # préfixe point → cache sous *nix
HMAC_KEY    = b"votre_cle_secrete_interne"    # modifiez par une vraie clé

# ── Calcul du HMAC d’un contenu bytes ───────────────────────────────────────
def _sign(data: bytes) -> str:
    return hmac.new(HMAC_KEY, data, hashlib.sha256).hexdigest()

# ── Lecture sécurisée ───────────────────────────────────────────────────────
def load_users() -> dict:
    if not USERS_FILE.exists():
        return {}
    raw = USERS_FILE.read_bytes()
    try:
        payload, sig = raw.rsplit(b"\n---SIGNATURE---\n", 1)
    except ValueError:
        sys.exit("users.json endommagé : signature manquante.")
    if not hmac.compare_digest(_sign(payload), sig.decode()):
        sys.exit("users.json corrompu : intégrité compromise.")
    return json.loads(payload.decode("utf-8"))

# ── Écriture sécurisée ──────────────────────────────────────────────────────
def save_users(users: dict):
    payload = json.dumps(users, ensure_ascii=False, indent=2).encode("utf-8")
    sig     = _sign(payload).encode()
    blob    = payload + b"\n---SIGNATURE---\n" + sig
    USERS_FILE.write_bytes(blob)

# ── Hachage de mot de passe ─────────────────────────────────────────────────
def hash_password(password: str) -> str:
    """
    Renvoie le SHA256 du mot de passe.
    """
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

# ── QR et utils localhost ────────────────────────────────────────────────────
def lan_ip() -> str:
    ip = socket.gethostbyname(socket.gethostname())
    if ip.startswith("127."):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
        except:
            ip = "0.0.0.0"
    return ip

def is_localhost(req) -> bool:
    return req.remote_addr in ("127.0.0.1", "::1")

# ────────────────────────────────────────────────────────────────────────────
# Blueprint
# ────────────────────────────────────────────────────────────────────────────
login_bp = Blueprint("login", __name__)

# ───────── 3. templates
login_template = """
<!DOCTYPE html><html lang='fr'>
{{ pwa_head()|safe }}
<head>
<meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Connexion</title>
<link href='https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css' rel='stylesheet'>
<link href='https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css' rel='stylesheet'>
<style>
 body{background:#f0fafe}.card{border-radius:1rem;box-shadow:0 4px 20px rgba(0,0,0,.08)}
 .btn-med{background:linear-gradient(45deg,#1a73e8,#0d9488);color:#fff}
 canvas{border:1px solid #e0e0e0;border-radius:.5rem;box-shadow:0 2px 6px rgba(0,0,0,.05)}
</style></head><body class='d-flex align-items-center justify-content-center min-vh-100 p-3'>
<div class='card p-4 w-100' style='max-width:420px'>
  <h3 class='text-center mb-3'><i class='fas fa-user-lock me-1'></i>Connexion</h3>
  {% with m=get_flashed_messages(with_categories=true) %}{% for c,msg in m %}
    <div class='alert alert-{{c}} small'>{{msg}}</div>{% endfor %}{% endwith %}

  <form method='POST'>
    <div class='mb-3'>
      <label class='form-label small'><i class='fas fa-users-cog me-1'></i>Rôle</label>
      <select name='role_select' class='form-select form-select-lg' required>
        <option value='admin'>Admin</option>
        <option value='medecin'>Médecin</option>
        <option value='assistante'>Assistante</option>
      </select>
    </div>
    <div class='mb-3'>
      <label class='form-label small'><i class='fas fa-envelope me-1'></i>Email</label>
      <input name='email' type='email' class='form-control form-control-lg' required>
    </div>
    <div class='mb-3'>
      <label class='form-label small'><i class='fas fa-key me-1'></i>Mot de passe</label>
      <input name='password' type='password' class='form-control form-control-lg' required>
    </div>
    <button class='btn btn-med btn-lg w-100'>Se connecter</button>
  </form>

  <!-- QR codes -->
  <div class='d-flex gap-3 my-4 flex-column flex-md-row'>
    <div class='text-center flex-fill'><canvas id='qrLocal' width='120' height='120'></canvas>
      <div class='small mt-2'>localhost</div></div>
    <div class='text-center flex-fill'><canvas id='qrLan' width='120' height='120'></canvas>
      <div class='small mt-2'>réseau local</div></div>
  </div>

  {% if local %}
  <div class='d-flex flex-column flex-sm-row gap-2'>
    <a href='{{ url_for("login.register") }}' class='btn btn-outline-secondary flex-fill'>
      <i class='fas fa-user-plus me-1'></i>S’enregistrer</a>
    <a href='{{ url_for("login.forgot_password") }}' class='btn btn-outline-secondary flex-fill'>
      <i class='fas fa-unlock-alt me-1'></i>Mot de passe oublié</a>
  </div>
  {% endif %}
</div>
<script src='https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js'></script>
<script src='https://cdnjs.cloudflare.com/ajax/libs/qrious/4.0.2/qrious.min.js'></script>
<script>
  new QRious({element:document.getElementById('qrLocal'),value:'http://127.0.0.1:3000',size:120,foreground:'#1a73e8'});
  new QRious({element:document.getElementById('qrLan'),  value:'{{ url_lan }}',size:120,foreground:'#0d9488'});
</script></body></html>"""

register_template = '''
<!DOCTYPE html>
<html lang="fr">
{{ pwa_head()|safe }}
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Enregistrement</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
  <style>
    .btn-medical { background: linear-gradient(45deg,#1a73e8,#0d9488); color:white; }
    body { background:#f0fafe; }
  </style>
</head>
<body class="d-flex align-items-center justify-content-center min-vh-100 p-3">
  <div class="card p-4 shadow w-100" style="max-width: 480px;">
    <h3 class="text-center mb-3"><i class="fas fa-user-plus"></i> Enregistrement</h3>
    {% with msgs = get_flashed_messages(with_categories=true) %}
      {% for cat,msg in msgs %}<div class="alert alert-{{cat}} small">{{msg}}</div>{% endfor %}
    {% endwith %}
    <form id="registerForm" method="POST">
      <div class="mb-3">
        <label class="form-label small"><i class="fas fa-envelope me-2"></i>Email</label>
        <input type="email" name="email" class="form-control form-control-lg" required>
      </div>
      <div class="mb-3 row g-2">
        <div class="col-12 col-md-6">
          <label class="form-label small"><i class="fas fa-key me-2"></i>Mot de passe</label>
          <input type="password" name="password" class="form-control form-control-lg" required>
        </div>
        <div class="col-12 col-md-6">
          <label class="form-label small"><i class="fas fa-key me-2"></i>Confirmer</label>
          <input type="password" name="confirm" class="form-control form-control-lg" required>
        </div>
      </div>
      <div class="mb-3">
        <label class="form-label small"><i class="fas fa-users-cog me-2"></i>Rôle</label>
        <select name="role" class="form-select form-select-lg" required>
          <option value="admin">Admin</option>
          <option value="medecin">Médecin</option>
          <option value="assistante">Assistante</option>
        </select>
      </div>
      <div class="mb-3">
        <label class="form-label small"><i class="fas fa-hospital-symbol me-2"></i>Nom Clinique/Cabinet</label>
        <input type="text" name="clinic" class="form-control form-control-lg" required>
      </div>
      <div class="mb-3 row g-2">
        <div class="col-12 col-md-6">
          <label class="form-label small"><i class="fas fa-calendar-alt me-2"></i>Date de création</label>
          <input type="date" name="creation_date" class="form-control form-control-lg" required>
        </div>
        <div class="col-12 col-md-6">
          <label class="form-label small"><i class="fas fa-map-marker-alt me-2"></i>Adresse</label>
          <input type="text" name="address" class="form-control form-control-lg" required>
        </div>
      </div>
      <button type="submit" class="btn btn-medical btn-lg w-100">S'enregistrer</button>
    </form>
    <div class="text-center mt-3">
      <a href="{{ url_for('login.login') }}" class="btn btn-outline-secondary d-inline-flex align-items-center">
        <i class="fas fa-arrow-left me-1"></i> Retour Connexion
      </a>
    </div>
  </div>
  <script>
    document.getElementById('registerForm').addEventListener('submit', function(e) {
      e.preventDefault();
      Swal.fire({
        title: 'Important',
        text: 'Veuillez conserver précieusement votre email, le nom de la clinique, la date de création et l’adresse. Ces informations seront nécessaires pour récupérer votre mot de passe.',
        icon: 'info',
        confirmButtonText: 'OK'
      }).then((result) => {
        if (result.isConfirmed) {
          this.submit();
        }
      });
    });
  </script>
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

reset_template = '''
<!DOCTYPE html>
<html lang="fr">
{{ pwa_head()|safe }}
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Réinitialiser mot de passe</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
  <style>
    .btn-medical { background: linear-gradient(45deg,#1a73e8,#0d9488); color:white; }
    body { background:#f0fafe; }
  </style>
</head>
<body class="d-flex align-items-center justify-content-center min-vh-100 p-3">
  <div class="card p-4 shadow w-100" style="max-width: 400px;">
    <h3 class="text-center mb-3"><i class="fas fa-redo-alt"></i> Réinitialiser mot de passe</h3>
    {% with msgs = get_flashed_messages(with_categories=true) %}
      {% for cat,msg in msgs %}<div class="alert alert-{{cat}} small">{{msg}}</div>{% endfor %}
    {% endwith %}
    <form method="POST">
      <div class="mb-3 row g-2">
        <div class="col-12 col-md-6">
          <label class="form-label small">Nouveau mot de passe</label>
          <input type="password" name="password" class="form-control form-control-lg" required>
        </div>
        <div class="col-12 col-md-6">
          <label class="form-label small">Confirmer</label>
          <input type="password" name="confirm" class="form-control form-control-lg" required>
        </div>
      </div>
      <button type="submit" class="btn btn-medical btn-lg w-100">Mettre à jour</button>
    </form>
  </div>
</body>
</html>
'''

forgot_template = '''
<!DOCTYPE html>
<html lang="fr">
{{ pwa_head()|safe }}
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Récupération mot de passe</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
  <style>
    .btn-medical { background: linear-gradient(45deg,#1a73e8,#0d9488); color:white; }
    body { background:#f0fafe; }
  </style>
</head>
<body class="d-flex align-items-center justify-content-center min-vh-100 p-3">
  <div class="card p-4 shadow w-100" style="max-width: 400px;">
    <h3 class="text-center mb-3"><i class="fas fa-unlock-alt"></i>Récupération</h3>
    {% with msgs = get_flashed_messages(with_categories=true) %}
      {% for cat,msg in msgs %}<div class="alert alert-{{cat}} small">{{msg}}</div>{% endfor %}
    {% endwith %}
    <form method="POST">
      <div class="mb-3">
        <label class="form-label small"><i class="fas fa-envelope me-2"></i>Email</label>
        <input type="email" name="email" class="form-control form-control-lg" required>
      </div>
      <div class="mb-3">
        <label class="form-label small"><i class="fas fa-hospital me-2"></i>Nom Clinique</label>
        <input type="text" name="clinic" class="form-control form-control-lg" required>
      </div>
      <div class="mb-3">
        <label class="form-label small"><i class="fas fa-calendar-alt me-2"></i>Date de création</label>
        <input type="date" name="creation_date" class="form-control form-control-lg" required>
      </div>
      <div class="mb-3">
        <label class="form-label small"><i class="fas fa-map-marker-alt me-2"></i>Adresse</label>
        <input type="text" name="address" class="form-control form-control-lg" required>
      </div>
      <button type="submit" class="btn btn-medical btn-lg w-100">Valider</button>
    </form>
    <div class="text-center mt-3">
      <a href="{{ url_for('login.login') }}" class="btn btn-outline-secondary d-inline-flex align-items-center">
        <i class="fas fa-arrow-left me-1"></i> Retour Connexion
      </a>
    </div>
  </div>
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''
# ───────── 4. Routes
@login_bp.route("/login", methods=["GET", "POST"])
def login():
    local = is_localhost(request)

    if request.method == "POST":
        role  = request.form["role_select"]
        email = request.form["email"].lower().strip()
        pwd   = request.form["password"]

        users = load_users()
        u = users.get(email)
        if u and u["password"] == hash_password(pwd) and u.get("role", "admin") == role:
            # Stockage de la session
            session["email"]     = email
            session["role"]      = role
            session.permanent    = True

            # Redirection directe vers la page d'accueil pour médecin et assistante
            if role in ("medecin", "assistante"):
                return redirect(url_for("accueil.accueil"))

            # Pour les autres rôles, on passe par la page d'activation
            return redirect(url_for("activation"))

        flash("Identifiants ou rôle invalides.", "danger")

    return render_template_string(
        login_template,
        url_lan = f"http://{lan_ip()}:3000",
        local   = local
    )
      
@login_bp.route("/register", methods=["GET","POST"])
def register():
    if not is_localhost(request):
        flash("La création de compte n’est possible qu’en localhost.","warning")
        return redirect(url_for("login.login"))
    f=request.form
    if request.method=="POST":
        users=load_users(); email=f["email"].lower()
        if email in users: flash("Email déjà enregistré.","danger")
        elif f["password"]!=f["confirm"]: flash("Les mots de passe ne correspondent pas.","danger")
        else:
            users[email]={"password":hash_password(f["password"]),"role":f["role"],
                          "clinic":f["clinic"],"creation_date":f["creation_date"],"address":f["address"]}
            save_users(users); flash("Compte créé.","success"); return redirect(url_for("login.login"))
    return render_template_string(register_template, local=True)

@login_bp.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    # Pour savoir si l'on est en localhost (utile dans le template)
    local = is_localhost(request)

    if request.method == 'POST':
        email         = request.form['email'].strip().lower()
        clinic        = request.form['clinic']
        creation_date = request.form['creation_date']
        address       = request.form['address']
        users         = load_users()
        user          = users.get(email)

        if (user
            and user.get('clinic') == clinic
            and user.get('creation_date') == creation_date
            and user.get('address') == address):
            # Génération du token et date d'expiration
            token  = generate_reset_token()
            expiry = (datetime.now() + timedelta(hours=1)).isoformat()

            user['reset_token']  = token
            user['reset_expiry'] = expiry
            save_users(users)

            return redirect(url_for('login.reset_password', token=token))

        flash('Données non reconnues, veuillez réessayer.', 'danger')

    # Affichage du formulaire, on passe aussi "local" pour le template
    return render_template_string(
        forgot_template,
        local=local
    )
  
@login_bp.route('/change_password', methods=['GET', 'POST'])
def change_password():
    email = session.get('email')
    if not email:
        flash('Vous devez être connecté pour changer votre mot de passe.', 'warning')
        return redirect(url_for('login.login'))

    users = load_users()
    user  = users.get(email)

    if request.method == 'POST':
        pwd     = request.form['password']
        confirm = request.form['confirm']
        if pwd != confirm:
            flash('Les mots de passe ne correspondent pas', 'warning')
        else:
            user['password'] = hash_password(pwd)
            save_users(users)
            flash('Mot de passe mis à jour', 'success')
            return redirect(url_for('login.login'))

    return render_template_string(reset_template)
  
@login_bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    users = load_users()
    for email, user in users.items():
        if user.get('reset_token') == token:
            expiry = datetime.fromisoformat(user.get('reset_expiry'))
            if datetime.now() > expiry:
                flash('Le lien a expiré', 'danger')
                return redirect(url_for('login.forgot_password'))
            if request.method == 'POST':
                pwd     = request.form['password']
                confirm = request.form['confirm']
                if pwd != confirm:
                    flash('Les mots de passe ne correspondent pas', 'warning')
                else:
                    user['password']     = hash_password(pwd)
                    user['reset_token']  = ''
                    user['reset_expiry'] = ''
                    save_users(users)
                    flash('Mot de passe mis à jour', 'success')
                    return redirect(url_for('login.login'))
            return render_template_string(reset_template)
    flash('Lien invalide', 'danger')
    return redirect(url_for('login.forgot_password'))

@login_bp.route('/logout')
def logout():
    session.pop('email', None)
    session.pop('role',  None)
    return redirect(url_for('login.login'))
