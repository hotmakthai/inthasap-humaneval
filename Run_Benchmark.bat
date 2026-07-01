@echo off
chcp 65001 >nul
title Council Benchmark
cd /d C:\Inthasap_Guard\Council_Lab
echo ============================================================
echo   COUNCIL BENCHMARK - measuring the council (uses real API)
echo ============================================================
echo.
python run_benchmark.py
echo.
echo ============================================================
echo   Done. Result saved in benchmarks\results\
echo ============================================================
pause
