"""
musica.py - Teoria musical de Mano Sonora

Aqui no hay camara ni sonido, solo calculos de musica:
  - Nombres de las notas y el circulo de quintas (orden de las tonalidades)
  - Escalas Mayor y menor
  - Acorde de cada grado de una tonalidad (I, ii, iii, IV, V, vi, vii°)
  - Las 8 teclas del teclado de melodia

Las notas se manejan como numeros MIDI
  60 = Do central, 61 = Do#, 62 = Re ... cada numero arriba es un semitono
  12 numeros arriba es la misma nota una octava mas aguda
"""

# Nombres de las 12 notas de la octava, todos con sostenido (#)
# El indice es la "clase de altura": 0 = Do, 1 = Do# ... 11 = Si
NOMBRES = ["Do", "Do#", "Re", "Re#", "Mi", "Fa", "Fa#", "Sol", "Sol#", "La",
           "La#", "Si"]

# Circulo de quintas: Do, Sol, Re, La, Mi, Si, Fa#, Do#, Sol#, Re#, La#, Fa
# Cada tonalidad comparte casi todas sus notas con sus vecinas, por eso
# girar la mano poco a poco cambia de tonalidad de forma suave
CIRCULO = [0, 7, 2, 9, 4, 11, 6, 1, 8, 3, 10, 5]

# Distancia en semitonos de cada grado de la escala a la tonica
ESCALAS = {
    "Mayor": [0, 2, 4, 5, 7, 9, 11],
    "menor": [0, 2, 3, 5, 7, 8, 10],   # menor natural
}

# Numeros romanos de los grados (en mayusculas, luego se ajustan)
NUMERALES = ["I", "II", "III", "IV", "V", "VI", "VII"]

# Nota MIDI donde empieza cada franja (octava) del teclado de melodia
# 48 = Do grave, 60 = Do central, 72 = Do agudo
OCTAVAS = {"grave": 48, "media": 60, "aguda": 72}


def nombre_nota(midi):
    """Nombre de una nota MIDI sin la octava, por ejemplo 62 -> "Re" """
    return NOMBRES[midi % 12]


def frecuencia(midi):
    """Frecuencia en Hz de una nota MIDI

    Formula estandar: el La 69 suena a 440 Hz y cada 12 notas (una octava)
    la frecuencia se duplica
    """
    return 440.0 * 2 ** ((midi - 69) / 12)


def nombre_tonalidad(tonica, modo):
    """Texto de la tonalidad, por ejemplo (7, "Mayor") -> "Sol Mayor" """
    return f"{NOMBRES[tonica]} {modo}"


def acorde_por_grado(tonica, modo, grado, invertir=False):
    """Acorde de un grado de la tonalidad

    tonica: clase de altura de la tonica (0 = Do ... 11 = Si)
    modo: "Mayor" o "menor"
    grado: 0 = I, 1 = II ... 6 = VII (es la sena que hace la mano)
    invertir: True para el acorde "al reves" (al que se llega acostando la mano)
      un mayor se vuelve menor, un menor se vuelve mayor
      y un disminuido se vuelve menor

    Regresa un diccionario con
      "numeral": IV, ii, vii° (mayusculas = mayor, minusculas = menor)
      "nombre": por ejemplo "Do Mayor"
      "corto": por ejemplo "Do", "Lam", "Si°" (para la fila de grados)
      "notas": notas MIDI [base una octava abajo, raiz, tercera, quinta]
    """
    escala = ESCALAS[modo]

    def nota(paso):
        # Nota de la escala que esta "paso" lugares arriba del grado
        # Si se pasa del septimo grado, sigue en la siguiente octava
        octava, i = divmod(grado + paso, 7)
        return escala[i] + 12 * octava

    # Un acorde se arma apilando terceras de la escala:
    # el grado, dos notas mas arriba y cuatro notas mas arriba
    # Ejemplo en Do Mayor, grado II: Re, Fa, La
    raiz, tercera, quinta = nota(0), nota(2), nota(4)

    # Distancias en semitonos desde la raiz
    tercera -= raiz
    quinta -= raiz

    # El tipo de acorde sale solo de esas distancias
    #   tercera de 4 semitonos -> Mayor
    #   tercera de 3 y quinta de 7 -> menor
    #   tercera de 3 y quinta de 6 -> disminuido
    if tercera == 4:
        calidad = "Mayor"
    elif quinta == 7:
        calidad = "menor"
    else:
        calidad = "disminuido"

    # Invertir: subir o bajar la tercera un semitono
    if invertir:
        if calidad == "Mayor":
            calidad, tercera = "menor", 3
        elif calidad == "menor":
            calidad, tercera = "Mayor", 4
        else:
            calidad, quinta = "menor", 7

    # Numeral: minusculas si no es mayor, y ° si es disminuido
    numeral = NUMERALES[grado]
    if calidad != "Mayor":
        numeral = numeral.lower()
    if calidad == "disminuido":
        numeral += "°"

    # La raiz se acomoda entre Do4 (60) y Si4 (71) para que todos los
    # acordes suenen en el mismo rango, sin brincos de grave a agudo
    base = 60 + (tonica + raiz) % 12
    return {
        "numeral": numeral,
        "nombre": f"{nombre_nota(base)} {calidad}",
        "corto": nombre_nota(base) + {"Mayor": "", "menor": "m",
                                      "disminuido": "°"}[calidad],
        # base - 12 es la misma raiz una octava abajo, le da cuerpo al acorde
        "notas": [base - 12, base, base + tercera, base + quinta],
    }


def escalera(tonica, modo, grado, octava=0):
    """Notas de la escala contadas desde la raiz de un acorde

    Regresa un diccionario paso -> nota MIDI, de -7 a +14 pasos
      0 = la raiz del acorde (la misma que en acorde_por_grado)
      1 = la siguiente nota de la escala, 2 = la tercera, -1 = la de abajo...
      7 = la raiz una octava arriba
    Lo usa el ritmo Secuencia: el patron se escribe en pasos y suena con
    las notas de la tonalidad, empezando desde el acorde que hace la mano
    """
    escala = ESCALAS[modo]
    base = 60 + (tonica + escala[grado]) % 12 + 12 * octava

    def nota(paso):
        vueltas, i = divmod(grado + paso, 7)
        return base + escala[i] + 12 * vueltas - escala[grado]

    return {paso: nota(paso) for paso in range(-7, 15)}


def teclado(tonica, modo, franja="media"):
    """Las 8 teclas del teclado de melodia

    Son las notas de la escala de la tonalidad, de la tonica hasta su octava
    Como solo estan las notas de la escala, ninguna nota suena "equivocada"
    franja: "grave", "media" o "aguda" (la elige el dedo del pellizco)
    """
    inicio = OCTAVAS[franja] + tonica
    return [inicio + s for s in ESCALAS[modo]] + [inicio + 12]
