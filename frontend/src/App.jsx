import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import Login from './pages/Login';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import ActivateAccount from './pages/ActivateAccount';
import RegisterAdmin from './pages/RegisterAdmin';
import RegisterSuccess from './pages/RegisterSuccess';
import Dashboard from './pages/Dashboard';
import AnneesAcademiques from './pages/AnneesAcademiques';
import Filieres from './pages/Filieres';
import Niveaux from './pages/Niveaux';
import UEList from './pages/UEList';
import Classes from './pages/Classes';
import StudentManagement from './pages/admin/StudentManagement';
import Enseignants from './pages/admin/Enseignants';
import Etablissements from './pages/admin/Etablissements';
import Validations from './pages/admin/Validations';
import QuizManagement from './pages/admin/QuizManagement';
import DevoirManagement from './pages/admin/DevoirManagement';
import DevoirDetail from './pages/student/DevoirDetail';
import Corrections from './pages/teacher/Corrections';
import ForceChangePassword from './pages/ForceChangePassword';
import MesCours from './pages/teacher/MesCours';
import MesQuiz from './pages/teacher/MesQuiz';
import MesDevoirsRouter from './pages/MesDevoirsRouter';
import Statistiques from './pages/teacher/Statistiques';
import GestionNotes from './pages/teacher/GestionNotes';
import QuizDisponibles from './pages/student/QuizDisponibles';
import MesResultats from './pages/student/MesResultats';
import MesNotes from './pages/student/MesNotes';
import Layout from './components/Layout';
import './App.css';

function PrivateRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="loading">Chargement</div>;
  return user ? children : <Navigate to="/login" />;
}

function PublicRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="loading">Chargement</div>;
  return user ? <Navigate to="/" /> : children;
}

function App() {
  return (
    <AuthProvider>
      <Router>
        <Routes>
          <Route path="/login" element={<PublicRoute><Login /></PublicRoute>} />
          <Route path="/forgot-password" element={<PublicRoute><ForgotPassword /></PublicRoute>} />
          <Route path="/reset-password/:token" element={<PublicRoute><ResetPassword /></PublicRoute>} />
          <Route path="/activate/:token" element={<PublicRoute><ActivateAccount /></PublicRoute>} />
          <Route path="/register" element={<PublicRoute><RegisterAdmin /></PublicRoute>} />
          <Route path="/register-success" element={<PublicRoute><RegisterSuccess /></PublicRoute>} />
          <Route path="/" element={<PrivateRoute><Layout /></PrivateRoute>}>
            <Route index element={<Dashboard />} />
            <Route path="annees-academiques" element={<AnneesAcademiques />} />
            <Route path="filieres" element={<Filieres />} />
            <Route path="niveaux" element={<Niveaux />} />
            <Route path="ues" element={<UEList />} />
            <Route path="classes" element={<Classes />} />
            <Route path="etudiants" element={<StudentManagement />} />
            <Route path="enseignants" element={<Enseignants />} />
            <Route path="etablissements" element={<Etablissements />} />
            <Route path="validations" element={<Validations />} />
            <Route path="quiz" element={<QuizManagement />} />
            <Route path="devoirs" element={<DevoirManagement />} />
            <Route path="devoirs/:id" element={<DevoirDetail />} />
            <Route path="devoirs/:id/corrections" element={<Corrections />} />
            <Route path="mes-cours" element={<MesCours />} />
            <Route path="mes-quiz" element={<MesQuiz />} />
            <Route path="mes-devoirs" element={<MesDevoirsRouter />} />
            <Route path="gestion-notes" element={<GestionNotes />} />
            <Route path="statistiques" element={<Statistiques />} />
            <Route path="quiz-disponibles" element={<QuizDisponibles />} />
            <Route path="mes-notes" element={<MesNotes />} />
            <Route path="mes-resultats" element={<MesResultats />} />
          </Route>
          <Route path="/changer-mot-de-passe" element={<PrivateRoute><ForceChangePassword /></PrivateRoute>} />
        </Routes>
      </Router>
    </AuthProvider>
  );
}

export default App;
