"""
=====================================================================
SERIALIZADORES DE LA APP "usuarios"
=====================================================================
- TokenPersonalizadoSerializer: login JWT con claims de rol.
- RegistroSerializer: alta de nuevos pasajeros.
- UsuarioSerializer: lectura del perfil.
"""

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Usuario


class TokenPersonalizadoSerializer(TokenObtainPairSerializer):
    """
    -----------------------------------------------------------------
    BLOQUE: Payload JWT personalizado (claims)
    get_token() se ejecuta al generar el par access/refresh. Aquí se
    agregan claims extra al payload del token:
        rol, username, email, es_admin_flota
    Como el access token se deriva del refresh, ambos tokens llevan
    los mismos claims. El token está FIRMADO (HS256 con SECRET_KEY),
    por lo que el cliente puede leer el rol pero no alterarlo.

    validate(): además de los tokens, la respuesta del login devuelve
    el rol y los datos del usuario para comodidad del frontend.
    -----------------------------------------------------------------
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['rol'] = user.rol
        token['username'] = user.username
        token['email'] = user.email
        token['es_admin_flota'] = user.es_admin_flota
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data['usuario'] = {
            'id': self.user.id,
            'username': self.user.username,
            'email': self.user.email,
            'rol': self.user.rol,
        }
        return data


class RegistroSerializer(serializers.ModelSerializer):
    """
    -----------------------------------------------------------------
    BLOQUE: Registro público de pasajeros
    - El rol se fuerza a PASAJERO: nadie puede auto-registrarse como
      Administrador de Flota (esos se crean desde /admin/ o por comando).
    - La contraseña se valida con los validadores de Django y se guarda
      hasheada mediante create_user().
    -----------------------------------------------------------------
    """

    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = Usuario
        fields = ('id', 'username', 'email', 'password', 'first_name', 'last_name', 'rut', 'telefono', 'rol')
        read_only_fields = ('id', 'rol')

    def create(self, validated_data):
        return Usuario.objects.create_user(rol=Usuario.Rol.PASAJERO, **validated_data)


class UsuarioSerializer(serializers.ModelSerializer):
    """Datos públicos del perfil del usuario autenticado."""

    class Meta:
        model = Usuario
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'rut', 'telefono', 'rol')
        read_only_fields = fields


class LogoutSerializer(serializers.Serializer):
    """Recibe el refresh token que se invalidará (blacklist) al cerrar sesión."""

    refresh = serializers.CharField()
