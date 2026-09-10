# uc04_person_following

## Pregunta de investigacion
<Una frase. Si no cabe en una frase, el caso de uso no esta acotado.>

## Hipotesis
<Que esperas medir y por que seria publicable.>

## Estado
- [ ] Entorno de simulacion
- [ ] Politica entrenada
- [ ] Validada en unitree_mujoco
- [ ] Desplegada en robot real
- [ ] Protocolo de evaluacion cerrado
- [ ] Resultados en `results/`

## Blockers
<Que te impide avanzar hoy.>

## Estructura
- `configs/`   configuracion versionada. NUNCA hardcodear parametros fuera de aqui.
- `train/`     entrenamiento (Colab o local)
- `deploy/`    inferencia sobre DDS (sim y real, mismo codigo)
- `eval/`      protocolo de evaluacion reproducible
- `notebooks/` exploracion. Lo que sobreviva se promueve a train/ o eval/
