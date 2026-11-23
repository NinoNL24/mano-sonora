"""Prueba la logica de gestos sin camara, con manos simuladas

Se construyen los 21 puntos de una mano con los dedos que se quieran alzados,
pellizcos y giros, y se le pasan al programa como si vinieran de MediaPipe

Uso:
    py probar_gestos.py
"""

import math

import numpy as np

import audio

# Un beat de mentira para poder probar el menu aunque beats/ este vacia
# (antes de importar main, que arma los botones con audio.BEATS)
audio.BEATS.setdefault("Prueba", None)

from main import App, NOMBRES_OCTAVA, TIEMPO_BOTON
from manos import Mano
import musica

# Mano derecha de frente a la camara, en unidades del tamano de la palma
# y negativa = hacia arriba (en la imagen la y crece hacia abajo)
NUDILLOS = {1: (-0.30, -0.95), 2: (-0.05, -1.0), 3: (0.18, -0.95),
            4: (0.38, -0.85)}


def hacer_mano(lado, centro, alzados, pellizco=None, giro=0.0, tam=110,
               gesto=None):
    p = [(0.0, 0.0)] * 21
    p[0] = (0.0, 0.0)
    # Pulgar
    p[1], p[2] = (-0.35, -0.15), (-0.55, -0.35)
    if 0 in alzados:
        p[3], p[4] = (-0.70, -0.55), (-0.85, -0.75)
    else:
        p[3], p[4] = (-0.35, -0.55), (-0.05, -0.60)
    # Demas dedos
    for dedo, (x, y) in NUDILLOS.items():
        base = 1 + 4 * dedo
        p[base] = (x, y)
        if dedo in alzados:
            p[base + 1:base + 4] = [(x, y - 0.35), (x, y - 0.6), (x, y - 0.8)]
        else:
            p[base + 1:base + 4] = [(x, y - 0.25), (x, y - 0.1), (x, y + 0.05)]
    if pellizco is not None:
        # Pulgar extendido hacia la punta del dedo pellizcado
        punta = p[4 * pellizco + 4]
        p[3] = (punta[0] - 0.25, punta[1] + 0.25)
        p[4] = (punta[0] - 0.04, punta[1] + 0.04)

    ang = math.radians(giro)
    espejo = -1 if lado == "Izquierda" else 1
    puntos = []
    for x, y in p:
        x *= espejo
        xr = x * math.cos(ang) - y * math.sin(ang)
        yr = x * math.sin(ang) + y * math.cos(ang)
        puntos.append((centro[0] + xr * tam, centro[1] + yr * tam))
    return Mano(puntos, lado, gesto)


class MotorFalso:
    """Guarda los mensajes que el programa le manda al audio"""

    def __init__(self):
        self.mensajes = []
        self.beat_activo = False
        self.paso = 0

    def __getattr__(self, nombre):
        def guardar(*args, **kwargs):
            # (nombre, argumentos o ajustes, ajustes con nombre como mano=)
            self.mensajes.append((nombre, args or kwargs, kwargs))
            if nombre == "alternar_beat":
                self.beat_activo = not self.beat_activo
        return guardar

    def ultimos(self, nombre, mano=None):
        """Mensajes con ese nombre (solo los de esa mano si se da mano)"""
        return [m for m in self.mensajes if m[0] == nombre
                and (mano is None or m[2].get("mano") == mano)]


W, H = 1280, 720
FPS = 30
errores = []


def revisar(condicion, descripcion):
    print(("  OK   " if condicion else "  FALLA ") + descripcion)
    if not condicion:
        errores.append(descripcion)


def correr(app, segundos, manos_fn, t0):
    """Llama a actualizar como si pasaran `segundos` a 30 cuadros/s"""
    n = int(segundos * FPS)
    t = t0
    for i in range(n):
        t = t0 + i / FPS
        manos = manos_fn(i)
        app.actualizar({m.lado: m for m in manos}, t, W, H)
    return t + 1 / FPS


def main():
    print("Lectura de dedos y senas")
    for alzados, grado in [({0}, 0), ({1}, 1), ({2}, 2), ({3}, 3), ({4}, 4),
                           ({1, 2}, 5), ({0, 4}, 6), ({0, 1}, 1),
                           (set(), None), ({1, 2, 3, 4}, None)]:
        m = hacer_mano("Derecha", (640, 500), alzados)
        detectados = {i for i, a in enumerate(m.arriba) if a}
        revisar(detectados == alzados and m.grado() == grado,
                f"dedos {sorted(alzados)} -> grado {grado}")
    m = hacer_mano("Izquierda", (300, 500), {1, 2})
    revisar(m.grado() == 5, "las senas funcionan igual con la mano izquierda")
    for dedo in (1, 2, 3):
        m = hacer_mano("Derecha", (640, 500), {0, 1, 2, 3, 4} - {dedo},
                       pellizco=dedo)
        revisar(m.pellizco() == dedo, f"pellizco con el dedo {dedo}")
    revisar(hacer_mano("Derecha", (640, 500), set()).pellizco() is None,
            "un puno no cuenta como pellizco")
    revisar(hacer_mano("Derecha", (640, 500), {0, 1, 2, 3, 4}).pellizco()
            is None, "mano abierta no es pellizco")
    m = hacer_mano("Derecha", (640, 500), {0, 1, 2, 4})
    revisar(m.grado(bajar=True) == 3, "modo bajar: anular doblado -> grado 3")
    revisar(hacer_mano("Derecha", (640, 500), {0, 1, 2, 3, 4}).grado(bajar=True)
            is None, "modo bajar: mano abierta = silencio")
    revisar(hacer_mano("Derecha", (640, 500), {0, 2, 3, 4}).grado(bajar=True)
            == 1, "modo bajar: indice doblado -> grado 1")
    revisar(hacer_mano("Derecha", (640, 500), {1, 2}).grado(bajar=True) == 5,
            "modo bajar: amor y paz sigue siendo VI")
    revisar(hacer_mano("Derecha", (640, 500), {0, 4}).grado(bajar=True) == 6,
            "modo bajar: pulgar y menique alzados sigue siendo VII")
    a0 = hacer_mano("Derecha", (640, 500), {1, 2, 3, 4}).angulo()
    a1 = hacer_mano("Derecha", (640, 500), {1, 2, 3, 4}, giro=30).angulo()
    revisar(abs((a0 - a1) - 30) < 1, "angulo de la mano al girar 30 grados")

    motor = MotorFalso()
    app = App(motor)
    t = 0.0

    print("Modo Configurar")
    # Apuntar al boton del beat "Prueba" con el indice derecho
    app._acomodar(W, H)
    boton = next(b for b in app.botones if b[5] == "Prueba")
    bx, by = (boton[0] + boton[2]) / 2, (boton[1] + boton[3]) / 2

    def apuntar(i):
        # La punta del indice (punto 8) queda sobre el boton
        m = hacer_mano("Derecha", (bx, by), {1})
        dx, dy = bx - m.puntos[8][0], by - m.puntos[8][1]
        return [hacer_mano("Derecha", (bx + dx, by + dy), {1})]

    t = correr(app, TIEMPO_BOTON * 0.5, apuntar, t)
    revisar(app.ajustes["beat"] == "Hi-hat", "a medio camino todavia no elige "
            "(sigue el Hi-hat de inicio)")
    t = correr(app, TIEMPO_BOTON, apuntar, t)
    revisar(app.ajustes["beat"] == "Prueba", "apuntar 0.6 s elige el beat")
    revisar(any(m[1] == {"beat": "Prueba"} for m in motor.ultimos("ajustar")),
            "el motor recibe el beat nuevo")
    revisar(motor.beat_activo, "al elegir un beat empieza a sonar")

    # Pellizco derecho y subir la mano = mas volumen
    t = correr(app, 1.0, lambda i: [hacer_mano(
        "Derecha", (900, 500 - i * 4), {0, 2, 3, 4}, pellizco=1)], t)
    revisar(app.ajustes["volumen"] > 0.9, f"pellizco y subir sube el volumen "
            f"({app.ajustes['volumen']})")
    # Pellizco izquierdo y bajar la mano = menos tempo
    t = correr(app, 1.0, lambda i: [hacer_mano(
        "Izquierda", (300, 300 + i * 4), {0, 2, 3, 4}, pellizco=1)], t)
    revisar(app.ajustes["bpm"] < 80, f"pellizco izquierdo y bajar baja el "
            f"tempo ({app.ajustes['bpm']} BPM)")
    # Girar la mano IZQUIERDA abierta 45 grados con el reloj = 2 tonalidades
    t = correr(app, 1.0, lambda i: [hacer_mano(
        "Izquierda", (300, 500), {0, 1, 2, 3, 4}, giro=min(45, i * 3))], t)
    revisar(app.tonica == 2, f"girar la izquierda 45 grados: Do -> Re "
            f"({musica.NOMBRES[app.tonica]})")
    t = correr(app, 1.0, lambda i: [hacer_mano(
        "Derecha", (900, 500), {0, 1, 2, 3, 4}, giro=min(45, i * 3))], t)
    revisar(app.tonica == 2, "girar la derecha ya no mueve la rueda")
    # Pulgar abajo con la DERECHA = menor
    t = correr(app, 0.3, lambda i: [hacer_mano(
        "Izquierda", (300, 400), {0}, gesto="Thumb_Down")], t)
    revisar(app.escala == "Mayor", "el pulgar izquierdo ya no cambia Mayor/menor")
    t = correr(app, 0.3, lambda i: [hacer_mano(
        "Derecha", (900, 400), {0}, gesto="Thumb_Down")], t)
    revisar(app.escala == "menor", "pulgar derecho abajo: tonalidad menor")
    t = correr(app, 0.3, lambda i: [hacer_mano(
        "Derecha", (900, 400), {0}, gesto="Thumb_Up")], t)
    revisar(app.escala == "Mayor", "pulgar derecho arriba: tonalidad Mayor")

    print("Cambio de modo y aplauso")
    punos = lambda i: [hacer_mano("Derecha", (900, 400), set()),
                       hacer_mano("Izquierda", (300, 400), set())]
    t = correr(app, 0.5, punos, t)
    revisar(app.modo == "Configurar", "doble puno 0.5 s todavia no cambia")
    t = correr(app, 1.0, punos, t)
    revisar(app.modo == "Play", "doble puno 1 s cambia a Play")
    t = correr(app, 1.5, punos, t)
    revisar(app.modo == "Play", "seguir con los punos no regresa de modo")

    beat_antes = motor.beat_activo
    t = correr(app, 1.0, lambda i: [
        hacer_mano("Derecha", (640 + max(60, 400 - i * 60), 400), {0, 1, 2, 3, 4}),
        hacer_mano("Izquierda", (640 - max(60, 400 - i * 60), 400), {0, 1, 2, 3, 4})],
        t + 1)
    revisar(motor.beat_activo != beat_antes, "aplauso cambia el beat on/off")

    print("Configurar: cada mano elige lo suyo")
    app.modo = "Configurar"
    app._acomodar(W, H)
    motor.mensajes.clear()

    def apuntar_a(lado, valor, clave=None):
        """Manos que apuntan con el indice de esa mano al boton con ese valor"""
        b = next(b for b in app.botones if b[5] == valor
                 and (clave is None or b[4] == clave))
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        m = hacer_mano(lado, (cx, cy), {1})
        dx, dy = cx - m.puntos[8][0], cy - m.puntos[8][1]
        return lambda i: [hacer_mano(lado, (cx + dx, cy + dy), {1})]

    t = correr(app, TIEMPO_BOTON + 0.2, apuntar_a("Derecha", "Piano"), t)
    t = correr(app, TIEMPO_BOTON + 0.2, apuntar_a("Derecha", "Arpegio"), t)
    revisar(app.por_mano["Derecha"]["instrumento"] == "Piano"
            and app.por_mano["Izquierda"]["instrumento"] == "Pad",
            "la derecha elige Piano y la izquierda sigue en Pad")
    revisar(motor.ultimos("ajustar", "Derecha")[-1][2]
            == {"mano": "Derecha", "ritmo": "Arpegio"},
            "el motor recibe el ritmo solo para la derecha")
    revisar(app.elegido_por("instrumento", "Piano") == ["Derecha"]
            and app.elegido_por("instrumento", "Pad") == ["Izquierda"],
            "cada boton sabe que mano lo eligio")
    t = correr(app, TIEMPO_BOTON + 0.2, apuntar_a("Izquierda", "Piano"), t)
    revisar(app.elegido_por("instrumento", "Piano") == ["Derecha", "Izquierda"],
            "Piano elegido por las dos (boton mitad y mitad)")
    encendido = motor.beat_activo
    otro = "Apagado" if encendido else "Encendido"
    t = correr(app, TIEMPO_BOTON + 0.2, apuntar_a("Derecha", otro, "activo"), t)
    revisar(motor.beat_activo != encendido
            and app.elegido_por("activo", otro) == ["Las dos"],
            f"boton Beat sonando: {otro}")
    revisar(app.elegido_por("beat", "Prueba") == ["Las dos"],
            "el beat es de las dos manos")

    print("Play: las dos manos tocan acordes a la vez (Re Mayor)")
    app.modo = "Play"
    motor.mensajes.clear()
    t = correr(app, 0.5, lambda i: [hacer_mano("Derecha", (900, 400), {3}),
                                    hacer_mano("Izquierda", (300, 400), {4})], t)
    der, izq = app.tocadores["Derecha"], app.tocadores["Izquierda"]
    esperado = musica.acorde_por_grado(2, "Mayor", 3)
    acordes = motor.ultimos("poner_acorde", "Derecha")
    revisar(len(acordes) == 1 and acordes[0][1][0] == esperado["notas"],
            f"derecha: anular = IV = {esperado['nombre']}")
    revisar(acordes[0][1][1] == (esperado["notas"][2], -1),
            "la nota movil es la tercera y baja 1 semitono")
    revisar(izq.info is not None and izq.info["numeral"] == "V"
            and len(motor.ultimos("poner_acorde", "Izquierda")) == 1,
            f"izquierda al mismo tiempo: menique = V ({izq.info and izq.info['nombre']})")
    t = correr(app, 0.5, lambda i: [hacer_mano("Derecha", (900, 400), {3})], t)
    revisar(izq.acorde is None and der.acorde == (3, 0),
            "quitar la izquierda calla solo la izquierda")
    t = correr(app, 0.5, lambda i: [hacer_mano("Izquierda", (300, 400), {3},
                                               giro=-80),
                                    hacer_mano("Derecha", (900, 400), {3})], t)
    revisar(izq.mezcla == 1.0 and der.mezcla == 0.0,
            "acostar la izquierda invierte solo su acorde")
    revisar(motor.ultimos("doblar", "Izquierda")[-1][1][0] == 1.0,
            "el motor recibe la inclinacion de la izquierda")

    t = correr(app, 0.3, lambda i: [hacer_mano("Derecha", (900, 400), {3},
                                               giro=45)], t)
    # La mano simulada no esta perfectamente vertical, por eso aproximado
    revisar(0.4 <= der.mezcla <= 0.6 and der.acorde == (3, 0),
            f"inclinar 45 grados = mitad del camino ({der.mezcla})")
    for giro in (80, -80):
        t = correr(app, 0.3, lambda i: [hacer_mano("Derecha", (900, 400), {3},
                                                   giro=giro)], t)
        revisar(der.mezcla == 1.0 and der.info_inv["nombre"] == "Sol menor",
                f"acostada {giro} grados = invertido ({der.info_inv['nombre']})")
    t = correr(app, 0.3, lambda i: [hacer_mano("Derecha", (900, 400), {3})], t)
    revisar(der.mezcla == 0.0, "al enderezarla regresa a Mayor")

    for y, octava in [(200, 1), (650, -1), (400, 0)]:
        t = correr(app, 0.3, lambda i: [hacer_mano("Derecha", (900, y), {3})], t)
        notas = motor.ultimos("poner_acorde", "Derecha")[-1][1][0]
        revisar(der.octava == octava and notas == [n + 12 * octava for n in
                                                   esperado["notas"]],
                f"altura {y} = octava {NOMBRES_OCTAVA[octava]}")
    t = correr(app, 0.3, lambda i: [hacer_mano("Derecha", (900, 200), {3})], t)
    t = correr(app, 0.3, lambda i: [hacer_mano("Derecha", (900, 339), {3})], t)
    revisar(der.octava == 1, "cerca de la linea no cambia de octava (margen)")
    t = correr(app, 0.3, lambda i: [hacer_mano("Derecha", (900, 400), {3})], t)
    revisar(der.octava == 0, "pasando el margen si cambia")
    t = correr(app, 0.5, lambda i: [hacer_mano("Derecha", (900, 400), {1, 2, 3, 4})], t)
    revisar(der.acorde is None, "derecha sin sena se calla")
    t = correr(app, 0.5, lambda i: [hacer_mano("Derecha", (900, 400), {3}),
                                    hacer_mano("Izquierda", (300, 400), {3})], t)
    t = correr(app, 0.5, lambda i: [], t)
    revisar(der.acorde is None and izq.acorde is None,
            "sin manos se callan las dos")

    print("Senas con dedos bajados")
    app.modo = "Configurar"
    app._callar()
    t = correr(app, TIEMPO_BOTON + 0.2, apuntar_a("Izquierda", "Bajar dedos"), t)
    revisar(app.ajustes["senas"] == "Bajar dedos",
            "apuntar con la izquierda tambien elige (Bajar dedos)")
    app.modo = "Play"
    t = correr(app, 0.5, lambda i: [
        hacer_mano("Derecha", (900, 400), {0, 1, 2, 4})], t)
    revisar(der.info is not None and der.info["numeral"] == "IV",
            "bajar el anular toca el grado IV")

    print("Dibujo (sin errores en cada modo)")
    frame = np.zeros((H, W, 3), np.uint8)
    manos = {"Derecha": hacer_mano("Derecha", (900, 400), {1}),
             "Izquierda": hacer_mano("Izquierda", (300, 400), {1, 2})}
    for modo in ("Configurar", "Play"):
        app.modo = modo
        for _ in range(4):
            app.actualizar(manos, t, W, H)
        app.dibujar(frame.copy(), manos, t)
        revisar(True, f"dibujar {modo}")

    print()
    print("Todo bien" if not errores else f"{len(errores)} pruebas fallaron")


if __name__ == "__main__":
    main()
