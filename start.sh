#!/bin/bash
# Script de démarrage PEL - Plateforme d'Évaluation en Ligne

echo "=== Démarrage de la plateforme PEL ==="

# Backend
echo "Démarrage du serveur Django..."
cd backend
source ../venv/bin/activate
python manage.py runserver &
DJANGO_PID=$!

# Worker de la file d'exécution (code des étudiants dans des conteneurs Docker).
# Avec SQLite, un seul worker évite les verrous de la base ; PEL_WORKERS_EXECUTION le change.
echo "Démarrage du worker d'exécution..."
python manage.py executer_file --workers "${PEL_WORKERS_EXECUTION:-1}" &
WORKER_PID=$!
cd ..

# Frontend
echo "Démarrage du serveur React..."
cd frontend
npm run dev &
VITE_PID=$!
cd ..

echo ""
echo "=== Serveurs démarrés ==="
echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:5173"
echo "Admin:    http://localhost:8000/admin/"
echo ""
echo "Identifiants admin: admin / admin123"
echo ""
echo "Appuyez sur Ctrl+C pour arrêter"

# Ctrl+C : les trois processus sont arrêtés ensemble.
arreter() {
    trap - INT TERM EXIT
    kill $DJANGO_PID $WORKER_PID $VITE_PID 2>/dev/null
    wait 2>/dev/null
}
trap arreter INT TERM EXIT
wait $DJANGO_PID $WORKER_PID $VITE_PID
