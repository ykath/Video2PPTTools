@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo VideoPPT 服务启动
echo ========================================
echo.

REM 检查Python环境
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.10 或更高版本
    echo.
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM 显示Python版本
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [信息] Python版本: %PYTHON_VERSION%
echo.

REM 加载配置文件
if exist config.env (
    echo [信息] 加载配置文件 config.env
    for /f "usebackq tokens=1,2 delims==" %%a in ("config.env") do (
        set "line=%%a"
        REM 跳过注释和空行
        if not "!line:~0,1!"=="#" if not "!line!"=="" (
            set "%%a=%%b"
        )
    )
) else (
    echo [警告] 未找到 config.env 配置文件，使用默认配置
)

REM 设置默认值
if not defined SERVER_PORT set SERVER_PORT=8002
if not defined SERVER_HOST set SERVER_HOST=127.0.0.1

echo [信息] 服务地址: http://%SERVER_HOST%:%SERVER_PORT%
echo [信息] 管理页面: http://%SERVER_HOST%:%SERVER_PORT%/manage/ppt
echo [信息] 浏览页面: http://%SERVER_HOST%:%SERVER_PORT%/
echo.
echo [提示] 按 Ctrl+C 停止服务
echo ========================================
echo.

REM 启动服务
uvicorn SpeechWeb.backend.app.main:app --host %SERVER_HOST% --port %SERVER_PORT%

if errorlevel 1 (
    echo.
    echo [错误] 服务启动失败！
    echo.
    echo 可能的原因:
    echo 1. 未安装依赖包，请运行: pip install -r requirements.txt
    echo 2. 端口 %SERVER_PORT% 已被占用
    echo 3. 缺少必要的文件或目录
    echo.
    pause
)

