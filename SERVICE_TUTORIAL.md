# PPT 服务使用教程

本文档对应当前仓库里的第一版 PPT 生成服务实现，覆盖：

- 本地如何启动
- 服务端如何启动
- 接口如何使用
- 常见问题怎么排查

当前服务能力：

- 输入文件支持 `.md` 和 `.pdf`
- DeepSeek 负责生成 `deck_spec.json`
- `gpt-image-2` 负责逐页生成整页幻灯片图片
- 自动组装为 `.pptx`
- 支持页数、语言、图片生成并发数等参数

## 1. 目录说明

本次新增的服务代码主要在：

- `server/app.py`：FastAPI 入口
- `server/worker.py`：后台任务 worker
- `server/pipeline/`：文本抽取、规划、生图、组装
- `server/Dockerfile`：镜像构建文件
- `docker-compose.yml`：容器启动配置
- `nginx/default.conf`：Nginx 反向代理配置
- `.env.example`：环境变量模板

任务输出目录默认是：

```text
./data/jobs/{job_id}/
```

每个任务目录通常包含：

```text
input.md / input.pdf
extracted.txt
deck_spec.json
status.json
job.log
origin_image/
speech.md
output.pptx
```

## 2. 启动前准备

启动前需要准备两个 key：

- `DEEPSEEK_API_KEY`
- `OPENAI_API_KEY`

其中：

- DeepSeek 用于生成 PPT 结构化方案
- OpenAI 的 `gpt-image-2` 用于生成每页幻灯片图片

还需要确认：

- 本机或服务器可以访问 DeepSeek API
- 本机或服务器可以访问 OpenAI API
- 如果走代理或中转站，配置对应的 `BASE_URL`

## 3. 环境变量说明

先复制模板文件：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

然后编辑 `.env`，至少填入：

```text
DEEPSEEK_API_KEY=你的_deepseek_key
OPENAI_API_KEY=你的_openai_key
```

如果你使用默认官方地址，通常不需要改：

```text
DEEPSEEK_BASE_URL=https://api.deepseek.com
OPENAI_BASE_URL=https://api.openai.com/v1
IMAGE_MODEL=gpt-image-2
```

几个重要参数：

- `MAX_ACTIVE_JOBS`：同时运行的 PPT 任务数，建议 `1`
- `MAX_IMAGE_CONCURRENCY_PER_JOB`：单个任务内部允许的最大图片并发数，建议 `5`
- `MAX_IMAGE_RETRIES`：每页图片失败后的自动重试次数，默认 `2`
- `API_TOKEN`：如果服务对外暴露，建议设置

## 4. 本地启动

本地启动有两种方式：

- Python 直接运行
- Docker 运行

### 4.1 用 Python 直接运行

建议使用 Python 3.11。

先安装依赖：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r server/requirements.txt
```

Windows PowerShell：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r server\requirements.txt
```

然后启动服务：

```bash
uvicorn server.app:app --host 0.0.0.0 --port 8000 --reload
```

启动后访问：

```text
http://127.0.0.1:8000
```

健康检查：

```text
GET http://127.0.0.1:8000/health
```

### 4.2 用 Docker 本地运行

前提：

- 已安装 Docker Desktop 或 Docker Engine
- Docker daemon 已启动

启动：

```bash
docker compose up -d --build
```

查看日志：

```bash
docker compose logs -f
```

停止服务：

```bash
docker compose down
```

启动后访问：

```text
http://127.0.0.1
```

## 5. 服务端启动

服务器上推荐直接用 Docker Compose。

### 5.1 准备条件

服务器需要：

- Linux 服务器更合适
- 已安装 Docker
- 已安装 Docker Compose
- 能访问 DeepSeek 和 OpenAI API

### 5.2 上传代码

把整个项目目录上传到服务器，例如：

```text
/opt/ppt-service
```

进入项目目录：

```bash
cd /opt/ppt-service
```

### 5.3 配置环境变量

```bash
cp .env.example .env
vim .env
```

至少填入：

```text
DEEPSEEK_API_KEY=你的_deepseek_key
OPENAI_API_KEY=你的_openai_key
```

如果服务要暴露给外部用户，建议再加：

```text
API_TOKEN=你自己的访问令牌
```

### 5.4 启动服务

```bash
docker compose up -d --build
```

查看状态：

```bash
docker compose ps
```

查看日志：

```bash
docker compose logs -f
```

停止服务：

```bash
docker compose down
```

重启服务：

```bash
docker compose restart
```

### 5.5 反向代理

如果你要对外提供服务，建议前面加 Nginx 或 Caddy，再转发到：

```text
127.0.0.1:8000
```

同时建议：

- 配 HTTPS
- 配 `API_TOKEN`
- 限制来源 IP 或加基础鉴权

## 6. 接口说明

当前服务接口有四个核心接口：

- `GET /health`
- `GET /styles`
- `POST /jobs`
- `GET /jobs/{job_id}`
- `GET /jobs/{job_id}/download`

如果设置了 `API_TOKEN`，请求时需要带上：

```text
Authorization: Bearer 你的_token
```

或者：

```text
X-API-Token: 你的_token
```

## 7. 如何使用

### 7.1 查询可用风格

```bash
curl http://127.0.0.1:8000/styles
```

带 token：

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://127.0.0.1:8000/styles
```

### 7.2 创建 PPT 任务

接口：

```text
POST /jobs
```

表单参数：

- `file`：上传的 `.md` 或 `.pdf`
- `style`：风格 ID，例如 `clean-professional`
- `page_count`：可选；不填则自动建议
- `language`：`zh` 或 `en`
- `title`：可选标题
- `image_concurrency`：图片并发数，范围 `2-5`

示例：

```bash
curl -X POST http://127.0.0.1:8000/jobs \
  -F "file=@./example.md" \
  -F "style=clean-professional" \
  -F "language=zh" \
  -F "page_count=8" \
  -F "image_concurrency=2"
```

带 token：

```bash
curl -X POST http://127.0.0.1:8000/jobs \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@./example.pdf" \
  -F "style=scientific-defense" \
  -F "language=zh" \
  -F "title=Transformer论文答辩" \
  -F "image_concurrency=3"
```

返回示例：

```json
{
  "job_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "status": "queued",
  "page_count": 8,
  "language": "zh",
  "image_concurrency": 2
}
```

### 7.3 查询任务状态

```bash
curl http://127.0.0.1:8000/jobs/JOB_ID
```

返回示例：

```json
{
  "job_id": "JOB_ID",
  "status": "generating_images",
  "total_slides": 8,
  "completed_slides": 3,
  "page_count": 8,
  "language": "zh",
  "style": "clean-professional",
  "image_concurrency": 2,
  "error_message": null,
  "created_at": "2026-06-15T12:00:00+00:00",
  "updated_at": "2026-06-15T12:03:00+00:00",
  "download_url": null
}
```

状态说明：

- `queued`：已进入队列
- `extracting`：正在提取文本
- `planning`：正在调用 DeepSeek 规划
- `generating_images`：正在逐页生图
- `assembling`：正在组装 PPT
- `completed`：已完成
- `failed`：失败

### 7.4 下载 PPT

只有当任务状态为 `completed` 时才能下载：

```bash
curl -L http://127.0.0.1:8000/jobs/JOB_ID/download -o result.pptx
```

带 token：

```bash
curl -L http://127.0.0.1:8000/jobs/JOB_ID/download \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -o result.pptx
```

## 8. 运行机制说明

### 8.1 页数规则

- 如果传了 `page_count`，服务会按这个页数要求 DeepSeek 生成
- 如果没传 `page_count`，服务会根据文本长度自动建议页数

### 8.2 图片并发规则

- 请求时可以传 `image_concurrency`
- 允许范围是 `2-5`
- 实际生效值还会受环境变量 `MAX_IMAGE_CONCURRENCY_PER_JOB` 限制

### 8.3 自动重试

生图阶段内置自动重试，不需要手动重试。

默认规则：

- 每页最多重试 `2` 次
- 总共尝试 `3` 次
- 对超时、429、5xx、网络异常自动重试
- 如果返回成功但图片损坏或为空，也自动重试

## 9. 如何查看生成结果

任务目录在：

```text
data/jobs/{job_id}/
```

重点文件：

- `status.json`：任务状态
- `job.log`：详细日志
- `extracted.txt`：提取后的文本
- `deck_spec.json`：DeepSeek 生成的结构化方案
- `origin_image/`：每页最终图片
- `speech.md`：讲稿
- `output.pptx`：最终 PPT

## 10. 常见问题

### 10.1 `Job queue is full`

说明：

- 当前排队任务太多

处理：

- 等待已有任务完成
- 或调大 `.env` 里的 `MAX_QUEUED_JOBS`

### 10.2 PDF 提取失败

说明：

- 第一版只支持文字型 PDF
- 扫描版 PDF 可能提取不到有效文本

处理：

- 先把 PDF OCR 成可复制文本
- 或先转成 Markdown / 文本再上传

### 10.3 生图失败

说明：

- 外部模型接口不稳定
- 已经内置自动重试

处理：

- 查看 `job.log`
- 检查 API key 是否有效
- 检查 API 配额和网络连接

### 10.4 Docker 无法启动

常见原因：

- Docker daemon 没启动
- `.env` 没配置
- 服务器无法访问外部 API

排查命令：

```bash
docker compose ps
docker compose logs -f
docker compose config
```

## 11. 推荐使用方式

个人本地试跑：

- 先用 Python 直接启动
- 用 `curl` 或 Postman 调接口

服务器长期运行：

- 用 Docker Compose
- 配置 `API_TOKEN`
- 配置反向代理和 HTTPS

如果后面你要继续做前端页面，我建议直接在这个服务前面再加一个上传页面和任务列表页，不需要推翻当前后端结构。
