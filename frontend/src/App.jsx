import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import Login from './pages/Login';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import ActivateAccount from './pages/ActivateAccount';
import RegisterAdmin from './pages/RegisterAdmin';
import RegisterSuccess from './pages/RegisterSuccess';
import Dashboard from './pages/Dashboard';
import AnneesAcademiques from './pages/AnneesAcademiques';
import Calendrier from './pages/Calendrier';
import Filieres from './pages/Filieres';
import Niveaux from './pages/Niveaux';
import UEList from './pages/UEList';
import Classes from './pages/Classes';
import Groupes from './pages/Groupes';
import StudentManagement from './pages/admin/StudentManagement';
import Enseignants from './pages/admin/Enseignants';
import Etablissements from './pages/admin/Etablissements';
import Validations from './pages/admin/Validations';
import QuizManagement from './pages/admin/QuizManagement';
import ValidationQuiz from './pages/admin/ValidationQuiz';
import DevoirManagement from './pages/admin/DevoirManagement';
import DevoirDetail from './pages/student/DevoirDetail';
import Corrections from './pages/teacher/Corrections';
import ForceChangePassword from './pages/ForceChangePassword';
import MesCours from './pages/teacher/MesCours';
import MesQuiz from './pages/teacher/MesQuiz';
import BanqueQuestions from './pages/teacher/BanqueQuestions';
import TentativesQuiz from './pages/teacher/TentativesQuiz';
import TableauBordQuiz from './pages/teacher/TableauBordQuiz';
import FicheEtudiant from './pages/teacher/FicheEtudiant';
import MesDevoirsRouter from './pages/MesDevoirsRouter';
import Statistiques from './pages/teacher/Statistiques';
import GestionNotes from './pages/teacher/GestionNotes';
import QuizDisponibles from './pages/student/QuizDisponibles';
import FicheQuiz from './pages/student/FicheQuiz';
import PasserQuiz from './pages/student/PasserQuiz';
import MesResultats from './pages/student/MesResultats';
import MesNotes from './pages/student/MesNotes';
import Layout from './components/Layout';
import Planning from './pages/teacher/Planning';
import SuiviGlobal from './pages/teacher/SuiviGlobal';
import RoleRoute, { ADMINS, GESTION } from './components/RoleRoute';
import Responsables from './pages/admin/Responsables';
import JournalAudit from './pages/admin/JournalAudit';
import './App.css';

function PrivateRoute({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <div className="loading">Chargement</div>;
  return user ? children : <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />;
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
            <Route path="annees-academiques" element={<RoleRoute roles={GESTION}><AnneesAcademiques /></RoleRoute>} />
            <Route path="calendrier" element={<RoleRoute roles={GESTION}><Calendrier /></RoleRoute>} />
            <Route path="filieres" element={<RoleRoute roles={GESTION}><Filieres /></RoleRoute>} />
            <Route path="niveaux" element={<RoleRoute roles={GESTION}><Niveaux /></RoleRoute>} />
            <Route path="ues" element={<RoleRoute roles={GESTION}><UEList /></RoleRoute>} />
            <Route path="classes" element={<RoleRoute roles={GESTION}><Classes /></RoleRoute>} />
            <Route path="groupes" element={<RoleRoute roles={GESTION}><Groupes /></RoleRoute>} />
            <Route path="etudiants" element={<RoleRoute roles={GESTION}><StudentManagement /></RoleRoute>} />
            <Route path="enseignants" element={<RoleRoute roles={GESTION}><Enseignants /></RoleRoute>} />
            <Route path="responsables" element={<RoleRoute roles={ADMINS}><Responsables /></RoleRoute>} />
            <Route path="journal" element={<RoleRoute roles={ADMINS}><JournalAudit /></RoleRoute>} />
            <Route path="etablissements" element={<RoleRoute roles={['superadmin']}><Etablissements /></RoleRoute>} />
            <Route path="validations" element={<RoleRoute roles={['superadmin']}><Validations /></RoleRoute>} />
            <Route path="quiz" element={<RoleRoute roles={GESTION}><QuizManagement /></RoleRoute>} />
            <Route path="validation-quiz" element={<RoleRoute roles={GESTION}><ValidationQuiz /></RoleRoute>} />
            <Route path="quiz/:id/tentatives" element={<RoleRoute roles={[...GESTION, 'enseignant']}><TentativesQuiz /></RoleRoute>} />
            <Route path="quiz/:id/statistiques" element={<RoleRoute roles={[...GESTION, 'enseignant']}><TableauBordQuiz /></RoleRoute>} />
            <Route path="etudiants/:id/resultats" element={<RoleRoute roles={[...GESTION, 'enseignant']}><FicheEtudiant /></RoleRoute>} />
            <Route path="devoirs" element={<RoleRoute roles={GESTION}><DevoirManagement /></RoleRoute>} />
            <Route path="devoirs/:id" element={<RoleRoute roles={[...GESTION, 'enseignant', 'etudiant']}><DevoirDetail /></RoleRoute>} />
            <Route path="devoirs/:id/corrections" element={<RoleRoute roles={[...GESTION, 'enseignant']}><Corrections /></RoleRoute>} />
            <Route path="mes-cours" element={<RoleRoute roles={['enseignant']}><MesCours /></RoleRoute>} />
            <Route path="mes-quiz" element={<RoleRoute roles={['enseignant']}><MesQuiz /></RoleRoute>} />
            <Route path="banque" element={<RoleRoute roles={[...GESTION, 'enseignant']}><BanqueQuestions /></RoleRoute>} />
            <Route path="mes-devoirs" element={<RoleRoute roles={['enseignant', 'etudiant']}><MesDevoirsRouter /></RoleRoute>} />
            <Route path="gestion-notes" element={<RoleRoute roles={['enseignant']}><GestionNotes /></RoleRoute>} />
            <Route path="statistiques" element={<RoleRoute roles={[...GESTION, 'enseignant']}><Statistiques /></RoleRoute>} />
            <Route path="planning" element={<RoleRoute roles={[...GESTION, 'enseignant']}><Planning /></RoleRoute>} />
            <Route path="suivi" element={<RoleRoute roles={[...GESTION, 'enseignant']}><SuiviGlobal /></RoleRoute>} />
            <Route path="quiz-disponibles" element={<RoleRoute roles={['etudiant']}><QuizDisponibles /></RoleRoute>} />
            <Route path="quiz-disponibles/quiz/:id" element={<RoleRoute roles={['etudiant']}><FicheQuiz /></RoleRoute>} />
            <Route path="quiz-disponibles/tentatives/:id" element={<RoleRoute roles={['etudiant']}><PasserQuiz /></RoleRoute>} />
            <Route path="mes-notes" element={<RoleRoute roles={['etudiant']}><MesNotes /></RoleRoute>} />
            <Route path="mes-resultats" element={<RoleRoute roles={['etudiant']}><MesResultats /></RoleRoute>} />
          </Route>
          <Route path="/changer-mot-de-passe" element={<PrivateRoute><ForceChangePassword /></PrivateRoute>} />
        </Routes>
      </Router>
    </AuthProvider>
  );
}

export default App;
