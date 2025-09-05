call conda activate fan

echo Starting Nuitka build...
python -m nuitka ^
    --standalone ^
    --lto=yes ^
    --windows-console-mode=disable ^
    --windows-icon-from-ico=app_icon.ico ^
    --plugin-enable=pyside6 ^
    --nofollow-import-to=tkinter,unittest ^
    --jobs=%NUMBER_OF_PROCESSORS% ^
    --remove-output ^
    --include-data-file="gui/style.qss=gui/style.qss" ^
    --include-data-file="app_icon.ico=app_icon.ico" ^
    --output-dir="dist" ^
    main.py

pause