"""Registro del Usuario personalizado en el panel /admin/ (incluye el campo rol)."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ('username', 'email', 'rol', 'is_staff', 'is_active')
    list_filter = ('rol', 'is_staff', 'is_active')
    fieldsets = UserAdmin.fieldsets + (('Datos del sistema', {'fields': ('rol', 'rut', 'telefono')}),)
    add_fieldsets = UserAdmin.add_fieldsets + (('Datos del sistema', {'fields': ('rol', 'email')}),)
