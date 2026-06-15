# PPT 生成服务改造方案

## 1. 改造目标

把当前的 `codex-ppt` skill 改造成一个简单的 PPT 生成服务。

你的实际需求是：

- 使用人数很少，5 人以内。
- 输入文件主要是 Markdown 或 PDF。
- 你提供 DeepSeek API key。
- 你提供 `gpt-image-2` API key。
- 服务把输入内容转换为文本流。
- 服务把文本、页数、风格和 prompt 发给 DeepSeek。
- DeepSeek 生成结构化 PPT 方案。
- 服务再调用 `gpt-image-2` 生成每页幻灯片图片。
- 最后把图片组装成 `.pptx` 文件。

第一版目标应该是简单、稳定、容易部署，而不是复杂的高并发微服务。开发完成后必须封装成 Docker 容器，方便在服务器上用 Docker Compose 部署。

## 2. 简化后的整体流程

```text
上传 Markdown / PDF
  -> 提取文本
  -> 拼接 DeepSeek prompt
  -> DeepSeek 生成 deck_spec.json
  -> 校验 deck_spec.json
  -> 调用 gpt-image-2 逐页生成图片
  -> 使用 assemble_ppt.py 组装 PPTX
  -> 返回下载地址
```

这个流程不再依赖 Codex 的交互式 skill 流程，也不需要子 agent。

## 3. 第一版推荐架构

第一版建议做成一个单容器服务：

```text
FastAPI 服务
  -> 接收上传文件
  -> 创建生成任务
  -> 后台执行 PPT 生成流程
  -> 保存任务状态
  -> 提供 PPT 下载接口
```

不建议第一版就引入：

- PostgreSQL
- Redis
- Celery
- RabbitMQ
- 多 worker 分布式调度

5 人以内使用时，本地文件状态已经够用。

## 4. 是否需要数据库

第一版不需要数据库。

原因：

- 用户数少。
- 任务量不大。
- 不需要复杂查询。
- 不需要计费系统。
- 不需要多机器 worker。
- 任务状态可以直接保存在本地文件中。

每个任务一个独立目录即可：

```text
/data/jobs/{job_id}/
├── input.md 或 input.pdf
├── extracted.txt
├── deck_spec.json
├── status.json
├── slides/
│   ├── slide_01.png
│   ├── slide_02.png
│   └── ...
├── speech.md
└── output.pptx
```

后续如果你需要用户系统、历史记录、任务检索、计费或多机器部署，再加数据库。

## 5. 任务状态设计

每个任务目录里放一个 `status.json`。

示例：

```json
{
  "job_id": "uuid",
  "status": "generating_images",
  "total_slides": 8,
  "completed_slides": 3,
  "error_message": null,
  "created_at": "2026-06-15T12:00:00Z",
  "updated_at": "2026-06-15T12:03:00Z"
}
```

推荐状态：

```text
queued
extracting
planning
generating_images
assembling
completed
failed
```

## 6. 并发策略

5 人以内不需要复杂并发。

推荐限制：

```text
同时生成 PPT 任务数：1 或 2
每个 PPT 内同时生成图片数：用户可选 2-5，默认 2
最大排队任务数：20
```

`image_concurrency` 可以作为创建任务时的用户参数，但服务端必须做限制：

- 最小值：2
- 最大值：5
- 默认值：2
- 如果环境变量 `MAX_IMAGE_CONCURRENCY_PER_JOB` 小于用户传入值，以环境变量为准

这样既能让用户根据任务紧急程度调整速度，也能避免单个任务过度占用 API 请求额度。

原因：

- 真正耗时的是 `gpt-image-2` 生图。
- 同时打太多图片请求容易限流。
- 并发过高会让失败率和成本都变得不可控。
- 低并发更容易排查问题。

第一版可以在 FastAPI 里启动一个后台 worker loop：

```text
用户提交任务
  -> 放入内存队列
  -> 后台 worker 取任务
  -> 执行完整生成流程
  -> 更新 status.json
```

如果服务重启，可以扫描 `/data/jobs` 目录，把未完成任务标记为 `failed` 或重新放回队列。

## 7. API 设计
### 7.0 用户可选参数

第一版建议开放三个核心参数：

```text
page_count：PPT 页数，可选；例如 5-20，不传时由系统自动建议
language：输出语言，例如 zh / en
image_concurrency：图片生成并发数，范围 2-5
```

其中 `language` 会传入 DeepSeek，用来控制 `deck_spec.json` 的文字语言。`page_count` 如果由用户提供，就作为硬性页数要求传入 DeepSeek；如果用户不提供，则由系统先根据内容长度生成建议页数，再交给 DeepSeek 生成对应页数的结构。

`image_concurrency` 不传给 DeepSeek，只影响后端调用 `gpt-image-2` 的并发速度。

服务端需要做参数校验：

- `page_count` 可选；如果用户填写，建议限制在 1-30。
- 如果用户不填写 `page_count`，系统自动建议页数，建议范围为 5-12，长文档最多不超过 30。
- `language` 第一版支持 `zh`、`en`，默认 `zh`。
- `image_concurrency` 限制在 2-5，默认 2。


### 7.1 创建任务

```text
POST /jobs
```

请求参数：

- 文件：`.md` 或 `.pdf`
- `style`：风格 ID
- `page_count`：页数，可选；不传时由系统自动建议
- `language`：输出语言，例如 `zh` 或 `en`
- `title`：可选标题
- `image_concurrency`：图片生成并发数，可选范围 2-5，默认 2

返回：

```json
{
  "job_id": "uuid",
  "status": "queued",
  "page_count": 8,
  "language": "zh",
  "image_concurrency": 2
}
```

### 7.2 查询任务状态

```text
GET /jobs/{job_id}
```

返回：

```json
{
  "job_id": "uuid",
  "status": "generating_images",
  "total_slides": 8,
  "completed_slides": 3,
  "error_message": null
}
```

### 7.3 下载 PPT

```text
GET /jobs/{job_id}/download
```

只有任务状态为 `completed` 时才允许下载。

### 7.4 查询风格列表

```text
GET /styles
```

返回当前支持的风格选项。

## 8. 页数选择策略

页数建议支持两种模式：

```text
用户指定页数
系统自动建议页数
```

### 8.1 用户指定页数

如果用户传入 `page_count`，服务应尽量严格按该页数生成。

规则：

- 最小值建议为 1 或 3，具体看是否允许单页 PPT。
- 最大值建议为 30。
- 超出范围直接返回参数错误。
- DeepSeek 返回的 slides 数量必须等于用户指定页数。

### 8.2 系统自动建议页数

如果用户不传 `page_count`，服务自动建议页数。

可以先用简单规则实现：

```text
短文本：5-6 页
中等文本：8-10 页
长文本：12-15 页
特别长文本：最多 30 页
```

第一版可以按提取后的文本长度估算：

```text
少于 3,000 字：5 页
3,000-8,000 字：8 页
8,000-15,000 字：10-12 页
超过 15,000 字：12-15 页
```

如果后续想更智能，可以让 DeepSeek 先根据内容复杂度返回一个建议页数，再由服务端校验上下限。

建议最终写入 `status.json` 和 `deck_spec.json`，让用户知道本次实际采用了多少页。
## 9. 风格选项设计

把现有 skill 里的风格参考文件改造成服务端风格库。

建议目录：

```text
server/styles/
├── clean-professional.md
├── scientific-defense.md
├── mckinsey-style.md
├── handdrawn-technical.md
└── data-dashboard.md
```

用户选择一个风格，例如：

```json
{
  "style": "scientific-defense",
  "page_count": 8,
  "language": "zh",
  "image_concurrency": 2
}
```

服务读取对应的风格文件，把风格说明拼入 DeepSeek prompt。

这样 DeepSeek 生成的每页 `image_prompt` 就会带上统一风格。

## 10. DeepSeek 输出格式

DeepSeek 不应该输出自由格式 Markdown，而应该输出严格 JSON。

推荐生成 `deck_spec.json`：

```json
{
  "title": "PPT 标题",
  "language": "zh",
  "style": "clean-professional",
  "slides": [
    {
      "index": 1,
      "title": "页面标题",
      "key_points": ["要点 A", "要点 B"],
      "image_prompt": "用于生成 16:9 整页 PPT 图片的详细 prompt。",
      "speaker_note": "这一页的演讲稿。"
    }
  ]
}
```

服务需要校验：

- JSON 是否有效。
- 页数是否等于 `page_count`。
- 每一页是否有 `index`、`title`、`image_prompt`、`speaker_note`。
- 页码是否连续。

如果校验失败，可以让 DeepSeek 修复 JSON，最多重试 1-2 次。

## 11. Markdown 和 PDF 处理

Markdown：

- 按 UTF-8 读取。
- 保留标题、列表、代码块等结构。
- 清理过多空行。

PDF：

- 优先支持文字型 PDF。
- 可以使用 PyMuPDF 或 pdfplumber 提取文本。
- 如果提取文本过短，直接返回错误。
- 第一版不做 OCR。

扫描版 PDF 可以后续再加 OCR。

## 12. 图片生成

每一页使用 `deck_spec.json` 里的 `image_prompt` 调用 `gpt-image-2`。

生图模型可能不稳定，所以图片生成模块必须内置自动重试机制。用户提交任务后，不需要手动触发重试；服务端在后台自动处理临时失败。

生成文件命名：

```text
slides/slide_01.png
slides/slide_02.png
slides/slide_03.png
```

自动重试规则：

- 每页默认最多重试 2 次，即总共尝试 3 次。
- 对 429、超时、5xx、网络异常使用自动重试。
- 对返回成功但图片文件不存在、文件为空、无法被 Pillow 打开的情况，也视为失败并自动重试。
- 重试期间任务状态仍保持为 `generating_images`。
- 每次重试都写入 `job.log`，记录 slide index、失败原因、attempt 次数和下一次等待时间。
- 如果某页最终仍然失败，才把整个任务标记为 `failed`。
- 保留已经生成的图片和失败日志，方便排查。

推荐指数退避策略：

```text
第 1 次失败：自动等待 2 秒后重试
第 2 次失败：自动等待 5 秒后重试
第 3 次仍失败：标记任务 failed
```

如果需要更保守，也可以改成：

```text
2 秒 -> 5 秒 -> 10 秒 -> failed
```

完成一页并通过图片有效性检查后，再更新 `completed_slides`。

## 13. PPT 组装

复用当前项目里的：

```text
skills/codex-ppt/scripts/assemble_ppt.py
```

输入：

- `slides/slide_XX.png`
- `speech.md` 或 `deck_spec.json` 里的 speaker notes

输出：

```text
output.pptx
```

## 14. 环境变量

使用 `.env` 管理 key，不要提交到 Git。

示例：

```text
DEEPSEEK_API_KEY=your_deepseek_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

OPENAI_API_KEY=your_openai_key
OPENAI_BASE_URL=https://api.openai.com/v1
IMAGE_MODEL=gpt-image-2

OUTPUT_DIR=/data/jobs
MAX_ACTIVE_JOBS=1
MAX_IMAGE_CONCURRENCY_PER_JOB=5
MAX_IMAGE_RETRIES=2
```

仓库里可以提供 `.env.example`，但不能提交真实 API key。

## 15. 建议目录结构

```text
server/
├── app.py
├── config.py
├── worker.py
├── schemas.py
├── pipeline/
│   ├── extract_text.py
│   ├── plan_with_deepseek.py
│   ├── generate_images.py
│   ├── assemble.py
│   └── job_store.py
├── styles/
│   ├── clean-professional.md
│   └── scientific-defense.md
├── requirements.txt
└── Dockerfile

docker-compose.yml
.env.example
```

## 16. Docker 部署要求

Docker 化是本项目的明确开发要求，不是可选项。

开发完成后必须提供：

- `server/Dockerfile`
- `docker-compose.yml`
- `.env.example`
- 持久化数据目录挂载配置
- 容器启动和停止说明
- 服务器部署说明

第一版只需要一个服务容器。

示例 `docker-compose.yml`：

```yaml
services:
  ppt-service:
    build: ./server
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./data:/data
    restart: unless-stopped
```

示例 `.env.example`：

```text
DEEPSEEK_API_KEY=your_deepseek_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

OPENAI_API_KEY=your_openai_key
OPENAI_BASE_URL=https://api.openai.com/v1
IMAGE_MODEL=gpt-image-2

OUTPUT_DIR=/data/jobs
MAX_ACTIVE_JOBS=1
MAX_IMAGE_CONCURRENCY_PER_JOB=5
MAX_IMAGE_RETRIES=2
```

服务器启动命令：

```bash
docker compose up -d --build
```

服务器停止命令：

```bash
docker compose down
```

启动后访问：

```text
http://服务器IP:8000
```

如果服务暴露到公网，必须增加简单鉴权，例如 API token，避免别人消耗你的 DeepSeek 和 `gpt-image-2` 额度。

## 17. 错误处理

失败时不要生成半成品 PPT 冒充成功。

需要明确处理：

- 文件类型不支持。
- PDF 无法提取有效文本。
- DeepSeek 返回无效 JSON。
- `gpt-image-2` 生图失败，且重试后仍失败。
- 某页图片缺失。
- PPT 组装失败。

失败信息写入 `status.json` 的 `error_message`。

## 18. 开发阶段建议

### 第一阶段：命令行跑通

先做一个本地命令：

```text
输入 md/pdf -> 输出 output.pptx
```

不急着做 API。

### 第二阶段：封装 FastAPI

加上传、状态查询、下载接口。

### 第三阶段：Docker 化

加 Dockerfile、docker-compose.yml、`.env.example`，并验证可以在服务器上通过 `docker compose up -d --build` 启动。

### 第四阶段：小规模可靠性增强

加重试、JSON 修复、任务清理、简单鉴权。

## 19. 最终建议

根据你目前的需求，最合适的方案是：

```text
单 Docker 容器
Docker Compose 部署
FastAPI
本地文件保存任务状态
用户可选择页数、语言和 2-5 的图片生成并发数
DeepSeek 负责生成 PPT 结构和图片 prompt
gpt-image-2 负责生成整页幻灯片图片
assemble_ppt.py 负责组装 PPTX
```

第一版不要上数据库和复杂队列。

等以后出现这些需求时，再考虑数据库：

- 多用户账号体系
- 历史任务检索
- 计费
- 多机器部署
- 更强的失败恢复
- 任务优先级





