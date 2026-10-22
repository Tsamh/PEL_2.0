import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export const ADMINS = ['superadmin', 'admin'];
export const GESTION = ['superadmin', 'admin', 'responsable_formation'];

export default function RoleRoute({ roles, children }) {
  const { user } = useAuth();
  if (!user || !roles.includes(user.role)) {
    return <Navigate to="/" replace />;
  }
  return children;
}
