#!/bin/bash
# Script de démarrage PEL - Plateforme d'Évaluation en Ligne

echo "=== Démarrage de la plateforme PEL ==="

# Backend
echo "Démarrage du serveur Django..."
cd backend
source ../venv/bin/activate
python manage.py runserver &
DJANGO_PID=$!
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
wait $DJANGO_PID $VITE_PID
