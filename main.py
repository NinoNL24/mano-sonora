"""
main.py - Programa principal de Mano Sonora (prototipo)

Une todas las piezas
  OpenCV:     abre la camara y dibuja la pantalla
  MediaPipe:  encuentra las manos y sus 21 puntos (en main(), num_hands=2)
  manos.py:   convierte los puntos en gestos
  musica.py:  calcula acordes y notas
  audio.py:   hace sonar todo

Flujo de cada cuadro de video (funcion main, al final del archivo)
  camara -> MediaPipe -> leer_manos() -> App.actualizar() -> App.dibujar()

Uso
  py main.py
Teclas de respaldo: q = salir, m = cambiar de modo, espacio = beat on/off
"""

from collections import deque
import math
from pathlib import Path
import time
import unicodedata

import cv2
import mediapipe as mp
import numpy as np

import audio
import musica
from manos import CONEXIONES, Mano

# ============================================================== ajustes

# MediaPipe dice si cada mano es izquierda o derecha, pero como volteamos la
# imagen (efecto espejo) con esta camara salian al reves
# Si en otra camara la derecha aparece como izquierda, cambiar a False
INVERTIR_MANOS = True

TIEMPO_CAMBIO = 1.0         # segundos de doble puno para cambiar de modo
TIEMPO_BOTON = 0.6          # segundos apuntando a un boton para elegirlo
CUADROS_ESTABLES = 2        # cuadros seguidos con la misma sena para cambiar el acorde
CUADROS_SILENCIO = 3        # para callar se espera uno mas (no corta al pasar de sena a sena)
GRADOS_POR_TONALIDAD = 20   # grados que hay que girar la mano por tonalidad

# Inclinar la mano de acordes de lado: Mayor <-> menor poco a poco
# Hasta 20 grados sigue normal, desde 70 ya esta invertido, en medio se desliza
INCLINA_INICIO = 20
INCLINA_FIN = 70

# Altura de la mano de acordes: 3 franjas de la pantalla = 3 octavas
# Para cambiar de franja hay que pasar la linea por este margen (4 % del
# alto), asi no brinca de octava si la mano queda justo en la frontera
MARGEN_OCTAVA = 0.04
FRANJAS_ACORDE = {1: (0, 1 / 3), 0: (1 / 3, 2 / 3), -1: (2 / 3, 1)}
NOMBRES_OCTAVA = {1: "aguda", 0: "media", -1: "grave"}

# Botones del modo Configurar: (clave del ajuste, titulo, opciones)
LISTAS = [
    # Hi-hat (ya viene) + uno por cada beats/*.mid
    ("beat", "Beat", list(audio.BEATS)),
    ("activo", "Beat sonando", ["Encendido", "Apagado"]),
    ("instrumento", "Instrumento", audio.INSTRUMENTOS),
    ("ritmo", "Ritmo", audio.RITMOS),
    ("senas", "Señas de acordes", ["Alzar dedos", "Bajar dedos"]),
]
# Ajustes de cada mano: cada una elige el suyo apuntando con su indice
# (los demas, beat y senas, son de las dos)
POR_MANO = ("instrumento", "ritmo")
SOLO_INTERFAZ = ("senas", "activo")  # ajustes que no van tal cual al motor
MANOS = audio.MANOS                  # ("Derecha", "Izquierda")
CORTO = {"Derecha": "Der", "Izquierda": "Izq"}

# Colores en BGR (OpenCV usa azul, verde, rojo en ese orden)
BLANCO = (255, 255, 255)
GRIS = (150, 150, 150)
OSCURO = (35, 35, 35)
AZUL = (255, 160, 60)       # mano derecha y elementos activos
NARANJA = (0, 140, 255)     # mano izquierda y cursor
VERDE = (90, 220, 90)
GENERAL = (70, 150, 70)     # opcion elegida que es de las dos manos (beat, senas)
COLOR_MANO = {"Derecha": AZUL, "Izquierda": NARANJA}
COLORES_GRADO = [(75, 83, 229), (36, 138, 240), (71, 197, 232),
                 (100, 217, 76), (201, 184, 47), (255, 155, 76),
                 (232, 114, 164)]   # un color por grado, de I a VII


def texto(s):
    """Quita los acentos porque la letra de OpenCV no los tiene: Melodía -> Melodia"""
    s = unicodedata.normalize("NFKD", s.replace("°", "o"))
    return "".join(c for c in s if not unicodedata.combining(c))


def escribir(frame, s, pos, escala=0.6, color=BLANCO, grosor=1):
    """Escribe texto con un borde negro para que se lea sobre el video"""
    x, y = int(pos[0]), int(pos[1])
    cv2.putText(frame, texto(s), (x, y), cv2.FONT_HERSHEY_SIMPLEX, escala,
                (0, 0, 0), grosor + 2)
    cv2.putText(frame, texto(s), (x, y), cv2.FONT_HERSHEY_SIMPLEX, escala,
                color, grosor)


def escribir_centrado(frame, s, cx, y, escala=0.6, color=BLANCO, grosor=1):
    """Igual que escribir, pero el texto queda centrado en cx"""
    ancho = cv2.getTextSize(texto(s), cv2.FONT_HERSHEY_SIMPLEX, escala,
                            grosor)[0][0]
    escribir(frame, s, (cx - ancho // 2, y), escala, color, grosor)


def dibujar_ondas(frame, x0, x1, yc, alto, notas, color, t, mezcla=0.0,
                  movil=None):
    """Ondas que se mueven con la forma del acorde que suena

    Cada nota del acorde es una onda senoidal; se suman y se dibujan
    Las notas se dibujan en proporcion a su frecuencia real (la tercera
    mayor es 1.26 veces la raiz, la quinta 1.5 veces...), asi cada tipo
    de acorde tiene su propia forma. Se mueven con el tiempo t
    Se dibujan 3 capas: las de atras mas oscuras y desfasadas
    mezcla y movil: la nota que se desliza al acostar la mano tambien
    cambia su onda
    """
    raiz = notas[1]
    razones = []
    for n in notas[1:]:
        if movil is not None and (n - movil[0]) % 12 == 0:
            n = n + mezcla * movil[1]
        razones.append(2 ** ((n - raiz) / 12))
    u = np.linspace(0, 1, max(2, x1 - x0))
    borde = np.sin(np.pi * u) ** 0.7       # se hace chiquita en las orillas
    for capa, brillo in ((2, 0.35), (1, 0.6), (0, 1.0)):
        y = np.zeros_like(u)
        for r in razones:
            y += np.sin(2 * np.pi * (2.5 * r * u - 0.6 * r * t) + capa * 0.9)
        y = y / len(razones) * borde * alto * (1 - 0.15 * capa)
        pts = np.stack([x0 + u * (x1 - x0), yc - y], axis=1).astype(np.int32)
        c = tuple(int(v * brillo) for v in color)
        cv2.polylines(frame, [pts], False, c, 3 if capa == 0 else 2,
                      cv2.LINE_AA)


# ========================================================= la aplicacion

class Tocador:
    """Lo que esta tocando una mano en Play

    Hay uno por mano, asi cada una toca su acorde al mismo tiempo
    Por ejemplo: la derecha deja el acorde principal en Secuencia y la
    izquierda va cambiando acordes encima
    """

    def __init__(self, lado):
        self.lado = lado            # "Derecha" o "Izquierda"
        self.candidato = None       # acorde que se esta "confirmando"
        self.cuenta = 0             # cuadros seguidos con el mismo candidato
        self.acorde = None          # (grado, octava) o None
        self.info = None            # resultado de musica.acorde_por_grado
        self.info_inv = None        # el mismo acorde invertido (Mayor <-> menor)
        self.octava = 0             # 1 = aguda, 0 = media, -1 = grave
        self.mezcla = 0.0           # 0 = acorde normal ... 1 = invertido
        self.movil = None           # (nota que se desliza, semitonos)


class App:
    """Estado del programa y que hace cada gesto en cada modo

    actualizar(): se llama en cada cuadro, lee los gestos y decide que hacer
    dibujar(): pinta todo encima del video
    """

    def __init__(self, motor):
        self.motor = motor          # el motor de audio (audio.Motor)
        self.modo = "Configurar"    # "Configurar" o "Play"

        # Lo que el usuario eligio en Configurar
        # Generales (de las dos manos)
        self.ajustes = {"beat": "Hi-hat", "senas": "Alzar dedos",
                        "bpm": 100, "volumen": 0.7}
        # De cada mano: instrumento y ritmo
        # Para empezar: la derecha con Sinte en Secuencia (el acorde
        # principal) y la izquierda con Pad sostenido (los cambios)
        self.por_mano = {
            "Derecha": {"instrumento": "Sinte", "ritmo": "Secuencia"},
            "Izquierda": {"instrumento": "Pad", "ritmo": "Sostenido"},
        }
        self.circulo = 0            # posicion en el circulo de quintas (0 = Do)
        self.escala = "Mayor"       # "Mayor" o "menor"

        # Mandar los ajustes iniciales al motor de audio
        motor.ajustar(**{k: v for k, v in self.ajustes.items()
                         if k not in SOLO_INTERFAZ})
        for lado, ajustes in self.por_mano.items():
            motor.ajustar(mano=lado, **ajustes)

        # Estado de los gestos (lo que se recuerda entre un cuadro y otro)
        self.puno_desde = None      # cuando empezo el doble puno
        self.esperar_soltar = False # True despues de cambiar de modo hasta abrir las manos
        self.distancias = deque()   # (tiempo, distancia entre palmas) para el aplauso
        self.ultimo_aplauso = -10.0
        self.boton = None           # boton que esta bajo el cursor
        self.boton_desde = 0.0      # desde cuando esta ahi
        self.boton_listo = False    # True cuando ya se eligio (no repetir)
        self.arrastre = {}          # lado -> (altura inicial, valor inicial)
        self.pellizcos = {}         # lado -> dedo (en Configurar)
        self.giro = None            # (angulo inicial, circulo inicial)
        self.puntero = None         # mano que esta apuntando en Configurar

        # Lo que esta tocando cada mano en Play
        self.tocadores = {lado: Tocador(lado) for lado in MANOS}

        self.botones = []           # (x0, y0, x1, y1, clave, valor) de cada boton
        self.centros = {}           # lado -> x del centro de su acorde en pantalla
        self.alto = 720             # alto de la imagen (se actualiza cada cuadro)

    @property
    def tonica(self):
        """Clase de altura de la tonalidad elegida en el circulo (0 = Do)"""
        return musica.CIRCULO[self.circulo]

    # ============================================================ logica

    def actualizar(self, manos, t, ancho, alto):
        """Se llama una vez por cuadro con las manos detectadas

        manos: {"Derecha": Mano, "Izquierda": Mano} (puede faltar alguna)
        t: tiempo actual en segundos
        """
        der, izq = manos.get("Derecha"), manos.get("Izquierda")
        self.alto = alto
        self._acomodar(ancho, alto)

        # Gestos que funcionan en cualquier modo
        self._aplauso(der, izq, t)
        if self._doble_puno(der, izq, t):
            return   # despues de cambiar de modo se ignora todo hasta abrir las manos

        # Gestos de cada modo
        if self.modo == "Configurar":
            self._configurar(der, izq, t, alto)
        else:
            self._tocar(manos)

    def cambiar_modo(self):
        """Pasa de Configurar a Play o al reves"""
        self._callar()
        self.modo = "Play" if self.modo == "Configurar" else "Configurar"
        # Olvidar gestos a medias del modo anterior
        self.boton = None
        self.arrastre.clear()
        self.pellizcos.clear()
        self.giro = None
        self.motor.efecto("whoosh")

    def _acomodar(self, w, h):
        """Calcula donde van los botones, el circulo y los acordes

        Todo se mide en proporcion al tamano de la imagen, asi funciona con
        cualquier resolucion de camara
        """
        self.botones = []
        self.titulos = []
        x0, x1 = int(w * 0.42), int(w * 0.88)   # columna de los botones
        y = int(h * 0.13)
        for clave, titulo, opciones in LISTAS:
            self.titulos.append((titulo, x0, y + 6))
            bw = (x1 - x0) / len(opciones)      # ancho de cada boton de la fila
            for i, op in enumerate(opciones):
                self.botones.append((int(x0 + i * bw) + 3, y + 12,
                                     int(x0 + (i + 1) * bw) - 3,
                                     y + 12 + int(h * 0.07), clave, op))
            y += int(h * 0.135)
        self.centro_circulo = (int(w * 0.23), int(h * 0.55))
        self.radio = int(h * 0.25)

        # Play: el acorde de cada mano en su mitad de la pantalla (con efecto
        # espejo la izquierda se ve a la izquierda)
        self.centros = {"Izquierda": int(w * 0.25), "Derecha": int(w * 0.75)}

    def _aplauso(self, der, izq, t):
        """Aplauso = prender o apagar el beat

        Se guarda la distancia entre las palmas de los ultimos 0.4 s
        Es aplauso si ahora estan juntas (menos de 1.3 tamanos de mano) y
        hace un momento estaban lejos (mas de 2.5); despues se esperan 0.8 s
        para no contar el mismo aplauso dos veces
        """
        if der is None or izq is None:
            return
        (xa, ya), (xb, yb) = der.centro(), izq.centro()
        d = math.hypot(xa - xb, ya - yb) / ((der.tamano + izq.tamano) / 2)
        self.distancias.append((t, d))
        while self.distancias and t - self.distancias[0][0] > 0.4:
            self.distancias.popleft()
        lejos = max(x for _, x in self.distancias) > 2.5
        if d < 1.3 and lejos and t - self.ultimo_aplauso > 0.8:
            self.motor.alternar_beat()
            self.ultimo_aplauso = t
            self.distancias.clear()

    def _doble_puno(self, der, izq, t):
        """Doble puno sostenido 1 s = cambiar de modo

        Regresa True mientras las manos sigan cerradas despues de cambiar,
        para que no se regrese de modo solo
        """
        ambos = (der is not None and izq is not None
                 and der.puno_completo() and izq.puno_completo())
        if not ambos:
            self.puno_desde = None
            self.esperar_soltar = False
            return False
        if self.esperar_soltar:
            return True
        if self.puno_desde is None:
            self.puno_desde = t         # empieza a contar (barra de progreso)
        elif t - self.puno_desde >= TIEMPO_CAMBIO:
            self.cambiar_modo()
            self.puno_desde = None
            self.esperar_soltar = True
        return False

    # ------------------------------------------------------ modo Configurar

    def _configurar(self, der, izq, t, alto):
        """Gestos del modo Configurar

        Mano derecha
          pellizco + subir/bajar = volumen
          pulgar arriba / abajo = Mayor / menor
          indice alzado = cursor
        Mano izquierda
          pellizco + subir/bajar = tempo
          mano abierta + girar = tonalidad (la rueda)
          indice alzado = cursor (si la derecha no esta apuntando)
        Con el cursor cada mano elige SU instrumento y ritmo
        """
        puntero = None
        if der is not None:
            dedo = der.pellizco(self.pellizcos.get("Derecha"))
            self.pellizcos["Derecha"] = dedo
            if dedo == 1:
                self._arrastrar("Derecha", der, "volumen", 0.0, 1.0, alto)
            else:
                self.arrastre.pop("Derecha", None)
            # Pulgar arriba / abajo: gestos que ya reconoce el modelo de MediaPipe
            if der.gesto == "Thumb_Up" and self.escala != "Mayor":
                self.escala = "Mayor"
                self.motor.efecto("clic")
            elif der.gesto == "Thumb_Down" and self.escala != "menor":
                self.escala = "menor"
                self.motor.efecto("clic")
            if dedo is None and der.apuntando():
                puntero = der
        else:
            # Si la mano desaparece se olvida lo que estaba haciendo
            self.pellizcos.pop("Derecha", None)
            self.arrastre.pop("Derecha", None)

        if izq is not None:
            dedo = izq.pellizco(self.pellizcos.get("Izquierda"))
            self.pellizcos["Izquierda"] = dedo
            if dedo == 1:
                self._arrastrar("Izquierda", izq, "bpm", 60, 160, alto)
            else:
                self.arrastre.pop("Izquierda", None)
            if dedo is None and izq.abierta():
                self._girar(izq)
            else:
                self.giro = None
            if puntero is None and dedo is None and izq.apuntando():
                puntero = izq
        else:
            self.pellizcos.pop("Izquierda", None)
            self.arrastre.pop("Izquierda", None)
            self.giro = None

        # Si cambia la mano que apunta, empieza a contar de nuevo
        if puntero is None or self.puntero is None or (
                puntero.lado != self.puntero.lado):
            self.boton = None
        self.puntero = puntero
        if puntero is not None:
            self._cursor(puntero, t)

    def _arrastrar(self, lado, mano, clave, minimo, maximo, alto):
        """Pellizcar y subir/bajar la mano: como agarrar una perilla

        Al empezar el pellizco se guarda la altura de la mano y el valor
        Despues: valor = valor inicial + cuanto subio la mano / media pantalla
        multiplicado por el rango (60 a 160 BPM o 0 a 100 % de volumen)
        """
        y = mano.centro()[1]
        if lado not in self.arrastre:
            self.arrastre[lado] = (y, self.ajustes[clave])
        y0, v0 = self.arrastre[lado]
        # En la imagen la y crece hacia abajo, por eso y0 - y = cuanto subio
        v = v0 + (y0 - y) / (alto * 0.5) * (maximo - minimo)
        v = min(maximo, max(minimo, v))
        v = int(round(v)) if clave == "bpm" else round(v, 2)
        if v != self.ajustes[clave]:
            self.ajustes[clave] = v
            self.motor.ajustar(**{clave: v})

    def _girar(self, mano):
        """Mano abierta girando: el circulo de tonalidades gira con ella

        Al abrir la mano se guarda su angulo; cada 20 grados de giro desde
        ahi mueve una tonalidad. Para llegar mas lejos se cierra la mano, se
        regresa y se vuelve a girar (como una llave de tuercas)
        """
        angulo = mano.angulo()
        if self.giro is None:
            self.giro = (angulo, self.circulo)
            return
        a0, c0 = self.giro
        # Diferencia de angulos entre -180 y 180 (para no brincar en 179 -> -179)
        delta = (angulo - a0 + 180) % 360 - 180
        # Girar en el sentido del reloj avanza en el circulo (Do -> Sol -> Re)
        nuevo = (c0 - int(delta / GRADOS_POR_TONALIDAD)) % 12
        if nuevo != self.circulo:
            self.circulo = nuevo
            self.motor.efecto("clic")

    def _cursor(self, mano, t):
        """Indice sobre un boton durante TIEMPO_BOTON segundos = elegirlo

        Sostener para confirmar (dwell) evita elegir algo solo por pasar
        el dedo encima
        """
        x, y = mano.punta_indice()
        encima = next((b for b in self.botones
                       if b[0] <= x <= b[2] and b[1] <= y <= b[3]), None)
        if encima != self.boton:
            # Llego a otro boton (o salio): empieza a contar de nuevo
            self.boton = encima
            self.boton_desde = t
            self.boton_listo = False
        elif (encima is not None and not self.boton_listo
              and t - self.boton_desde >= TIEMPO_BOTON):
            self.boton_listo = True
            self._elegir(encima[4], encima[5], mano.lado)

    def _elegir(self, clave, valor, lado):
        """Aplica una opcion elegida con el cursor

        Instrumento y ritmo son de la mano que apunto (lado)
        Beat, beat sonando y senas son de las dos
        """
        if clave == "activo":
            # Encender o apagar el beat (lo mismo que aplaudir)
            if (valor == "Encendido") != self.motor.beat_activo:
                self.motor.alternar_beat()
                self.motor.efecto("clic")
            return
        ajustes = self.por_mano[lado] if clave in POR_MANO else self.ajustes
        if ajustes[clave] == valor:
            return
        ajustes[clave] = valor
        if clave in POR_MANO:
            self.motor.ajustar(mano=lado, **{clave: valor})
        elif clave not in SOLO_INTERFAZ:
            self.motor.ajustar(**{clave: valor})
        # Al elegir un beat se prende de una vez para escucharlo
        if clave == "beat" and not self.motor.beat_activo:
            self.motor.alternar_beat()
        self.motor.efecto("clic")

    def elegido_por(self, clave, valor):
        """Manos que tienen elegida esa opcion (para pintar el boton)

        Para las opciones de las dos manos regresa ["Las dos"] si esta elegida
        """
        if clave in POR_MANO:
            return [lado for lado in MANOS if self.por_mano[lado][clave] == valor]
        if clave == "activo":
            actual = "Encendido" if self.motor.beat_activo else "Apagado"
            return ["Las dos"] if actual == valor else []
        return ["Las dos"] if self.ajustes[clave] == valor else []

    # ------------------------------------------------------------ modo Play

    def _tocar(self, manos):
        """Gestos del modo Play: cada mano toca su acorde

        Sena = grado, acostarla de lado = Mayor <-> menor, altura = octava
        Las dos manos tocan al mismo tiempo, cada una con su instrumento y
        su ritmo. Si una mano no se ve o no hace ninguna sena, esa no suena
        """
        for lado in MANOS:
            self._acordes(self.tocadores[lado], manos.get(lado))

    def _acordes(self, tocador, mano):
        """Una mano de acordes: sena = grado, altura = octava, inclinacion = Mayor/menor

        El acorde suena solo mientras la mano hace una sena; si no se ve o
        no hace ninguna, se calla
        """
        bajar = self.ajustes["senas"] == "Bajar dedos"
        grado = mano.grado(bajar) if mano is not None else None
        if grado is None:
            self._poner_acorde(tocador, None)
            return
        self._altura(tocador, mano)
        self._inclinar(tocador, mano)
        self._poner_acorde(tocador, (grado, tocador.octava))

    def _altura(self, tocador, mano):
        """Franja de la pantalla donde esta la palma = octava del acorde

        Arriba = aguda, en medio = media, abajo = grave
        Mientras la palma siga en su franja (o dentro del margen) no cambia
        """
        y = mano.centro()[1] / self.alto
        lo, hi = FRANJAS_ACORDE[tocador.octava]
        if lo - MARGEN_OCTAVA <= y < hi + MARGEN_OCTAVA:
            return
        tocador.octava = 1 if y < 1 / 3 else (0 if y < 2 / 3 else -1)

    def _inclinar(self, tocador, mano):
        """Mano acostada de lado = invertir el acorde poco a poco

        mezcla 0 = normal, 1 = invertido (Mayor -> menor o menor -> Mayor)
        En medio la tercera se desliza entre las dos, como doblar una cuerda
        """
        inc = mano.inclinacion()
        mezcla = (inc - INCLINA_INICIO) / (INCLINA_FIN - INCLINA_INICIO)
        mezcla = round(min(1.0, max(0.0, mezcla)), 2)
        if mezcla != tocador.mezcla:
            tocador.mezcla = mezcla
            self.motor.doblar(mezcla, mano=tocador.lado)

    def _poner_acorde(self, tocador, deseado):
        """Cambia el acorde solo si la misma sena se mantiene unos cuadros

        Al pasar de una sena a otra la mano cruza posiciones intermedias;
        sin esta espera sonarian acordes de paso
        deseado: (grado, octava) o None para silencio
        La inclinacion no pasa por aqui: se manda directo al motor con
        doblar() para que el deslizamiento responda al instante
        """
        if deseado == tocador.candidato:
            tocador.cuenta += 1
        else:
            tocador.candidato = deseado
            tocador.cuenta = 1
        # Para cambiar de acorde bastan 2 cuadros (responde rapido); para
        # callar se piden 3, porque al pasar de una sena a otra la mano
        # puede verse un instante sin sena y no queremos que se corte
        necesarios = CUADROS_SILENCIO if deseado is None else CUADROS_ESTABLES
        if tocador.cuenta < necesarios or deseado == tocador.acorde:
            return
        tocador.acorde = deseado
        if deseado is None:
            tocador.info = tocador.info_inv = None
            self.motor.poner_acorde(None, mano=tocador.lado)
            return
        grado, octava = deseado
        normal = musica.acorde_por_grado(self.tonica, self.escala, grado)
        inv = musica.acorde_por_grado(self.tonica, self.escala, grado,
                                      invertir=True)
        # Subir o bajar todo el acorde 12 semitonos por octava
        for acorde in (normal, inv):
            acorde["notas"] = [n + 12 * octava for n in acorde["notas"]]
        tocador.info, tocador.info_inv = normal, inv
        # La nota movil es la unica que cambia entre normal e invertido
        # (la tercera, o la quinta en el disminuido) y se mueve 1 semitono
        movil = next((a, b - a) for a, b in zip(normal["notas"], inv["notas"])
                     if a != b)
        tocador.movil = movil
        # Notas de la escala desde la raiz, para el ritmo Secuencia
        escalera = musica.escalera(self.tonica, self.escala, grado, octava)
        self.motor.poner_acorde(normal["notas"], movil, mano=tocador.lado,
                                escalera=escalera)

    def _callar(self, lado=None):
        """Silencia el acorde de esa mano, o de las dos si lado=None

        Se usa al cambiar de modo
        """
        for tocador in self.tocadores.values():
            if lado is not None and tocador.lado != lado:
                continue
            m = tocador.lado
            tocador.candidato = None
            tocador.cuenta = 0
            if tocador.acorde is not None:
                self.motor.poner_acorde(None, mano=m)
            tocador.acorde = None
            tocador.info = tocador.info_inv = None
            if tocador.mezcla:
                tocador.mezcla = 0.0
                self.motor.doblar(0.0, mano=m)

    # ============================================================ dibujo

    def dibujar(self, frame, manos, t):
        """Pinta todo encima del cuadro de video"""
        h, w = frame.shape[:2]

        # Esqueleto de cada mano: azul la derecha, naranja la izquierda
        for mano in manos.values():
            color = COLOR_MANO[mano.lado]
            pts = [(int(x), int(y)) for x, y in mano.puntos]
            for a, b in CONEXIONES:
                cv2.line(frame, pts[a], pts[b], color, 2)
            for p in pts:
                cv2.circle(frame, p, 3, VERDE, -1)

        # Barra de estado de arriba: siempre muestra todos los ajustes
        # Renglon 1: lo general. Renglon 2: lo de cada mano en su color
        a = self.ajustes
        cv2.rectangle(frame, (0, 0), (w, 58), OSCURO, -1)
        estado = "on" if self.motor.beat_activo else "off"
        escribir(frame, f"{self.modo.upper()} | "
                 f"{musica.nombre_tonalidad(self.tonica, self.escala)} | "
                 f"Beat: {a['beat']} ({estado}) | {a['bpm']} BPM | "
                 f"Vol {int(a['volumen'] * 100)}%", (10, 23), 0.55)
        for lado, x in (("Izquierda", 10), ("Derecha", w // 2)):
            m = self.por_mano[lado]
            escribir(frame, f"{CORTO[lado]}: {m['instrumento']}, {m['ritmo']}",
                     (x, 48), 0.55, COLOR_MANO[lado])

        # Indicador de pulso: 4 circulos, se llena el tiempo que suena
        if self.motor.beat_activo:
            for i in range(4):
                lleno = -1 if self.motor.paso // 4 == i else 2
                cv2.circle(frame, (w - 90 + i * 22, 76), 7, VERDE, lleno)

        if self.modo == "Configurar":
            self._dibujar_configurar(frame, manos, t)
        else:
            self._dibujar_play(frame, t)

        # Barra de progreso del doble puno
        if self.puno_desde is not None:
            avance = min(1.0, (t - self.puno_desde) / TIEMPO_CAMBIO)
            cv2.rectangle(frame, (w // 2 - 150, 70), (w // 2 + 150, 90),
                          GRIS, 2)
            cv2.rectangle(frame, (w // 2 - 150, 70),
                          (w // 2 - 150 + int(300 * avance), 90), VERDE, -1)
            escribir(frame, "Cambiando de modo...", (w // 2 - 110, 115))

        # Linea de ayuda de abajo con los gestos del modo actual
        if self.modo == "Configurar":
            ayuda = ("Indice = elegir | Izq: abierta y girar = tonalidad, "
                     "pellizco = tempo | Der: pulgar arriba/abajo = "
                     "Mayor/menor, pellizco = volumen")
        else:
            verbo = "baja" if a["senas"] == "Bajar dedos" else "alza"
            ayuda = (f"Las dos manos: {verbo} dedos = acorde, acostar = "
                     "Mayor/menor, altura = octava")
        escribir(frame, ayuda + " | doble puno: modo | aplauso: beat",
                 (10, h - 12), 0.45)

    def _dibujar_configurar(self, frame, manos, t):
        """Pantalla de Configurar: barras, circulo, botones y cursor"""
        h, w = frame.shape[:2]
        a = self.ajustes

        # Barras verticales: tempo a la izquierda, volumen a la derecha
        for x, titulo, valor, frac in [
                (35, "Tempo", f"{a['bpm']}", (a["bpm"] - 60) / 100),
                (w - 35, "Volumen", f"{int(a['volumen'] * 100)}%",
                 a["volumen"])]:
            y0, y1 = int(h * 0.85), int(h * 0.2)
            cv2.line(frame, (x, y0), (x, y1), GRIS, 6)
            yv = int(y0 + (y1 - y0) * frac)
            cv2.line(frame, (x, y0), (x, yv), AZUL, 6)
            cv2.circle(frame, (x, yv), 10, AZUL, -1)
            escribir(frame, titulo, (x - 30, y1 - 28), 0.5)
            escribir(frame, valor, (x - 15, y1 - 10), 0.5)

        # Circulo de tonalidades: 12 nombres repartidos cada 30 grados
        cx, cy = self.centro_circulo
        cv2.circle(frame, (cx, cy), self.radio, GRIS, 1)
        for i, pc in enumerate(musica.CIRCULO):
            ang = math.radians(90 - i * 30)   # empieza arriba y va con el reloj
            x = int(cx + self.radio * 0.8 * math.cos(ang))
            y = int(cy - self.radio * 0.8 * math.sin(ang))
            if i == self.circulo:
                cv2.circle(frame, (x, y), 22, AZUL, -1)
            escribir(frame, musica.NOMBRES[pc], (x - 15, y + 6), 0.55)
        escribir(frame, musica.nombre_tonalidad(self.tonica, self.escala),
                 (cx - 55, cy + 8), 0.7, VERDE, 2)
        if self.giro is not None:
            escribir(frame, "Girando: tonalidad", (cx - 80, cy + self.radio + 30))

        # Botones
        #   instrumento y ritmo: azul = lo eligio la derecha,
        #   naranja = la izquierda, mitad y mitad = las dos
        #   beat y senas (de las dos manos): verde
        #   borde del color de la mano que esta apuntando encima
        for titulo, x, y in self.titulos:
            escribir(frame, titulo, (x, y), 0.55)
        for x0, y0, x1, y1, clave, valor in self.botones:
            quien = self.elegido_por(clave, valor)
            if quien == ["Las dos"]:
                cv2.rectangle(frame, (x0, y0), (x1, y1), GENERAL, -1)
            elif len(quien) == 2:
                # Izquierda en la mitad izquierda, derecha en la derecha
                xm = (x0 + x1) // 2
                cv2.rectangle(frame, (x0, y0), (xm, y1), NARANJA, -1)
                cv2.rectangle(frame, (xm, y0), (x1, y1), AZUL, -1)
            elif quien:
                cv2.rectangle(frame, (x0, y0), (x1, y1), COLOR_MANO[quien[0]], -1)
            else:
                cv2.rectangle(frame, (x0, y0), (x1, y1), OSCURO, -1)
            encima = self.boton and self.boton[:4] == (x0, y0, x1, y1)
            borde = COLOR_MANO[self.puntero.lado] if encima and self.puntero else GRIS
            cv2.rectangle(frame, (x0, y0), (x1, y1), borde, 4 if encima else 2)
            escribir(frame, valor, (x0 + 6, y1 - 12), 0.45)

        # Instruccion y cursor en la punta del indice con anillo de progreso
        ultimo = self.botones[-1]
        escribir(frame, "Para elegir: alza solo el indice, ponlo sobre una "
                 "opcion y sostenlo", (self.botones[0][0], ultimo[3] + 28),
                 0.5, BLANCO)
        escribir(frame, "Cada mano elige su instrumento y su ritmo",
                 (self.botones[0][0], ultimo[3] + 52), 0.5, BLANCO)
        escribir(frame, "Derecha", (self.botones[0][0], ultimo[3] + 76), 0.5,
                 AZUL, 2)
        escribir(frame, "Izquierda", (self.botones[0][0] + 90, ultimo[3] + 76),
                 0.5, NARANJA, 2)
        if self.puntero is not None:
            color = COLOR_MANO[self.puntero.lado]
            x, y = map(int, self.puntero.punta_indice())
            cv2.circle(frame, (x, y), 9, color, -1)
            cv2.circle(frame, (x, y), 18, color, 1)
            if self.boton is not None:
                avance = min(1.0, (t - self.boton_desde) / TIEMPO_BOTON)
                cv2.ellipse(frame, (x, y), (18, 18), -90, 0, 360 * avance,
                            color, 5)

        # Herramienta activa: que se esta controlando con el pellizco
        if "Derecha" in self.arrastre:
            escribir(frame, f"Pellizco: Volumen {int(a['volumen'] * 100)}%",
                     (int(w * 0.42), h - 40), 0.6, AZUL, 2)
        if "Izquierda" in self.arrastre:
            escribir(frame, f"Pellizco: Tempo {a['bpm']} BPM",
                     (int(w * 0.42), h - 70), 0.6, NARANJA, 2)

    def _dibujar_play(self, frame, t):
        """Pantalla de Play: el acorde de cada mano, cada una en su mitad"""
        h, w = frame.shape[:2]
        cv2.line(frame, (w // 2, 70), (w // 2, h - 30), GRIS, 1)
        for lado in MANOS:
            self._dibujar_acorde(frame, self.tocadores[lado],
                                 self.centros[lado], t)

    def _dibujar_acorde(self, frame, tocador, cx, t):
        """Lo de una mano: su acorde, la barra de inclinacion, los 7 grados
        con el acorde de cada uno y abajo las ondas del acorde que suena"""
        h, w = frame.shape[:2]
        color_mano = COLOR_MANO[tocador.lado]
        escribir_centrado(frame, tocador.lado, cx, int(h * 0.19), 0.6,
                          color_mano, 2)
        y = int(h * 0.33)
        if tocador.info is not None:
            # Pasando la mitad de la inclinacion ya se ve el invertido
            info = tocador.info_inv if tocador.mezcla >= 0.5 else tocador.info
            color = COLORES_GRADO[tocador.acorde[0]]
            escribir_centrado(frame, info["numeral"], cx, y, 1.6, color, 3)
            escribir_centrado(frame, info["nombre"], cx, y + 38, 0.65)
            # Barra de inclinacion: cuanto se ha deslizado la tercera
            yb = y + 75
            cv2.line(frame, (cx - 70, yb), (cx + 70, yb), GRIS, 6)
            cv2.line(frame, (cx - 70, yb),
                     (cx - 70 + int(140 * tocador.mezcla), yb), color, 6)
            escribir(frame, tocador.info["nombre"].split()[-1][:3],
                     (cx - 115, yb + 5), 0.45)
            escribir(frame, tocador.info_inv["nombre"].split()[-1][:3],
                     (cx + 78, yb + 5), 0.45)

        # Los 7 grados de la tonalidad y abajo de cada uno su acorde
        # (cambian solos con la tonalidad); el que suena, resaltado
        yg = int(h * 0.53)
        for g in range(7):
            acorde = musica.acorde_por_grado(self.tonica, self.escala, g)
            xg = cx + (g - 3) * 52
            activo = tocador.acorde is not None and tocador.acorde[0] == g
            color = COLORES_GRADO[g] if activo else GRIS
            escribir_centrado(frame, acorde["numeral"], xg, yg, 0.7, color,
                              2 if activo else 1)
            escribir_centrado(frame, acorde["corto"], xg, yg + 24, 0.42,
                              color if activo else BLANCO)

        # Ondas del acorde que suena, del color de su grado
        x0, x1 = cx - w // 4 + 30, cx + w // 4 - 30
        yo = int(h * 0.79)
        if tocador.info is not None:
            dibujar_ondas(frame, x0, x1, yo, h * 0.09, tocador.info["notas"],
                          COLORES_GRADO[tocador.acorde[0]], t,
                          tocador.mezcla, tocador.movil)
        else:
            cv2.line(frame, (x0, yo), (x1, yo), OSCURO, 2)


# ===================================================== camara y MediaPipe

def leer_manos(resultado, ancho, alto):
    """Convierte el resultado de MediaPipe en {"Derecha": Mano, "Izquierda": Mano}

    resultado.hand_landmarks: los 21 puntos de cada mano (de 0 a 1)
    resultado.handedness: si cada mano es "Left" o "Right"
    resultado.gestures: el gesto que reconocio el modelo en cada mano
    """
    manos = {}
    for i, (puntos, lados) in enumerate(zip(resultado.hand_landmarks,
                                            resultado.handedness)):
        # Lado de la mano (corregido con INVERTIR_MANOS)
        derecha = (lados[0].category_name == "Right") != INVERTIR_MANOS
        lado = "Derecha" if derecha else "Izquierda"

        # Gesto del modelo, solo si esta al menos 60 % seguro
        gesto = None
        if i < len(resultado.gestures) and resultado.gestures[i]:
            g = resultado.gestures[i][0]
            if g.score >= 0.6:
                gesto = g.category_name

        # Puntos de proporcion (0 a 1) a pixeles de la imagen
        manos[lado] = Mano([(p.x * ancho, p.y * alto) for p in puntos],
                           lado, gesto)
    return manos


def main():
    # Modelo de MediaPipe (red neuronal ya entrenada por Google)
    modelo = Path(__file__).with_name("gesture_recognizer.task")
    if not modelo.is_file():
        print("Falta gesture_recognizer.task en la carpeta del programa")
        return

    # Opciones del detector
    #   VIDEO: usa el cuadro anterior para seguir las manos mas rapido
    #   num_hands=2: AQUI se le dice que busque hasta dos manos
    opciones = mp.tasks.vision.GestureRecognizerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(modelo)),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_hands=2,
    )

    # Camara 0 (la principal) a 1280 x 720
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("No se pudo abrir la camara. Revisa los permisos")
        return
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    # Guardar solo 1 cuadro: asi siempre se procesa el mas reciente y no
    # uno viejo que se quedo esperando (menos retraso entre mano y sonido)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    # Motor de audio: carga beats y sonidos y abre la tarjeta de sonido
    motor = audio.Motor()
    beats = [b for b in audio.BEATS if b != "Hi-hat"]
    print("Beats cargados de beats/:", ", ".join(beats) or "ninguno")
    for aviso in motor.avisos:
        print("Aviso:", aviso)
    motor.iniciar()
    print(f"Retraso de la tarjeta de sonido: {motor.latencia_ms:.0f} ms")

    app = App(motor)
    ultimo_ms = -1
    print("Mano Sonora: q = salir, m = cambiar modo, espacio = beat on/off")

    try:
        with mp.tasks.vision.GestureRecognizer.create_from_options(
                opciones) as detector:
            while True:
                # 1. Leer un cuadro de la camara
                ret, frame = cap.read()
                if not ret:
                    print("No se pudo leer la camara")
                    break
                # Efecto espejo: mover la mano a la derecha se ve a la derecha
                frame = cv2.flip(frame, 1)
                alto, ancho = frame.shape[:2]

                # 2. Detectar las manos con MediaPipe
                # Se usa una copia mas chica (640 px): es mas rapido y los
                # puntos vienen en proporcion (0 a 1) de todos modos
                chica = cv2.resize(frame, (640, int(640 * alto / ancho)))
                # OpenCV guarda los colores como BGR y MediaPipe usa RGB
                rgb = cv2.cvtColor(chica, cv2.COLOR_BGR2RGB)
                imagen = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                # El modo VIDEO pide un tiempo en ms que siempre vaya creciendo
                ms = max(time.monotonic_ns() // 1_000_000, ultimo_ms + 1)
                ultimo_ms = ms
                resultado = detector.recognize_for_video(imagen, ms)

                # 3. Puntos -> gestos -> decisiones -> sonido
                manos = leer_manos(resultado, ancho, alto)
                t = time.monotonic()
                app.actualizar(manos, t, ancho, alto)

                # 4. Dibujar y mostrar
                app.dibujar(frame, manos, t)
                cv2.imshow("Mano Sonora", frame)

                # Teclas de respaldo
                tecla = cv2.waitKey(1) & 0xFF
                if tecla == ord("q"):
                    break
                if tecla == ord("m"):
                    app.cambiar_modo()
                if tecla == ord(" "):
                    motor.alternar_beat()
    except KeyboardInterrupt:
        pass
    finally:
        # Al salir: callar, cerrar audio, camara y ventanas
        for lado in audio.MANOS:
            motor.poner_acorde(None, mano=lado)
        time.sleep(0.2)
        motor.detener()
        cap.release()
        cv2.destroyAllWindows()
        for _ in range(5):
            cv2.waitKey(1)


if __name__ == "__main__":
    main()
