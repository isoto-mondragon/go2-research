# Mandar al robot en lenguaje natural

> **Para quién:** quien quiere decirle al robot qué hacer con una frase, sin programar.
> **Qué hace:** escribes *"avanza dos metros y da la vuelta"*, Gemini lo traduce a
> una lista de acciones, tú la revisas y el robot la ejecuta. Igual en simulador
> y en el robot real.

```
frase ──► Gemini ──► plan (JSON) ──► validar y recortar ──► confirmar ──► robot.avanzar(), robot.girar_*()...
```

**El modelo no escribe código.** Solo rellena una lista de acciones de un menú
cerrado. Lo que no está en el menú, no se puede pedir; las cantidades se recortan
a los topes de `configs/params.yaml`; y los verbos de `robot` aplican encima sus
propios límites de velocidad, rampa y seguridad.

| acción | unidad | simulador | robot real |
|---|---|---|---|
| `avanzar`, `retroceder` | metros | sí | sí |
| `girar_izquierda`, `girar_derecha` | grados | sí | sí |
| `esperar` | segundos | sí | sí |
| `parar` | - | sí | sí |
| `levantarse`, `sentarse` | - | no hace nada | sí |

Los metros y los grados son **aproximados**: el robot no mide lo que avanza,
calcula `distancia = velocidad × tiempo`. Para 1 m en el robot real, mídelo.

## 1. Consigue una clave de Gemini (gratis)

1. Entra en <https://aistudio.google.com/apikey> con una cuenta de Google.
2. Pulsa **Create API key** y cópiala.
3. En la raíz del repositorio, si no existe `.env`: `cp .env.example .env`
4. Edita `.env` y rellena la línea (sin comillas ni espacios):

```
GEMINI_API_KEY=AIza...tu_clave
```

`.env` no se sube a git. **No la pegues en el chat, en un issue ni en un fichero
versionado.** En el plan gratuito, Google puede usar lo que envíes para mejorar
sus productos: no escribas nada que no quieras que salga de tu ordenador.

No hay que instalar nada ni reconstruir la imagen: el caso habla con la API con
la biblioteca estándar de Python.

## 2. Pruébalo en el simulador

Con el simulador abierto (`docs/GUIA.md`, parte 3) y `run_policy.py --mode sim
--teleop` en marcha, dentro del contenedor:

```bash
python3 usecases/uc06_lenguaje_natural/deploy/main.py --mode sim
```

Deberías ver `Modo sim. Dime que quieres que haga.` y un `>`. Prueba, por orden:

```
> avanza medio metro
> gira a la derecha 90 grados
> haz un cuadrado de un metro
> y ahora al reves
> salta
```

La última no está en el menú: el robot no se mueve y te dice qué sí puede hacer.
`salir` (o Ctrl-C) termina. Sin simulador, añade `--dry-run`: se traduce y se
"ejecuta de mentira" (no manda nada), pero sí hace falta internet y la clave.

## 3. El robot real

Primero `--dry-run`, y luego, con espacio libre de 3 m, el mando en la mano
(**L2 + B** lo para) y `docs/SAFETY.md` leído:

```bash
python3 usecases/uc06_lenguaje_natural/deploy/main.py --mode real --iface <IFACE>
```

En real **siempre pide confirmación** (`Ejecutar? [s/N]`) antes de mover nada.
Empieza con distancias pequeñas.

**Internet y robot a la vez:** el cable Ethernet va al robot, así que Gemini tiene
que llegar por otra interfaz (Wi-Fi del portátil). Si el robot funciona pero sale
`No hay conexion con Gemini`, es eso.

## Ajustes (`configs/params.yaml`, sección `mi_caso`)

| parámetro | qué hace |
|---|---|
| `modelo` | modelo de Gemini (`gemini-flash-lite-latest` por defecto: rápido y suficiente para 8 acciones) |
| `velocidad`, `velocidad_giro` | con qué velocidad se ejecuta el plan |
| `max_metros`, `max_grados`, `max_espera` | tope por acción; lo que pase se recorta |
| `max_pasos`, `max_segundos_plan` | un plan mayor se rechaza entero |
| `confirmar_en_sim` | pedir confirmación también en simulación |

## Cómo ampliarlo

- **Una acción nueva** (p. ej. `seguir_persona`): añádela a `ACCIONES` en
  `deploy/traductor.py` y una rama en `ejecutar()` de `deploy/ejecutor.py`. El
  modelo la usa sin más cambios, porque el menú sale de esa tabla.
- **Otro modelo o proveedor** (Claude, OpenAI, Ollama en local sin internet):
  solo cambia `Traductor.traducir()`; debe devolver el mismo JSON.
- **Que decida mirando** (*"ve hasta la persona"*): hace falta pasar la imagen al
  modelo y un bucle realimentado. Es el siguiente paso, no está hecho.

## Problemas

| se ve | qué pasa |
|---|---|
| `Falta GEMINI_API_KEY` | no está en `.env`, o `.env` no está en la raíz del repo |
| `Gemini rechaza la clave` | clave mal copiada, con comillas o espacios |
| `El modelo no existe` | cambia `modelo` en `params.yaml` |
| `Gemini saturado (503)` | pico de demanda de Google; reintenta solo hasta 3 veces. Si sigue, prueba otro `modelo` en `params.yaml` |
| `Demasiadas peticiones` | límite del plan gratuito (pocas peticiones por minuto); espera un minuto |
| `No hay conexion con Gemini` | sin internet (ver arriba, con el robot real) |
