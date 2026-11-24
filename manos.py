"""
manos.py - Lectura de las manos

Convierte los 21 puntos que da MediaPipe por cada mano en gestos:
  - Que dedos estan alzados o doblados
  - Senas de acordes (grados I a VII)
  - Pellizco y con que dedo
  - Puno, mano abierta, apuntando
  - Centro de la palma e inclinacion de la mano

Puntos de MediaPipe que mas se usan
  0 = muneca
  4 = punta del pulgar      3 = articulacion del pulgar
  8 = punta del indice      6 = articulacion media del indice
  12 = punta del medio      10 = articulacion media del medio
  16 = punta del anular     14 = articulacion media del anular
  20 = punta del menique    18 = articulacion media del menique
  5, 9, 13, 17 = nudillos (base de cada dedo)

Idea clave: todas las distancias se comparan contra el tamano de la mano
(muneca al nudillo del medio), asi funciona igual cerca o lejos de la camara
"""

import math

# Pares de puntos que se unen con una linea para dibujar el esqueleto
CONEXIONES = [
    (0, 1), (1, 2), (2, 3), (3, 4),             # pulgar
    (0, 5), (5, 6), (6, 7), (7, 8),             # indice
    (5, 9), (9, 10), (10, 11), (11, 12),        # medio
    (9, 13), (13, 14), (14, 15), (15, 16),      # anular
    (13, 17), (0, 17), (17, 18), (18, 19), (19, 20),   # palma y menique
]

# Numeracion de los dedos que usa todo el programa
#   0 = pulgar, 1 = indice, 2 = medio, 3 = anular, 4 = menique
#
# Senas de acordes (grado 0 = I ... 6 = VII)
#   I a V: un solo dedo (pulgar I, indice II, medio III, anular IV, menique V)
#     ese dedo se alza, o se baja si en Configurar se eligio "Bajar dedos"
#   VI y VII: siempre la misma forma de mano, en los dos modos
FORMAS_FIJAS = {
    frozenset({1, 2}): 5,   # VI: amor y paz (indice y medio alzados)
    frozenset({0, 4}): 6,   # VII: pulgar y menique alzados
}

# Pellizco: distancia pulgar-dedo (medida en tamanos de mano)
#   para empezar a pellizcar hay que bajar de 0.30
#   para soltar hay que pasar de 0.45
# Que soltar pida mas distancia que empezar (histeresis) evita que el
# pellizco se prenda y apague solo cuando los dedos quedan en el limite
PELLIZCO_ENTRA = 0.30
PELLIZCO_SALE = 0.45

# Dedo del pellizco -> punto de su punta
PUNTAS = {1: 8, 2: 12, 3: 16}


class Mano:
    """Una mano detectada en el cuadro actual y sus gestos"""

    def __init__(self, puntos, lado, gesto=None):
        self.puntos = puntos    # lista de 21 puntos (x, y) en pixeles
        self.lado = lado        # "Izquierda" o "Derecha"
        self.gesto = gesto      # gesto que reconocio el modelo, p. ej. "Thumb_Up"

        # Tamano de la mano: muneca (0) al nudillo del medio (9)
        # max(1.0, ...) evita dividir entre cero si la mano sale muy chica
        self.tamano = max(1.0, self.distancia(0, 9))

        # Lista de 5 True/False: que dedos estan alzados
        self.arriba = self._dedos_arriba()

    def distancia(self, a, b):
        """Distancia en pixeles entre dos puntos de la mano"""
        (xa, ya), (xb, yb) = self.puntos[a], self.puntos[b]
        return math.hypot(xa - xb, ya - yb)

    def _dedos_arriba(self):
        """Decide que dedos estan alzados

        Pulgar: alzado si su punta (4) queda mas lejos de la base del
        menique (17) que su articulacion (3), porque el pulgar se dobla
        hacia un lado y no hacia la palma

        Indice a menique: alzado si la punta queda mas lejos de la muneca
        que la articulacion media; al doblar el dedo la punta se acerca a
        la palma y la regla se invierte
        Compara distancias y no posiciones arriba/abajo, asi funciona
        aunque la mano este inclinada
        """
        arriba = [self.distancia(4, 17) > self.distancia(3, 17)]
        for punta, medio in [(8, 6), (12, 10), (16, 14), (20, 18)]:
            arriba.append(self.distancia(punta, 0) > self.distancia(medio, 0))
        return arriba

    # ---------------------------------------------------- formas de la mano

    def puno(self):
        """Indice a menique doblados (el pulgar no cuenta)

        Es la base de puno_completo()
        """
        return not any(self.arriba[1:])

    def puno_completo(self):
        """Puno con el pulgar tambien cerrado

        Se usa para el doble puno (cambiar de modo). Tambien cuenta si el modelo de MediaPipe dice
        "Closed_Fist". Asi un pulgar arriba no se confunde con puno
        """
        return self.gesto == "Closed_Fist" or (self.puno() and not self.arriba[0])

    def abierta(self):
        """Los 4 dedos (indice a menique) alzados: sirve para girar la tonalidad"""
        return all(self.arriba[1:])

    def apuntando(self):
        """Solo el indice alzado: es el cursor de Configurar"""
        return self.arriba[1] and not any(self.arriba[2:])

    def grado(self, bajar=False):
        """Grado de la sena de acorde (0 = I ... 6 = VII) o None si no es sena

        bajar=False: la sena son los dedos alzados (solo el anular = IV)
        bajar=True: la sena son los dedos doblados (bajar el anular = IV)
        VI y VII se revisan primero porque tienen la misma forma en los dos
        modos
        """
        alzados = frozenset(i for i, a in enumerate(self.arriba) if a)

        # VI y VII. El pulgar es el dedo que MediaPipe detecta peor, asi
        # que si la sena no lo usa (amor y paz) da igual si esta alzado
        for forma, grado in FORMAS_FIJAS.items():
            if alzados == forma or (0 not in forma and alzados - {0} == forma):
                return grado

        # I a V: debe quedar exactamente un dedo alzado (o doblado)
        dedos = frozenset(range(5)) - alzados if bajar else alzados
        # Misma tolerancia del pulgar: indice + pulgar sigue siendo II
        if len(dedos) == 2 and 0 in dedos:
            dedos = dedos - {0}
        if len(dedos) == 1:
            return next(iter(dedos))
        return None

    def pellizco(self, previo=None):
        """Dedo que se junta con el pulgar: 1 indice, 2 medio, 3 anular o None

        previo: dedo que pellizcaba en el cuadro anterior; mientras no se
        separe lo suficiente (PELLIZCO_SALE) se conserva ese mismo dedo,
        asi el pellizco no se suelta solo a medio movimiento
        En Configurar el pellizco con el indice controla volumen y tempo
        """
        # Distancia de la punta del pulgar a cada punta, en tamanos de mano
        distancias = {d: self.distancia(4, p) / self.tamano
                      for d, p in PUNTAS.items()}

        # Si ya se estaba pellizcando, seguir con el mismo dedo
        if previo is not None and distancias[previo] < PELLIZCO_SALE:
            return previo

        # Pellizco nuevo: gana el dedo mas cercano al pulgar
        dedo = min(distancias, key=distancias.get)
        if distancias[dedo] >= PELLIZCO_ENTRA:
            return None

        # En un puno el pulgar tambien queda cerca de las puntas
        # En un pellizco real al menos dos de los otros dedos siguen alzados
        otros = [i for i in (1, 2, 3, 4) if i != dedo]
        if sum(self.arriba[i] for i in otros) < 2:
            return None
        return dedo

    # ----------------------------------------------------------- posiciones

    def centro(self):
        """Centro de la palma: promedio de la muneca y los 4 nudillos

        Esos puntos casi no se mueven al doblar o juntar los dedos, por eso
        se usa para la altura (octava), los pellizcos y el aplauso
        """
        xs = [self.puntos[i][0] for i in (0, 5, 9, 13, 17)]
        ys = [self.puntos[i][1] for i in (0, 5, 9, 13, 17)]
        return sum(xs) / 5, sum(ys) / 5

    def punta_indice(self):
        """Punta del indice: la posicion del cursor en Configurar"""
        return self.puntos[8]

    def angulo(self):
        """Inclinacion de la mano en grados (90 = derecha hacia arriba)

        Es el angulo de la linea muneca -> nudillo del medio
        En la imagen la y crece hacia abajo, por eso se usa y0 - y9
        """
        (x0, y0), (x9, y9) = self.puntos[0], self.puntos[9]
        return math.degrees(math.atan2(y0 - y9, x9 - x0))

    def inclinacion(self):
        """Cuanto esta acostada la mano hacia un lado, sin importar cual

        0 = derecha hacia arriba, 90 = acostada de lado
        Se mide en el plano de la imagen, asi los dedos se siguen viendo
        completos y la sena se sigue leyendo bien
        """
        return abs((self.angulo() - 90 + 180) % 360 - 180)
