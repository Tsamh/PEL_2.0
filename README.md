# PEL - Plateforme d'Évaluation en Ligne

Plateforme d'évaluation en ligne multi-établissements combinant quiz (QCM, vrai/faux, réponses courtes) et devoirs de programmation avec IDE intégré.

## Technologies

- **Backend:** Django 6 + Django REST Framework
- **Frontend:** React 19 + Vite
- **Base de données:** SQLite (dev) / PostgreSQL (prod)
- **Auth:** JWT (SimpleJWT)
- **Email:** SMTP (Gmail ou autre)

## Installation

### Prérequis
- Python 3.10+
- Node.js 18+
- npm

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
```

## URLs

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| API Backend | http://localhost:8000/api/ |
| Admin Django | http://localhost:8000/admin/ |

## Rôles utilisateurs

| Rôle | Description |
|------|-------------|
| `superadmin` | Admin plateforme PEL (crée les établissements) |
| `admin` | Admin d'un établissement (gère étudiants, filières) |
| `responsable_formation` | Responsable pédagogique |
| `enseignant` | Création de quiz/devoirs |
| `etudiant` | Passation des évaluations |

## Flux d'inscription étudiant

1. **Admin école** crée un étudiant (manuellement ou import CSV/Excel)
2. **Email envoyé** avec lien d'activation (valable 7 jours)
3. **Étudiant** clique sur le lien, crée son mot de passe
4. **Connexion** avec email + mot de passe créé

### Import CSV/Excel

Format du fichier :
```csv
email,nom,prenom
jean.dupont@email.com,Dupont,Jean
marie.martin@email.com,Martin,Marie
```

## Modules

### Référentiel académique
- Établissements
- Années académiques, filières, niveaux
- Unités d'enseignement (UE), Enseignements composable (EC)
- Classes, groupes (TD/TP)
- Inscriptions, affectations enseignants

### Sécurité
- Mot de passe fort (8+ car., majuscule, chiffre, spécial)
- Tokens à usage unique avec expiration
- Rate limiting sur login
- CORS restreint
- Variables d'environnement pour les secrets

## API Endpoints

### Authentification
- `POST /api/accounts/login/` - Connexion (JWT)
- `POST /api/accounts/token/refresh/` - Rafraîchir le token

### Utilisateurs
- `GET /api/accounts/users/me/` - Profil courant
- `POST /api/accounts/users/invite_student/` - Inviter un étudiant
- `POST /api/accounts/users/import_students/` - Import CSV/Excel
- `POST /api/accounts/users/activate/` - Activer un compte
- `POST /api/accounts/users/forgot_password/` - Mot de passe oublié
- `POST /api/accounts/users/reset_password/` - Réinitialiser le mot de passe
- `POST /api/accounts/users/change_password/` - Changer le mot de passe

### Référentiel
- `/api/referentiel/etablissements/`
- `/api/referentiel/annees-academiques/`
- `/api/referentiel/filieres/`
- `/api/referentiel/niveaux/`
- `/api/referentiel/ues/`
- `/api/referentiel/ecs/`
- `/api/referentiel/classes/`
- `/api/referentiel/groupes/`
- `/api/referentiel/inscriptions/`
