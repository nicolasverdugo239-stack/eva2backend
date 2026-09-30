"""
=====================================================================
VISTAS DE AUTENTICACIÓN (JWT)
=====================================================================
    POST /api/auth/registro/  -> crea un Pasajero (público)
    POST /api/auth/login/     -> entrega access + refresh con claim rol
    POST /api/auth/refresh/   -> renueva el access token
    POST /api/auth/logout/    -> invalida el refresh (blacklist)
    GET  /api/auth/perfil/    -> datos del usuario autenticado

IMPORTANTE (carro persistente): el logout SOLO invalida el token. El
carro del usuario vive en PostgreSQL (tabla ventas_carro) y NO se
toca, por lo que al volver a iniciar sesión (en cualquier dispositivo)
los ítems siguen allí.
"""

from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import (
    LogoutSerializer,
    RegistroSerializer,
    TokenPersonalizadoSerializer,
    UsuarioSerializer,
)


class LoginView(TokenObtainPairView):
    """Login JWT: retorna tokens access/refresh con el claim de rol."""

    serializer_class = TokenPersonalizadoSerializer


class RegistroView(generics.CreateAPIView):
    """Registro público de nuevos pasajeros."""

    serializer_class = RegistroSerializer
    permission_classes = [permissions.AllowAny]


class PerfilView(generics.RetrieveAPIView):
    """Devuelve el perfil del usuario dueño del token."""

    serializer_class = UsuarioSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class LogoutView(APIView):
    """
    -----------------------------------------------------------------
    BLOQUE: Logout
    Agrega el refresh token a la blacklist (app token_blacklist), de
    modo que no pueda volver a usarse para obtener access tokens.
    -----------------------------------------------------------------
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=LogoutSerializer, responses={205: None})
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RefreshToken(serializer.validated_data['refresh']).blacklist()
        except TokenError:
            return Response({'detail': 'Token inválido o ya expirado.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {'detail': 'Sesión cerrada. Su carro de pasajes se mantiene guardado.'},
            status=status.HTTP_205_RESET_CONTENT,
        )
