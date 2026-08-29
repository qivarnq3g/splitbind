from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from splitbind.access.models import Organization, Role, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "organization", "role", "is_active", "is_staff")
    list_filter = ("organization", "role", "is_active", "is_staff")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "email")}),
        ("Account status", {"fields": ("is_active",)}),
        ("SplitBind access", {"fields": ("organization", "role")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("username", "password1", "password2")}),
        ("SplitBind access", {"fields": ("organization", "role")}),
    )

    def _can_manage_accounts(self, request) -> bool:
        return bool(
            request.user.is_authenticated
            and (request.user.is_superuser or request.user.role == Role.ADMINISTRATOR)
        )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        return queryset.filter(
            organization_id=request.user.organization_id,
            is_superuser=False,
        )

    def has_module_permission(self, request) -> bool:
        return self._can_manage_accounts(request)

    def has_view_permission(self, request, obj=None) -> bool:
        return self._can_manage_accounts(request)

    def has_add_permission(self, request) -> bool:
        return self._can_manage_accounts(request)

    def has_change_permission(self, request, obj=None) -> bool:
        return self._can_manage_accounts(request)

    def has_delete_permission(self, request, obj=None) -> bool:
        return self._can_manage_accounts(request)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "organization" and not request.user.is_superuser:
            kwargs["queryset"] = Organization.objects.filter(pk=request.user.organization_id)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change) -> None:
        if not request.user.is_superuser:
            obj.organization_id = request.user.organization_id
            obj.is_superuser = False
        obj.is_staff = obj.role == Role.ADMINISTRATOR
        super().save_model(request, obj, form, change)
