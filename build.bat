@echo off
echo ==================================================
echo  Building Gigabyte Fan & Battery Manager with Nuitka
echo ==================================================
echo.
echo Cleaning up previous build...
if exist dist (
    rmdir /s /q dist
)
echo.

REM Activate your python environment if needed, e.g., conda activate fan
REM conda activate fan

echo Starting Nuitka build...
python -m nuitka ^
    --onefile ^
    --lto=yes ^
    --windows-console-mode=disable ^
    --windows-icon-from-ico=app_icon.ico ^
    --plugin-enable=pyside6 ^
    --include-data-file="gui/style.qss=gui/style.qss" ^
    --output-dir="dist" ^
    --output-filename="GigabyteFanBatteryManager" ^
    main.py

echo.
echo ==================================================
echo  Build finished. Check the 'dist' directory.
echo ==================================================
pause