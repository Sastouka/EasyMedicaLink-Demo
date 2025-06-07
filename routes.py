# routes.py
from __future__ import annotations

import os
import pandas as pd
import uuid
from datetime import datetime
from typing import Dict
from pathlib import Path

LISTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Liste_Medications_Analyses_Radiologies.xlsx')

from flask import (
    request, render_template_string, redirect, url_for,
    send_file, flash, jsonify, session
)
import theme

# Dépendances internes
import utils
from templates import (
    main_template,
    settings_template,
    alert_template,
)

# ---------------------------------------------------------------------------
#  HELPERS INTERNES AU MODULE
# ---------------------------------------------------------------------------

def _config() -> Dict:
    return utils.load_config()

# ---------------------------------------------------------------------------
#  ENREGISTREMENT DES ROUTES D'APPLICATION
# ---------------------------------------------------------------------------

def register_routes(app):
    """Attache toutes les routes à l'instance Flask passée en argument."""

    # ---------------------------------------------------------------------
    #  PAGE PRINCIPALE – ENREGISTREMENT CONSULTATION
    # ---------------------------------------------------------------------
    @app.route("/consultation", methods=["GET", "POST"])
    def index():
        config = _config()
        theme_names = list(theme.THEMES.keys())
        utils.background_file = config.get("background_file_path")

        # 1️⃣ Charger la liste "de base" depuis Excel ou constantes par défaut
        if os.path.exists(LISTS_FILE):
            df_lists = pd.read_excel(LISTS_FILE, sheet_name=0, dtype=str).fillna('')
            base_meds = df_lists['Medications'].dropna().astype(str).tolist()
            base_analyses = df_lists['Analyses'].dropna().astype(str).tolist()
            base_radios = df_lists['Radiologies'].dropna().astype(str).tolist()
        else:
            base_meds = utils.default_medications_options
            base_analyses = utils.default_analyses_options
            base_radios = utils.default_radiologies_options

        # 2️⃣ Récupérer les ajouts du menu Paramètres
        cfg_meds = config.get("medications_options", [])
        cfg_analyses = config.get("analyses_options", [])
        cfg_radios = config.get("radiologies_options", [])

        # 2️⃣5️⃣ Récupérer la dernière consultation
        consult_file = Path(utils.EXCEL_FILE_PATH)
        last_consult = {}
        if consult_file.exists():
            try:
                df_last = pd.read_excel(consult_file, sheet_name=0, dtype=str).fillna('')
                if not df_last.empty:
                    last_consult = df_last.iloc[-1].to_dict()
            except Exception as e:
                print(f"Erreur lors du chargement de la dernière consultation depuis {consult_file}: {e}")
                last_consult = {}


        # 3️⃣ Fusionner Excel + Paramètres en supprimant les doublons
        meds_options = list(dict.fromkeys(base_meds + cfg_meds))
        analyses_options = list(dict.fromkeys(base_analyses + cfg_analyses))
        radiologies_options = list(dict.fromkeys(base_radios + cfg_radios))

        saved_medications, saved_analyses, saved_radiologies = [], [], []

        if request.method == "POST":
            form_data = request.form.to_dict()
            consultation_date = request.form.get("consultation_date", datetime.now().strftime("%Y-%m-%d"))
            medication_list = request.form.getlist("medications_list")
            analyses_list = request.form.getlist("analyses_list")
            radiologies_list = request.form.getlist("radiologies_list")

            patient_id = form_data.get("patient_id", "").strip()
            # --- MODIFICATION : Récupérer nom et prenom des champs séparés ou les déduire ---
            nom = form_data.get("nom", "").strip()
            prenom = form_data.get("prenom", "").strip()
            patient_name = form_data.get("patient_name", "").strip() # Nom complet du patient

            # Si les champs nom/prenom sont vides mais patient_name est rempli, tenter de splitter
            if not nom and not prenom and patient_name:
                name_parts = patient_name.split(' ', 1)
                nom = name_parts[0] if name_parts else ""
                prenom = name_parts[1] if len(name_parts) > 1 else ""
            # Si nom et prenom sont remplis, reconstruire patient_name si nécessaire
            elif nom or prenom:
                patient_name = f"{nom} {prenom}".strip()
            # --------------------------------------------------------------------------------


            certificate_category = form_data.get("certificate_category", "").strip()
            # On récupère le contenu complet du certificat pour la génération de PDF
            # mais on ne l'enregistre plus dans le fichier Excel
            certificate_full_content = form_data.get("certificate_content", "").strip()
            rest_duration = utils.extract_rest_duration(certificate_full_content)


            if not patient_id:
                return render_template_string(
                    alert_template,
                    alert_type="warning",
                    alert_title="Attention",
                    alert_text="Veuillez entrer l'ID du patient.",
                    redirect_url=url_for(".index"),
                )

            # Vérification d'unicité ID/nom (dans ConsultationData.xlsx pour cohérence)
            if os.path.exists(utils.EXCEL_FILE_PATH):
                df_existing_consult = pd.read_excel(utils.EXCEL_FILE_PATH, sheet_name=0, dtype=str).fillna('')
                if patient_id in df_existing_consult["patient_id"].astype(str).tolist():
                    existing_entries_for_id = df_existing_consult[df_existing_consult["patient_id"].astype(str) == patient_id]
                    if not existing_entries_for_id.empty:
                        # Utiliser 'nom' et 'prenom' si disponibles, sinon 'patient_name' pour la comparaison
                        most_common_full_name = ""
                        if 'nom' in existing_entries_for_id.columns and 'prenom' in existing_entries_for_id.columns:
                            # Tenter de reconstruire le nom complet à partir de 'nom' et 'prenom'
                            temp_df = existing_entries_for_id.copy()
                            temp_df['full_name_combined'] = temp_df['nom'].fillna('') + ' ' + temp_df['prenom'].fillna('')
                            temp_df['full_name_combined'] = temp_df['full_name_combined'].str.strip()
                            if not temp_df['full_name_combined'].empty:
                                most_common_full_name = temp_df['full_name_combined'].mode().iloc[0]
                            elif not existing_entries_for_id['patient_name'].empty:
                                most_common_full_name = existing_entries_for_id['patient_name'].mode().iloc[0]
                        elif not existing_entries_for_id['patient_name'].empty:
                            most_common_full_name = existing_entries_for_id['patient_name'].mode().iloc[0]

                        if most_common_full_name.strip().lower() != patient_name.strip().lower():
                            flash(f"L'ID patient '{patient_id}' est déjà associé à '{most_common_full_name}'. Veuillez utiliser ce nom ou un autre ID.", "error")
                            return redirect(url_for(".index"))


            # Gestion de la fusion des données existantes (mise à jour de consultation existante)
            new_entry = True
            df = pd.DataFrame()
            if os.path.exists(utils.EXCEL_FILE_PATH):
                df = pd.read_excel(utils.EXCEL_FILE_PATH, sheet_name=0, dtype=str).fillna('')

                df['date_obj'] = pd.to_datetime(df['consultation_date'].astype(str).str[:10], errors='coerce').dt.date
                current_date_obj = datetime.strptime(consultation_date, "%Y-%m-%d").date()

                mask = (df['patient_id'] == patient_id) & (df['date_obj'] == current_date_obj)
                existing_entries = df[mask]

                if not existing_entries.empty:
                    new_entry = False
                    idx = existing_entries.index[0]

                    def merge_items(existing, new_items_list):
                        existing_str = str(existing) if pd.notna(existing) else ''
                        existing_list = [item.strip() for item in existing_str.split('; ') if item.strip()]
                        merged = list(dict.fromkeys(existing_list + new_items_list))
                        return merged

                    df.at[idx, 'medications'] = '; '.join(merge_items(df.at[idx, 'medications'], medication_list))
                    df.at[idx, 'analyses'] = '; '.join(merge_items(df.at[idx, 'analyses'], analyses_list))
                    df.at[idx, 'radiologies'] = '; '.join(merge_items(df.at[idx, 'radiologies'], radiologies_list))

                    update_fields = [
                        'clinical_signs', 'bp', 'temperature', 'heart_rate',
                        'respiratory_rate', 'diagnosis', 'doctor_comment',
                        'certificate_category', 'rest_duration'
                    ]
                    for field in update_fields:
                        if field == 'certificate_category':
                            df.at[idx, field] = certificate_category
                        elif field == 'rest_duration':
                            df.at[idx, field] = rest_duration
                        elif form_data.get(field):
                            df.at[idx, field] = form_data[field]
                    
                    # --- MODIFICATION : Mise à jour des colonnes nom, prenom et patient_name ---
                    df.at[idx, 'nom'] = nom
                    df.at[idx, 'prenom'] = prenom
                    df.at[idx, 'patient_name'] = patient_name # Assurer que patient_name est aussi mis à jour
                    # -----------------------------------------------------------------------------

                    # S'assurer que 'certificate_content' est retiré si présent ou ne pas y toucher
                    if 'certificate_content' in df.columns:
                        df.at[idx, 'certificate_content'] = '' # ou np.nan si vous voulez une vraie valeur manquante

                    df.drop('date_obj', axis=1, inplace=True)
                    df.to_excel(utils.EXCEL_FILE_PATH, index=False)
                    flash("Consultation mise à jour avec succès", "success")

            if new_entry:
                new_row = {
                    "consultation_date": consultation_date,
                    "patient_id": patient_id,
                    "patient_name": patient_name, # Nom complet
                    "nom": nom,       # Nom de famille
                    "prenom": prenom, # Prénom
                    "date_of_birth": form_data.get("date_of_birth", "").strip(),
                    "gender": form_data.get("gender", "").strip(),
                    "age": form_data.get("patient_age", "").strip(),
                    "patient_phone": form_data.get("patient_phone", "").strip(),
                    "antecedents": form_data.get("antecedents", "").strip(),
                    "clinical_signs": form_data.get("clinical_signs", "").strip(),
                    "bp": form_data.get("bp", "").strip(),
                    "temperature": form_data.get("temperature", "").strip(),
                    "heart_rate": form_data.get("heart_rate", "").strip(),
                    "respiratory_rate": form_data.get("respiratory_rate", "").strip(),
                    "diagnosis": form_data.get("diagnosis", "").strip(),
                    "medications": "; ".join(medication_list),
                    "analyses": "; ".join(analyses_list),
                    "radiologies": "; ".join(radiologies_list),
                    "certificate_category": certificate_category,
                    "certificate_content":  "",
                    "rest_duration": rest_duration,
                    "doctor_comment": form_data.get("doctor_comment", "").strip(),
                    "consultation_id": str(uuid.uuid4()),
                }

                # S'assurer que toutes les colonnes nécessaires existent dans le DataFrame avant d'ajouter une nouvelle ligne
                # Cela gère le cas où le DataFrame est vide au départ et ne contient pas encore toutes les colonnes
                required_cols_for_df = [
                    "consultation_date", "patient_id", "patient_name", "nom", "prenom",
                    "date_of_birth", "gender", "age", "patient_phone", "antecedents",
                    "clinical_signs", "bp", "temperature", "heart_rate", "respiratory_rate",
                    "diagnosis", "medications", "analyses", "radiologies",
                    "certificate_category", "certificate_content", "rest_duration",
                    "doctor_comment", "consultation_id"
                ]
                for col in required_cols_for_df:
                    if col not in df.columns:
                        df[col] = '' # Ajouter la colonne avec des valeurs vides par défaut
                
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

                df.to_excel(utils.EXCEL_FILE_PATH, index=False)
                flash("Nouvelle consultation enregistrée", "success")

            session['prefill_suivi_patient_id'] = patient_id
            session['prefill_suivi_patient_name'] = patient_name

            utils.load_patient_data()
            saved_medications, saved_analyses, saved_radiologies = medication_list, analyses_list, radiologies_list

        # 4️⃣ Lecture des données pour l'affichage (après POST ou pour GET)
        consult_path = Path(utils.EXCEL_FILE_PATH)
        df_consult = pd.DataFrame()
        if consult_path.exists():
            try:
                df_consult = pd.read_excel(consult_path, sheet_name=0, dtype=str).fillna('')
            except Exception as e:
                print(f"Erreur lors du chargement de df_consult depuis {consult_path}: {e}")
                df_consult = pd.DataFrame()

        consult_rows = df_consult.to_dict(orient="records")

        # Le dictionnaire patient_data est construit à partir des mappings de utils.py
        # qui sont maintenant mis à jour pour inclure nom et prenom
        patient_data = {
            pid: {
                "name":          utils.patient_id_to_name.get(pid, ""),
                "nom":           utils.patient_id_to_nom.get(pid, ""),
                "prenom":        utils.patient_id_to_prenom.get(pid, ""),
                "age":           utils.patient_id_to_age.get(pid, ""),
                "phone":         utils.patient_id_to_phone.get(pid, ""),
                "antecedents":   utils.patient_id_to_antecedents.get(pid, ""),
                "date_of_birth": utils.patient_id_to_dob.get(pid, ""),
                "gender":        utils.patient_id_to_gender.get(pid, ""),
            }
            for pid in utils.patient_ids
        }

        prefill_suivi_patient_id = session.pop('prefill_suivi_patient_id', None)
        prefill_suivi_patient_name = session.pop('prefill_suivi_patient_name', None)

        return render_template_string(
            main_template,
            config=config,
            current_date=datetime.now().strftime("%d/%m/%Y"),
            medications_options=meds_options,
            analyses_options=analyses_options,
            radiologies_options=radiologies_options,
            certificate_categories=utils.certificate_categories,
            default_certificate_text=utils.default_certificate_text,
            patient_ids=utils.patient_ids,
            patient_names=utils.patient_names,
            host_address=f"http://{utils.LOCAL_IP}:3000",
            patient_data=patient_data,
            saved_medications=saved_medications,
            saved_analyses=saved_analyses,
            saved_radiologies=saved_radiologies,
            theme_names=theme_names,
            consult_rows=consult_rows,
            last_consult=last_consult,
            prefill_suivi_patient_id=prefill_suivi_patient_id,
            prefill_suivi_patient_name=prefill_suivi_patient_name
        )

    # ---------------------------------------------------------------------
    #  API JSON / TABLEAU SUIVI
    # ---------------------------------------------------------------------
    @app.route("/get_last_consultation")
    def get_last_consultation():
        pid = request.args.get("patient_id", "").strip()
        if pid and os.path.exists(utils.EXCEL_FILE_PATH):
            df = pd.read_excel(utils.EXCEL_FILE_PATH, sheet_name=0, dtype=str).fillna('')
            df = df[df["patient_id"].astype(str) == pid]
            if not df.empty:
                last_consult = df.iloc[-1].to_dict()
                last_consult.pop('certificate_content', None) # Supprime la clé si elle existe
                return jsonify(last_consult)
        return jsonify({})

    @app.route("/get_consultations")
    def get_consultations():
        pid = request.args.get("patient_id", "").strip()
        if pid and os.path.exists(utils.EXCEL_FILE_PATH):
            df = pd.read_excel(utils.EXCEL_FILE_PATH, sheet_name=0, dtype=str).fillna('')
            df = df[df["patient_id"].astype(str) == pid]
            if 'certificate_content' in df.columns:
                df = df.drop(columns=['certificate_content'])
            return df.to_json(orient="records", force_ascii=False)
        return "[]"

    @app.route("/delete_consultation", methods=["POST"])
    def delete_consultation():
        cid = request.form.get("consultation_id", "").strip()
        if cid:
            try:
                df = pd.read_excel(utils.EXCEL_FILE_PATH, sheet_name=0, dtype=str).fillna('')
                df = df[df["consultation_id"] != cid]
                df.to_excel(utils.EXCEL_FILE_PATH, index=False)
                return "OK", 200
            except Exception as e:
                return str(e), 500
        return "Missing parameters", 400

    # ---------------------------------------------------------------------
    #  PDF À LA VOLÉE
    # ---------------------------------------------------------------------
    @app.route("/generate_pdf_route")
    def generate_pdf_route():
        form_data = {
            k: request.args.get(k, "") for k in [
                "doctor_name", "patient_name", "patient_age", "date_of_birth", "gender",
                "location", "clinical_signs", "bp", "temperature", "heart_rate",
                "respiratory_rate", "diagnosis", "certificate_content",
            ]
        }
        form_data["include_certificate"] = request.args.get("include_certificate", "off")
        medications = request.args.get("medications_list", "").split("\n")
        analyses    = request.args.get("analyses_list", "").split("\n")
        radiologies = request.args.get("radiologies_list", "").split("\n")

        # Ces lignes ne sont plus nécessaires car utils.py gère l'affichage conditionnel
        medications = [item for item in medications if item.strip()]
        analyses    = [item for item in analyses if item.strip()]
        radiologies = [item for item in radiologies if item.strip()]

        pdf_path = os.path.join(utils.PDF_FOLDER, f"Ordonnance_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf")
        utils.generate_pdf_file(pdf_path, form_data, medications, analyses, radiologies)
        return send_file(pdf_path, as_attachment=True, download_name=os.path.basename(pdf_path))

    @app.route("/generate_history_pdf")
    def generate_history_pdf():
        pid   = request.args.get("patient_id_filter", "").strip()
        pname = request.args.get("patient_name_filter", "").strip()
        if not os.path.exists(utils.EXCEL_FILE_PATH):
            flash("Aucune donnée de consultation.", "warning")
            return redirect(url_for(".index"))
        df = pd.read_excel(utils.EXCEL_FILE_PATH, sheet_name=0, dtype=str).fillna('')
        if pid:
            df_filtered = df[df["patient_id"].astype(str) == pid]
        elif pname:
            df_filtered = df[df["patient_name"].astype(str).str.contains(pname, case=False, na=False)]
        else:
            flash("Sélectionnez l'ID ou le nom du patient.", "warning")
            return redirect(url_for(".index"))
        if df_filtered.empty:
            flash("Aucune consultation trouvée pour ce patient.", "info")
            return redirect(url_for(".index"))
        
        if 'certificate_content' in df_filtered.columns:
            df_filtered = df_filtered.drop(columns=['certificate_content'])

        pdf_path = os.path.join(utils.PDF_FOLDER, f"Historique_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf")
        utils.generate_history_pdf_file(pdf_path, df_filtered)
        return send_file(pdf_path, as_attachment=True, download_name=os.path.basename(pdf_path))

    # ---------------------------------------------------------------------
    #  IMPORT EXCEL / BACKGROUND
    # ---------------------------------------------------------------------
    @app.route("/import_excel", methods=["POST"])
    def import_excel():
        if "excel_file" not in request.files or request.files["excel_file"].filename == "":
            return jsonify({"status": "warning", "message": "Aucun fichier sélectionné."})
        f = request.files["excel_file"]
        filename = utils.secure_filename(f.filename)
        file_path = os.path.join(utils.EXCEL_FOLDER, filename)
        f.save(file_path)
        try:
            # Tenter de lire le fichier importé et de mettre à jour les listes
            df_imported = pd.read_excel(file_path, dtype=str).fillna('')
            df_imported.columns = [c.lower() for c in df_imported.columns]

            cfg = _config()
            current_meds = set(cfg.get("medications_options", []))
            current_analyses = set(cfg.get("analyses_options", []))
            current_radios = set(cfg.get("radiologies_options", []))

            if "medications" in df_imported.columns:
                current_meds.update(df_imported["medications"].dropna().tolist())
            if "analyses" in df_imported.columns:
                current_analyses.update(df_imported["analyses"].dropna().tolist())
            if "radiologies" in df_imported.columns:
                current_radios.update(df_imported["radiologies"].dropna().tolist())

            cfg.update({
                "medications_options": sorted(list(current_meds)),
                "analyses_options": sorted(list(current_analyses)),
                "radiologies_options": sorted(list(current_radios)),
            })
            utils.save_config(cfg)

            # Si le fichier importé est info_Base_patient.xlsx ou ConsultationData.xlsx,
            # forcer un rechargement complet des données patient
            if filename == "info_Base_patient.xlsx" or filename == "ConsultationData.xlsx":
                utils.load_patient_data()

            return jsonify({"status": "success", "message": "Import réussi."})
        except Exception as e:
            return jsonify({"status": "error", "message": f"Erreur : {e}"})

    @app.route("/import_background", methods=["POST"])
    def import_background():
        if "background_file" not in request.files or request.files["background_file"].filename == "":
            return jsonify({"status": "warning", "message": "Aucun fichier sélectionné."})
        f = request.files["background_file"]
        filename = utils.secure_filename(f.filename)
        path = os.path.join(utils.BACKGROUND_FOLDER, filename)
        f.save(path)
        ext = os.path.splitext(filename)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".pdf"):
            return jsonify({"status": "warning", "message": "Format non supporté."})
        utils.background_file = path
        cfg = _config(); cfg["background_file_path"] = path; utils.save_config(cfg)
        return jsonify({"status": "success", "message": f"Arrière plan importé : {path}"})

    # ---------------------------------------------------------------------
    #  COMMENTAIRE DE SUIVI PATIENT
    # ---------------------------------------------------------------------
    @app.route("/update_comment", methods=["POST"])
    def update_comment():
        pid = request.form.get("suivi_patient_id", "").strip()
        new_comment = request.form.get("new_doctor_comment", "").strip()
        if not pid:
            flash("Veuillez entrer l'ID du patient.", "warning")
            return redirect(url_for(".index"))
        if os.path.exists(utils.EXCEL_FILE_PATH):
            df = pd.read_excel(utils.EXCEL_FILE_PATH, sheet_name=0, dtype=str).fillna('')
            if 'doctor_comment' not in df.columns:
                df['doctor_comment'] = ''
            df.loc[df["patient_id"].astype(str) == pid, "doctor_comment"] = new_comment
            df.to_excel(utils.EXCEL_FILE_PATH, index=False)
            flash("Commentaire mis à jour.", "success")
        else:
            flash("Fichier de données non trouvé.", "error")
        return redirect(url_for(".index"))

    # ---------------------------------------------------------------------
    #  PARAMÈTRES APP
    # ---------------------------------------------------------------------
    from flask import current_app

    @app.route("/settings", methods=["GET", "POST"])
    def settings():
        cfg = utils.load_config()
        theme_names = list(theme.THEMES.keys())

        if request.method == "POST":
            cfg.update({
                "nom_clinique":         request.form.get("nom_clinique", ""),
                "cabinet":              request.form.get("cabinet", ""),
                "centre_medical":       request.form.get("centre_medecin", ""),
                "doctor_name":          request.form.get("nom_medecin", ""),
                "location":             request.form.get("lieu", ""),
                "theme":                request.form.get("theme", cfg.get("theme", theme.DEFAULT_THEME)),
                "background_file_path": request.form.get("arriere_plan", ""),
            })

            storage_path = request.form.get("storage_path", "").strip()
            if storage_path:
                cfg["storage_path"] = storage_path

            cfg["medications_options"] = (
                request.form.get("liste_medicaments","").splitlines()
                if request.form.get("liste_medicaments","") else utils.default_medications_options
            )
            cfg["analyses_options"] = (
                request.form.get("liste_analyses","").splitlines()
                if request.form.get("liste_analyses","") else utils.default_analyses_options
            )
            cfg["radiologies_options"] = (
                request.form.get("liste_radiologies","").splitlines()
                if request.form.get("liste_radiologies","") else utils.default_radiologies_options
            )

            utils.save_config(cfg)
            session["theme"] = cfg["theme"]

            utils.init_app(current_app)
            current_app.config["background_file_path"] = cfg.get("background_file_path", "")
            utils.background_file      = current_app.config["background_file_path"]

            utils.load_patient_data()

            if request.accept_mimetypes.accept_json:
                return jsonify({
                    "nom_clinique":         cfg.get("nom_clinique"),
                    "cabinet":              cfg.get("cabinet"),
                    "centre_medical":       cfg.get("centre_medical"),
                    "doctor_name":          cfg.get("doctor_name"),
                    "location":             cfg.get("location"),
                    "storage_path":         cfg.get("storage_path", ""),
                    "background_file_path": cfg.get("background_file_path",""),
                    "theme":                cfg.get("theme"),
                    "medications_options":  cfg.get("medications_options"),
                    "analyses_options":     cfg.get("analyses_options"),
                    "radiologies_options":  cfg.get("radiologies_options"),
                    "theme_names":          theme_names,
                    "theme_vars":           theme.current_theme(),
                })
            return jsonify({"status": "success"})

        return render_template_string(
            settings_template,
            config=cfg,
            theme_names=theme_names,
            theme_vars=theme.current_theme()
        )

    # ---------------------------------------------------------------------
    #  TÉLÉCHARGEMENT DE L'APPLI WINDOWS
    # ---------------------------------------------------------------------
    @app.route("/download_app")
    def download_app():
        file_path = os.path.join(utils.BASE_DIR, "EasyMedicalink.rar")
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
        flash("Le fichier n'existe pas.", "error")
        return redirect(url_for(".index"))
