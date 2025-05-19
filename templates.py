main_template = """
<!DOCTYPE html>
<html lang="fr">
{{ pwa_head()|safe }}
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ config.nom_clinique or config.cabinet or 'EasyMedicalink' }}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://fonts.googleapis.com/css2?family=Great+Vibes&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <link rel="stylesheet" href="https://cdn.datatables.net/1.13.1/css/dataTables.bootstrap5.min.css">

  <!-- INJECTION DYNAMIQUE DES VARIABLES DE THÈME -->
  <style>
    :root {
      {% for var, val in theme_vars.items() %}
        --{{ var }}: {{ val }};
      {% endfor %}
    }
  </style>

  <!-- Styles header principal inchangés -->
  <style>
    .card-header h1,
    .card-header .header-item,
    .card-header p {
      font-size: 30px !important;
    }
    .card-header h1 i,
    .card-header .header-item i,
    .card-header p i {
      font-size: 30px !important;
    }
  </style>

  <!-- Styles généraux mis à jour pour utiliser les vars CSS -->
  <style>
    body {
      background: var(--bg-color);
      padding-top: 56px;
      color: var(--text-color);
    }

    .card {
      background: var(--card-bg);
      border-radius: 15px;
      box-shadow: 0 4px 20px var(--card-shadow);
      transition: transform 0.2s ease;
    }

    .card:hover {
      transform: none !important;
      transition: none !important;
    }

    .nav-tabs .nav-link {
      border: none;
      color: #64748b;
      font-weight: 500;
      font-size: 24px;         /* ← taille du texte des onglets */
      transition: all 0.2s ease;
      position: relative;
    }

    .nav-tabs .nav-link i {
      font-size: 28px;         /* ← taille des icônes */
    }

    .nav-tabs .nav-link::after {
      content: '';
      position: absolute;
      bottom: 0;
      left: 0;
      width: 0;
      height: 3px;
      background: var(--primary-color);
      transition: width 0.3s ease;
    }

    .nav-tabs .nav-link.active {
      background: transparent;
      color: var(--primary-color) !important;
    }

    .nav-tabs .nav-link.active::after {
      width: 100%;
    }

    .form-control:focus {
      border-color: var(--primary-color);
      box-shadow: 0 0 0 0.25rem rgba(26, 115, 232, 0.15);
    }

    .dynamic-list {
      border: 2px solid #e2e8f0;
      border-radius: 10px;
      transition: border-color 0.2s ease;
    }

    .dynamic-list:focus {
      border-color: var(--primary-color);
    }

    .icon-pulse {
      animation: pulse 1.5s infinite;
    }

    @keyframes pulse {
      0% { transform: scale(1); }
      50% { transform: scale(1.05); }
      100% { transform: scale(1); }
    }

    .btn-medical {
      background: linear-gradient(45deg, var(--primary-color), var(--secondary-color));
      border: none;
      color: var(--button-text) !important;
      transition: transform 0.2s ease;
    }

    .btn-medical:hover {
      transform: translateY(-2px);
    }
  </style>

  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
  <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
  <script src="https://cdn.datatables.net/1.13.1/js/jquery.dataTables.min.js"></script>
  <script src="https://cdn.datatables.net/1.13.1/js/dataTables.bootstrap5.min.js"></script>

  <script>
    // Toutes les fonctions originales strictement conservées
    document.addEventListener("DOMContentLoaded", function() {
      document.querySelectorAll("#medication_combobox, #analysis_combobox, #radiology_combobox").forEach(function(input) {
        input.addEventListener("keydown", function(e) {
          if (e.key === "Enter") {
            e.preventDefault();
            return false;
          }
        });
      });

      var medCombo = document.getElementById("medication_combobox");
      if (medCombo) {
        medCombo.addEventListener("keydown", function(e) {
          if (e.key === "Enter") {
            e.preventDefault();
            addMedication();
          }
        });
      }

      var analysisCombo = document.getElementById("analysis_combobox");
      if (analysisCombo) {
        analysisCombo.addEventListener("keydown", function(e) {
          if (e.key === "Enter") {
            e.preventDefault();
            addAnalysis();
          }
        });
      }

      var radCombo = document.getElementById("radiology_combobox");
      if (radCombo) {
        radCombo.addEventListener("keydown", function(e) {
          if (e.key === "Enter") {
            e.preventDefault();
            addRadiology();
          }
        });
      }
    });

    function ajaxFileUpload(formId, endpoint) {
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
              if (formId === "importExcelForm") {
                  $('#importExcelModal').modal('hide');
              } else if (formId === "importBackgroundForm") {
                  $('#importBackgroundModal').modal('hide');
              }
              setTimeout(function() {
                  $('.modal-backdrop').remove();
              }, 2100);
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
      return false;
    }

    document.querySelectorAll("#medication_combobox, #analysis_combobox, #radiology_combobox").forEach(function(input) {
      input.addEventListener("keydown", function(e) {
        if (e.key === "Enter") { e.preventDefault(); }
      });
    });

    document.addEventListener("DOMContentLoaded", function() {
      document.getElementById("submitBtn").addEventListener("click", function(e) {
        e.preventDefault();
        Swal.fire({
          title: 'Vérification des onglets',
          text: "Avez-vous parcouru tous les onglets (Consultation, Médicaments, Biologie, Radiologies, Certificats) ?",
          icon: 'warning',
          showCancelButton: true,
          confirmButtonText: 'Oui, je confirme',
          cancelButtonText: 'Non, vérifier'
        }).then((result) => {
          if (result.isConfirmed) {
            document.querySelectorAll("#medications_listbox option").forEach(function(option) { option.selected = true; });
            document.querySelectorAll("#analyses_listbox option").forEach(function(option) { option.selected = true; });
            document.querySelectorAll("#radiologies_listbox option").forEach(function(option) { option.selected = true; });
            document.getElementById("mainForm").submit();
          }
        });
      });
    });
    
// Ajouter ce code dans la section JavaScript
document.addEventListener('DOMContentLoaded', function() {
    // Gestion de la persistance des onglets
    const triggerTabList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tab"]'))
    
    triggerTabList.forEach(function (triggerEl) {
        const tabTrigger = new bootstrap.Tab(triggerEl)
        
        triggerEl.addEventListener('click', function (event) {
            event.preventDefault()
            tabTrigger.show()
        })
    })

    // Restaurer l'onglet actif depuis le localStorage
    const activeTab = localStorage.getItem('activeTab')
    if (activeTab) {
        const triggerEl = document.querySelector(`[data-bs-target="${activeTab}"]`)
        if (triggerEl) bootstrap.Tab.getOrCreateInstance(triggerEl).show()
    }

    // Sauvegarder l'onglet actif lors du changement
    document.querySelectorAll('[data-bs-toggle="tab"]').forEach(function(tabEl) {
        tabEl.addEventListener('shown.bs.tab', function(event) {
            localStorage.setItem('activeTab', event.target.getAttribute('data-bs-target'))
        })
    })
})

    var certificateTemplates = {{ certificate_categories|tojson }};
    window.addEventListener("DOMContentLoaded", function() {
      document.getElementById("certificate_category").addEventListener("change", function() {
        var cat = this.value;
        if(certificateTemplates[cat]) { document.getElementById("certificate_content").value = certificateTemplates[cat]; }
      });
      window.medicationCount = 1;
      window.analysisCount = 1;
      window.radiologyCount = 1;
      console.log("Patient data:", patientData);
    });

    function updateListNumbers(listboxId) {
      var listbox = document.getElementById(listboxId);
      for (var i = 0; i < listbox.options.length; i++) {
        var parts = listbox.options[i].value.split(". ");
        var text = (parts.length > 1) ? parts.slice(1).join(". ") : listbox.options[i].value;
        listbox.options[i].text = (i + 1) + ". " + text;
      }
    }

    function addMedication() {
      var combo = document.getElementById("medication_combobox");
      var listbox = document.getElementById("medications_listbox");
      var value = combo.value.trim();
      if (value !== "") {
        var option = document.createElement("option");
        option.text = window.medicationCount + ". " + value;
        option.value = value;
        listbox.add(option);
        window.medicationCount++;
        combo.value = "";
      }
    }

    function removeMedication() {
      var listbox = document.getElementById("medications_listbox");
      for (var i = listbox.options.length - 1; i >= 0; i--) { if (listbox.options[i].selected) { listbox.remove(i); } }
      updateListNumbers("medications_listbox");
      window.medicationCount = listbox.options.length + 1;
    }

    function addAnalysis() {
      var combo = document.getElementById("analysis_combobox");
      var listbox = document.getElementById("analyses_listbox");
      var value = combo.value.trim();
      if (value !== "") {
        var option = document.createElement("option");
        option.text = window.analysisCount + ". " + value;
        option.value = value;
        listbox.add(option);
        window.analysisCount++;
        combo.value = "";
      }
    }

    function removeAnalysis() {
      var listbox = document.getElementById("analyses_listbox");
      for (var i = listbox.options.length - 1; i >= 0; i--) { if (listbox.options[i].selected) { listbox.remove(i); } }
      updateListNumbers("analyses_listbox");
      window.analysisCount = listbox.options.length + 1;
    }

    function addRadiology() {
      var combo = document.getElementById("radiology_combobox");
      var listbox = document.getElementById("radiologies_listbox");
      var value = combo.value.trim();
      if (value !== "") {
        var option = document.createElement("option");
        option.text = window.radiologyCount + ". " + value;
        option.value = value;
        listbox.add(option);
        window.radiologyCount++;
        combo.value = "";
      }
    }

    function removeRadiology() {
      var listbox = document.getElementById("radiologies_listbox");
      for (var i = listbox.options.length - 1; i >= 0; i--) { if (listbox.options[i].selected) { listbox.remove(i); } }
      updateListNumbers("radiologies_listbox");
      window.radiologyCount = listbox.options.length + 1;
    }

    var patientData = {{ patient_data|tojson }};
    document.addEventListener("DOMContentLoaded", function(){
      document.getElementById("suivi_patient_id").addEventListener("change", function() {
         var id = this.value.trim();
         if(patientData[id]){
            document.getElementById("suivi_patient_name").value = patientData[id].name;
         } else {
            document.getElementById("suivi_patient_name").value = "";
         }
         $('#consultationsTable').DataTable().ajax.reload();
      });
    });

    document.addEventListener("DOMContentLoaded", function(){
      document.getElementById("patient_id").addEventListener("change", function() {
         var id = this.value.trim();
         console.log("Patient ID modifié:", id);
         if(patientData[id]){
            document.getElementById("patient_name").value = patientData[id].name;
            document.getElementById("patient_age").value = patientData[id].age;
            document.getElementById("patient_phone").value = patientData[id].phone;
            document.getElementById("antecedents").value = patientData[id].antecedents;
            document.getElementById("date_of_birth").value = patientData[id].date_of_birth;
            document.getElementById("gender").value = patientData[id].gender;
            document.getElementById("suivi_patient_id").value = id;
            document.getElementById("suivi_patient_name").value = patientData[id].name;
         } else { console.log("Aucune donnée trouvée pour cet ID:", id); }
         if(id){
              fetch("/get_last_consultation?patient_id=" + id)
              .then(response => response.json())
              .then(data => {
                  console.log("Données de la dernière consultation:", data);
                  if(Object.keys(data).length !== 0){
                        document.getElementById("clinical_signs").value = data.clinical_signs || "";
                        document.getElementById("bp").value = data.bp || "";
                        document.getElementById("temperature").value = data.temperature || "";
                        document.getElementById("heart_rate").value = data.heart_rate || "";
                        document.getElementById("respiratory_rate").value = data.respiratory_rate || "";
                        document.getElementById("diagnosis").value = data.diagnosis || "";
                        var medications_listbox = document.getElementById("medications_listbox");
                        medications_listbox.innerHTML = "";
                        if(data.medications){
                             data.medications.split("; ").forEach((item, index)=>{
                                  var option = document.createElement("option");
                                  option.text = (index+1) + ". " + item;
                                  option.value = item;
                                  medications_listbox.add(option);
                             });
                        }
                        var analyses_listbox = document.getElementById("analyses_listbox");
                        analyses_listbox.innerHTML = "";
                        if(data.analyses){
                             data.analyses.split("; ").forEach((item, index)=>{
                                  var option = document.createElement("option");
                                  option.text = (index+1) + ". " + item;
                                  option.value = item;
                                  analyses_listbox.add(option);
                             });
                        }
                        var radiologies_listbox = document.getElementById("radiologies_listbox");
                        radiologies_listbox.innerHTML = "";
                        if(data.radiologies){
                             data.radiologies.split("; ").forEach((item, index)=>{
                                  var option = document.createElement("option");
                                  option.text = (index+1) + ". " + item;
                                  option.value = item;
                                  radiologies_listbox.add(option);
                             });
                        }
                        document.getElementById("certificate_category").value = data.certificate_category || "";
                        document.getElementById("certificate_content").value = data.certificate_content || "";
                  }
              })
              .catch(error => { console.error("Erreur lors de la récupération de la dernière consultation :", error); });
         }
      });
    });

    document.addEventListener("DOMContentLoaded", function(){
      document.getElementById("date_of_birth").addEventListener("change", function() {
        var dob = this.value;
        if (dob) {
          var birthDate = new Date(dob);
          var today = new Date();
          var ageYears = today.getFullYear() - birthDate.getFullYear();
          var m = today.getMonth() - birthDate.getMonth();
          if (m < 0 || (m === 0 && today.getDate() < birthDate.getDate())) {
            ageYears--;
          }
          var ageMonths = today.getMonth() - birthDate.getMonth();
          if (today.getDate() < birthDate.getDate()) {
            ageMonths--;
          }
          ageMonths = (ageMonths + 12) % 12;
          var ageString = ageYears > 0 ? ageYears + " ans " + ageMonths + " mois" : ageMonths + " mois";
          document.getElementById("patient_age").value = ageString;
        }
      });
    });

    function filterConsultations() {
      var id = document.getElementById("suivi_patient_id").value.trim();
      var name = document.getElementById("suivi_patient_name").value.trim();
      var params = new URLSearchParams(window.location.search);
      if (id) { params.set("patient_id_filter", id); }
      if (name) { params.set("patient_name_filter", name); }
      document.getElementById("historyPdfBtn").href = "{{ url_for('generate_history_pdf') }}?" + params.toString();
      window.location.href = "?" + params.toString();
    }

    function generateHistoryPDF() {
       var id = document.getElementById("suivi_patient_id").value.trim();
       var name = document.getElementById("suivi_patient_name").value.trim();
       if (!id && !name) {
           Swal.fire({
               icon: 'warning',
               title: 'Attention',
               text: "Veuillez renseigner l'ID ou le nom du patient."
           });
           return;
       }
       var params = new URLSearchParams();
       if (id) { params.set("patient_id_filter", id); }
       if (name) { params.set("patient_name_filter", name); }
       var url = "{{ url_for('generate_history_pdf') }}" + "?" + params.toString();
       fetch(url, {
  method: 'GET',
  credentials: 'same-origin'
})
.then(resp => {
  if (!resp.ok) throw new Error("Erreur réseau");
  return resp.blob();
})
.then(blob => {
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = blobUrl;
  a.download = 'consultation.pdf';
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(blobUrl);
})
.catch(err => {
  console.error(err);
  Swal.fire('Erreur', 'Impossible de générer le PDF.', 'error');
});
    }

    function generatePDF() {
      const doctor_name = document.getElementById("doctor_name").value;
      const patient_name = document.getElementById("patient_name").value;
      const patient_age = document.getElementById("patient_age").value;
      const date_of_birth = document.getElementById("date_of_birth").value;
      const gender = document.getElementById("gender").value;
      const location = document.getElementById("location").value;
      const clinical_signs = document.getElementById("clinical_signs").value;
      const bp = document.getElementById("bp").value;
      const temperature = document.getElementById("temperature").value;
      const heart_rate = document.getElementById("heart_rate").value;
      const respiratory_rate = document.getElementById("respiratory_rate").value;
      const diagnosis = document.getElementById("diagnosis").value;
      const certificate_content = document.getElementById("certificate_content").value;
      const include_certificate = document.getElementById("include_certificate").checked ? "on" : "off";
      
      let medications = [];
      const medications_listbox = document.getElementById("medications_listbox");
      for (let option of medications_listbox.options) { medications.push(option.value); }
      let analyses = [];
      const analyses_listbox = document.getElementById("analyses_listbox");
      for (let option of analyses_listbox.options) { analyses.push(option.value); }
      let radiologies = [];
      const radiologies_listbox = document.getElementById("radiologies_listbox");
      for (let option of radiologies_listbox.options) { radiologies.push(option.value); }
      
      const params = new URLSearchParams();
      params.set("doctor_name", doctor_name);
      params.set("patient_name", patient_name);
      params.set("patient_age", patient_age);
      params.set("date_of_birth", date_of_birth);
      params.set("gender", gender);
      params.set("location", location);
      params.set("clinical_signs", clinical_signs);
      params.set("bp", bp);
      params.set("temperature", temperature);
      params.set("heart_rate", heart_rate);
      params.set("respiratory_rate", respiratory_rate);
      params.set("diagnosis", diagnosis);
      params.set("certificate_content", certificate_content);
      params.set("include_certificate", include_certificate);
      params.set("medications_list", medications.join("\\n"));
      params.set("analyses_list", analyses.join("\\n"));
      params.set("radiologies_list", radiologies.join("\\n"));
      
      const url = "{{ url_for('generate_pdf_route') }}" + "?" + params.toString();
      window.open(url, "_blank");
    }

    $(document).ready(function(){
      var table = $('#consultationsTable').DataTable({
         ajax: {
           url: "/get_consultations",
           data: function(d) {
             d.patient_id = $('#suivi_patient_id').val();
           },
           dataSrc: ''
         },
         columns: [
           { data: "consultation_date" },
           { data: "patient_id" },
           { data: "patient_name" },
           { data: "date_of_birth" },
           { data: "gender" },
           { data: "age" },
           { data: "patient_phone" },
           { data: "antecedents" },
           { data: "clinical_signs" },
           { data: "bp" },
           { data: "temperature" },
           { data: "heart_rate" },
           { data: "respiratory_rate" },
           { data: "diagnosis" },
           { data: "medications" },
           { data: "analyses" },
           { data: "radiologies" },
           { data: "certificate_category" },
           { data: "certificate_content" },
           { data: "rest_duration" },
           { data: "doctor_comment" },
           { 
             data: "consultation_id",
             render: function(data, type, row, meta) {
                return '<button class="btn btn-sm btn-danger delete-btn" data-id="'+data+'">Supprimer</button>';
             }
           }
         ]
      });
      $('#consultationsTable tbody').on('click', '.delete-btn', function(e){
         e.preventDefault();
         var consultationId = $(this).data('id');
         if(confirm("Voulez-vous vraiment supprimer cette consultation ?")){
           $.ajax({
             url: '/delete_consultation',
             method: 'POST',
             data: { consultation_id: consultationId },
             success: function(response){
                table.ajax.reload();
             },
             error: function(err){
                alert("Erreur lors de la suppression");
             }
           });
         }
      });
      $('#refreshTableBtn').click(function(){
         table.ajax.reload();
      });
    });
  </script>
  <style>
  /* Barres de navigation et Offcanvas */
  .navbar,
  .offcanvas-header {
    background: linear-gradient(45deg, var(--primary-color), var(--secondary-color)) !important;
  }

  /* Fond de l’Offcanvas body */
  .offcanvas-body {
    background: var(--card-bg) !important;
    color: var(--text-color) !important;
  }

  /* Entête des cartes (zone nom clinique, onglets, etc.) */
  .card-header {
    background: var(--primary-color) !important;
    color: var(--button-text) !important;
  }

  /* Zone principale de contenu (cartes, formulaires) */
  .card,
  .form-control,
  .dataTables_wrapper {
    background: var(--card-bg) !important;
    color: var(--text-color) !important;
  }

  /* Liens, textes cliquables */
  a, .nav-link, .btn-link {
    color: var(--primary-color) !important;
  }
  a:hover, .nav-link:hover, .btn-link:hover {
    color: var(--secondary-color) !important;
  }
</style>

  <style>
    /* Forcer le texte EasyMedicalink en blanc */
    .navbar .navbar-brand,
    .navbar .navbar-brand:hover {
      color: #ffffff !important;
    }
  </style>
  <style>
  /* Forcer le texte du bouton “Télécharger” en blanc */
  .btn-primary,
  .btn-primary:hover,
  .btn-primary:focus {
    color: #ffffff !important;
  }
</style>

</head>
<body class="min-h-screen flex flex-col">
  <!-- Barre de navigation -->
  <nav class="navbar navbar-dark fixed-top"
       style="background: linear-gradient(45deg, var(--primary-color), var(--secondary-color));">
    <div class="container-fluid d-flex align-items-center">
      <button class="navbar-toggler" style="transform: scale(0.75);" 
              type="button" data-bs-toggle="offcanvas" data-bs-target="#settingsOffcanvas">
        <i class="fas fa-bars"></i>
      </button>
      <a class="navbar-brand ms-auto d-flex align-items-center"
         href="{{ url_for('accueil.accueil') }}"
         style="font-family: 'Great Vibes', cursive; font-size:2rem; color:white;">
        <!-- Icône Accueil, avec 1 cm d’espacement à sa droite -->
        <i class="fas fa-home" style="margin-right:0.5cm;"></i>
        <!-- Icône Cœur animé -->
        <i class="fas fa-heartbeat icon-pulse me-2"></i>
        EasyMedicalink
      </a>
    </div>
  </nav>

<!-- Ajoutez ces boutons “Plein écran” et “Retour Web” dans votre menu Paramètres -->
<div class="offcanvas offcanvas-start" tabindex="-1" id="settingsOffcanvas">
  <div class="offcanvas-header bg-gradient-to-r from-[#1a73e8] to-[#0d9488] text-white flex justify-between items-center">
    <h5 class="flex items-center"><i class="fas fa-cog me-2"></i>Paramètres</h5>
    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="offcanvas"></button>
  </div>
  <div class="offcanvas-body p-4 bg-white shadow-lg rounded-tr-2xl rounded-br-2xl">
    <!-- Boutons plein écran / retour web -->
    <!-- Boutons modifier mot de passe & déconnexion -->
    <div class="flex space-x-2 mb-4">
      <a href="{{ url_for('login.change_password') }}" class="btn-medical flex-1 py-2 flex justify-center items-center">
        <i class="fas fa-key me-2"></i>Modifier passe
      </a>
      <a href="/logout" class="btn-medical flex-1 py-2 flex justify-center items-center">
        <i class="fas fa-sign-out-alt me-2"></i>Déconnexion
      </a>
    </div>
    <form id="settingsForm" action="{{ url_for('settings') }}" method="POST" class="space-y-4">
      <div>
        <label for="nom_clinique" class="form-label font-medium"><i class="fas fa-hospital me-2"></i>Nom Clinique/Cabinet</label>
        <input type="text" id="nom_clinique" name="nom_clinique"
               class="form-control dynamic-list" value="{{ config.nom_clinique | default('') }}">
      </div>
      <div>
        <label for="centre_medecin" class="form-label font-medium"><i class="fas fa-clinic-medical me-2"></i>Centre Médical</label>
        <input type="text" id="centre_medecin" name="centre_medecin"
               class="form-control dynamic-list" value="{{ config.centre_medical | default('') }}">
      </div>
      <div>
        <label for="nom_medecin" class="form-label font-medium"><i class="fas fa-user-md me-2"></i>Nom Médecin</label>
        <input type="text" id="nom_medecin" name="nom_medecin"
               class="form-control dynamic-list" value="{{ config.doctor_name | default('') }}">
      </div>
      <div>
        <label for="lieu" class="form-label font-medium"><i class="fas fa-map-marker-alt me-2"></i>Lieu</label>
        <input type="text" id="lieu" name="lieu"
               class="form-control dynamic-list" value="{{ config.location | default('') }}">
      </div>
      <div>
        <label for="theme" class="form-label font-medium"><i class="fas fa-palette me-2"></i>Thème</label>
        <select id="theme" name="theme" class="form-select">
          {% for t in theme_names %}
            <option value="{{ t }}" {% if config.theme == t %}selected{% endif %}>{{ t.capitalize() }}</option>
          {% endfor %}
        </select>
      </div>
      <div>
        <label for="arriere_plan" class="form-label font-medium"><i class="fas fa-image me-2"></i>Arrière-plan</label>
        <input type="text" id="arriere_plan" name="arriere_plan"
               class="form-control dynamic-list" value="{{ config.background_file_path | default('') }}">
      </div>
      <div>
        <label for="storage_path" class="form-label font-medium"><i class="fas fa-folder-open me-2"></i>Stockage</label>
        <input type="text" id="storage_path" name="storage_path"
               class="form-control dynamic-list" value="{{ config.storage_path | default('') }}">
      </div>
      <div>
        <label for="liste_medicaments" class="form-label font-medium"><i class="fas fa-pills me-2"></i>Médicaments</label>
        <textarea id="liste_medicaments" name="liste_medicaments" rows="5"
                  class="form-control dynamic-list">{% if config.medications_options %}{{ config.medications_options | join('\\n') }}{% endif %}</textarea>
      </div>
      <div>
        <label for="liste_analyses" class="form-label font-medium"><i class="fas fa-microscope me-2"></i>Analyses</label>
        <textarea id="liste_analyses" name="liste_analyses" rows="5"
                  class="form-control dynamic-list">{% if config.analyses_options %}{{ config.analyses_options | join('\\n') }}{% endif %}</textarea>
      </div>
      <div>
        <label for="liste_radiologies" class="form-label font-medium"><i class="fas fa-x-ray me-2"></i>Radiologies</label>
        <textarea id="liste_radiologies" name="liste_radiologies" rows="5"
                  class="form-control dynamic-list">{% if config.radiologies_options %}{{ config.radiologies_options | join('\\n') }}{% endif %}</textarea>
      </div>
      <button type="submit" class="btn-medical w-full py-2 mt-2 flex justify-center items-center">
        <i class="fas fa-save me-2"></i>Enregistrer
      </button>
    </form>
      <!-- sweetalert2 (si pas déjà inclus) -->
  <script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
  <script>
    document.getElementById("settingsForm").addEventListener("submit", function(e) {
      e.preventDefault();
      const form = this;
      const data = new FormData(form);
      fetch(form.action, {
        method: 'POST',
        headers: { 'Accept': 'application/json' },
        body: data
      })
      .then(res => res.json())
      .then(json => {
        Swal.fire({
          title: 'Paramètres enregistrés',
          text:  'Voulez-vous recharger pour appliquer les changements ?',
          icon:  'success',
          showCancelButton: true,
          confirmButtonText: 'Recharger',
          cancelButtonText:  'Plus tard'
        }).then(result => {
          if (result.isConfirmed) {
            window.location.reload();
          }
        });
      })
      .catch(() => {
        Swal.fire('Erreur','Impossible d’enregistrer les paramètres.','error');
      });
    });
  </script>

  </div>
</div>

<div class="container my-4">
  <div class="card shadow-lg">
    <div class="card-header bg-gradient-to-r from-[#1a73e8] to-[#0d9488] text-white py-3">
      <h1 class="text-center mb-2 header-item">
        <i class="fas fa-hospital me-2"></i>{{ config.nom_clinique or config.cabinet or 'EasyMedicalink' }}
      </h1>
      <div class="d-flex justify-content-center gap-4">
        <div class="d-flex align-items-center header-item">
          <i class="fas fa-user-md me-2"></i><span>{{ config.doctor_name }}</span>
        </div>
        <div class="d-flex align-items-center header-item">
          <i class="fas fa-map-marker-alt me-2"></i><span>{{ config.location }}</span>
        </div>
      </div>
      <p class="text-center mt-2 header-item">
        <i class="fas fa-calendar-day me-2"></i>{{ current_date }}
      </p>
    </div>


    <div class="card-body">
      <form method="POST" enctype="multipart/form-data" id="mainForm">
        <ul class="nav nav-tabs justify-content-center" id="myTab" role="tablist">
          <li class="nav-item" role="presentation">
            <button class="nav-link active" id="basic-info-tab" data-bs-toggle="tab" data-bs-target="#basic-info">
              <i class="fas fa-user-injured me-2"></i>Infos Base
            </button>
          </li>
          <li class="nav-item" role="presentation">
            <button class="nav-link" id="consultation-tab" data-bs-toggle="tab" data-bs-target="#consultation">
              <i class="fas fa-stethoscope me-2"></i>Consultation
            </button>
          </li>
          <li class="nav-item" role="presentation">
            <button class="nav-link" id="medicaments-tab" data-bs-toggle="tab" data-bs-target="#medicaments">
              <i class="fas fa-pills me-2"></i>Médicaments
            </button>
          </li>
          <li class="nav-item" role="presentation">
            <button class="nav-link" id="biologie-tab" data-bs-toggle="tab" data-bs-target="#biologie">
              <i class="fas fa-dna me-2"></i>Biologie
            </button>
          </li>
          <li class="nav-item" role="presentation">
            <button class="nav-link" id="radiologies-tab" data-bs-toggle="tab" data-bs-target="#radiologies">
              <i class="fas fa-x-ray me-2"></i>Radiologies
            </button>
          </li>
          <li class="nav-item" role="presentation">
            <button class="nav-link" id="certificat-tab" data-bs-toggle="tab" data-bs-target="#certificat">
              <i class="fas fa-file-medical me-2"></i>Certificat
            </button>
          </li>
          <li class="nav-item" role="presentation">
            <button class="nav-link" id="suivi-tab" data-bs-toggle="tab" data-bs-target="#suivi">
              <i class="fas fa-history me-2"></i>Suivi
            </button>
          </li>
        </ul>

        <div class="tab-content py-3">
          <!-- Onglet Informations de Base -->
      <div class="tab-pane fade show active" id="basic-info" role="tabpanel">
  <div class="card shadow-lg mb-4">
    <div class="card-body">
      <!-- Médecin (inchangé) -->
      <div class="mb-3 row">
        <label for="doctor_name" class="col-sm-3 col-form-label"><i class="fas fa-user-md me-2"></i>Médecin</label>
        <div class="col-sm-9">
          <input type="text" class="form-control" name="doctor_name" id="doctor_name"
                 value="{{ request.form.get('doctor_name', config.doctor_name if config.doctor_name is defined else '') }}">
        </div>
      </div>
      <!-- Lieu (inchangé) -->
      <div class="mb-3 row">
        <label for="location" class="col-sm-3 col-form-label"><i class="fas fa-map-marker-alt me-2"></i>Lieu</label>
        <div class="col-sm-9">
          <input type="text" class="form-control" name="location" id="location"
                 value="{{ request.form.get('location', config.location if config.location is defined else '') }}">
        </div>
      </div>
      <!-- ID Patient -->
      <div class="mb-3 row">
        <label for="patient_id" class="col-sm-3 col-form-label"><i class="fas fa-id-card me-2"></i>ID Patient</label>
        <div class="col-sm-9">
          <input type="text" class="form-control" name="patient_id" id="patient_id" list="patient_ids"
                 value="{{ request.form.get('patient_id', last_consult.get('patient_id','')) }}">
          <datalist id="patient_ids">
            {% for pid in patient_ids %}
            <option value="{{ pid }}"></option>
            {% endfor %}
          </datalist>
        </div>
      </div>
      <!-- Nom Patient -->
      <div class="mb-3 row">
        <label for="patient_name" class="col-sm-3 col-form-label"><i class="fas fa-user me-2"></i>Nom Patient</label>
        <div class="col-sm-9">
          <input type="text" class="form-control" name="patient_name" id="patient_name" list="patient_names"
                 value="{{ request.form.get('patient_name', last_consult.get('patient_name','')) }}">
          <datalist id="patient_names">
            {% for name in patient_names %}
            <option value="{{ name }}"></option>
            {% endfor %}
          </datalist>
        </div>
      </div>
      <!-- Date de Naissance -->
      <div class="mb-3 row">
        <label for="date_of_birth" class="col-sm-3 col-form-label"><i class="fas fa-calendar-alt me-2"></i>Date Naissance</label>
        <div class="col-sm-9">
          <input type="date" class="form-control" name="date_of_birth" id="date_of_birth"
                 value="{{ request.form.get('date_of_birth', last_consult.get('date_of_birth','')) }}">
        </div>
      </div>
      <!-- Genre -->
      <div class="mb-3 row">
        <label for="gender" class="col-sm-3 col-form-label"><i class="fas fa-venus-mars me-2"></i>Genre</label>
        <div class="col-sm-9">
          <select name="gender" class="form-select" id="gender">
            <option value="Masculin" {% if request.form.get('gender', last_consult.get('gender','')) == 'Masculin' %}selected{% endif %}>Masculin</option>
            <option value="Féminin"   {% if request.form.get('gender', last_consult.get('gender','')) == 'Féminin'   %}selected{% endif %}>Féminin</option>
            <option value="Autre"      {% if request.form.get('gender', last_consult.get('gender','')) == 'Autre'      %}selected{% endif %}>Autre</option>
          </select>
        </div>
      </div>
      <!-- Âge -->
      <div class="mb-3 row">
        <label for="patient_age" class="col-sm-3 col-form-label"><i class="fas fa-calendar-day me-2"></i>Âge</label>
        <div class="col-sm-9">
          <input type="text" class="form-control" name="patient_age" id="patient_age"
                 value="{{ request.form.get('patient_age', last_consult.get('age','')) }}">
        </div>
      </div>
      <!-- Antécédents -->
      <div class="mb-3 row">
        <label for="antecedents" class="col-sm-3 col-form-label"><i class="fas fa-file-medical me-2"></i>Antécédents</label>
        <div class="col-sm-9">
          <input type="text" class="form-control" name="antecedents" id="antecedents"
                 value="{{ request.form.get('antecedents', last_consult.get('antecedents','')) }}">
        </div>
      </div>
      <!-- Téléphone -->
      <div class="mb-3 row">
        <label for="patient_phone" class="col-sm-3 col-form-label"><i class="fas fa-phone me-2"></i>Téléphone</label>
        <div class="col-sm-9">
          <input type="text" class="form-control" name="patient_phone" id="patient_phone"
                 value="{{ request.form.get('patient_phone', last_consult.get('patient_phone','')) }}">
        </div>
      </div>
    </div>
  </div>
</div>

          <!-- Onglet Consultation -->
          <div class="tab-pane fade" id="consultation" role="tabpanel">
            <div class="card shadow-lg mb-4">
              <div class="card-body">
                <div class="mb-3">
                  <label for="clinical_signs" class="form-label"><i class="fas fa-notes-medical me-2"></i>Signes Cliniques</label>
                  <textarea class="form-control" name="clinical_signs" id="clinical_signs" rows="2">{{ request.form.get('clinical_signs', '') }}</textarea>
                </div>
                <div class="row mb-3">
                  <div class="col-sm-6">
                    <label for="bp" class="form-label"><i class="fas fa-heartbeat me-2"></i>Tension (mmHg)</label>
                    <input type="text" class="form-control" name="bp" id="bp" value="{{ request.form.get('bp', '') }}">
                  </div>
                  <div class="col-sm-6">
                    <label for="temperature" class="form-label"><i class="fas fa-thermometer-half me-2"></i>Température (°C)</label>
                    <input type="text" class="form-control" name="temperature" id="temperature" value="{{ request.form.get('temperature', '') }}">
                  </div>
                </div>
                <div class="row mb-3">
                  <div class="col-sm-6">
                    <label for="heart_rate" class="form-label"><i class="fas fa-heart me-2"></i>FC (bpm)</label>
                    <input type="text" class="form-control" name="heart_rate" id="heart_rate" value="{{ request.form.get('heart_rate', '') }}">
                  </div>
                  <div class="col-sm-6">
                    <label for="respiratory_rate" class="form-label"><i class="fas fa-lungs me-2"></i>FR (rpm)</label>
                    <input type="text" class="form-control" name="respiratory_rate" id="respiratory_rate" value="{{ request.form.get('respiratory_rate', '') }}">
                  </div>
                </div>
                <div class="mb-3">
                  <label for="diagnosis" class="form-label"><i class="fas fa-diagnoses me-2"></i>Diagnostic</label>
                  <input type="text" class="form-control" name="diagnosis" id="diagnosis" value="{{ request.form.get('diagnosis', '') }}">
                </div>
                <div class="mb-3">
                  <label for="doctor_comment" class="form-label"><i class="fas fa-comment-medical me-2"></i>Commentaire</label>
                  <textarea class="form-control" name="doctor_comment" id="doctor_comment" rows="3">{{ request.form.get('doctor_comment', '') }}</textarea>
                </div>
              </div>
            </div>
          </div>

          <!-- Onglet Médicaments -->
          <div class="tab-pane fade" id="medicaments" role="tabpanel">
            <div class="card shadow-lg mb-4">
              <div class="card-body">
                <div class="mb-3">
                  <label for="medication_combobox" class="form-label"><i class="fas fa-prescription-bottle-alt me-2"></i>Médicament</label>
                  <div class="input-group">
                    <input type="text" class="form-control" id="medication_combobox" placeholder="Sélectionnez un médicament" list="medications_options_list">
                    <datalist id="medications_options_list">
                      {% for m in medications_options %}
                      <option value="{{ m }}"></option>
                      {% endfor %}
                    </datalist>
                    <button type="button" class="btn btn-medical" onclick="addMedication()">
                      <i class="fas fa-plus-circle me-2"></i>Ajouter
                    </button>
                  </div>
                  <select id="medications_listbox" name="medications_list" multiple class="form-select mt-2 dynamic-list" size="5">
                    {% if saved_medications %}
                      {% for med in saved_medications %}
                        <option selected value="{{ med }}">{{ loop.index }}. {{ med }}</option>
                      {% endfor %}
                    {% endif %}
                  </select>
                  <button type="button" class="btn btn-danger mt-2" onclick="removeMedication()">
                    <i class="fas fa-trash-alt me-2"></i>Supprimer Sélection
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- Onglet Biologie -->
          <div class="tab-pane fade" id="biologie" role="tabpanel">
            <div class="card shadow-lg mb-4">
              <div class="card-body">
                <div class="mb-3">
                  <label for="analysis_combobox" class="form-label"><i class="fas fa-microscope me-2"></i>Analyse</label>
                  <div class="input-group">
                    <input type="text" class="form-control" id="analysis_combobox" placeholder="Sélectionnez une analyse" list="analyses_options_list">
                    <datalist id="analyses_options_list">
                      {% for a in analyses_options %}
                      <option value="{{ a }}"></option>
                      {% endfor %}
                    </datalist>
                    <button type="button" class="btn btn-medical" onclick="addAnalysis()">
                      <i class="fas fa-plus-circle me-2"></i>Ajouter
                    </button>
                  </div>
                  <select id="analyses_listbox" name="analyses_list" multiple class="form-select mt-2 dynamic-list" size="5">
                    {% if saved_analyses %}
                      {% for a in saved_analyses %}
                        <option selected value="{{ a }}">{{ loop.index }}. {{ a }}</option>
                      {% endfor %}
                    {% endif %}
                  </select>
                  <button type="button" class="btn btn-danger mt-2" onclick="removeAnalysis()">
                    <i class="fas fa-trash-alt me-2"></i>Supprimer Sélection
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- Onglet Radiologies -->
          <div class="tab-pane fade" id="radiologies" role="tabpanel">
            <div class="card shadow-lg mb-4">
              <div class="card-body">
                <div class="mb-3">
                  <label for="radiology_combobox" class="form-label"><i class="fas fa-x-ray me-2"></i>Radiologie</label>
                  <div class="input-group">
                    <input type="text" class="form-control" id="radiology_combobox" placeholder="Sélectionnez une radiologie" list="radiologies_options_list">
                    <datalist id="radiologies_options_list">
                      {% for r in radiologies_options %}
                      <option value="{{ r }}"></option>
                      {% endfor %}
                    </datalist>
                    <button type="button" class="btn btn-medical" onclick="addRadiology()">
                      <i class="fas fa-plus-circle me-2"></i>Ajouter
                    </button>
                  </div>
                  <select id="radiologies_listbox" name="radiologies_list" multiple class="form-select mt-2 dynamic-list" size="5">
                    {% if saved_radiologies %}
                      {% for r in saved_radiologies %}
                        <option selected value="{{ r }}">{{ loop.index }}. {{ r }}</option>
                      {% endfor %}
                    {% endif %}
                  </select>
                  <button type="button" class="btn btn-danger mt-2" onclick="removeRadiology()">
                    <i class="fas fa-trash-alt me-2"></i>Supprimer Sélection
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- Onglet Certificat Médical -->
          <div class="tab-pane fade" id="certificat" role="tabpanel">
            <div class="card shadow-lg mb-4">
              <div class="card-body">
                <div class="mb-3">
                  <label for="certificate_category" class="form-label"><i class="fas fa-tags me-2"></i>Catégorie</label>
                  <select class="form-select" name="certificate_category" id="certificate_category">
                    <option value="">-- Sélectionnez --</option>
                    {% for key in certificate_categories.keys() %}
                    <option value="{{ key }}" {% if request.form.get('certificate_category','') == key %}selected{% endif %}>{{ key }}</option>
                    {% endfor %}
                  </select>
                </div>
                <div class="mb-3">
                  <label for="certificate_content" class="form-label"><i class="fas fa-file-alt me-2"></i>Contenu</label>
                  <textarea class="form-control" name="certificate_content" id="certificate_content" rows="5">{{ request.form.get('certificate_content', default_certificate_text) }}</textarea>
                </div>
                <div class="form-check">
                  <input class="form-check-input" type="checkbox" name="include_certificate" id="include_certificate" {% if request.form.get('include_certificate','')=='on' %}checked{% endif %}>
                  <label class="form-check-label" for="include_certificate">
                    <i class="fas fa-check-circle me-2"></i>Inclure le certificat
                  </label>
                </div>
              </div>
            </div>
          </div>

          <!-- Onglet Suivi Patient -->
          <div class="tab-pane fade" id="suivi" role="tabpanel" aria-labelledby="suivi-tab">
            <div class="card shadow-lg mb-4">
              <div class="card-header bg-gradient-to-r from-[#1a73e8] to-[#0d9488] text-white">
                <h5 class="mb-0 flex items-center">
                  <i class="fas fa-notes-medical me-2"></i>Suivi Patient
                </h5>
              </div>
              <div class="card-body bg-white">
                <div class="mb-4 flex flex-wrap gap-2">
                  <input type="text" id="suivi_patient_id" class="form-control dynamic-list flex-grow" placeholder="ID Patient">
                  <input type="text" id="suivi_patient_name" class="form-control dynamic-list flex-grow" placeholder="Nom Patient">
                </div>
                <div class="table-responsive rounded-lg overflow-auto" style="max-height:400px;">
                  <table id="consultationsTable"
                        class="table table-striped table-hover align-middle mb-0"
                        style="min-width:1200px;">
                    <thead class="table-primary">
                      <tr>
                        <th>Date</th><th>ID Patient</th><th>Nom Patient</th><th>Date Naissance</th>
                        <th>Genre</th><th>Âge</th><th>Téléphone</th><th>Antécédents</th>
                        <th>Signes Cliniques</th><th>TA</th><th>Temp.</th><th>FC</th>
                        <th>FR</th><th>Diagnostic</th><th>Médicaments</th><th>Analyses</th>
                        <th>Radiologies</th><th>Catégorie Certif.</th><th>Contenu Certif.</th>
                        <th>Durée Repos</th><th>Commentaire</th><th>Actions</th>
                      </tr>
                    </thead>
                    <tbody></tbody>
                  </table>
                </div>

                <!-- Carte contenant uniquement Rafraîchir & PDF Historique -->
                <div class="card mt-4">
                  <div class="card-body d-flex justify-content-around">
                    <button type="button" id="refreshBtn" class="btn btn-medical"
                            onclick="$('#consultationsTable').DataTable().ajax.reload();">
                      <i class="fas fa-sync-alt me-2"></i>Rafraîchir
                    </button>
                    <button type="button" class="btn btn-outline-success" onclick="generateHistoryPDF()">
                      <i class="fas fa-file-pdf me-2"></i>PDF Historique
                    </button>
                  </div>
                </div>

              </div>
            </div>
          </div>
        </div>

          <!-- Script à placer juste après votre section JS existante -->
          <script>
            document.getElementById('suiviSaveBtn').addEventListener('click', function() {
              Swal.fire({
                title: 'Vérification des onglets',
                text: "Avez-vous parcouru tous les onglets (Consultation, Médicaments, Biologie, Radiologies, Certificats) ?",
                icon: 'warning',
                showCancelButton: true,
                confirmButtonText: 'Oui, je confirme',
                cancelButtonText: 'Non, vérifier'
              }).then((result) => {
                if (result.isConfirmed) {
                  // Sélectionner tous les items des listes avant envoi
                  document.querySelectorAll("#medications_listbox option").forEach(opt => opt.selected = true);
                  document.querySelectorAll("#analyses_listbox option").forEach(opt => opt.selected = true);
                  document.querySelectorAll("#radiologies_listbox option").forEach(opt => opt.selected = true);
                  // Soumettre le formulaire principal
                  document.getElementById('mainForm').submit();
                }
              });
            });
          </script>

        <div class="d-flex flex-wrap justify-content-around gap-2 mt-4">
  <!-- Bouton Enregistrer intercepté par SweetAlert -->
  <button
    type="button"
    id="submitBtn"
    class="btn btn-medical"
  >
    <i class="fas fa-save me-2"></i>Enregistrer
  </button>

  <!-- Les autres boutons restent inchangés -->
  <button
    type="button"
    class="btn btn-medical"
    onclick="generatePDF()"
  >
    <i class="fas fa-file-pdf me-2"></i>Générer PDF
  </button>
  <button
    type="reset"
    class="btn btn-danger"
  >
    <i class="fas fa-undo me-2"></i>Réinitialiser
  </button>
  <button
    type="button"
    class="btn btn-medical"
    data-bs-toggle="modal"
    data-bs-target="#importExcelModal"
  >
    <i class="fas fa-file-import me-2"></i>Importer Listes
  </button>
  <button
    type="button"
    class="btn btn-medical"
    data-bs-toggle="modal"
    data-bs-target="#importBackgroundModal"
  >
    <i class="fas fa-image me-2"></i>Arrière-plan
  </button>
</div>


<div class="card-footer text-center py-3" style="background: #f8fafc;">
  <!-- Bouton Télécharger centré -->
  <div class="mb-3">
  <!-- Signature -->
  <p class="text-muted small mb-1">
    <i class="fas fa-heartbeat text-danger me-1"></i>
    SASTOUKA DIGITAL © 2025 • sastoukadigital@gmail.com tel +212652084735
  </p>

  <!-- Adresse réseau locale en dernière ligne, sans icône ni flèche -->
  <p class="small mb-0">
   Ouvrir l’application en réseau {{ host_address }}
  </p>
</div>



<!-- Modales originales conservées -->
<div class="modal fade" id="importExcelModal" tabindex="-1">
  <div class="modal-dialog">
    <div class="modal-content">
      <div class="modal-header bg-primary text-white">
        <h5 class="modal-title"><i class="fas fa-file-excel me-2"></i>Importer Excel</h5>
        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body">
        <form id="importExcelForm" onsubmit="return ajaxFileUpload('importExcelForm','/import_excel')">
          <div class="mb-3">
            <label for="excel_file" class="form-label"><i class="fas fa-file-excel me-2"></i>Fichier Excel</label>
            <input type="file" class="form-control" name="excel_file" id="excel_file" required>
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

<div class="modal fade" id="importBackgroundModal" tabindex="-1">
  <div class="modal-dialog">
    <div class="modal-content">
      <div class="modal-header bg-primary text-white">
        <h5 class="modal-title"><i class="fas fa-image me-2"></i>Importer Arrière-plan</h5>
        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body">
        <form id="importBackgroundForm" onsubmit="return ajaxFileUpload('importBackgroundForm','/import_background')">
          <div class="mb-3">
            <label for="background_file" class="form-label"><i class="fas fa-file-image me-2"></i>Fichier</label>
            <input type="file" class="form-control" name="background_file" id="background_file" required>
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
<script>
  document.addEventListener("DOMContentLoaded", function() {
    document.getElementById("submitBtn").addEventListener("click", function(e) {
      e.preventDefault();
      Swal.fire({
        title: 'Vérification des onglets',
        text: "Avez-vous parcouru tous les onglets (Consultation, Médicaments, Biologie, Radiologies, Certificats) ?",
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: 'Oui, je confirme',
        cancelButtonText: 'Non, vérifier'
      }).then((result) => {
        if (result.isConfirmed) {
          // Avant envoi, on sélectionne tous les items des listes
          document.querySelectorAll("#medications_listbox option").forEach(o => o.selected = true);
          document.querySelectorAll("#analyses_listbox option").forEach(o => o.selected = true);
          document.querySelectorAll("#radiologies_listbox option").forEach(o => o.selected = true);
          // Puis on soumet le formulaire
          document.getElementById("mainForm").submit();
        }
      });
    });
  });
</script>
<script>
  document.getElementById('settingsForm').addEventListener('submit', function(e) {
    e.preventDefault();  // on bloque le rechargement

    const form = this;
    const data = new FormData(form);

    fetch(form.action, {
      method: 'POST',
      body: data,
      headers: { 'Accept': 'application/json' }
    })
    .then(resp => {
      if (!resp.ok) throw new Error('Erreur réseau');
      return resp.json();
    })
    .then(json => {
      // 0) Mise à jour immédiate des variables CSS du thème
      if (json.theme_vars) {
        Object.entries(json.theme_vars).forEach(([key, val]) => {
          document.documentElement.style.setProperty(`--${key}`, val);
        });
      }

      // 1) Mise à jour du header en place
      const headerH1 = document.querySelector('.card-header h1.header-item');
      headerH1.innerHTML = `<i class="fas fa-hospital me-2"></i>${json.nom_clinique}`;

      const doctorEl = document.querySelector('.card-header .header-item i.fa-user-md').parentNode;
      doctorEl.innerHTML = `<i class="fas fa-user-md me-2"></i><span>${json.doctor_name}</span>`;

      const locationEl = document.querySelector('.card-header .header-item i.fa-map-marker-alt').parentNode;
      locationEl.innerHTML = `<i class="fas fa-map-marker-alt me-2"></i><span>${json.location}</span>`;

      // 2) Fermeture de l’offcanvas
      const offcanvasEl = document.getElementById('settingsOffcanvas');
      bootstrap.Offcanvas.getInstance(offcanvasEl).hide();
    })
    .catch(err => {
      console.error(err);
      Swal.fire('Erreur', 'Impossible de sauvegarder vos paramètres', 'error');
    });
  });
</script>
<script>
document.addEventListener('DOMContentLoaded', () => {

  /* ---- 0. Ciblage ---- */
  const form       = document.getElementById('mainForm');          // tout le formulaire
  const keep       = ['doctor_name', 'location'];                  // champs à garder
  const listboxes  = ['medications_listbox','analyses_listbox','radiologies_listbox'];

  /* ---- 1. Interception des deux boutons <button type="reset"> ---- */
  document.querySelectorAll('button[type="reset"]').forEach(btn => {
    btn.addEventListener('click', e => {
      e.preventDefault();          // on bloque le reset natif
      customReset();               // puis notre reset complet
    });
  });

  /* ---- 2. Fonction de reset maison ---- */
  function customReset() {
    /* 2-a) Sauver Médecin & Lieu */
    const saved = {};
    keep.forEach(id => { const el=document.getElementById(id); if (el) saved[id]=el.value; });

    /* 2-b) Vider tous les champs du formulaire */
    form.querySelectorAll('input, select, textarea').forEach(el => {
      if (keep.includes(el.id)) return;               // on saute Médecin & Lieu

      if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
        if (['checkbox','radio'].includes(el.type)) el.checked = false;
        else el.value = '';
      } else if (el.tagName === 'SELECT') {
        el.selectedIndex = -1;
        if (el.multiple) el.innerHTML = '';           // vide totalement les <select multiple>
      }
    });

    /* 2-c) Vider les trois listboxes dynamiques */
    listboxes.forEach(id => { const lb=document.getElementById(id); if (lb) lb.innerHTML=''; });

    /* 2-d) Réinitialiser vos compteurs globaux si vous les utilisez */
    window.medicationCount = 1;
    window.analysisCount   = 1;
    window.radiologyCount  = 1;

    /* 2-e) Restaurer Médecin & Lieu */
    Object.entries(saved).forEach(([id,val]) => { document.getElementById(id).value = val; });
  }

});
</script>
</body>
</html>
 """

alert_template = """
<!DOCTYPE html>
<html lang="fr">
{{ pwa_head()|safe }}
<head>
  <meta charset="UTF-8">
  <title>Alerte</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.3/font/bootstrap-icons.css" rel="stylesheet">
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
<style>
:root {
  {% for var, val in theme_vars.items() %}
    --{{ var }}: {{ val }};
  {% endfor %}
}
</style>
<style>
  /* Barres de navigation et Offcanvas */
  .navbar,
  .offcanvas-header {
    background: linear-gradient(45deg, var(--primary-color), var(--secondary-color)) !important;
  }

  /* Fond de l’Offcanvas body */
  .offcanvas-body {
    background: var(--card-bg) !important;
    color: var(--text-color) !important;
  }

  /* Entête des cartes (zone nom clinique, onglets, etc.) */
  .card-header {
    background: var(--primary-color) !important;
    color: var(--button-text) !important;
  }

  /* Zone principale de contenu (cartes, formulaires) */
  .card,
  .form-control,
  .dataTables_wrapper {
    background: var(--card-bg) !important;
    color: var(--text-color) !important;
  }

  /* Pied de page, boutons secondaires */
  .card-footer,
  .footer,
  .btn-secondary {
    background: var(--secondary-color) !important;
    color: var(--button-text) !important;
  }

  /* Liens, textes cliquables */
  a, .nav-link, .btn-link {
    color: var(--primary-color) !important;
  }
  a:hover, .nav-link:hover, .btn-link:hover {
    color: var(--secondary-color) !important;
  }
</style>

</head>
<body>
<script>
  Swal.fire({
    icon: '{{ alert_type }}',
    title: '{{ alert_title }}',
    html: '{{ alert_text }} {% if extra_info %} <br><br> {{ extra_info }} {% endif %}',
    timer: 3000,
    timerProgressBar: true,
    didClose: () => { window.location.href = "{{ redirect_url }}"; }
  });
</script>
</body>
</html>
"""

settings_template = """
<!DOCTYPE html>
<html lang="fr">
{{ pwa_head()|safe }}
<head>
  <meta charset="UTF-8">
  <title>Paramètres de l'application</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.3/font/bootstrap-icons.css" rel="stylesheet">
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    :root {
      {% for var, val in theme_vars.items() %}
        --{{ var }}: {{ val }};
      {% endfor %}
    }
  </style>
  <style>
    /* Vos styles existants… */
  </style>
</head>
<body class="bg-light">
  <div class="container my-5">
    <h2 class="text-center mb-4">Paramètres de l'application</h2>
    {% with msgs = get_flashed_messages(with_categories=true) %}
      {% for cat,msg in msgs %}
        <div class="alert alert-{{ cat }}">{{ msg }}</div>
      {% endfor %}
    {% endwith %}
    <form id="settingsForm" action="{{ url_for('settings') }}" method="POST">
      <div class="mb-3">
        <label for="nom_clinique" class="form-label">Nom Clinique / Cabinet :</label>
        <input type="text" class="form-control" name="nom_clinique" id="nom_clinique"
               value="{{ config.nom_clinique or '' }}">
      </div>
      <div class="mb-3">
        <label for="centre_medecin" class="form-label">Centre Médical :</label>
        <input type="text" class="form-control" name="centre_medecin" id="centre_medecin"
               value="{{ config.centre_medical or '' }}">
      </div>
      <div class="mb-3">
        <label for="nom_medecin" class="form-label">Nom du Médecin :</label>
        <input type="text" class="form-control" name="nom_medecin" id="nom_medecin"
               value="{{ config.doctor_name or '' }}">
      </div>
      <div class="mb-3">
        <label for="lieu" class="form-label">Lieu :</label>
        <input type="text" class="form-control" name="lieu" id="lieu"
               value="{{ config.location or '' }}">
      </div>
      <div class="mb-3">
        <label for="theme" class="form-label">Thème :</label>
        <select class="form-select" name="theme" id="theme">
          {% for t in theme_names %}
            <option value="{{ t }}" {% if config.theme == t %}selected{% endif %}>{{ t.capitalize() }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="mb-3">
        <label for="arriere_plan" class="form-label">Arrière-plan :</label>
        <input type="text" class="form-control" name="arriere_plan" id="arriere_plan"
               value="{{ config.background_file_path or '' }}">
      </div>
      <div class="mb-3">
        <label for="liste_medicaments" class="form-label">Liste des Médicaments :</label>
        <textarea class="form-control" name="liste_medicaments" id="liste_medicaments" rows="4">{% if config.medications_options %}{{ config.medications_options|join('\\n') }}{% endif %}</textarea>
      </div>
      <div class="mb-3">
        <label for="liste_analyses" class="form-label">Liste des Analyses :</label>
        <textarea class="form-control" name="liste_analyses" id="liste_analyses" rows="4">{% if config.analyses_options %}{{ config.analyses_options|join('\\n') }}{% endif %}</textarea>
      </div>
      <div class="mb-3">
        <label for="liste_radiologies" class="form-label">Liste des Radiologies :</label>
        <textarea class="form-control" name="liste_radiologies" id="liste_radiologies" rows="4">{% if config.radiologies_options %}{{ config.radiologies_options|join('\\n') }}{% endif %}</textarea>
      </div>
      <button type="submit" class="btn btn-success w-100">Enregistrer Paramètres</button>
    </form>
  </div>

  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
  <script>
    document.addEventListener('DOMContentLoaded', () => {
      const form = document.getElementById('settingsForm');
      form.addEventListener('submit', e => {
        e.preventDefault();
        fetch(form.action, {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json'
          },
          body: new FormData(form)
        })
        .then(res => res.json())
        .then(data => {
          Swal.fire({ icon:'success', title:'Paramètres enregistrés', timer:800, showConfirmButton:false });
          // Fermer Offcanvas si besoin (ID settingsOffcanvas)
          const offcanvas = document.getElementById('settingsOffcanvas');
          if (offcanvas) bootstrap.Offcanvas.getInstance(offcanvas).hide();
          setTimeout(() => window.location.reload(), 3000);
        })
        .catch(() => {
          Swal.fire({ icon:'error', title:'Erreur', text:'Échec de la sauvegarde.' });
        });
      });
    });
  </script>
    <!-- sweetalert2 (si pas déjà inclus) -->
  <script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
  <script>
    document.getElementById("settingsForm").addEventListener("submit", function(e) {
      e.preventDefault();
      const form = this;
      const data = new FormData(form);
      // Envoi en AJAX pour récupérer la réponse JSON sans recharger tout de suite
      fetch(form.action, {
        method: 'POST',
        headers: { 'Accept': 'application/json' },
        body: data
      })
      .then(res => res.json())
      .then(json => {
        Swal.fire({
          title: 'Paramètres enregistrés',
          text:  'Voulez-vous recharger pour appliquer les changements ?',
          icon:  'success',
          showCancelButton: true,
          confirmButtonText: 'Recharger',
          cancelButtonText:  'Plus tard'
        }).then(result => {
          if (result.isConfirmed) {
            window.location.reload();
          }
        });
      })
      .catch(() => {
        Swal.fire('Erreur','Impossible d’enregistrer les paramètres.','error');
      });
    });
  </script>
</body>
</html>
"""
