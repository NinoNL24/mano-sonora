"""
audio.py - Motor de sonido de Mano Sonora

Que hace
  - Abre la tarjeta de sonido y genera el audio en bloques de 256 muestras
  - Un reloj divide cada compas en 16 pasos segun el tempo (BPM)
    con el se tocan los golpes y arpegios del acorde
  - Toca los beats: cada .mid de la carpeta beats/ es un patron y se toca
    con los sonidos .wav de beats/sonidos/
  - Genera los instrumentos con matematicas (numpy)
      Pad: senoidales
      Piano: sintesis FM
      Guitarra: algoritmo Karplus-Strong
      8 bits: onda cuadrada

Como se comunica con el resto del programa
  main.py corre en el hilo de video y nunca toca el audio directamente
  Solo deja mensajes en una cola ("pon este acorde", "sube el volumen")
  El hilo de audio los lee al empezar cada bloque
  Asi, aunque la camara se trabe, el sonido no se corta
"""

from collections import deque
import math
from pathlib import Path
import wave

import numpy as np

import musica

def _elegir_salida():
    """Tarjeta de sonido y muestras por segundo con el menor retraso posible

    En Windows hay varias formas de mandar audio a la tarjeta. La normal
    (MME) tarda ~100 ms en sonar; WASAPI tarda ~20 ms, pero hay que usar
    las muestras por segundo de la tarjeta (casi siempre 48000)
    Si no hay WASAPI se usa la normal a 44100 (calidad de CD)
    """
    try:
        import sounddevice as sd
        for api in sd.query_hostapis():
            if "WASAPI" in api["name"] and api["default_output_device"] >= 0:
                disp = api["default_output_device"]
                return disp, int(sd.query_devices(disp)["default_samplerate"])
    except Exception:
        pass
    return None, 44100


SALIDA, SR = _elegir_salida()   # SR = muestras por segundo
BLOQUE = 256    # muestras que pide la tarjeta de sonido cada vez (~5 ms)
PASOS = 16      # pasos por compas: cada paso es una semicorchea

# Opciones que aparecen en los menus de Configurar
INSTRUMENTOS = ["Pad", "Piano", "Guitarra", "8 bits", "Sinte"]
RITMOS = ["Sostenido", "Golpes", "Arpegio", "Secuencia"]

# Patron del ritmo Secuencia: 16 pasos (semicorcheas), como el secuenciador
# de un sintetizador
# Cada numero es una nota de la ESCALA contada desde la raiz del acorde
# que hace la mano:
#   0 = raiz   1 = la nota que sigue   2 = tercera   4 = quinta
#   7 = raiz una octava arriba   -1, -2 ... = notas de abajo
#   None = silencio
# Como esta en pasos de la escala, el patron sigue al acorde y a la
# tonalidad: cambias de acorde y la misma figura suena desde otra nota
# Este es el intro que pasaste en tablatura (compases 1 y 2): en Do# menor
# con el acorde i suena tal cual. En la tablatura va en corcheas a 168,
# aqui en semicorcheas, asi que el tempo equivalente es 84 BPM
SECUENCIA = [-3, 0, 1, 2, 4, 7, 8, 9,
             8, 7, 4, 2, 1, 0, -3, 0]

# Pasos que dura cada nota de la Secuencia
# Mas de 1 = las notas se enciman y resuenan ("let ring" de la tablatura)
DURA_SECUENCIA = 3

# Carpeta donde van los beats .mid y la subcarpeta sonidos/ con los .wav
CARPETA_BEATS = Path(__file__).with_name("beats")

# Nota MIDI -> nombre del .wav, segun el estandar de bateria General MIDI
# Tambien se puede nombrar el archivo con el numero de nota (36.wav) o
# cambiar esta tabla con beats/sonidos/mapa.txt (lineas "36 = bombo")
NOTAS_GM = {
    35: "bombo", 36: "bombo", 37: "aro", 38: "tarola", 40: "tarola",
    39: "aplauso", 42: "hihat", 44: "hihat", 46: "hihat_abierto",
    49: "platillo", 57: "platillo", 51: "ride", 53: "ride", 59: "ride",
    41: "tom_bajo", 43: "tom_bajo", 45: "tom_medio", 47: "tom_medio",
    48: "tom_alto", 50: "tom_alto", 54: "pandero", 56: "cencerro",
}

# Volumen de cada parte de la mezcla
GANANCIA_BATERIA = 0.7
GANANCIA_ACORDE = 0.22   # por nota (el acorde tiene 4 notas)
GANANCIA_MELODIA = 0.45  # la melodia suena mas fuerte que cada nota del acorde

# Segundos que tarda en apagarse una nota al soltarla, por instrumento
CAIDA = {"Pad": 0.6, "Piano": 0.25, "Guitarra": 0.1, "8 bits": 0.08,
         "Sinte": 0.06}


# ======================================================== sonidos y archivos

def _tiempo(segundos):
    """Arreglo con el tiempo de cada muestra (0, 1/SR, 2/SR, ...)"""
    return np.arange(int(SR * segundos)) / SR


def _ruido(n, semilla):
    """n muestras de ruido entre -1 y 1 (siempre el mismo para cada semilla)"""
    return np.random.default_rng(semilla).uniform(-1, 1, n)


def _suavizar(x, k):
    """Promedio movil de k muestras: un filtro pasa-bajas sencillo"""
    return np.convolve(x, np.ones(k) / k, mode="same")


def leer_wav(ruta):
    """Lee un WAV y lo regresa como mono a SR muestras por segundo con valores de -1 a 1

    Acepta 8, 16, 24 o 32 bits; el estereo se promedia a mono y si viene a
    otra frecuencia (por ejemplo 48 kHz) se convierte con interpolacion
    """
    with wave.open(str(ruta), "rb") as w:
        canales, ancho = w.getnchannels(), w.getsampwidth()
        frecuencia, datos = w.getframerate(), w.readframes(w.getnframes())

    # Convertir los bytes a numeros segun cuantos bytes usa cada muestra
    if ancho == 1:
        x = (np.frombuffer(datos, np.uint8).astype(float) - 128) / 128
    elif ancho == 2:
        x = np.frombuffer(datos, "<i2") / 32768
    elif ancho == 3:
        # numpy no tiene enteros de 24 bits: se arman con los 3 bytes
        b = np.frombuffer(datos, np.uint8).reshape(-1, 3).astype(np.int32)
        x = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        x = np.where(x >= 2 ** 23, x - 2 ** 24, x) / 2 ** 23
    else:
        x = np.frombuffer(datos, "<i4") / 2 ** 31

    # Mono: promedio de los canales
    x = x.reshape(-1, canales).mean(axis=1)

    # Cambiar a SR muestras por segundo si hace falta
    if frecuencia != SR:
        x = np.interp(np.arange(0, len(x), frecuencia / SR),
                      np.arange(len(x)), x)
    return x


class Patron:
    """Un beat leido de un archivo MIDI: cuando suena cada golpe

    golpes: lista de (posicion en pasos, nota MIDI, fuerza 1-127)
    largo: cuantos pasos dura el patron antes de repetirse (16 por compas)
    notas: notas MIDI que usa, para saber que .wav hay que cargar
    """

    def __init__(self, ruta=None, golpes=None):
        if golpes is not None:
            # Patron hecho en el codigo (como el Hi-hat), sin archivo
            self.golpes = sorted(golpes)
            self.largo = PASOS
            self.notas = sorted({n for _, n, _ in golpes})
            return
        import mido   # biblioteca para leer archivos MIDI
        archivo = mido.MidiFile(str(ruta))
        golpes = []
        for pista in archivo.tracks:
            # En MIDI cada mensaje trae el tiempo desde el anterior (en ticks)
            # se van sumando para saber el tiempo absoluto
            tick = 0
            for msg in pista:
                tick += msg.time
                if msg.type == "note_on" and msg.velocity > 0:
                    # ticks -> pasos: una negra son ticks_per_beat ticks y
                    # tiene 4 pasos (semicorcheas)
                    # Se guarda con decimales para respetar el swing
                    pos = tick / archivo.ticks_per_beat * 4
                    golpes.append((pos, msg.note, msg.velocity))
        if not golpes:
            raise ValueError("no tiene notas")
        self.golpes = sorted(golpes)

        # Largo en compases completos: si el ultimo golpe esta en el primer
        # compas dura 16 pasos, si esta en el segundo dura 32, etc
        ultimo = self.golpes[-1][0]
        self.largo = PASOS * max(1, math.floor(ultimo / PASOS) + 1)
        self.notas = sorted({n for _, n, _ in golpes})


HIHAT = 42   # nota General MIDI del hi-hat cerrado


def patron_hihat():
    """Beat "Hi-hat": marca el tempo como un hi-hat cerrado

    Un golpe en cada corchea (cada 2 pasos); los de cada tiempo (cada 4
    pasos) mas fuertes, asi se siente donde cae el pulso sin sonar a
    metronomo. Sirve de guia para que las secuencias y los golpes entren
    a tempo
    """
    golpes = [(p, HIHAT, 120 if p % 4 == 0 else 70) for p in range(0, PASOS, 2)]
    return Patron(golpes=golpes)


def crear_hihat():
    """Sonido de hi-hat cerrado hecho con sintesis (como una caja de ritmos 808)

    - Seis ondas cuadradas a frecuencias que no son armonicas entre si:
      suenan "metalicas", como un platillo
    - Un poco de ruido para el "tss"
    - Pasa-altas (restar el promedio de cada 4 muestras): deja solo lo agudo
    - Se apaga muy rapido (~35 ms): eso lo hace "cerrado"
    """
    t = _tiempo(0.18)
    metal = sum(np.sign(np.sin(2 * np.pi * f * 1.9 * t))
                for f in (205.3, 304.4, 369.6, 522.7, 540.0, 800.0))
    sonido = metal / 6 + 0.8 * _ruido(len(t), 9)
    sonido = sonido - _suavizar(sonido, 4)          # pasa-altas sencillo
    sonido *= np.exp(-t / 0.035) * np.minimum(1, t / 0.0005)
    return 0.5 * sonido / np.max(np.abs(sonido))


def cargar_beats(carpeta=CARPETA_BEATS):
    """Lee cada .mid de la carpeta como un beat

    El nombre del boton sale del archivo: mi_reggaeton.mid -> "Mi reggaeton"
    Regresa el diccionario {nombre: Patron} y la lista de errores
    El primero siempre es el Hi-hat, que ya viene con el programa
    """
    beats = {"Hi-hat": patron_hihat()}
    errores = []
    for ruta in sorted(Path(carpeta).glob("*.mid")):
        nombre = ruta.stem.replace("_", " ").capitalize()
        try:
            beats[nombre] = Patron(ruta)
        except Exception as e:
            errores.append(f"{ruta.name}: {e}")
    return beats, errores


def cargar_sonidos(carpeta, notas):
    """Busca y lee el .wav de cada nota MIDI que usan los beats

    Orden de busqueda para cada nota
      1. un archivo con el numero de la nota (36.wav)
      2. el nombre de mapa.txt si existe, o el nombre General MIDI (bombo.wav)
    Regresa {nota: sonido}, las notas que no tienen .wav y los errores
    """
    carpeta = Path(carpeta)

    # Tabla nota -> nombre, con los cambios de mapa.txt encima
    mapa = dict(NOTAS_GM)
    archivo_mapa = carpeta / "mapa.txt"
    if archivo_mapa.is_file():
        for linea in archivo_mapa.read_text(encoding="utf-8").splitlines():
            if "=" in linea and not linea.strip().startswith("#"):
                nota, nombre = linea.split("=", 1)
                mapa[int(nota)] = nombre.strip()

    sonidos, faltan, errores = {}, [], []
    for nota in notas:
        candidatos = [carpeta / f"{nota}.wav"]
        if nota in mapa:
            candidatos.append(carpeta / f"{mapa[nota]}.wav")
        ruta = next((c for c in candidatos if c.is_file()), None)
        if ruta is None:
            faltan.append(f"{nota} ({mapa.get(nota, 'sin nombre')})")
            continue
        try:
            sonidos[nota] = leer_wav(ruta)
        except Exception as e:
            errores.append(f"{ruta.name}: {e} (exporta en WAV PCM 16 o 24 bits)")
    return sonidos, faltan, errores


# Los beats se cargan una vez al importar este archivo, porque main.py
# necesita la lista de nombres para armar los botones del menu Beat
BEATS, ERRORES_BEATS = cargar_beats()


def crear_efectos():
    """Sonidos cortos de la interfaz: clic al elegir y whoosh al cambiar de modo"""
    # Clic: un tono agudo de 40 ms que se apaga rapido
    t = _tiempo(0.04)
    clic = 0.5 * np.sin(2 * np.pi * 1400 * t) * np.exp(-t / 0.01)

    # Whoosh: ruido suave que sube y baja, con un tono que va subiendo
    t = _tiempo(0.5)
    forma = np.sin(np.pi * t / 0.5) ** 2
    whoosh = (0.6 * _suavizar(_ruido(len(t), 5), 6) * forma
              + 0.2 * np.sin(2 * np.pi * (300 * t + 900 * t ** 2)) * forma)
    return {"clic": clic, "whoosh": whoosh}


# Cache de cuerdas de guitarra ya calculadas: frecuencia -> sonido
_cuerdas = {}


def cuerda(frecuencia, duracion=2.0):
    """Sonido de una cuerda pulsada con el algoritmo Karplus-Strong

    1. Se empieza con un pedazo de ruido del largo de una vibracion
       (un "periodo": SR / frecuencia muestras)
    2. Cada muestra nueva es el promedio de dos muestras de un periodo antes
    3. El promedio va quitando los agudos del ruido: suena como una cuerda
       que vibra y se apaga sola
    El resultado se guarda en _cuerdas para no calcularlo dos veces
    """
    clave = round(frecuencia, 2)
    if clave in _cuerdas:
        return _cuerdas[clave]

    # En notas agudas el periodo tiene pocas muestras y redondearlo desafina
    # la nota; se genera una o dos octavas abajo y luego se acelera
    # (al doble o al cuadruple de velocidad sube 1 o 2 octavas)
    acelerar = 1
    while SR / (frecuencia / acelerar) < 100:
        acelerar *= 2
    if acelerar > 1:
        grave = cuerda(frecuencia / acelerar, duracion * acelerar)
        posiciones = np.arange(int(SR * duracion)) * acelerar
        sonido = np.interp(posiciones, np.arange(len(grave)), grave)
        _cuerdas[clave] = sonido
        return sonido

    # + 0.5 compensa el medio paso de retraso que agrega el promedio
    periodo = int(round(SR / frecuencia + 0.5))
    total = int(SR * duracion)
    y = np.zeros(total + periodo)

    # Excitacion: ruido apenas suavizado, sin nivel constante (DC)
    # (si tuviera DC quedaria un "zumbido" que nunca se apaga)
    golpe = _suavizar(_ruido(periodo, int(frecuencia)), 2)
    y[:periodo] = golpe - golpe.mean()

    # y[n] = 0.498 * (y[n - periodo] + y[n - periodo + 1])
    # 0.498 * 2 = 0.996: en cada vuelta la cuerda pierde un poco de energia
    # Se calcula por pedazos de (periodo - 1) muestras porque cada pedazo
    # solo depende del anterior: numpy lo hace sin un ciclo por muestra
    pos = periodo
    while pos < total:
        fin = min(pos + periodo - 1, total)
        y[pos:fin] = 0.498 * (y[pos - periodo:fin - periodo]
                              + y[pos - periodo + 1:fin - periodo + 1])
        pos = fin

    sonido = 0.8 * y[:total]
    _cuerdas[clave] = sonido
    return sonido


# ===================================================================== voces
# Una "voz" es algo que esta sonando: una nota de un instrumento o un golpe
# de bateria. Cada voz sabe generar sus siguientes n muestras con generar(n)
# y avisa con terminada = True cuando ya no suena

class Nota:
    """Una nota de un instrumento (del acorde o de la melodia)"""

    def __init__(self, midi, instrumento, ganancia, etiqueta, pasos=None,
                 doblez=0.0, canal=None):
        self.midi = midi
        self.canal = canal          # mano que la toca: "Derecha" o "Izquierda"
        self.frecuencia = musica.frecuencia(midi)
        self.instrumento = instrumento
        self.ganancia = ganancia
        self.etiqueta = etiqueta    # "acorde" o "melodia"
        self.pasos = pasos          # pasos del reloj que dura; None = hasta soltarla
        self.t = 0                  # muestras desde que empezo
        self.suelta = None          # muestra en la que se solto (None = sonando)
        self.terminada = False
        # Doblez: semitonos que se sube o baja la nota mientras suena
        # (la tercera que se desliza de Mayor a menor). Puede tener decimales
        self.doblez = doblez
        self.f_actual = self.frecuencia * 2 ** (doblez / 12)
        self.fase = 0.0             # fase acumulada de la onda (en radianes)
        if instrumento == "Guitarra":
            # Una cuerda ya pulsada no se puede doblar en este motor: nace
            # en el semitono mas cercano a donde va la mano
            self.cuerda = cuerda(musica.frecuencia(midi + round(doblez)))

    def soltar(self):
        """Empieza a apagarse (como levantar el dedo de una tecla)"""
        if self.suelta is None:
            self.suelta = self.t

    def _sinte(self, w, segundos):
        """Sinte analogico: dos ondas de sierra con un filtro que se cierra

        Es el sonido tipico de los secuenciadores de sintetizador: cada nota
        empieza brillante ("pluck") y en ~0.1 s se vuelve redonda
        - Sierra: suma de armonicos k = 1, 2, 3 ... con volumen 1/k
          (solo los que caben abajo de 20 kHz, para que no suene sucio)
        - Filtro pasa-bajas: los armonicos arriba de la frecuencia de corte
          se bajan; el corte empieza alto y baja con el tiempo
        - Dos osciladores, uno desafinado 0.7 %: suena "gordo", como analogico
        El corte se calcula una vez por bloque (cada ~6 ms), no se nota
        """
        f = self.f_actual
        k = np.arange(1, int(min(24, 18000 / f)) + 1)
        corte = f * (1.3 + 7 * np.exp(-segundos / 0.12))
        volumen = (1 / k) / np.sqrt(1 + (k * f / corte) ** 4)
        armonicos = np.sin(np.outer(k, w)) + np.sin(np.outer(k, w * 1.007))
        return 0.5 * volumen @ armonicos

    def generar(self, n):
        """Siguientes n muestras de la nota"""
        muestras = self.t + np.arange(n)   # numero de cada muestra
        s = muestras / SR                  # tiempo en segundos

        # Fase de la onda. Se va sumando muestra por muestra (en vez de
        # 2 pi f t) para que la frecuencia pueda cambiar a media nota sin
        # que la onda brinque: asi suena el deslizamiento de la tercera
        # La frecuencia va en linea recta de la anterior a la nueva
        objetivo = self.frecuencia * 2 ** (self.doblez / 12)
        f = np.linspace(self.f_actual, objetivo, n, endpoint=False)
        paso = 2 * np.pi * f / SR
        w = self.fase + np.cumsum(paso) - paso
        self.fase = w[-1] + paso[-1]
        self.f_actual = objetivo

        if self.instrumento == "Pad":
            # Senoidal + armonicos suaves (2 y 3 veces la frecuencia)
            # + una copia desafinada 0.4 % que da efecto de coro
            onda = (0.6 * np.sin(w) + 0.2 * np.sin(2 * w)
                    + 0.05 * np.sin(3 * w) + 0.35 * np.sin(w * 1.004))
            # Entra poco a poco en 80 ms
            envolvente = np.minimum(1, s / 0.08)
        elif self.instrumento == "Piano":
            # Sintesis FM: una senoidal modula la fase de otra
            # El indice de modulacion empieza alto (sonido de campana) y baja
            # con el tiempo (sonido suave), como un piano electrico
            indice = 1.8 * np.exp(-s / 0.3)
            onda = (np.sin(w + indice * np.sin(w))
                    # "tine": un brillo muy agudo al inicio del golpe
                    + 0.15 * np.sin(14 * w) * np.exp(-s / 0.04))
            # Ataque casi inmediato y se apaga solo en ~1.5 s
            envolvente = np.minimum(1, s / 0.003) * np.exp(-s / 1.5)
        elif self.instrumento == "Guitarra":
            # La cuerda ya esta calculada: solo se lee el pedazo que toca
            fuera = muestras >= len(self.cuerda)
            onda = self.cuerda[np.minimum(muestras, len(self.cuerda) - 1)]
            envolvente = np.where(fuera, 0.0, 1.0)
        elif self.instrumento == "Sinte":
            onda = self._sinte(w, s[0])
            # Ataque inmediato, baja un poco y se queda en 60 %
            envolvente = np.minimum(1, s / 0.003) * (0.6 + 0.4 * np.exp(-s / 0.2))
        else:  # 8 bits
            # Onda cuadrada: solo +1 o -1, como las consolas viejas
            onda = 0.5 * np.sign(np.sin(w))
            envolvente = np.minimum(1, s / 0.005)

        # Si ya se solto, se apaga de forma exponencial
        if self.suelta is not None:
            desde = np.maximum(0, muestras - self.suelta)
            envolvente = envolvente * np.exp(
                -desde / (CAIDA[self.instrumento] * SR))

        self.t += n

        # Terminada cuando ya casi no se oye o cuando se acabo la cuerda
        fin = envolvente[-1]
        if (fin < 1e-3 and (self.suelta is not None or s[-1] > 0.5)) or (
                self.instrumento == "Guitarra" and self.t >= len(self.cuerda)):
            self.terminada = True
        return onda * envolvente * self.ganancia


class Golpe:
    """Un sonido ya hecho (golpe de bateria o efecto) que se toca una vez

    retraso: muestras de silencio antes de que empiece, para que el golpe
    caiga en su muestra exacta aunque no coincida con el inicio del bloque
    """

    def __init__(self, sonido, ganancia, retraso=0):
        self.sonido = sonido
        self.ganancia = ganancia
        self.i = -retraso   # posicion de lectura; negativa = aun no empieza
        self.terminada = False

    def generar(self, n):
        """Siguientes n muestras del golpe (con ceros si aun no empieza)"""
        salida = np.zeros(n)
        desde = max(0, -self.i)
        trozo = self.sonido[max(0, self.i):max(0, self.i + n)]
        salida[desde:desde + len(trozo)] = trozo * self.ganancia
        self.i += n
        self.terminada = self.i >= len(self.sonido)
        return salida


# ===================================================================== motor

MANOS = ("Derecha", "Izquierda")


class Canal:
    """Lo que toca una mano: su instrumento, su ritmo, su acorde y su melodia

    Hay un canal por mano, asi cada una puede sonar con su propia
    configuracion y las dos al mismo tiempo (por ejemplo la izquierda con
    Pad sostenido y la derecha con Piano en arpegio)
    Todo esto corre en el hilo de audio, lo usa el Motor
    """

    def __init__(self, motor, mano):
        self.motor = motor
        self.mano = mano                # "Derecha" o "Izquierda"
        self.instrumento = "Pad"
        self.ritmo = "Sostenido"
        self.acorde = None              # notas MIDI del acorde actual
        self.movil = None               # (nota que se desliza, semitonos) o None
        self.escalera = None            # paso de la escala -> nota (para Secuencia)
        self.mezcla = 0.0               # 0 = acorde normal, 1 = invertido
        self.mezcla_objetivo = 0.0      # a donde va la mezcla (lo pide la mano)

    def notas(self, etiqueta):
        """Las notas de este canal con esa etiqueta ("acorde" o "melodia")"""
        return [v for v in self.motor._voces if isinstance(v, Nota)
                and v.canal == self.mano and v.etiqueta == etiqueta]

    def soltar(self, etiqueta, midi=None):
        """Suelta las notas de este canal con esa etiqueta (todas o solo midi)"""
        for v in self.notas(etiqueta):
            if midi is None or v.midi == midi:
                v.soltar()

    def tocar(self, midi, pasos=None, ganancia=GANANCIA_ACORDE):
        """Agrega una nota del acorde a lo que esta sonando"""
        self.motor._voces.append(Nota(midi, self.instrumento, ganancia,
                                      "acorde", pasos, self.doblez(midi),
                                      self.mano))

    def nota_on(self, midi):
        """Nota de melodia (si ya sonaba se suelta y vuelve a empezar)"""
        self.soltar("melodia", midi)
        self.motor._voces.append(Nota(midi, self.instrumento,
                                      GANANCIA_MELODIA, "melodia",
                                      canal=self.mano))

    def doblez(self, midi):
        """Semitonos que hay que mover esta nota del acorde ahorita

        Solo la nota movil se mueve (en cualquier octava, por la tercera de
        arriba de la Secuencia): mezcla 0.5 = medio semitono
        """
        if self.movil is None or (midi - self.movil[0]) % 12 != 0:
            return 0.0
        return self.mezcla * self.movil[1]

    def suavizar(self):
        """Una vez por bloque: acerca la mezcla al objetivo y dobla las notas

        Se acerca 30 % en cada bloque (~20 ms para llegar): asi el
        deslizamiento es suave aunque la camara vaya a 30 cuadros por segundo
        """
        self.mezcla += (self.mezcla_objetivo - self.mezcla) * 0.3
        for v in self.notas("acorde"):
            # Las que ya se estan apagando se quedan como estaban
            if v.suelta is None:
                v.doblez = self.doblez(v.midi)

    def cambiar_acorde(self, notas):
        """Cambia el acorde segun el ritmo de esta mano"""
        self.acorde = notas
        if self.ritmo == "Sostenido":
            # Las notas que se repiten entre el acorde viejo y el nuevo
            # siguen sonando sin cortarse; las demas se sueltan
            sonando = set()
            for v in self.notas("acorde"):
                if notas and v.midi in notas and v.suelta is None:
                    sonando.add(v.midi)
                else:
                    v.soltar()
            for midi in notas or []:
                if midi not in sonando:
                    self.tocar(midi)
            return

        self.soltar("acorde")
        if not notas:
            return
        if self.ritmo == "Golpes":
            # El acorde nuevo suena de inmediato y despues sigue al reloj
            self.golpe_acorde()
            return

        # Arpegio y Secuencia: "cambio de carril"
        # No vuelven a empezar: la posicion sale del reloj, asi que solo
        # cambian las notas y el ritmo sigue igual que antes
        # Para que se oiga al instante, la nota que va sonando se cambia por
        # la del acorde nuevo en el mismo lugar del patron, y se apaga
        # justo cuando toca la siguiente
        actual = (self.motor.paso - 1) % PASOS   # paso que esta sonando ahorita
        if self.ritmo == "Secuencia":
            quedan = 1                           # una nota en cada paso
        else:
            quedan = 2 - actual % 2              # pasos hasta la siguiente nota
        # Si la siguiente nota ya va a caer en menos de 30 ms, mejor esperarla
        if quedan == 1 and self.motor._faltan < SR * 0.03:
            return
        if self.ritmo == "Secuencia":
            self.nota_secuencia(actual)
        else:
            self.nota_arpegio(actual, pasos=quedan)

    def golpe_acorde(self):
        """Todas las notas del acorde juntas, duran 3 pasos"""
        for midi in self.acorde:
            self.tocar(midi, pasos=3)

    def nota_arpegio(self, paso, pasos=2):
        """La nota del arpegio que toca en ese paso del compas

        Va de grave a agudo, una nota cada 2 pasos: paso 0 -> nota 0,
        paso 2 -> nota 1 ... Como sale del paso y no de un contador, cambiar
        de acorde no reinicia el arpegio
        """
        notas = sorted(self.acorde)
        # Suena una nota a la vez, asi que va mas fuerte que en el acorde
        self.tocar(notas[(paso // 2) % len(notas)], pasos=pasos,
                   ganancia=GANANCIA_ACORDE * 1.8)

    def nota_secuencia(self, paso):
        """La nota del patron SECUENCIA que toca en ese paso

        El patron esta en pasos de la escala desde la raiz del acorde; la
        escalera (paso -> nota MIDI) la manda main.py con cada acorde
        Cada nota dura DURA_SECUENCIA pasos, asi resuenan una sobre otra
        """
        paso_escala = SECUENCIA[paso % len(SECUENCIA)]
        if paso_escala is None:
            return   # silencio en este paso
        escalera = self.escalera or self._escalera_del_acorde()
        # Las notas que coinciden con la raiz van acentuadas (mas fuertes)
        acento = 1.25 if paso_escala % 7 == 0 else 1.0
        self.tocar(escalera[paso_escala], pasos=DURA_SECUENCIA,
                   ganancia=GANANCIA_ACORDE * 1.3 * acento)

    def _escalera_del_acorde(self):
        """Escalera de respaldo si no llego una con el acorde

        Usa la escala Mayor si el acorde es mayor y la menor si es menor,
        empezando en su raiz
        """
        _, raiz, tercera, _ = sorted(self.acorde)
        escala = musica.ESCALAS["Mayor" if tercera - raiz == 4 else "menor"]
        escalera = {}
        for paso in range(-7, 15):
            vueltas, i = divmod(paso, 7)
            escalera[paso] = raiz + escala[i] + 12 * vueltas
        return escalera

    def en_paso(self, p):
        """Ritmo del acorde al inicio de cada paso del compas

        Golpes: en cada tiempo (cada 4 pasos)
        Arpegio: cada 2 pasos
        Secuencia: en cada paso, la nota que diga el patron SECUENCIA
        """
        if not self.acorde:
            return
        if self.ritmo == "Golpes" and p % 4 == 0:
            self.soltar("acorde")
            self.golpe_acorde()
        elif self.ritmo == "Arpegio" and p % 2 == 0:
            self.soltar("acorde")
            self.nota_arpegio(p)
        elif self.ritmo == "Secuencia":
            # Aqui no se sueltan las anteriores: se apagan solas al cumplir
            # sus pasos, y mientras tanto resuenan con la nueva
            self.nota_secuencia(p)


class Motor:
    """El motor de audio completo

    Metodos para el programa principal (solo dejan mensajes en la cola):
      poner_acorde, doblar, nota_on, nota_off, ajustar, alternar_beat, efecto
    Los que dicen mano= van al canal de esa mano ("Derecha" o "Izquierda")
    iniciar() abre la tarjeta de sonido y detener() la cierra
    generar() es lo que corre en el hilo de audio
    """

    def __init__(self, beats=None, carpeta_sonidos=None):
        # Beats (patrones MIDI) y los sonidos .wav que usan
        # (beats y carpeta_sonidos solo se pasan en las pruebas)
        self.beats = BEATS if beats is None else beats
        notas = {n for p in self.beats.values() if p for n in p.notas}
        carpeta = carpeta_sonidos or CARPETA_BEATS / "sonidos"
        self._sonidos, faltan, errores = cargar_sonidos(carpeta, notas)
        # Hi-hat: si no hay hihat.wav (o 42.wav) se usa el sintetizado
        if HIHAT not in self._sonidos:
            self._sonidos[HIHAT] = crear_hihat()
            faltan = [f for f in faltan if not f.startswith(f"{HIHAT} ")]

        # Avisos que main.py muestra en la consola al arrancar
        self.avisos = (ERRORES_BEATS if beats is None else []) + errores
        if faltan:
            self.avisos.append("Notas sin sonido .wav: " + ", ".join(faltan))

        # Ajustes generales (solo los cambia el hilo de audio al leer mensajes)
        self.bpm = 100
        self.volumen = 0.7
        self.beat = "Hi-hat"
        self.beat_activo = False

        # Un canal por mano, cada uno con su instrumento y su ritmo
        self.canales = {mano: Canal(self, mano) for mano in MANOS}

        # Estado que la pantalla puede leer
        self.paso = 0                        # paso actual del compas (0 a 15)
        self.ultimo_audio = np.zeros(1024)   # ultimas muestras generadas

        # Estado interno del hilo de audio
        self._voces = []            # todo lo que esta sonando
        self._faltan = 0.0          # muestras que faltan para el siguiente paso
        self._paso_beat = 0         # paso dentro del patron del beat
        self._mensajes = deque()    # cola de mensajes del programa principal
        self._efectos = crear_efectos()
        self._stream = None         # la conexion con la tarjeta de sonido

        # Calcular todas las cuerdas de guitarra al arrancar, para que tocar
        # una nota nueva nunca haga esperar al audio
        for midi in range(36, 101):
            cuerda(musica.frecuencia(midi))

    # ------------------------------ lo que usa main.py (solo deja mensajes)

    def poner_acorde(self, notas, movil=None, mano="Derecha", escalera=None):
        """Notas MIDI del acorde nuevo de esa mano, o None para callarlo

        movil: (nota, semitonos) la nota que cambia al invertir el acorde
        y cuanto se mueve (-1 de Mayor a menor, +1 de menor a Mayor)
        escalera: notas de la escala desde la raiz (musica.escalera), para
        el ritmo Secuencia
        """
        self._mensajes.append(("acorde", (mano, notas, movil, escalera)))

    def doblar(self, mezcla, mano="Derecha"):
        """Cuanto invertir el acorde: 0 = normal, 1 = invertido, o en medio

        La nota movil se desliza poco a poco hasta ese punto
        """
        self._mensajes.append(("doblar", (mano, mezcla)))

    def nota_on(self, midi, mano="Derecha"):
        """Empieza a sonar una nota de la melodia"""
        self._mensajes.append(("nota_on", (mano, midi)))

    def nota_off(self, midi, mano="Derecha"):
        """Suelta una nota de la melodia"""
        self._mensajes.append(("nota_off", (mano, midi)))

    def ajustar(self, mano=None, **ajustes):
        """Cambia bpm, volumen, beat, instrumento o ritmo

        instrumento y ritmo son de cada mano: con mano= solo cambian esa,
        sin mano= cambian las dos
        """
        self._mensajes.append(("ajustes", (mano, ajustes)))

    def alternar_beat(self):
        """Prende o apaga el beat"""
        self._mensajes.append(("alternar_beat", None))

    def efecto(self, nombre):
        """Toca un efecto de la interfaz: "clic" o "whoosh" """
        self._mensajes.append(("efecto", nombre))

    def iniciar(self):
        """Abre la tarjeta de sonido con sounddevice

        La tarjeta llama a _callback cada vez que necesita otro bloque
        de 256 muestras, en su propio hilo
        """
        import sounddevice as sd
        # latency="low": la tarjeta guarda lo menos posible antes de sonar,
        # asi el acorde se oye casi en cuanto se pide
        # Primero se intenta con WASAPI (SALIDA, el de menos retraso) y si
        # falla, con la tarjeta normal
        for disp in (SALIDA, None):
            try:
                self._stream = sd.OutputStream(
                    device=disp, samplerate=SR, channels=1, dtype="float32",
                    blocksize=BLOQUE, callback=self._callback, latency="low",
                )
                break
            except Exception:
                if disp is None:
                    raise
        self.latencia_ms = self._stream.latency * 1000
        self._stream.start()

    def _callback(self, outdata, frames, info_tiempo, estado):
        # outdata es donde hay que escribir el audio del bloque
        outdata[:, 0] = self.generar(frames)

    def detener(self):
        """Cierra la tarjeta de sonido"""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    # ------------------------------------------------------- hilo de audio

    def generar(self, frames):
        """Genera el siguiente bloque de audio

        1. Lee los mensajes pendientes
        2. Parte el bloque justo donde empieza cada paso del reloj, para que
           los eventos caigan en la muestra exacta
        3. Suma todas las voces
        4. Aplica volumen y un recorte suave
        """
        self._leer_mensajes()
        for canal in self.canales.values():
            canal.suavizar()
        salida = np.zeros(frames)
        pos = 0
        while pos < frames:
            if self._faltan <= 0:
                # Empieza un paso nuevo del compas
                self._avanzar_paso()
                # Muestras que dura un paso: 1 minuto / BPM negras / 4 pasos
                self._faltan += SR * 60 / self.bpm / 4
            # Generar hasta el siguiente paso o hasta el final del bloque
            n = min(frames - pos, max(1, math.ceil(self._faltan)))
            salida[pos:pos + n] = self._mezclar(n)
            pos += n
            self._faltan -= n

        # tanh: recorte suave, aunque se sumen muchas notas nunca "truena"
        salida = np.tanh(salida * (0.2 + self.volumen))
        self.ultimo_audio = np.concatenate((self.ultimo_audio, salida))[-1024:]
        return salida.astype(np.float32)

    def _leer_mensajes(self):
        """Aplica todo lo que pidio el programa principal desde el ultimo bloque"""
        while self._mensajes:
            tipo, dato = self._mensajes.popleft()
            if tipo == "acorde":
                mano, notas, movil, escalera = dato
                canal = self.canales[mano]
                canal.movil = movil
                canal.escalera = escalera
                canal.cambiar_acorde(notas)
            elif tipo == "doblar":
                mano, mezcla = dato
                self.canales[mano].mezcla_objetivo = mezcla
            elif tipo == "nota_on":
                mano, midi = dato
                self.canales[mano].nota_on(midi)
            elif tipo == "nota_off":
                mano, midi = dato
                self.canales[mano].soltar("melodia", midi)
            elif tipo == "ajustes":
                self._ajustar(*dato)
            elif tipo == "alternar_beat":
                self.beat_activo = not self.beat_activo
                if self.beat_activo:
                    # Arrancar desde el primer tiempo del compas
                    self.paso = 0
                    self._faltan = 0
                    self._paso_beat = 0
            elif tipo == "efecto":
                self._voces.append(Golpe(self._efectos[dato], 1.0))

    def _ajustar(self, mano, ajustes):
        """Aplica ajustes generales al motor y los de mano a su canal"""
        canales = list(self.canales.values()) if mano is None else [
            self.canales[mano]]
        for clave, valor in ajustes.items():
            if clave == "bpm" and valor != self.bpm:
                # Lo que falta del paso actual se ajusta al tempo nuevo, para
                # que el siguiente paso llegue a tiempo
                self._faltan *= self.bpm / valor
            if clave == "beat":
                # El beat nuevo empieza en el mismo lugar del compas
                self._paso_beat = self.paso
            if clave not in ("instrumento", "ritmo"):
                setattr(self, clave, valor)
                continue
            for canal in canales:
                cambia_ritmo = clave == "ritmo" and valor != canal.ritmo
                setattr(canal, clave, valor)
                # Con ritmo nuevo se vuelve a tocar el acorde con ese ritmo
                if cambia_ritmo:
                    canal.cambiar_acorde(canal.acorde)

    def _avanzar_paso(self):
        """Lo que pasa al inicio de cada paso del compas

        Aqui se disparan juntos el beat y el ritmo de los acordes: los dos
        salen del MISMO reloj y en la misma muestra, por eso van pegados
        """
        p = self.paso

        # Las notas con duracion en pasos se sueltan solas al terminar
        for v in self._voces:
            if isinstance(v, Nota) and v.pasos is not None and v.suelta is None:
                v.pasos -= 1
                if v.pasos <= 0:
                    v.soltar()

        # Beat y ritmo del acorde de cada mano
        self._programar_bateria()
        for canal in self.canales.values():
            canal.en_paso(p)

        self.paso = (p + 1) % PASOS

    def _programar_bateria(self):
        """Golpes del beat que caen en este paso del reloj

        Un golpe justo en el paso suena en la misma muestra que las notas
        del acorde; uno con decimales (el swing de un MIDI) suena ese pedazo
        de paso despues (retraso en muestras)
        """
        patron = self.beats.get(self.beat)
        if not self.beat_activo or patron is None:
            return
        paso = self._paso_beat
        self._paso_beat = (paso + 1) % patron.largo
        muestras_por_paso = SR * 60 / self.bpm / 4
        for pos, nota, fuerza in patron.golpes:
            if not paso <= pos < paso + 1:
                continue
            sonido = self._sonidos.get(nota)
            if sonido is None:
                continue   # nota sin .wav: no suena
            retraso = round((pos - paso) * muestras_por_paso)
            # La fuerza (velocity) del MIDI controla el volumen
            ganancia = GANANCIA_BATERIA * fuerza / 127
            self._voces.append(Golpe(sonido, ganancia, retraso))

    def _mezclar(self, n):
        """Suma n muestras de todas las voces y quita las que ya terminaron"""
        salida = np.zeros(n)
        for v in self._voces:
            salida += v.generar(n)
        self._voces = [v for v in self._voces if not v.terminada]
        return salida
