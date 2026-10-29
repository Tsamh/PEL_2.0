# PEL - Plateforme d'Évaluation en Ligne

Plateforme d'évaluation en ligne multi-établissements combinant quiz (QCM, vrai/faux, réponses courtes) et devoirs de programmation avec IDE intégré (Monaco Editor).

## Technologies

- **Backend:** Django 6 + Django REST Framework + SimpleJWT
- **Frontend:** React 19 + Vite
- **Base de données:** SQLite (dev) / PostgreSQL (prod)
- **Editeur de code:** Monaco Editor (dark theme)
- **Auth:** JWT (SimpleJWT)
- **Email:** SMTP (fallback console en dev)

## Installation

### Prérequis
- Python 3.10+
- Node.js 18+
- npm
- Docker (moteur démarré, utilisable par l'utilisateur qui lance le worker) pour exécuter le code des étudiants

Images d'exécution à télécharger une fois (le worker ne les télécharge jamais lui-même) :

```bash
docker pull python:3.12-alpine
docker pull node:20-alpine
docker pull gcc:13
docker pull eclipse-temurin:21-jdk
```

### Setup

```bash
cd PEL

# Environnement Python
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt

# Configuration
cp backend/.env.example backend/.env
# Éditer backend/.env avec vos paramètres SMTP

# Backend
cd backend
python manage.py migrate
python manage.py createsuperuserpel --username admin --email admin@pel.com --password admin123 --nom "Admin" --prenom "Super"
cd ..

# Frontend
cd frontend
npm install
```

### Démarrage

```bash
./start.sh
```

Ou manuellement :

```bash
# Terminal 1 - Backend
cd backend && source ../venv/bin/activate && python manage.py runserver

# Terminal 2 - Frontend
cd frontend && npm run dev

# Terminal 3 - Worker d'exécution (file des essais et des corrections)
cd backend && source ../venv/bin/activate && python manage.py executer_file --workers 1
```

`executer_file --une-fois` traite la file puis s'arrête (cron, tests). Avec SQLite, garder `--workers 1`.

### Réglages de l'exécution (`backend/.env`)

| Variable | Défaut | Rôle |
|---|---|---|
| `PEL_EXECUTEUR` | `docker` | `docker` en usage réel ; `factice` seulement pour les tests (aucun code exécuté). |
| `PEL_IMAGE_PYTHON`, `PEL_IMAGE_JAVASCRIPT`, `PEL_IMAGE_C`, `PEL_IMAGE_CPP`, `PEL_IMAGE_JAVA` | voir les `docker pull` ci-dessus | Images Docker par langage (réglage `PEL_IMAGES_EXECUTION`). |
| `PEL_WORKERS_EXECUTION` | `2` (`1` dans `start.sh`) | Nombre de fils du worker. |

Sans Docker, les essais et les corrections passent en erreur avec le message « Le service d'exécution est indisponible. » ; aucun code n'est exécuté sans isolation. La limite de 20 exécutions par minute utilise le cache Django : avec plusieurs processus web, configurer un cache partagé (Redis ou Memcached).

## URLs

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| API Backend | http://localhost:8000/api/ |
| Admin Django | http://localhost:8000/admin/ |

## Rôles utilisateurs

| Rôle | Description |
|------|-------------|
| `superadmin` | Admin plateforme PEL (crée les établissements, valide les admins) |
| `admin` | Admin d'un établissement (gère étudiants, enseignants, filières, quiz, devoirs) |
| `responsable_formation` | Responsable pédagogique |
| `enseignant` | Crée et corrige les quiz et devoirs de programmation, gère les notes |
| `etudiant` | Passe les évaluations, soumet des codes, consulte ses notes |

## Architecture

```
PEL/
├── backend/
│   ├── accounts/          # Utilisateurs, auth, invitations
│   ├── referentiel/       # Filieres, niveaux, UE, EC, classes, affectations
│   ├── quiz/              # Quiz, questions, choix, résultats
│   ├── programming/       # Devoirs, soumissions, exécution de code, notes par matière
│   ├── reporting/         # Statistiques
│   └── config/            # Settings Django, URLs
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── admin/     # Gestion admin (étudiants, enseignants, quiz, devoirs)
│       │   ├── teacher/   # Enseignant (mes cours, mes quiz, mes devoirs, corrections, gestion notes, stats)
│       │   └── student/   # Étudiant (quiz disponibles, mes devoirs, mes notes, mes résultats)
│       ├── components/    # CodeEditor, CountdownTimer, Layout
│       ├── context/       # AuthContext
│       └── services/      # API axios
└── start.sh
```

## Flux d'inscription

### Admin (superadmin → admin)
1. **Superadmin** crée un établissement → un admin est invité par email
2. **Admin** clique sur le lien d'activation → crée son mot de passe
3. **Superadmin** valide l'admin → il peut se connecter

### Étudiant (admin → étudiant)
1. **Admin** invite un étudiant (avec ou sans mot de passe)
   - **Avec mot de passe** → l'étudiant se connecte directement (doit changer son mdp à la 1ère connexion)
   - **Sans mot de passe** → email avec lien d'activation
2. L'étudiant accède à la plateforme

### Enseignant (admin → enseignant)
1. **Admin** invite un enseignant avec mot de passe et lui assigne des classes
2. L'enseignant se connecte et accède à ses cours

## Modules

### Référentiel académique
- Établissements
- Années académiques avec création de filières en lot
- Filières, niveaux (L1-D3 seedés)
- Unités d'enseignement (UE), Enseignements composable (EC)
- Classes, groupes (TD/TP)
- Inscriptions étudiants
- Affectations enseignants → classes
- **Filtrage par rôle** : l'enseignant ne voit que ses filières, niveaux, classes et matières assignées

### Quiz
- QCM, vrai/faux, réponses courtes
- **Création avec questions intégrées** (admin et enseignant)
- Filtrage par filière, niveau, année académique
- Quiz publiés / brouillons
- Timer de passation
- Questions avec choix multiples

### Devoirs de programmation
- Langages : Python, Java, C, C++, JavaScript
- **Langage imposé** : l'enseignant choisit le langage, l'étudiant ne peut pas le changer
- **Monaco Editor** intégré (dark theme, syntax highlighting)
- **Exécution isolée** dans des conteneurs Docker jetables (sans réseau, mémoire, processus et temps limités) pour Python, JavaScript, C, C++ et Java
- **Limites par exercice** : temps par test (2 000 ms par défaut) et mémoire (256 Mo par défaut)
- **Cas de test** publics ou cachés, pondérés, comparaison tolérante (espaces de fin de ligne, lignes vides finales)
- **Politique de résultats** : après validation par l'enseignant (défaut) ou immédiate
- Code initial fourni aux étudiants (lecture seule)
- Solution de référence (cachée aux étudiants)
- Timer avec soumission automatique
- Date limite de soumission
- **Matière (EC) associée** au devoir

### Exécution de code
- Demandes mises en file et traitées par le worker `executer_file` ; la page interroge le résultat chaque seconde
- « Exécuter » lance le code avec l'entrée saisie ; « Tester » le lance sur les tests publics
- Statut par test : Accepté, Erreur de compilation, Erreur d'exécution, Mauvaise réponse, Temps dépassé, Mémoire dépassée, Erreur du service
- L'étudiant ne reçoit jamais l'entrée ni la sortie attendue d'un test caché ; une exécution à la fois, 20 par minute

### Corrections
- Vue des soumissions par devoir
- Code soumis affiché dans Monaco Editor (read-only)
- **Correction automatique** à la soumission : note proposée = somme des (poids des tests cachés réussis / poids des tests cachés) × points
- **Validation** par l'enseignant : note proposée arrondie ou note ajustée, avec remarques
- **Relance** des corrections en erreur (ou de toutes)
- Statistiques : total, validées, à valider, correction en cours

### Notes par matière
- **Devoir (manuelle)** : note saisie par le prof via Gestion des notes
- **Devoir (prog)** : score calculé automatiquement depuis les soumissions de programmation
  - Formule : `(score / points_max) × 20`, moyenne sur tous les devoirs de la matière
- **Examen** : note saisie manuellement par le prof
- **Moyenne** = `max(devoir_manuelle, devoir_prog) × 0.4 + examen × 0.6`
- L'étudiant voit les deux notes de devoir et la moyenne calculée
- Le prof voit la note de prog auto-calculée à côté de sa saisie manuelle

### Sécurité
- Mot de passe fort (8+ car., majuscule, chiffre, spécial)
- Tokens à usage unique avec expiration (7 jours)
- Rate limiting sur login
- CORS restreint
- Variables d'environnement pour les secrets
- Changement de mot de passe forcé à la première connexion
- Les étudiants ne voient pas la solution, les cas de test, ni les détails d'erreur

## API Endpoints

### Authentification
- `POST /api/accounts/login/` - Connexion (JWT) — champ `login` (email ou username)
- `POST /api/accounts/token/refresh/` - Rafraîchir le token

### Utilisateurs
- `GET /api/accounts/users/me/` - Profil courant
- `GET /api/accounts/users/dashboard_stats/` - Statistiques par rôle
- `POST /api/accounts/users/register_admin/` - Inscription admin
- `GET /api/accounts/users/pending_validations/` - Admins en attente
- `POST /api/accounts/users/{id}/validate_admin/` - Valider/rejeter un admin
- `POST /api/accounts/users/invite_student/` - Inviter un étudiant (avec/sans mot de passe)
- `POST /api/accounts/users/invite_enseignant/` - Inviter un enseignant (avec classes)
- `POST /api/accounts/users/import_students/` - Import CSV/Excel
- `POST /api/accounts/users/activate/` - Activer un compte
- `POST /api/accounts/users/forgot_password/` - Mot de passe oublié
- `POST /api/accounts/users/reset_password/` - Réinitialiser le mot de passe
- `POST /api/accounts/users/change_password/` - Changer le mot de passe
- `POST /api/accounts/users/force_change_password/` - Changement forcé (1ère connexion)

### Référentiel
- `/api/referentiel/etablissements/`
- `/api/referentiel/annees-academiques/` (+ `create_with_filieres/`)
- `/api/referentiel/filieres/` — filtré par établissement (admin) ou affectations (enseignant)
- `/api/referentiel/niveaux/` — filtré par classes assignées (enseignant)
- `/api/referentiel/ues/`
- `/api/referentiel/ecs/` — filtré par `?classe=` et affectations (enseignant)
- `/api/referentiel/cours/`
- `/api/referentiel/classes/` — filtré par affectations (enseignant)
- `/api/referentiel/groupes/`
- `/api/referentiel/inscriptions/`
- `/api/referentiel/affectations-enseignants/`

### Quiz
- `/api/quiz/quizzes/` - CRUD quiz avec questions imbriquées (enseignant : ses quiz, admin : son établissement)
- `/api/quiz/questions/` - CRUD questions
- `/api/quiz/choix/` - CRUD choix

### Programmation
- `/api/programming/devoirs/` - CRUD devoirs (enseignant : ses devoirs, admin : son établissement)
- `POST /api/programming/devoirs/{id}/executer/` - Essai asynchrone `{exercice, fichiers, mode: run|test, entree}` (202)
- `GET /api/programming/executions/{id}/` - Statut et résultats d'une exécution
- `/api/programming/soumissions/` - Soumissions étudiants (correction automatique mise en file)
- `POST /api/programming/soumissions/{id}/corriger/` - Valider la note (score facultatif : note proposée arrondie) et les remarques
- `POST /api/programming/soumissions/{id}/recorriger/` - Relancer les corrections en erreur (`{tout: true}` : toutes)

### Notes
- `/api/programming/notes/` - CRUD notes par matière
- `POST /api/programming/notes/bulk_update/` - Mise à jour en masse des notes
- `GET /api/programming/notes/mes_notes/` - Notes de l'étudiant (avec note de prog calculée)

## Import CSV/Excel

Format du fichier :
```csv
email,nom,prenom
jean.dupont@email.com,Dupont,Jean
marie.martin@email.com,Martin,Marie
```
