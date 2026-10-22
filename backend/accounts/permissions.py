from rest_framework.permissions import BasePermission, SAFE_METHODS

SUPERADMIN = 'superadmin'
ADMIN = 'admin'
RESPONSABLE = 'responsable_formation'
ENSEIGNANT = 'enseignant'
ETUDIANT = 'etudiant'

GESTION = (SUPERADMIN, ADMIN, RESPONSABLE)
CREATEURS = GESTION + (ENSEIGNANT,)
TOUS_LES_ROLES = CREATEURS + (ETUDIANT,)

MESSAGE_REFUS = "Vous n'avez pas les droits nécessaires pour cette action."


def has_role(user, *roles):
    return bool(user and user.is_authenticated and user.role in roles)


class _RolePermissionBase(BasePermission):
    roles = ()
    message = MESSAGE_REFUS

    def has_permission(self, request, view):
        return has_role(request.user, *self.roles)


class IsSuperAdmin(_RolePermissionBase):
    roles = (SUPERADMIN,)


class IsAdmin(_RolePermissionBase):
    roles = (SUPERADMIN, ADMIN)


class IsGestionnaire(_RolePermissionBase):
    roles = GESTION


class IsEnseignant(_RolePermissionBase):
    roles = (ENSEIGNANT,)


class IsEtudiant(_RolePermissionBase):
    roles = (ETUDIANT,)


def RolePermission(read=TOUS_LES_ROLES, write=()):
    """Permission distinguant les rôles autorisés en lecture et en écriture."""

    class _RolePermission(BasePermission):
        message = MESSAGE_REFUS

        def has_permission(self, request, view):
            roles = read if request.method in SAFE_METHODS else write
            return has_role(request.user, *roles)

    return _RolePermission


def peut_gerer_compte(acteur, cible):
    """Règle de gestion des comptes : qui peut modifier, désactiver ou réactiver qui."""
    if acteur.role == SUPERADMIN:
        return True
    if acteur.pk == cible.pk:
        return acteur.role in (ADMIN, RESPONSABLE)
    if not acteur.etablissement_id or acteur.etablissement_id != cible.etablissement_id:
        return False
    if acteur.role == ADMIN:
        return cible.role in (RESPONSABLE, ENSEIGNANT, ETUDIANT)
    if acteur.role == RESPONSABLE:
        return cible.role == ETUDIANT
    return False


class CanManageUser(BasePermission):
    message = MESSAGE_REFUS

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return peut_gerer_compte(request.user, obj)
