from rest_framework.permissions import SAFE_METHODS, BasePermission

from splitbind.access.models import Role


class HasRole(BasePermission):
    role: str

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.role == self.role)


class IsAdministrator(HasRole):
    role = Role.ADMINISTRATOR


class IsIssuer(HasRole):
    role = Role.ISSUER


class IsVerifier(HasRole):
    role = Role.VERIFIER


class IsAuditor(HasRole):
    role = Role.AUDITOR


class IsAdministratorOrAuditor(BasePermission):
    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.role in {Role.ADMINISTRATOR, Role.AUDITOR}
        )


class IsAuditorReadOnly(IsAuditor):
    def has_permission(self, request, view) -> bool:
        return request.method in SAFE_METHODS and super().has_permission(request, view)
