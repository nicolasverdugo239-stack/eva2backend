"""
=====================================================================
CONFIGURACIÓN GLOBAL DEL PROYECTO "pasajes_buses"
Sistema de Reservas de Pasajes de Buses Interurbanos (Proyecto 4)
=====================================================================
Este archivo centraliza:
  - Apps instaladas (DRF, SimpleJWT, django-filter, drf-spectacular).
  - Conexión nativa a PostgreSQL (motor django.db.backends.postgresql).
  - Configuración de JWT (access / refresh + blacklist para logout).
  - Datos del alumno que se muestran en el footer de las vistas HTML.

Los valores sensibles (credenciales de BD, SECRET_KEY) se leen desde
variables de entorno, con valores por defecto para desarrollo local.
"""

import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------
# BLOQUE: SEGURIDAD BÁSICA
# En producción SECRET_KEY y DEBUG deben venir de variables de entorno.
# ---------------------------------------------------------------------
SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure-br_#xsa4l%^h#q@-2r*p*x0(du%zzo!eia!(x*tjja=3ckbqc=',
)
DEBUG = os.environ.get('DJANGO_DEBUG', 'True') == 'True'
ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')


# ---------------------------------------------------------------------
# BLOQUE: APLICACIONES INSTALADAS
#   - Apps de terceros: DRF, JWT (+ blacklist), django-filter, spectacular.
#   - Apps propias:
#       usuarios -> Usuario personalizado con ROL (Pasajero / Admin Flota)
#       flota    -> Ciudades, Terminales, Rutas, Buses, Servicios, Asientos
#       ventas   -> Carro de Pasajes, Ventas (órdenes) y Boletos
# ---------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Terceros
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'django_filters',
    'drf_spectacular',
    # Propias
    'usuarios.apps.UsuariosConfig',
    'flota.apps.FlotaConfig',
    'ventas.apps.VentasConfig',
    'panel.apps.PanelConfig',  # CRUD web con formularios HTML (Admin Flota)
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'pasajes_buses.urls'

# ---------------------------------------------------------------------
# BLOQUE: TEMPLATES
# Se agrega la carpeta /templates del proyecto y un context processor
# propio que inyecta los datos del alumno en TODAS las plantillas HTML
# (así el footer base siempre los muestra).
# ---------------------------------------------------------------------
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'pasajes_buses.context_processors.datos_alumno',
            ],
        },
    },
]

WSGI_APPLICATION = 'pasajes_buses.wsgi.application'


# ---------------------------------------------------------------------
# BLOQUE: BASE DE DATOS POSTGRESQL (NO SQLite)
# Motor nativo django.db.backends.postgresql (driver psycopg 3).
# ---------------------------------------------------------------------
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'buses_interurbanos_db'),
        'USER': os.environ.get('DB_USER', 'postgres'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'postgres'),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}


# ---------------------------------------------------------------------
# BLOQUE: MODELO DE USUARIO PERSONALIZADO
# Reemplaza al User de Django para agregar el campo "rol" (CHOICES).
# ---------------------------------------------------------------------
AUTH_USER_MODEL = 'usuarios.Usuario'

# Login por sesión del panel web (/panel/). La API sigue usando JWT.
LOGIN_URL = 'panel:login'
LOGIN_REDIRECT_URL = 'panel:inicio'
LOGOUT_REDIRECT_URL = 'panel:login'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# ---------------------------------------------------------------------
# BLOQUE: INTERNACIONALIZACIÓN (Chile)
# ---------------------------------------------------------------------
LANGUAGE_CODE = 'es-cl'
TIME_ZONE = 'America/Santiago'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ---------------------------------------------------------------------
# BLOQUE: DJANGO REST FRAMEWORK
#   - Autenticación por JWT (Bearer token) como mecanismo principal.
#   - Permiso por defecto: solo lectura para anónimos; cada vista define
#     explícitamente sus permisos (público / pasajero / admin flota).
#   - django-filter como backend de filtros global + búsqueda y orden.
#   - drf-spectacular genera el esquema OpenAPI.
# ---------------------------------------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ),
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}


# ---------------------------------------------------------------------
# BLOQUE: SIMPLE JWT
#   - Access token corto (60 min) y refresh token largo (1 día).
#   - ROTATE + BLACKLIST: al refrescar se invalida el refresh anterior,
#     y el logout agrega el refresh a la lista negra.
#   - Los claims de ROL se agregan en usuarios/serializers.py
#     (TokenPersonalizadoSerializer).
# ---------------------------------------------------------------------
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'UPDATE_LAST_LOGIN': True,
}


# ---------------------------------------------------------------------
# BLOQUE: DOCUMENTACIÓN OPENAPI / SWAGGER (drf-spectacular)
# Swagger UI queda disponible en /api/docs/
# ---------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    'TITLE': 'API Pasajes de Buses Interurbanos',
    'DESCRIPTION': (
        'Backend DRF + PostgreSQL para la venta de pasajes de buses '
        'interurbanos: búsqueda de servicios, carro de pasajes persistente, '
        'checkout con verificación atómica de asientos y emisión de boletos.\n\n'
        'Autenticación: obtenga un token en /api/auth/login/ y use el botón '
        '"Authorize" con el access token.'
    ),
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'SWAGGER_UI_SETTINGS': {'persistAuthorization': True},
    # Varios modelos tienen un campo "estado" con CHOICES distintos:
    # se les da un nombre propio en el esquema.
    'ENUM_NAME_OVERRIDES': {
        'EstadoServicioEnum': 'flota.models.Servicio.Estado',
        'EstadoAsientoEnum': 'flota.models.Asiento.Estado',
        'EstadoVentaEnum': 'ventas.models.Venta.Estado',
        'EstadoBoletoEnum': 'ventas.models.Boleto.Estado',
    },
}


# ---------------------------------------------------------------------
# BLOQUE: DATOS DEL ALUMNO (FOOTER)
# Se muestran en la página base "/", en Swagger (/api/docs/) y en la
# raíz JSON de la API (/api/). Pueden sobreescribirse por variables
# de entorno.
# ---------------------------------------------------------------------
DATOS_ALUMNO = {
    'nombre': os.environ.get('ALUMNO_NOMBRE', 'Jonathan Nicolas Verdugo Garrido'),
    'seccion': os.environ.get('ALUMNO_SECCION', 'SECCIÓN'),
    'anio': os.environ.get('ALUMNO_ANIO', '2026'),
}
