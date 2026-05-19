@echo off
echo ============================================
echo   Voice Monitor - Сборка в EXE
echo ============================================
echo.

echo [1/3] Установка зависимостей...
pip install pyinstaller
pip install -r requirements.txt
echo.

echo [2/3] Создание папки для модели...
if not exist "models" mkdir models
echo.

echo [3/3] Сборка EXE...
pyinstaller --onefile --windowed --name VoiceMonitor ^
    --add-data "config.py;." ^
    --add-data "profanity_list.py;." ^
    --add-data "profanity_detector.py;." ^
    --icon=NONE ^
    main.py

echo.
echo ============================================
echo   Сборка завершена!
echo   EXE файл: dist\VoiceMonitor.exe
echo ============================================
echo.
echo ВАЖНО: Не забудьте скачать модель Vosk:
echo https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip
echo Распакуйте в: models\vosk-model-small-ru\
echo.
pause
