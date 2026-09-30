"""
=====================================================================
VALIDADOR DE RUT CHILENO (módulo 11)
=====================================================================
Acepta formatos 12.345.678-5, 12345678-5 o 123456785 y devuelve el RUT
normalizado "12345678-5". Si el dígito verificador no coincide lanza
un ValidationError.
"""

import re

from rest_framework import serializers


def normalizar_rut(valor):
    rut = re.sub(r'[^0-9kK]', '', valor or '').upper()
    if len(rut) < 2:
        raise serializers.ValidationError('RUT inválido.')

    cuerpo, dv = rut[:-1], rut[-1]
    if not cuerpo.isdigit():
        raise serializers.ValidationError('RUT inválido.')

    # Cálculo del dígito verificador: multiplicar de derecha a izquierda
    # por la serie 2,3,4,5,6,7,2,3... y aplicar módulo 11.
    suma, factor = 0, 2
    for digito in reversed(cuerpo):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - (suma % 11)
    esperado = {11: '0', 10: 'K'}.get(resto, str(resto))

    if dv != esperado:
        raise serializers.ValidationError('El dígito verificador del RUT no es válido.')
    return f'{int(cuerpo)}-{dv}'
