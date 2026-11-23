"""Prueba el motor de audio sin camara: genera archivos WAV para escucharlos

Uso:
    py probar_audio.py          genera los WAV en la carpeta demos/
    py probar_audio.py --vivo   ademas toca una progresion por las bocinas
"""

from pathlib import Path
import sys
import time
import wave

import numpy as np

import audio
import musica

DEMOS = Path(__file__).with_name("demos")
SOL = 7  # tonica de Sol

# Progresion I - V - vi - IV, un acorde por compas
PROGRESION = [0, 4, 5, 3]

def guardar(nombre, muestras):
    DEMOS.mkdir(exist_ok=True)
    datos = (np.clip(muestras, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(DEMOS / nombre), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(audio.SR)
        w.writeframes(datos.tobytes())


def tocar_progresion(motor, bpm, compases=4):
    """Simula a alguien tocando: manda los mensajes en el momento justo"""
    motor.ajustar(bpm=bpm)
    paso = audio.SR * 60 / bpm / 4

    eventos = []
    for c in range(compases):
        inicio = c * 16 * paso
        acorde = musica.acorde_por_grado(SOL, "Mayor", PROGRESION[c % 4])
        eventos.append((inicio, motor.poner_acorde, acorde["notas"]))
    eventos.sort(key=lambda e: e[0])

    total = int(compases * 16 * paso + audio.SR)
    bloques = []
    pos = 0
    while pos < total:
        while eventos and eventos[0][0] <= pos:
            _, funcion, dato = eventos.pop(0)
            funcion(dato)
        if pos >= compases * 16 * paso:
            motor.poner_acorde(None)
        bloques.append(motor.generar(audio.BLOQUE))
        pos += audio.BLOQUE
    return np.concatenate(bloques)


def motor_con(beat=None, instrumento="Pad", ritmo="Sostenido"):
    """Motor con ese instrumento y ritmo; beat=None = sin beat"""
    motor = audio.Motor()
    motor.ajustar(instrumento=instrumento, ritmo=ritmo)
    if beat is not None:
        motor.ajustar(beat=beat)
        motor.alternar_beat()
    return motor


def dos_manos(bpm=96, compases=4):
    """La idea de la expo: la derecha deja el acorde principal (I) en
    Secuencia con Sinte y la izquierda va cambiando acordes con Pad,
    con el Hi-hat marcando el tempo"""
    m = motor_con("Hi-hat")
    m.ajustar(bpm=bpm)
    m.ajustar(mano="Derecha", instrumento="Sinte", ritmo="Secuencia")
    m.ajustar(mano="Izquierda", instrumento="Pad", ritmo="Sostenido")
    i = musica.acorde_por_grado(SOL, "Mayor", 0)
    m.poner_acorde(i["notas"], mano="Derecha",
                   escalera=musica.escalera(SOL, "Mayor", 0))
    compas = audio.SR * 60 / bpm * 4
    bloques = []
    for c in range(compases):
        a = musica.acorde_por_grado(SOL, "Mayor", PROGRESION[c % 4])
        m.poner_acorde([n - 12 for n in a["notas"]], mano="Izquierda")
        bloques += [m.generar(audio.BLOQUE)
                    for _ in range(int(compas / audio.BLOQUE))]
    for lado in audio.MANOS:
        m.poner_acorde(None, mano=lado)
    bloques += [m.generar(audio.BLOQUE) for _ in range(150)]
    return np.concatenate(bloques)


def main():
    print("Generando demos en", DEMOS)
    beats = list(audio.BEATS)
    print("Beats:", ", ".join(beats))
    for aviso in audio.Motor().avisos:
        print("Aviso:", aviso)

    # Un demo por cada beat, para escuchar como quedo con sus sonidos
    for beat in beats:
        sonido = tocar_progresion(motor_con(beat, "Pad", "Sostenido"), 96)
        guardar(f"beat_{beat.lower().replace(' ', '_')}.wav", sonido)

    for inst in audio.INSTRUMENTOS:
        sonido = tocar_progresion(motor_con("Hi-hat", inst, "Golpes"), 96)
        guardar(f"instrumento_{inst.lower().replace(' ', '')}.wav", sonido)

    for ritmo in audio.RITMOS:
        sonido = tocar_progresion(motor_con(None, "Piano", ritmo), 96)
        guardar(f"ritmo_{ritmo.lower()}.wav", sonido)

    guardar("dos_manos.wav", dos_manos())

    # El sinte con su secuencia: Do# menor, acorde i, a 84 BPM (4 compases)
    m = motor_con("Hi-hat", "Sinte", "Secuencia")
    m.ajustar(bpm=84)
    acorde = musica.acorde_por_grado(1, "menor", 0)
    m.poner_acorde(acorde["notas"], (acorde["notas"][2], 1),
                   escalera=musica.escalera(1, "menor", 0))
    compas = audio.SR * 60 / 84 * 4
    bloques = [m.generar(audio.BLOQUE)
               for _ in range(int(4 * compas / audio.BLOQUE))]
    m.poner_acorde(None)
    bloques += [m.generar(audio.BLOQUE) for _ in range(150)]
    guardar("sinte_secuencia.wav", np.concatenate(bloques))

    m = audio.Motor()
    m.efecto("clic")
    clic = np.concatenate([m.generar(audio.BLOQUE) for _ in range(40)])
    m.efecto("whoosh")
    whoosh = np.concatenate([m.generar(audio.BLOQUE) for _ in range(100)])
    guardar("efectos.wav", np.concatenate((clic, whoosh)))

    # Rendimiento: el bloque debe generarse mucho mas rapido de lo que dura
    m = motor_con("Hi-hat", "Guitarra", "Arpegio")
    m.poner_acorde(musica.acorde_por_grado(SOL, "Mayor", 0)["notas"])
    inicio = time.perf_counter()
    for _ in range(500):
        m.generar(audio.BLOQUE)
    ms = (time.perf_counter() - inicio) / 500 * 1000
    dura = audio.BLOQUE / audio.SR * 1000
    print(f"Bloque: {ms:.2f} ms para generar {dura:.1f} ms de audio")

    # El peor caso: las dos manos con Sinte sostenido (8 notas)
    m = audio.Motor()
    m.ajustar(instrumento="Sinte", ritmo="Sostenido")
    for mano, grado in (("Derecha", 0), ("Izquierda", 4)):
        m.poner_acorde(musica.acorde_por_grado(SOL, "Mayor", grado)["notas"],
                       mano=mano)
    inicio = time.perf_counter()
    for _ in range(500):
        m.generar(audio.BLOQUE)
    ms = (time.perf_counter() - inicio) / 500 * 1000
    print(f"Peor caso (2 acordes Sinte): {ms:.2f} ms por bloque")

    print("Listo:", ", ".join(sorted(p.name for p in DEMOS.glob("*.wav"))))

    if "--vivo" in sys.argv:
        motor = motor_con("Hi-hat", "Piano", "Golpes")
        motor.iniciar()
        for grado in PROGRESION * 2:
            motor.poner_acorde(
                musica.acorde_por_grado(SOL, "Mayor", grado)["notas"])
            time.sleep(4 * 60 / motor.bpm)
        motor.poner_acorde(None)
        time.sleep(1)
        motor.detener()


if __name__ == "__main__":
    main()
