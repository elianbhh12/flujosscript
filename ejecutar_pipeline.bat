@echo off
setlocal

rem Se ubica siempre en la carpeta donde esta este .bat, sin importar
rem desde donde lo ejecutes (doble clic, acceso directo, etc.)
cd /d "%~dp0"

echo ============================================================
echo   PIPELINE DYNAMO - config-control / text-analyzer / UDZ
echo ============================================================
echo.

where python >nul 2>nul
if errorlevel 1 goto :sin_python

python -c "import boto3, openpyxl" >nul 2>nul
if errorlevel 1 goto :instalar_dependencias

:ejecutar
python -m python_pipeline.cli
goto :fin

:instalar_dependencias
echo Instalando dependencias necesarias (boto3, openpyxl)...
python -m pip install -r requirements.txt
if errorlevel 1 goto :error_pip
echo.
goto :ejecutar

:sin_python
echo ERROR: no se encontro "python" en el PATH de este equipo.
echo Instala Python 3.9 o superior y vuelve a intentar.
echo.
pause
exit /b 1

:error_pip
echo.
echo ERROR: no se pudieron instalar las dependencias.
pause
exit /b 1

:fin
echo.
echo ============================================================
pause
