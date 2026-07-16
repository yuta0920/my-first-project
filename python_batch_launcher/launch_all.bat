@echo off
rem このファイルをダブルクリックすると、scripts.txt に書かれた全スクリプトが起動します。
cd /d "%~dp0"
python launch_all.py
if errorlevel 1 (
    echo.
    echo エラーが発生しました。上のメッセージを確認してください。
    pause
)
