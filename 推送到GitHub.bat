@echo off
chcp 65001 >nul
title DITTO! — 推送到 GitHub
cd /d "%~dp0"

echo ==================================================
echo   把 DITTO! 原型推送到你的 GitHub 仓库
echo ==================================================
echo.
echo 先在 GitHub 上新建一个【空仓库】（不要勾选 README / .gitignore）
echo 名字建议：ditto     可见性：Public 或 Private 都可以
echo.
set /p URL=把仓库地址粘贴到这里（例如 https://github.com/你的名字/ditto.git）：

if "%URL%"=="" (
  echo 没有输入地址，退出。
  pause
  exit /b 1
)

echo.
echo 正在设置远程地址...
git remote remove origin >nul 2>&1
git remote add origin %URL%

echo.
echo 正在推送（第一次会弹出 GitHub 登录窗口，登录你的账号即可）...
git branch -M main
git push -u origin main
if errorlevel 1 (
  echo.
  echo 推送失败。常见原因：
  echo   1) 仓库不是空的（新建时勾了 README）——把仓库删掉重建一个空仓库
  echo   2) 仓库地址写错
  echo   3) 登录窗口被关掉了——再运行一次这个 bat
  echo.
  pause
  exit /b 1
)

echo.
echo ==================================================
echo   推送成功！
echo   仓库里现在有：server.py / test.html / test-en.html / README.md 等
echo.
echo   下一步（永久上线）：
echo   1) 打开 render.com，用 GitHub 账号登录
echo   2) New -^> Web Service -^> 选择这个仓库
echo   3) Runtime 选 Python，Start Command 填：python server.py $PORT
echo   4) 部署完成后会得到一个 https://xxxx.onrender.com 的永久地址
echo ==================================================
pause
