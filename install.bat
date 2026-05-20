@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

title VoiceMonitor — Установка

echo.
echo  ============================================
echo     VoiceMonitor — Установка
echo  ============================================
echo.

:: Проверяем Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo  [1/3] Python не найден. Скачиваю...
    echo.
    
    set PYTHON_URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
    set PYTHON_EXE=%TEMP%\vm_python_setup.exe
    
    powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON_EXE%' -UseBasicParsing" 2>nul
    
    if not exist "%PYTHON_EXE%" (
        echo.
        echo   Ошибка скачивания Python.
        echo   Проверьте интернет-соединение.
        echo.
        pause
        exit /b 1
    )
    
    echo   Установка Python (тихая, ~1 мин)...
    start /wait "" "%PYTHON_EXE%" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_test=0
    del "%PYTHON_EXE%" 2>nul
    
    echo   Python установлен!
    echo.
) else (
    echo  [1/3] Python найден!
    echo.
)

:: Перезагружаем PATH
for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v PATH 2^>nul') do set "UPATH=%%B"
for /f "tokens=2*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PATH 2^>nul') do set "SPATH=%%B"
set "PATH=%UPATH%;%SPATH%;%PATH%"

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo   Python не найден в PATH.
    echo   Перезапустите компьютер и попробуйте снова.
    echo.
    pause
    exit /b 1
)

echo  [2/3] Установка зависимостей...
echo.
python -m pip install --upgrade pip -q 2>nul
python -m pip install pyaudio vosk pystray Pillow python-Levenshtein pygame -q 2>nul

if %errorlevel% neq 0 (
    echo.
    echo   Ошибка установки зависимостей.
    echo   Попробуйте запустить install.bat от имени администратора.
    echo.
    pause
    exit /b 1
)

echo  [3/3] Готово!
echo.
echo  ============================================
echo     Запуск VoiceMonitor
echo  ============================================
echo.
echo  При первом запуске будет скачана модель (~50 MB).
echo  Нажмите Ctrl+C в окне программы для остановки.
echo.

python app.py
pause
