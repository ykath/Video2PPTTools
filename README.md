# VideoPPT 独立部署包

视频转PPT服务独立部署版本，支持Bilibili和YouTube视频自动下载、截图提取、PPT生成及本地播放。

## 功能特性

- ✅ **视频下载**: 支持Bilibili和YouTube视频自动下载
- ✅ **智能截图**: 自动提取视频关键帧，去重相似画面
- ✅ **PPT生成**: 将截图自动转换为PowerPoint演示文稿
- ✅ **视频管理**: Web界面管理所有已处理的视频任务
- ✅ **本地播放**: 支持视频本地播放，截图时间轴导航

## 环境要求

- **Python**: 3.10 或更高版本
- **操作系统**: Windows 10/11
- **硬盘空间**: 建议至少10GB可用空间（用于存储视频和截图）

## 快速开始

### 1. 安装Python依赖

在部署目录下打开命令行，执行：

```bash
pip install -r requirements.txt
```

### 2. 配置服务（可选）

编辑 `config.env` 文件修改配置：

```ini
# 服务端口（默认8002）
SERVER_PORT=8002
SERVER_HOST=127.0.0.1

# 工具路径（通常无需修改）
BBDOWN_EXECUTABLE=tools/BBDown.exe
YTDLP_EXECUTABLE=tools/yt-dlp.exe
```

### 3. FFMpeg 工具安装
确认本机安装并环境配置了ffmpeg工具，BBDown在下载视频过程中需要使用该工具进行视频、音频合并处理。
https://www.gyan.dev/ffmpeg/builds/#release-builds

### 4. 启动服务

双击运行 `start_server.bat` 或在命令行执行：

```bash
start_server.bat
```

服务启动后会显示访问地址，默认为：
- **主页**: http://127.0.0.1:8002/
- **管理页面**: http://127.0.0.1:8002/manage/ppt

## 使用说明

### 添加视频任务

1. 访问管理页面: http://127.0.0.1:8002/manage/ppt
2. 在"添加新任务"表单中输入视频URL
3. 配置参数（可选）：
   - **相似度阈值**: 0-1之间，越高去重越严格（推荐0.95）
   - **最小间隔**: 截图最小时间间隔（秒）
   - **跳过开头**: 跳过视频开头N秒
4. 点击"提交任务"

### 浏览已处理视频

1. 访问主页: http://127.0.0.1:8002/
2. 浏览所有已完成的视频任务
3. 点击视频卡片进入播放页面
4. 支持搜索功能，可按标题或URL检索

### 本地播放

1. 在主页点击视频卡片
2. 进入播放页面，上方播放视频，下方显示截图时间轴
3. 双击截图可跳转到对应时间点
4. 支持多分段视频切换

## 目录结构

```
VideoPPTDeploy/
├── config.env                    # 配置文件
├── start_server.bat              # 启动脚本
├── requirements.txt              # Python依赖
├── README.md                     # 本文档
├── tools/                        # 下载工具
│   ├── BBDown.exe               # B站下载器
│   └── yt-dlp.exe               # YouTube下载器
├── Src/                          # 核心代码
│   ├── config.py                # 配置模块
│   ├── database.py              # 数据库模块
│   └── video_to_ppt/            # 视频转PPT模块
├── SpeechWeb/                    # Web服务
│   ├── backend/                 # 后端API
│   └── frontend/                # 前端资源
├── data/                         # 数据目录
│   ├── speech_videos.db         # 数据库文件
│   └── video_to_ppt_jobs/       # 任务数据（视频、截图、PPT）
└── logs/                         # 日志目录（自动创建）
```

## 配置说明

### config.env 配置项

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| SERVER_PORT | 服务端口 | 8002 |
| SERVER_HOST | 服务地址 | 127.0.0.1 |
| BBDOWN_EXECUTABLE | BBDown工具路径 | tools/BBDown.exe |
| YTDLP_EXECUTABLE | yt-dlp工具路径 | tools/yt-dlp.exe |
| VIDEO_TO_PPT_ROOT | 数据存储目录 | data/video_to_ppt_jobs |
| DATABASE_PATH | 数据库文件路径 | data/speech_videos.db |

### 任务参数说明

| 参数 | 说明 | 默认值 | 范围 |
|------|------|--------|------|
| similarity_threshold | 相似度阈值 | 0.95 | 0-1 |
| min_interval_seconds | 最小截图间隔（秒） | 2.0 | >0 |
| skip_first_seconds | 跳过开头（秒） | 0 | ≥0 |
| image_format | 图片格式 | jpg | jpg/png |
| image_quality | 图片质量 | 95 | 1-100 |

## 常见问题

### 1. 服务启动失败

**问题**: 运行 `start_server.bat` 后报错

**解决方案**:
- 确认已安装Python 3.10+
- 确认已安装依赖: `pip install -r requirements.txt`
- 检查端口是否被占用，可修改 `config.env` 中的 `SERVER_PORT`

### 2. 视频下载失败

**问题**: 任务状态显示"failed"

**解决方案**:
- **B站视频**: 确认 `tools/BBDown.exe` 存在
- **YouTube视频**: 确认 `tools/yt-dlp.exe` 存在
- 检查网络连接
- 查看任务详情中的错误信息

### 3. 无法访问Web界面

**问题**: 浏览器无法打开服务地址

**解决方案**:
- 确认服务已成功启动
- 检查防火墙设置
- 尝试使用 `http://localhost:8002` 访问

### 4. 已有数据无法显示

**问题**: 复制到新电脑后，视频和截图无法访问

**解决方案**:
- 确认 `data/video_to_ppt_jobs/` 目录完整复制
- 确认数据库文件 `data/speech_videos.db` 已复制
- 路径转换脚本已自动执行，无需手动处理

## 迁移到其他电脑

1. **复制整个部署目录**到目标电脑
2. **安装Python** 3.10或更高版本
3. **安装依赖**: `pip install -r requirements.txt`
4. **启动服务**: 运行 `start_server.bat`

所有路径已转换为相对路径，无需额外配置。

## 技术支持

### API文档

服务启动后访问: http://127.0.0.1:8002/docs

### 日志查看

日志文件位于 `logs/` 目录，可用于故障排查。

### 数据备份

重要数据位于 `data/` 目录：
- `speech_videos.db`: 数据库文件
- `video_to_ppt_jobs/`: 所有视频、截图和PPT文件

建议定期备份此目录。

## 更新历史

- **v0.1.0** (2025-11): 初始独立部署版本
  - 支持Bilibili和YouTube视频
  - 智能截图提取
  - PPT自动生成
  - Web管理界面
  - 本地视频播放

## 许可证

本软件仅供学习和个人使用。

