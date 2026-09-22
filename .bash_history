id
touch /workspace/prueba && ls -la /workspace/prueba && rm /workspace/prueba
python3 -m go2core.paths
git -C /workspace rev-parse --short HEAD
python3 usecases/uc03_energy/eval/measure_cot.py --mode sim
python3 usecases/uc03_energy/eval/plot_cot.py experiments/uc03_energy/2026-09-22T101124_f14f4f7_cot
exit
