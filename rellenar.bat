@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Preparando el entorno de Python por primera vez...
    py -3 -m venv .venv 2>nul || python -m venv .venv
    if not exist ".venv\Scripts\python.exe" goto sinpython
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
    if errorlevel 1 goto error
)
".venv\Scripts\python.exe" rellenar.py %*
echo.
pause
exit /b

:sinpython
echo No se ha encontrado Python. Instalalo desde https://www.python.org/downloads/
echo (marca la casilla "Add python.exe to PATH") y vuelve a intentarlo.
pause
exit /b 1

:error
echo No se han podido instalar las dependencias. Comprueba la conexion a internet.
pause
exit /b 1
