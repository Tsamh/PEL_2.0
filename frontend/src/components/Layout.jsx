import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const adminMenu = [
  { section: 'Administration' },
  { path: '/', label: 'Tableau de bord' },
  { path: '/etablissements', label: 'Établissements', roles: ['superadmin'] },
  { path: '/validations', label: 'Validations', roles: ['superadmin'] },
  { path: '/journal', label: "Journal d'audit", roles: ['superadmin', 'admin'] },
  { section: 'Référentiel' },
  { path: '/annees-academiques', label: 'Années académiques' },
  { path: '/calendrier', label: 'Calendrier' },
  { path: '/filieres', label: 'Filières' },
  { path: '/niveaux', label: 'Niveaux' },
  { path: '/ues', label: 'Unités d\'enseignement' },
  { path: '/classes', label: 'Classes' },
  { path: '/groupes', label: 'Groupes TD/TP' },
  { section: 'Gestion' },
  { path: '/etudiants', label: 'Étudiants' },
  { path: '/responsables', label: 'Responsables', roles: ['superadmin', 'admin'] },
  { path: '/enseignants', label: 'Enseignants' },
  { path: '/quiz', label: 'Quiz' },
  { path: '/validation-quiz', label: 'Validation des quiz' },
  { path: '/banque', label: 'Banque de questions' },
  { path: '/statistiques', label: 'Statistiques des quiz' },
  { path: '/planning', label: 'Planning des évaluations' },
  { path: '/suivi', label: 'Suivi global' },
  { path: '/devoirs', label: 'Devoirs de programmation' },
];

const teacherMenu = [
  { section: 'Enseignement' },
  { path: '/', label: 'Tableau de bord' },
  { path: '/mes-cours', label: 'Mes cours' },
  { path: '/mes-quiz', label: 'Mes quiz' },
  { path: '/banque', label: 'Banque de questions' },
  { path: '/planning', label: 'Planning' },
  { path: '/mes-devoirs', label: 'Mes devoirs' },
  { section: 'Notes' },
  { path: '/gestion-notes', label: 'Gestion des notes' },
  { section: 'Résultats' },
  { path: '/statistiques', label: 'Statistiques' },
  { path: '/suivi', label: 'Suivi global' },
];

const studentMenu = [
  { section: 'Menu' },
  { path: '/', label: 'Tableau de bord' },
  { section: 'Évaluations' },
  { path: '/quiz-disponibles', label: 'Quiz disponibles' },
  { path: '/mes-devoirs', label: 'Mes devoirs' },
  { section: 'Résultats' },
  { path: '/mes-notes', label: 'Mes notes' },
  { path: '/mes-resultats', label: 'Mes résultats' },
];

function getMenuItems(role) {
  switch (role) {
    case 'superadmin':
    case 'admin':
    case 'responsable_formation':
      return adminMenu;
    case 'enseignant':
      return teacherMenu;
    case 'etudiant':
      return studentMenu;
    default:
      return [{ section: 'Menu' }, { path: '/', label: 'Tableau de bord' }];
  }
}

function getRoleLabel(role) {
  const labels = {
    superadmin: 'Super Administrateur',
    admin: 'Administrateur',
    responsable_formation: 'Resp. Formation',
    enseignant: 'Enseignant',
    etudiant: 'Étudiant',
  };
  return labels[role] || role;
}

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const menuItems = getMenuItems(user?.role);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="brand">
            <div className="brand-icon">PEL</div>
            <span className="brand-name">PEL</span>
          </div>
          <p>Plateforme d'Évaluation</p>
        </div>
        <nav>
          {menuItems.map((item, index) =>
            item.section ? (
              <div key={index} className="nav-section">{item.section}</div>
            ) : (
              (!item.roles || item.roles.includes(user?.role)) && (
                <NavLink key={item.path} to={item.path} end={item.path === '/'}>
                  {item.label}
                </NavLink>
              )
            )
          )}
        </nav>
        <div className="sidebar-footer">
          <div className="user-info">
            <div className="user-avatar">
              {user?.first_name?.[0]}{user?.last_name?.[0]}
            </div>
            <div className="user-details">
              <span>{user?.first_name} {user?.last_name}</span>
              <small>{getRoleLabel(user?.role)}</small>
            </div>
          </div>
          <button className="btn-logout" onClick={handleLogout}>Déconnexion</button>
        </div>
      </aside>
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}
