# Mano Sonora: como funciona por dentro

Guia para explicar el proyecto y contestar las preguntas de la exposicion
Cada respuesta dice **que hace**, **como lo hace** y **en que parte del codigo esta**

---

## Resumen en 30 segundos

> Mano Sonora es un sintetizador que se toca con las manos frente a la camara
> La camara ve las manos, MediaPipe encuentra 21 puntos en cada una, y con
> esos puntos el programa reconoce senas: cada sena es un acorde de la
> tonalidad elegida. Cada mano toca su propio acorde con su propio
> instrumento y ritmo, todo a tempo con un beat
> El sonido no son grabaciones: se genera con matematicas en tiempo real

**Tecnologias**

| Pieza | Para que |
|---|---|
| Python | Lenguaje de todo el programa |
| OpenCV (`cv2`) | Abrir la camara, voltear la imagen y dibujar la interfaz |
| MediaPipe (Google) | Red neuronal que encuentra las manos y sus 21 puntos |
| NumPy | Calculos con arreglos: generar el sonido rapido |
| sounddevice | Mandar el audio a la tarjeta de sonido |
| mido | Leer archivos MIDI (para beats propios) |

**Archivos**

| Archivo | Que hace |
|---|---|
| `main.py` | Programa principal: camara, modos, que hace cada gesto y la pantalla |
| `manos.py` | Convierte los 21 puntos en gestos (dedos alzados, senas, pellizco, giro) |
| `musica.py` | Teoria musical: tonalidades, grados, acordes, escalas |
| `audio.py` | Motor de sonido: reloj, instrumentos, ritmos, beat |
| `probar_gestos.py` | 64 pruebas automaticas con manos simuladas |
| `probar_audio.py` | Genera WAV de prueba y mide el rendimiento |

---

## El recorrido de un cuadro de video

Esto pasa unas 25 a 30 veces por segundo (`main()` en `main.py`)

```
Camara ──> voltear (espejo) ──> MediaPipe ──> 21 puntos por mano
   ──> manos.py: que gesto es ──> main.py: que hacer con ese gesto
   ──> audio.py: cambiar el sonido ──> dibujar la pantalla
```

El audio corre en **otro hilo** al mismo tiempo: la tarjeta de sonido le pide
pedazos de 256 muestras (unos 5 ms) y el motor los genera. El programa
principal solo le deja mensajes ("pon este acorde", "cambia el tempo")

---

## 1. Deteccion de las manos

**¿Como detectan las manos?**
- Con **MediaPipe Gesture Recognizer**, un modelo de Google ya entrenado
  (`gesture_recognizer.task`). Recibe una imagen y regresa, por cada mano:
  - 21 puntos (muneca, nudillos, articulaciones y puntas de los dedos)
  - si es mano izquierda o derecha
  - algunos gestos que ya conoce (pulgar arriba, pulgar abajo, puno)
- Codigo: `main()` en `main.py`, `opciones = ...GestureRecognizerOptions(...)`

**¿Entrenaron ustedes la red neuronal?**
- No. Usamos el modelo ya entrenado de Google. Lo nuestro es todo lo que
  pasa despues: convertir los puntos en gestos, los gestos en musica y la
  musica en sonido. Entrenar un modelo propio necesitaria miles de fotos
  etiquetadas y no daria mejor resultado que el de Google

**¿Como hacen que detecte dos manos?**
- Con el parametro `num_hands=2` en las opciones del detector (`main()`)

**¿Como sabe cual es la izquierda y cual la derecha?**
- MediaPipe lo dice en `handedness` ("Left" o "Right")
- Como volteamos la imagen (espejo), con nuestra camara salian al reves;
  por eso existe `INVERTIR_MANOS = True` al inicio de `main.py`
- Codigo: `leer_manos()` en `main.py`

**¿Por que voltean la imagen?**
- Para que funcione como un espejo: si mueves la mano a tu derecha, en la
  pantalla tambien se mueve a la derecha. Sin eso es muy confuso
- Codigo: `cv2.flip(frame, 1)` en `main()`

**¿Que es el modo VIDEO de MediaPipe?**
- En lugar de analizar cada foto desde cero, usa lo que encontro en el
  cuadro anterior para seguir las manos. Es mas rapido y mas estable
- Pide un tiempo en milisegundos que siempre vaya creciendo (`ms` en `main()`)

**¿Por que achican la imagen a 640 px antes de detectar?**
- MediaPipe es mas rapido con imagenes chicas y los puntos vienen en
  proporcion (de 0 a 1), asi que se pueden pasar a la imagen grande sin
  perder precision. La pantalla se sigue viendo a 1280 x 720

**¿Que pasa si una mano sale de la camara?**
- Esa mano deja de sonar (en 3 cuadros, ~0.1 s) y se olvida lo que estaba
  haciendo (pellizco a medias, giro a medias). La otra mano sigue normal

---

## 2. Leer gestos a partir de los puntos (`manos.py`)

**¿Como saben si un dedo esta alzado?**
- Indice a menique: el dedo esta alzado si **la punta esta mas lejos de la
  muneca que la articulacion de en medio**. Al doblar el dedo la punta se
  acerca a la palma y la regla se invierte
- Pulgar: se dobla hacia un lado, no hacia la palma, asi que se compara
  contra la base del menique: alzado si la punta (4) esta mas lejos del
  punto 17 que su articulacion (3)
- Codigo: `Mano._dedos_arriba()`

**¿Por que comparan distancias y no si la punta esta "mas arriba"?**
- Porque si la mano esta inclinada, "arriba" ya no significa alzado. Las
  distancias no cambian al girar la mano, asi las senas se leen bien
  aunque la mano este acostada (eso lo usamos para Mayor/menor)

**¿Funciona igual cerca o lejos de la camara?**
- Si. Todas las distancias se dividen entre el **tamano de la mano**
  (distancia de la muneca al nudillo del medio). Lejos la mano se ve chica
  pero las proporciones son las mismas
- Codigo: `self.tamano` en `Mano.__init__`

**¿Como reconocen las senas de los acordes?**
- Primero se saca el conjunto de dedos alzados, por ejemplo {anular}
- I a V: un solo dedo (pulgar = I, indice = II, medio = III, anular = IV,
  menique = V)
- VI y VII tienen forma fija: amor y paz {indice, medio} = VI y
  {pulgar, menique} = VII
- En Configurar se puede elegir "Bajar dedos": entonces la sena es el dedo
  que **se dobla** en vez del que se alza (VI y VII no cambian)
- Codigo: `Mano.grado()` y `FORMAS_FIJAS`

**¿Por que a veces ignoran el pulgar?**
- Es el dedo que MediaPipe detecta peor. Si la sena no usa el pulgar (por
  ejemplo amor y paz), da igual si esta alzado o no. Asi hay menos errores

**¿Como detectan el pellizco?**
- Se mide la distancia de la punta del pulgar a la punta de cada dedo (en
  tamanos de mano). Si es menor a 0.30 es pellizco
- Para soltarlo hay que pasar de 0.45. Que soltar pida mas distancia que
  empezar se llama **histeresis**: evita que parpadee cuando los dedos estan
  justo en el limite
- Un puno tambien junta el pulgar con los dedos; para no confundirlo se pide
  que al menos 2 de los otros dedos sigan alzados
- Codigo: `Mano.pellizco()`, `PELLIZCO_ENTRA`, `PELLIZCO_SALE`

**¿Como miden la inclinacion de la mano?**
- Con el angulo de la linea muneca (punto 0) → nudillo del medio (punto 9),
  usando `atan2` (la funcion de trigonometria que da el angulo de una linea)
- La imagen tiene la y hacia abajo, por eso se usa `y0 - y9`
- Codigo: `Mano.angulo()` y `Mano.inclinacion()`

**¿Que es el "centro de la palma"?**
- El promedio de la muneca y los 4 nudillos. Esos puntos casi no se mueven
  al doblar los dedos, asi que es una posicion estable de la mano. Se usa
  para la altura (octava), los pellizcos y el aplauso
- Codigo: `Mano.centro()`

---

## 3. Que hace cada gesto (`main.py`, clase `App`)

### Siempre

**¿Como cambian de modo con el doble puno?**
- Si las dos manos estan en puno completo (incluido el pulgar) durante
  1 segundo, cambia entre Configurar y Play. Se ve una barra de progreso
- Despues del cambio espera a que abras las manos, para que no se regrese
  solo
- Tambien se acepta el "Closed_Fist" que reconoce MediaPipe
- Codigo: `_doble_puno()`, `TIEMPO_CAMBIO`

**¿Como detectan el aplauso?**
- Se guarda la distancia entre las dos palmas durante los ultimos 0.4 s
- Es aplauso si **ahora estan juntas** (menos de 1.3 tamanos de mano) y
  **hace un momento estaban lejos** (mas de 2.5). Es decir, se detecta el
  movimiento de juntarlas rapido, no solo que esten juntas
- Despues espera 0.8 s para no contar el mismo aplauso dos veces
- Codigo: `_aplauso()`

### Modo Configurar

**¿Como se eligen las opciones sin tocar nada?**
- Alzas solo el indice y aparece un cursor en la punta. Si lo dejas
  **0.6 s** sobre un boton, se elige (un anillo se va llenando)
- A esto se le llama **dwell** (sostener para confirmar). Evita elegir algo
  solo por pasar el dedo encima, que es el problema clasico de las
  interfaces sin contacto (el "toque de Midas")
- Codigo: `_cursor()`, `_elegir()`, `TIEMPO_BOTON`

**¿Como hace cada mano su propia configuracion?**
- Instrumento y ritmo se guardan por mano (`por_mano`). La mano que apunta
  elige lo suyo
- Los botones se pintan azul (derecha), naranja (izquierda) o mitad y mitad
  si las dos eligieron lo mismo
- Codigo: `_elegir()`, `elegido_por()`, `_dibujar_configurar()`

**¿Como funciona la rueda de tonalidades?**
- Datos: la lista `CIRCULO` de `musica.py` tiene las 12 tonalidades en orden
  de **circulo de quintas** (Do, Sol, Re, La...). Vecinas comparten casi
  todas sus notas, por eso girar poco a poco suena natural
- Dibujo: 12 nombres cada 30° (360 / 12) con seno y coseno:
  `x = centro + radio·cos(angulo)`, `y = centro − radio·sin(angulo)`
- Giro: con la mano **izquierda abierta**. Al abrirla se guarda su angulo;
  cada **20°** de giro mueve una tonalidad. Para llegar mas lejos se cierra
  la mano, se regresa y se gira otra vez, como una llave de tuercas
  (la muneca solo gira comodo unos 60°)
- `(angulo - inicial + 180) % 360 - 180` evita un brinco cuando el angulo
  pasa de 179° a −179°
- Codigo: `_girar()`, `GRADOS_POR_TONALIDAD`

**¿Como cambian entre Mayor y menor?**
- Pulgar arriba o abajo con la mano **derecha**. Esos dos gestos ya los
  reconoce el modelo de MediaPipe ("Thumb_Up" / "Thumb_Down")

**¿Como controlan tempo y volumen?**
- Pellizcar y subir o bajar la mano, como girar una perilla. Al empezar el
  pellizco se guarda la altura; despues el valor cambia segun cuanto
  subiste (media pantalla = todo el rango)
- Izquierda = tempo (60 a 160 BPM), derecha = volumen (0 a 100 %)
- Codigo: `_arrastrar()`

### Modo Play

**¿Como tocan dos acordes a la vez?**
- Cada mano tiene su propio `Tocador` (en `main.py`) y su propio `Canal` de
  audio (en `audio.py`), con su instrumento, ritmo y acorde. No se estorban
- Idea de uso: la derecha deja el acorde principal (I) con Sinte en
  Secuencia y la izquierda va cambiando acordes encima con Pad

**¿Por que el acorde no cambia con cualquier temblor de la mano?**
- Al pasar de una sena a otra la mano cruza formas intermedias. Para no
  tocar esos "acordes de paso", la sena nueva tiene que verse **2 cuadros
  seguidos** (~70 ms). Para callar se piden 3, para que no se corte en el
  instante en que la mano no hace ninguna sena
- Codigo: `_poner_acorde()`, `CUADROS_ESTABLES`, `CUADROS_SILENCIO`

**¿Como cambia de Mayor a menor "poco a poco" al acostar la mano?**
- Un acorde Mayor y su menor solo cambian en **una nota**: la tercera baja
  1 semitono (Do-**Mi**-Sol → Do-**Re#**-Sol)
- La inclinacion de la mano (0° a 90°) se convierte en un valor de 0 a 1:
  hasta 20° es 0 (normal) y desde 70° es 1 (invertido). En medio, esa nota
  **se desliza** de una a otra, como cuando un guitarrista dobla la cuerda
- Se inclina de lado (no hacia la camara) para que los dedos se sigan
  viendo completos y la sena no se pierda
- Codigo: `_inclinar()`, `INCLINA_INICIO`, `INCLINA_FIN`; en el audio
  `Motor.doblar()` y `Nota.doblez`

**¿Como eligen la octava con la altura?**
- La pantalla se divide en 3 franjas: arriba aguda, en medio media, abajo
  grave. Se mira en que franja esta el centro de la palma
- Para cambiar de franja hay que pasar la linea por un margen (4 % del alto):
  otra vez histeresis, para que no brinque si la mano queda en la frontera
- Codigo: `_altura()`, `MARGEN_OCTAVA`

---

## 4. Teoria musical (`musica.py`)

**¿Como convierten una nota en sonido?**
- Las notas se manejan como numeros MIDI: 60 = Do central, 61 = Do#...
- La frecuencia sale de la formula estandar:
  `f = 440 · 2^((n − 69) / 12)`. El La 69 suena a 440 Hz y cada 12 notas
  (una octava) la frecuencia se duplica
- Codigo: `frecuencia()`

**¿Que es un "grado" y por que usan grados en vez de acordes fijos?**
- Una tonalidad tiene 7 notas; el grado es el acorde que se construye sobre
  cada una (I, ii, iii, IV, V, vi, vii°)
- La sena dice el grado, no el acorde. Asi la misma sena sirve en cualquier
  tonalidad, y **todos los acordes que puedes tocar suenan bien juntos**:
  no hay forma de tocar una nota "equivocada"

**¿Como calculan el acorde de cada grado?**
- Apilando terceras de la escala: la nota del grado, dos notas mas arriba y
  cuatro notas mas arriba. Ejemplo en Do Mayor, grado II: Re, Fa, La
- El tipo de acorde sale solo de las distancias en semitonos:
  - tercera de 4 → Mayor
  - tercera de 3 y quinta de 7 → menor
  - tercera de 3 y quinta de 6 → disminuido
- Se agrega la raiz una octava abajo para darle cuerpo
- Codigo: `acorde_por_grado()`

**¿Por que unos numerales van en mayuscula y otros en minuscula?**
- Es la convencion musical: mayuscula = Mayor (IV), minuscula = menor (ii),
  y ° = disminuido (vii°)

**¿Por que todas las notas con # y no con b?**
- Son la misma nota con dos nombres (Do# = Reb). Elegimos # para que todo
  sea consistente y facil de leer

---

## 5. Generacion del sonido (`audio.py`)

**¿Usan grabaciones de instrumentos?**
- No. Todo se **sintetiza** en tiempo real con NumPy. Solo el beat puede
  usar .wav si uno quiere poner sus propios sonidos de bateria

**¿Como hacen cada instrumento?**

| Instrumento | Tecnica | En pocas palabras |
|---|---|---|
| Pad | Sintesis aditiva | Senoidal + armonicos suaves + una copia desafinada 0.4 % (efecto coro); entra poco a poco |
| Piano | Sintesis FM | Una senoidal modula la fase de otra; la modulacion empieza fuerte (brillo de campana) y baja, como un piano electrico |
| Guitarra | Karplus-Strong | Un pedazo de ruido que se repite y se va promediando consigo mismo; el promedio quita los agudos y suena a cuerda pulsada |
| 8 bits | Onda cuadrada | Solo +1 y −1, como las consolas viejas |
| Sinte | Sierra + filtro | Dos ondas de sierra (una desafinada 0.7 %) con un filtro pasa-bajas que se cierra: cada nota empieza brillante y se vuelve redonda ("pluck") |

- Codigo: `Nota.generar()`, `Nota._sinte()`, `cuerda()`

**¿Como funciona Karplus-Strong exactamente?**
1. Se llena un "periodo" (SR / frecuencia muestras) con ruido
2. Cada muestra nueva = promedio de dos muestras de un periodo atras, × 0.996
3. El promedio es un filtro pasa-bajas: en cada vuelta se pierden agudos y
   energia, igual que una cuerda real
- En notas agudas el periodo tiene pocas muestras y redondearlo desafina;
  por eso se genera una octava abajo y se acelera
- Las cuerdas se calculan al arrancar y se guardan, para no hacer esperar al
  audio. Codigo: `cuerda()`

**¿Como hace el Sinte el filtro que se cierra?**
- Una onda de sierra es la suma de armonicos (1, 2, 3... veces la
  frecuencia) con volumen 1/k
- El filtro baja el volumen de los armonicos que pasan de una frecuencia de
  corte; el corte empieza alto y baja con el tiempo
- Solo se suman armonicos abajo de 18 kHz para que no suene sucio (aliasing)

**¿Como evitan que el programa se trabe con el audio?**
- El audio corre en un **hilo aparte** que lo llama la tarjeta de sonido
- El programa principal nunca toca el audio directamente: deja mensajes en
  una cola (`deque`) y el hilo de audio los lee al inicio de cada bloque
- Generar un bloque de 5.3 ms tarda entre 0.1 y 1.5 ms (lo medimos con
  `probar_audio.py`), asi que sobra tiempo

**¿Como hacen que todo vaya a tempo?**
- Hay un **reloj de 16 pasos** por compas (cada paso es una semicorchea)
- Un paso dura `SR · 60 / BPM / 4` muestras. El motor **parte cada bloque
  justo donde empieza un paso**, asi los eventos caen en la muestra exacta,
  no "mas o menos" al inicio del bloque
- Codigo: `Motor.generar()`, `Motor._avanzar_paso()`

**¿Como sincronizan el beat con los acordes?**
- El beat y el ritmo de los acordes salen **del mismo reloj** y se disparan
  en la misma llamada (`_avanzar_paso`). Medimos que cada golpe del hi-hat
  cae **en la misma muestra** que la nota del acorde, aunque se cambie el
  tempo a medio camino
- Si se cambia el tempo, lo que falta del paso actual se ajusta al tempo
  nuevo (`_faltan *= bpm_viejo / bpm_nuevo`), asi no se pierde el pulso

**¿Que ritmos hay y como funcionan?**
- **Sostenido**: el acorde suena mientras hagas la sena; al cambiar, las
  notas que se repiten siguen sonando sin cortarse
- **Golpes**: el acorde se toca en cada tiempo (cada 4 pasos)
- **Arpegio**: una nota del acorde cada 2 pasos, de grave a agudo
- **Secuencia**: una nota en cada paso, siguiendo un patron de 16 pasos
  como el secuenciador de un sintetizador

**¿Que pasa con el arpegio si cambian de acorde a medio compas?**
- No vuelve a empezar. La nota que toca sale de la posicion del reloj
  (`paso // 2`), no de un contador propio. Al cambiar de acorde solo cambian
  las notas y el ritmo sigue igual: como cambiar de carril en una carretera
- La nota que estaba sonando se cambia al instante por la del acorde nuevo
- Codigo: `Canal.nota_arpegio()`, `Canal.cambiar_acorde()`

**¿Como funciona la Secuencia y por que sigue al acorde?**
- El patron (`SECUENCIA` en `audio.py`) esta escrito en **pasos de la
  escala** contados desde la raiz del acorde: 0 = raiz, 2 = tercera,
  4 = quinta, 7 = raiz arriba, −3 = tres notas abajo...
- Al cambiar de acorde, la misma figura suena desde otra nota y siempre
  dentro de la tonalidad
- Las notas duran 3 pasos, asi se enciman y resuenan ("let ring")
- El patron por defecto lo sacamos de una tablatura; comprobamos que en Do#
  menor con el acorde i da exactamente las 16 notas de la tablatura
- Codigo: `musica.escalera()`, `Canal.nota_secuencia()`

**¿Como se desliza la nota al acostar la mano sin hacer ruidos ("clics")?**
- Normalmente una onda se calcula como `sin(2π·f·t)`. Si cambias f de golpe,
  la onda brinca y suena un clic
- Por eso la **fase se va acumulando muestra por muestra**: cada muestra
  avanza segun la frecuencia de ese momento, y la frecuencia cambia en linea
  recta dentro de cada bloque. La onda nunca brinca
- Ademas el valor se suaviza: se acerca 30 % al objetivo en cada bloque
  (~20 ms para llegar), aunque la camara mande datos a saltos
- Codigo: `Nota.generar()` (fase), `Canal.suavizar()`

**¿Como hicieron el hi-hat?**
- Sintesis como una caja de ritmos 808: seis ondas cuadradas a frecuencias
  que no son armonicas entre si (suenan metalicas) + un poco de ruido
- Un filtro pasa-altas deja solo lo agudo y se apaga en ~35 ms (cerrado)
- Toca en cada corchea, mas fuerte en cada tiempo: marca el pulso sin sonar
  a metronomo
- Codigo: `crear_hihat()`, `patron_hihat()`

**¿Se pueden poner beats propios?**
- Si. Cada archivo .mid en la carpeta `beats/` aparece como boton. Se lee
  con `mido`: cada golpe guarda su posicion (en pasos, con decimales para
  respetar el swing), su nota y su fuerza
- Los sonidos se buscan en `beats/sonidos/` por numero de nota (36.wav) o por
  su nombre General MIDI (bombo.wav, tarola.wav...)
- Codigo: `Patron`, `cargar_beats()`, `cargar_sonidos()`, `leer_wav()`

**¿Por que no "truena" el audio aunque suenen muchas notas?**
- Al final se pasa todo por `tanh`, una curva que nunca pasa de −1 y 1:
  es un recorte suave (como un compresor). Asi dos acordes + beat nunca
  saturan feo

**¿Que tanto retraso tiene entre la mano y el sonido?**
- Camara + deteccion: un cuadro (~35 ms) y se guarda solo el cuadro mas
  reciente (`CAP_PROP_BUFFERSIZE = 1`)
- Confirmar la sena: 2 cuadros (~70 ms)
- Tarjeta de sonido: usamos **WASAPI** de Windows, ~22 ms. La forma normal
  (MME) tenia ~100 a 200 ms. Por eso el audio va a 48 kHz, que es lo que
  pide la tarjeta. Codigo: `_elegir_salida()`, `Motor.iniciar()`

---

## 6. Interfaz y diseno (Interfaces Avanzadas)

**¿Por que estos gestos?**
- Senas de un dedo para I a V: son faciles de recordar (dedo 1 = grado 1...)
- Amor y paz y "pulgar + menique" son senas que todos conocen y que no se
  confunden con las de un dedo
- Gestos continuos (girar, subir, acostar) para valores continuos
  (tonalidad, volumen, Mayor/menor) y senas discretas para opciones
  discretas (acordes)
- Gestos de "seguridad" que no se hacen por accidente para acciones grandes:
  doble puno 1 s para cambiar de modo

**¿Por que dos modos?**
- Para que los mismos gestos signifiquen cosas distintas sin confundirse:
  en Configurar el indice es cursor; en Play es una sena de acorde

**¿Que retroalimentacion le da al usuario?**
- Visual: esqueleto de cada mano en su color, cursor con anillo de progreso,
  barra del doble puno, barra de inclinacion, el grado que suena resaltado,
  el nombre del acorde, y ondas animadas del color del grado
- Sonora: clic al elegir algo y "whoosh" al cambiar de modo
- Siempre visible: barra de arriba con todos los ajustes y linea de ayuda
  abajo con los gestos del modo actual

**¿Que son las ondas de abajo?**
- Cada nota del acorde se dibuja como una onda senoidal con su frecuencia
  real relativa (la tercera mayor vibra 1.26 veces la raiz, la quinta 1.5)
  y se suman. Por eso un Mayor, un menor y un disminuido se ven distintos
- Se mueven con el tiempo y cambian cuando acuestas la mano
- Codigo: `dibujar_ondas()` en `main.py`

**¿Es accesible?**
- Funciona con cualquier mano: cada una tiene su configuracion
- Se puede elegir "alzar" o "bajar" dedos segun lo que sea mas comodo
- No hay que tocar nada (ni teclado ni mouse); solo hay teclas de respaldo
  (q = salir, m = modo, espacio = beat)

---

## 7. Pruebas

**¿Como probaron que funciona?**
- `probar_gestos.py`: crea **manos simuladas** (los 21 puntos calculados a
  mano, con los dedos alzados, pellizcos o giros que se quieran) y se las
  pasa al programa como si vinieran de la camara. Son **64 pruebas
  automaticas**: senas, pellizcos, giro de la rueda, cursor, aplauso, doble
  puno, dos manos, inclinacion, octavas y que la pantalla se dibuje sin error
- `probar_audio.py`: genera archivos WAV de cada instrumento y ritmo para
  escucharlos sin camara, y mide cuanto tarda en generarse cada bloque
- Ademas medimos: que el beat y la secuencia caigan en la misma muestra, que
  la tercera se deslice de Mi (330 Hz) a Re# (311 Hz), y que la secuencia de
  la tablatura salga nota por nota

**¿Por que probar con manos simuladas?**
- Porque con la camara cada prueba es distinta (luz, posicion). Con manos
  simuladas el resultado es siempre el mismo y se puede repetir en segundos
  cada vez que cambiamos el codigo

---

## 8. Limitaciones y que mejorariamos

- Con poca luz o fondo con colores de piel MediaPipe pierde puntos
- Si una mano tapa a la otra, MediaPipe puede confundir cual es cual
- El pulgar es el dedo menos confiable; por eso las senas lo toleran
- No hay reverb (eco de sala); se podria agregar con un filtro de retardo
- La guitarra no se puede "doblar" a medio sonido (cambia de semitono en
  semitono); los demas instrumentos si
- Mejoras posibles: grabar lo que se toca a un archivo, mas patrones de
  secuencia elegibles desde la interfaz, mas beats

---

## Glosario rapido

| Palabra | Significado |
|---|---|
| Landmark / punto | Cada uno de los 21 puntos que MediaPipe da por mano |
| Histeresis | Usar un limite para entrar y otro para salir, para que no parpadee |
| Dwell | Sostener el cursor sobre un boton para confirmarlo |
| Grado | Acorde construido sobre cada nota de la escala (I a VII) |
| Tercera / quinta | Notas 3 y 5 de la escala contando desde la raiz del acorde |
| Semitono | La distancia mas chica entre dos notas (una tecla del piano) |
| MIDI | Numeracion de notas (60 = Do central) y formato de archivo musical |
| BPM | Pulsos por minuto: el tempo |
| Paso | Una semicorchea; hay 16 por compas |
| Muestra | Cada numero del audio; se generan 48 000 por segundo |
| Sintesis | Crear el sonido con matematicas en vez de grabarlo |
| Latencia | Retraso entre hacer el gesto y oir el sonido |
