import { useAuth } from '../context/AuthContext';
import MesDevoirsEnseignant from '../pages/teacher/MesDevoirs';
import MesDevoirsEtudiant from '../pages/student/MesDevoirs';

export default function MesDevoirsRouter() {
  const { user } = useAuth();
  if (user?.role === 'enseignant') return <MesDevoirsEnseignant />;
  return <MesDevoirsEtudiant />;
}
