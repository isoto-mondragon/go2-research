# uc00 — Plantilla de caso de uso

Un caso de uso completo y ejecutable, vacío de lógica. Se copia, se renombra y
ya funciona: trae resueltos los argumentos, el contrato, las dos salidas
(simulador y robot real), los límites de velocidad, la rampa, la parada al
salir y el registro con `manifest.json`.

Por defecto lee la telemetría del robot, la imprime y manda velocidad cero.
Todo lo demás lo pones tú en un único sitio.

## Probarla (sin mover nada)

```bash
python3 usecases/uc00_plantilla/deploy/main.py --mode sim --dry-run
```

Funciona aunque no haya simulador: avisa de que no hay telemetría y sigue. Con
el simulador arrancado imprime inclinación, batería y temperatura reales (en
simulación los dos últimos salen a 0: no hay `bms_state` ni temperatura).

## Crear tu caso de uso

```bash
cp -r usecases/uc00_plantilla usecases/uc05_mi_caso
python3 usecases/uc05_mi_caso/deploy/main.py --mode sim --dry-run    # sigue funcionando
```

El nombre de la carpeta es el nombre del caso en `experiments/`; no hay que
cambiar nada en el código. Después:

1. **`deploy/main.py`, función `decidir()`**: busca `AQUÍ VA TU LÓGICA`. Recibe
   la telemetría y el tiempo, devuelve `(vx, vy, wz)`. No te ocupes de límites
   ni rampas: el limitador los aplica después.
2. **`configs/params.yaml`**: topes de velocidad, rampa y seguridad. Tus
   parámetros van en `mi_caso:`; se guardan enteros en cada `manifest.json`.
3. **`eval/measure.py`, función `medir()`**: sustituye las métricas de ejemplo
   por las tuyas.
4. Cambia este README y da de alta el caso en la tabla del `README.md` raíz.

## Ejecutar

| qué | comando |
|---|---|
| comprobar, sin enviar nada | `... deploy/main.py --mode sim --dry-run` |
| simulación | simulador + `run_policy.py --mode sim --teleop`, y luego `... deploy/main.py --mode sim` |
| robot real, primero en seco | `... deploy/main.py --mode real --dry-run` |
| robot real | `... deploy/main.py --mode real` (pide confirmación; mando en la mano) |
| registrar el experimento | añade `--log --tag mi_etiqueta` |
| medir lo registrado | `python3 usecases/<uc>/eval/measure.py` |

Otros argumentos: `--iface`, `--duration` (10 s por defecto), `--config`.

## Cosas que no son fallos

- **En simulación el robot solo se mueve con la política RL.** unitree_mujoco
  no emula Sport Mode; hace falta `run_policy.py --teleop` escuchando.
- **En el robot real, por debajo de ~0.2 m/s Sport Mode ignora la orden.** La
  plantilla sube las órdenes pequeñas a ese mínimo (`vel_min_util`).
- **En el robot real la salida llama a `SportClient` directamente**, con la
  secuencia completa `StandUp` → `BalanceStand` → `Move`. Con `Go2Controller`,
  uc04 no movía el robot; la causa probable es que falta `BalanceStand()`
  (pendiente de verificar con el robot). Ver `docs/API.md`.

## Reglas del proyecto

- Todo script que mueva el robot tiene `--dry-run`.
- Todo experimento tiene `manifest.json` con el sha de git; `measure.py` se
  niega a medir uno sin él. Haz commit antes de medir: con cambios sin
  commitear el run no es reproducible.
- Antes de tocar el robot físico, [`docs/SAFETY.md`](../../docs/SAFETY.md).

Las líneas exactas de cada operación (leer estado, mover, contrato, rutas,
cámara, registro) están en [`docs/API.md`](../../docs/API.md).
