@echo off
REM Batch script to activate conda environment and run PyInstaller

echo Activating conda environment 'fan'...
call conda activate fan

REM Check if conda activate was successful. Note: Error checking for conda activate can be tricky in batch.
REM This basic check might not catch all activation issues.
if errorlevel 1 (
    echo ERROR: Failed to activate conda environment 'fan'.
    echo Please ensure the environment exists and conda is initialized for your shell.
    pause
    exit /b 1
)

echo Running  main.py...
python  .\main.py 

if errorlevel 1 (
    echo ERROR: Failed. Check the output above for details.
    pause
    exit /b 1
)

echo PyInstaller process completed successfully.
