MANO SONORA - PROTOTIPO

Ejecutar
--------
    py main.py

Necesita: opencv-python, mediapipe, numpy, sounddevice, mido
    py -m pip install opencv-python mediapipe numpy sounddevice mido
y el archivo gesture_recognizer.task en esta carpeta (ya esta)

Beats: pon tus patrones .mid en beats/ y tus sonidos .wav en beats/sonidos/
(ver beats/LEEME.txt)

Teclas de respaldo: q = salir, m = cambiar de modo, espacio = beat on/off


Archivos
--------
main.py           Programa principal: camara, modos, que hace cada gesto y la pantalla
manos.py          Lee las manos: dedos alzados, senas, pellizco, giro, puno
musica.py         Teoria: tonalidades, grados y escalas
audio.py          Motor de sonido: reloj, beats MIDI, instrumentos, ritmos
probar_gestos.py  Prueba los gestos con manos simuladas (sin camara)
probar_audio.py   Genera WAV de prueba en demos/ (sin camara)


Donde esta cada cosa en el codigo
---------------------------------
Camara y deteccion de manos
  Abrir la camara (1280 x 720) ............ main.py  main()  cv2.VideoCapture
  Efecto espejo ........................... main.py  main()  cv2.flip
  Detectar DOS manos ...................... main.py  main()  num_hands=2
  Modelo de MediaPipe ..................... main.py  main()  gesture_recognizer.task
  Detectar en cada cuadro ................. main.py  main()  recognize_for_video
  Saber si es mano izquierda o derecha .... main.py  leer_manos()  (y INVERTIR_MANOS)
  Gestos del modelo (Thumb_Up, etc) ....... main.py  leer_manos()

Lectura de gestos (manos.py, clase Mano)
  Que dedos estan alzados ................. _dedos_arriba()
  Senas de acordes I a VII ................ grado()  y  FORMAS_FIJAS
  Pellizco y con que dedo ................. pellizco()  (PELLIZCO_ENTRA / SALE)
  Puno / puno completo .................... puno()  puno_completo()
  Mano abierta / apuntando ................ abierta()  apuntando()
  Centro de la palma ...................... centro()
  Inclinacion de la mano .................. angulo()  inclinacion()

Que hace cada gesto (main.py, clase App)
  Llamada de cada cuadro .................. actualizar()
  Aplauso = beat on/off ................... _aplauso()
  Boton Beat sonando ...................... _elegir()  elegido_por()
  Doble puno = cambiar modo ............... _doble_puno()  cambiar_modo()
  Gestos de Configurar .................... _configurar()
    pellizco y subir/bajar ................ _arrastrar()
    girar la mano = tonalidad ............. _girar()
    cursor y sostener para elegir ......... _cursor()  _elegir()
    opciones de cada mano ................. POR_MANO, por_mano, elegido_por()
  Gestos de Play .......................... _tocar()
    lo que toca cada mano ................. clase Tocador (una por mano)
    mano de acordes ....................... _acordes()
    altura = octava ....................... _altura()  (MARGEN_OCTAVA)
    acostar = Mayor/menor ................. _inclinar()  (INCLINA_INICIO / FIN)
    acorde estable (2 cuadros, 3 callar) .. _poner_acorde()  CUADROS_ESTABLES
  Posicion de botones y acordes ........... _acomodar()
  Dibujar la pantalla ..................... dibujar()  _dibujar_configurar()  _dibujar_play()
  Ondas del acorde que suena .............. dibujar_ondas()
  Grados con su acorde abajo .............. _dibujar_acorde()
  Botones mitad azul / naranja ............ _dibujar_configurar()
  Tiempos y ajustes (1 s, 0.6 s, 20 grados)  constantes al inicio de main.py

Musica (musica.py)
  Nota MIDI a frecuencia (Hz) ............. frecuencia()
  Circulo de quintas ...................... CIRCULO
  Escalas Mayor y menor ................... ESCALAS
  Acorde de cada grado .................... acorde_por_grado()
  Escala desde la raiz (para Secuencia) ... escalera()

Sonido (audio.py)
  Abrir la tarjeta de sonido .............. Motor.iniciar()
  Elegir WASAPI (menos retraso) ........... _elegir_salida()
  Mensajes del programa al audio .......... Motor.poner_acorde() nota_on() ajustar() ...
  Un canal por mano ....................... clase Canal (instrumento, ritmo, acorde)
  Generar cada bloque de audio ............ Motor.generar()
  Reloj de 16 pasos ....................... Motor._avanzar_paso()
  Ritmos (sostenido, golpes, arpegio) ..... Canal.cambiar_acorde() golpe_acorde() en_paso()
  Arpegio que sigue al reloj .............. Canal.nota_arpegio()
  Instrumentos (Pad, Piano FM, 8 bits) .... clase Nota, generar()
  Sinte (sierra + filtro) ................. Nota._sinte()
  Patron de la Secuencia (editable) ....... SECUENCIA (al inicio de audio.py)
  Tocar la Secuencia ...................... Canal.nota_secuencia()
  Deslizar la tercera (Mayor <-> menor) ... Motor.doblar()  Canal.doblez()  Nota.doblez
  Guitarra (Karplus-Strong) ............... cuerda()
  Leer beats .mid ......................... clase Patron, cargar_beats()
  Beat Hi-hat (patron y sonido) ........... patron_hihat(), crear_hihat()
  Leer sonidos .wav ....................... leer_wav(), cargar_sonidos()
  Tocar el beat al tempo .................. Motor._programar_bateria()
  Beat y acordes en el mismo reloj ........ Motor._avanzar_paso()
  Mezcla y volumen ........................ Motor._mezclar(), final de generar()
  Clic y whoosh ........................... crear_efectos()


Gestos
------
Siempre
  Doble puno 1 s ............ cambiar entre Configurar y Play
  Aplaudir .................. beat on/off

Configurar (el programa empieza aqui)
  Indice alzado (cualquier mano)
                              apuntar a un boton 0.6 s para elegirlo
                              Instrumento y Ritmo son de cada mano:
                              la mano que apunta elige lo suyo
                                azul = derecha, naranja = izquierda,
                                mitad y mitad = las dos eligieron eso
                              Beat, Beat sonando y Senas son de las dos (verde)
  Izq. mano abierta + girar . tonalidad (cada 20 grados = una tonalidad)
  Izq. pellizco + subir/bajar tempo
  Der. pulgar arriba/abajo .. Mayor / menor
  Der. pellizco + subir/bajar volumen

Beat
  Hi-hat ya viene con el programa: un hi-hat cerrado en cada corchea, mas
  fuerte en cada tiempo, para que las secuencias y los golpes entren a
  tempo. Si pones un hihat.wav en beats/sonidos/ usa ese en vez del
  sintetizado
  Los .mid de beats/ aparecen junto a el
  Beat sonando: Encendido / Apagado (lo mismo que aplaudir)

Play
  Las dos manos tocan acordes al mismo tiempo, cada una con su
  instrumento y su ritmo
  Idea para la expo: la derecha deja el acorde principal (I) con Sinte en
  Secuencia y la izquierda va cambiando acordes con Pad sostenido
  (asi empieza configurado)
  Si una mano no se ve o no hace sena, esa mano no suena

  Senas ..................... grados I a VII
                              pulgar, indice, medio, anular, menique,
                              amor y paz, pulgar + menique
                              I a V: alzando ese dedo, o bajandolo si en
                              Configurar se eligio "Bajar dedos"
                              VI y VII: misma forma en los dos modos
  Acostarla de lado ......... Mayor <-> menor poco a poco (la tercera se
                              desliza): derecha = normal, acostada = invertido
  Altura .................... octava: arriba aguda, en medio media, abajo grave

Ritmo Arpegio
  El arpegio sigue al reloj: al cambiar de acorde no vuelve a empezar,
  solo cambia de notas y sigue en el mismo lugar (como cambiar de carril)

Ritmo Secuencia (va muy bien con el instrumento Sinte)
  Una nota en cada semicorchea, segun el patron SECUENCIA de audio.py,
  como el secuenciador de un sintetizador; las notas resuenan un poco
  una sobre otra (DURA_SECUENCIA)
  El patron esta en pasos de la escala desde la raiz del acorde, asi
  sigue al acorde que hagas y a la tonalidad
  Igual que el arpegio, sigue al reloj al cambiar de acorde
  Por defecto es el intro de la tablatura: Configurar en Do# menor,
  84 BPM, Sinte + Secuencia, y en Play el acorde i (pulgar)
  Para armar tu secuencia cambia los 16 numeros de SECUENCIA:
    0 = raiz   1 = nota que sigue   2 = tercera   4 = quinta
    7 = raiz arriba   -1, -2 ... = notas de abajo   None = silencio

Que tan rapido responde
-----------------------
  Beat y acordes salen del mismo reloj y caen en la misma muestra de audio,
  aunque cambies el tempo con el pellizco
  Sonido: se usa WASAPI de Windows (~20 ms de retraso en vez de ~100 ms);
  al arrancar main.py dice cuanto retraso tiene la tarjeta
  Camara: guarda solo 1 cuadro, siempre se procesa el mas reciente
  Acordes: basta que la sena se vea 2 cuadros seguidos para cambiar
  (para callar se esperan 3, asi no se corta al pasar de sena a sena)

Nombres de las notas
--------------------
  Todas con sostenido: Do, Do#, Re, Re#, Mi, Fa, Fa#, Sol, Sol#, La, La#, Si
