"""
=====================================================================
PERMISOS PERSONALIZADOS (RBAC) BASADOS EN EL CLAIM "rol" DEL JWT
=====================================================================
Cuando una petición llega con "Authorization: Bearer <access>", la
clase JWTAuthentication valida la firma del token y deja:
    request.user -> instancia de Usuario
    request.auth -> el token validado (AccessToken), que se comporta
                    como un diccionario con sus claims.

Estas clases leen el claim "rol" directamente desde el token
(request.auth['rol']). Si no hubiera token JWT (por ejemplo, sesión del
admin de Django) se usa como respaldo el campo rol del usuario en BD.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Usuario


def obtener_rol(request):
    """
    -----------------------------------------------------------------
    BLOQUE: Lectura del rol
    1) Intenta leer el claim "rol" desde el token JWT validado.
    2) Si no existe, recurre al campo rol del usuario autenticado.
    -----------------------------------------------------------------
    """
    token = getattr(request, 'auth', None)
    if token is not None and hasattr(token, 'get'):
        rol = token.get('rol')
        if rol:
            return rol
    usuario = getattr(request, 'user', None)
    if usuario is not None and usuario.is_authenticated:
        return usuario.rol
    return None


class EsAdministradorFlota(BasePermission):
    """
    Permite el acceso solo a usuarios autenticados cuyo rol sea
    ADMIN_FLOTA (gestión de inventario/servicios y cambio de estados).
    """

    message = 'Solo un Administrador de Flota puede realizar esta acción.'

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and obtener_rol(request) == Usuario.Rol.ADMIN_FLOTA
        )


class EsPasajero(BasePermission):
    """
    Permite el acceso solo a usuarios autenticados con rol PASAJERO.
    """

    message = 'Esta acción está disponible solo para Pasajeros.'

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and obtener_rol(request) == Usuario.Rol.PASAJERO
        )


class LecturaPublicaEscrituraAdmin(BasePermission):
    """
    -----------------------------------------------------------------
    BLOQUE: Catálogo público
    - GET / HEAD / OPTIONS -> cualquier visitante (sin token).
    - POST / PUT / PATCH / DELETE -> solo Administrador de Flota.
    Se usa en los endpoints del catálogo (servicios, rutas, ciudades...).
    -----------------------------------------------------------------
    """

    message = 'Solo un Administrador de Flota puede modificar el catálogo.'

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return EsAdministradorFlota().has_permission(request, view)
