# 本地部署方案（不使用 Python 虚拟环境）

本文档说明如何在本地启动当前 PPT 服务，且**不使用 Python 虚拟环境**。

适用场景：

- 你不想使用 `.venv`
- 你希望尽快在本机把服务跑起来
- 你当前主要使用 Windows PowerShell

当前最推荐的本地方案是：

1. `Docker` 本地运行
2. 系统 Python 直接安装依赖并运行

## 1. 推荐方案：Docker 本地运行

这是最稳的方式，因为：

- 不依赖本机 Python 环境是否干净
- 不依赖 PowerShell 激活脚本
- 不容易遇到包版本冲突
- 和后续服务器部署方式一致

### 1.1 准备条件

本机需要：

- 已安装 Docker Desktop
- Docker Desktop 已启动

先确认 Docker 可用：

```powershell
docker version
docker compose version
```

如果 Docker 没启动，先打开 Docker Desktop。

### 1.2 配置环境变量

在项目根目录执行：

```powershell
Copy-Item .env.example .env
```

然后编辑 `.env`，至少填这两个：

```text
DEEPSEEK_API_KEY=你的_deepseek_key
OPENAI_API_KEY=你的_openai_key
```

如果你用官方接口，通常不用改：

```text
DEEPSEEK_BASE_URL=https://api.deepseek.com
OPENAI_BASE_URL=https://api.openai.com/v1
IMAGE_MODEL=gpt-image-2
```

### 1.3 启动服务

在项目根目录执行：

```powershell
docker compose up -d --build
```

查看日志：

```powershell
docker compose logs -f
```

查看状态：

```powershell
docker compose ps
```

停止服务：

```powershell
docker compose down
```

### 1.4 访问服务

启动成功后访问：

```text
http://127.0.0.1
```

健康检查：

```powershell
curl http://127.0.0.1/health
```

## 2. 备选方案：系统 Python 直接运行

如果你暂时不用 Docker，也可以直接使用系统 Python，不创建虚拟环境。

这个方案更简单，但要注意：

- 会把依赖安装到你当前 Python 环境
- 可能和你机器上已有的 Python 包冲突
- 后续升级依赖时更容易变脏

### 2.1 先确认 Python 和 pip

在 PowerShell 执行：

```powershell
python --version
python -m pip --version
```

建议 Python 版本：

```text
Python 3.11
```

如果 `python -m pip --version` 报错，说明你当前 Python 没带 pip，这条路就不适合，建议直接走 Docker。

### 2.2 安装依赖

在项目根目录执行：

```powershell
python -m pip install -r server\requirements.txt
```

如果你不想把包装到全局 site-packages，可以用用户目录安装：

```powershell
python -m pip install --user -r server\requirements.txt
```

### 2.3 配置环境变量

先复制模板：

```powershell
Copy-Item .env.example .env
```

然后编辑 `.env`，至少填入：

```text
DEEPSEEK_API_KEY=你的_deepseek_key
OPENAI_API_KEY=你的_openai_key
```

### 2.4 启动服务

在项目根目录执行：

```powershell
python -m uvicorn server.app:app --host 0.0.0.0 --port 8000 --reload
```

如果 `python -m uvicorn` 找不到模块，说明 `uvicorn` 没装成功，重新执行：

```powershell
python -m pip install uvicorn[standard]
```

### 2.5 访问服务

```text
http://127.0.0.1:8000
```

健康检查：

```powershell
curl http://127.0.0.1:8000/health
```

## 3. 如何使用

### 3.1 查询风格

```powershell
curl http://127.0.0.1:8000/styles
```

### 3.2 上传 Markdown 生成 PPT

```powershell
curl -X POST http://127.0.0.1:8000/jobs `
  -F "file=@.\example.md" `
  -F "style=clean-professional" `
  -F "language=zh" `
  -F "page_count=8" `
  -F "image_concurrency=2"
```

### 3.3 上传 PDF 生成 PPT

```powershell
curl -X POST http://127.0.0.1:8000/jobs `
  -F "file=@.\example.pdf" `
  -F "style=scientific-defense" `
  -F "language=zh" `
  -F "image_concurrency=3"
```

返回结果里会有：

```json
{
  "job_id": "你的任务ID",
  "status": "queued"
}
```

### 3.4 查询任务状态

```powershell
curl http://127.0.0.1:8000/jobs/你的任务ID
```

### 3.5 下载结果

```powershell
curl -L http://127.0.0.1:8000/jobs/你的任务ID/download -o result.pptx
```

## 4. Windows PowerShell 常见问题

### 4.1 `source` 不能用

原因：

- `source` 是 Linux/macOS 的 shell 命令
- PowerShell 不支持这个命令

这也是为什么这里不再推荐你走虚拟环境激活路线。

### 4.2 `Activate.ps1` 报错

原因：

- PowerShell 的执行策略限制
- 或命令路径写法不对

既然你明确不想用虚拟环境，这个问题可以直接绕开。

### 4.3 `python -m pip` 不可用

说明：

- 当前系统 Python 没有 pip

处理：

- 优先改用 Docker
- 或重装一个带 pip 的 Python

### 4.4 `docker compose build` 失败

常见原因：

- Docker Desktop 没启动
- 网络无法拉取基础镜像
- 无法访问 Python 包下载源

排查命令：

```powershell
docker compose config
docker compose ps
docker compose logs -f
```

## 5. 最终建议

如果你明确不想使用 Python 虚拟环境，本地最推荐的启动方式就是：

```text
Docker Desktop + docker compose up -d --build
```

这是最省心、最接近服务器部署、也最不容易踩 PowerShell 环境问题的方案。
