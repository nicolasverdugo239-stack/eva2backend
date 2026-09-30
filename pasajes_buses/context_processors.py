"""
=====================================================================
CONTEXT PROCESSOR: DATOS DEL ALUMNO
=====================================================================
Inyecta la variable {{ alumno }} (nombre, sección y año definidos en
settings.DATOS_ALUMNO) en todas las plantillas HTML. El footer de
templates/base.html y el de Swagger la utilizan.
"""

from django.conf import settings


def datos_alumno(request):
    return {'alumno': settings.DATOS_ALUMNO}
