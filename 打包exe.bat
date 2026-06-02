@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo   打包为单文件 .exe
echo ========================================
echo.

echo [1/2] 安装 PyInstaller...
pip install pyinstaller -q

echo [2/2] 开始打包（约 2-5 分钟）...
pyinstaller --onefile --windowed --name "抖音评论爬虫" ^
  --add-data "douyin.js;." ^
  --hidden-import customtkinter ^
  --hidden-import CTkMessagebox ^
  --hidden-import httpx ^
  --hidden-import execjs ^
  --hidden-import playwright ^
  --hidden-import cookiesparser ^
  --collect-all customtkinter ^
  gui.py

echo.
echo ========================================
echo   打包完成！exe 在 dist/ 文件夹
echo ========================================
pause
