# PPT 服务测试方案

本文档用于测试当前 PPT 生成服务的核心功能是否可用。

本轮测试重点：

- Nginx 代理是否可用
- API token 是否生效
- Markdown 是否能生成 PPT
- PDF 是否能生成 PPT
- 指定页数是否生效
- 不指定页数时是否能自动建议页数
- 中文和英文输出是否可用
- 两种风格是否可用
- 最终 PPT 是否可以下载和打开

本轮不测试：

- 大规模并发
- 故意制造异常链路
- 所有风格逐一覆盖

## 1. 测试环境

默认服务地址：

```text
http://101.37.70.54:8080
```

如果你后面切到 80 端口，则使用：

```text
http://101.37.70.54
```

以下命令使用变量表示：

```bash
BASE_URL=http://101.37.70.54:8080
API_TOKEN=你的API_TOKEN
```

如果没有设置 `API_TOKEN`，命令里的 `Authorization` 请求头可以去掉。

## 2. 测试风格

本轮只测试两种风格：

- `clean-professional`：清爽专业风
- `scientific-defense`：科研答辩风

这样可以验证风格参数确实生效，又不会让测试成本过高。

## 3. 测试数据准备

### 3.1 Markdown 测试文件

文件名：

```text
test.md
```

内容示例：

```markdown
# AI PPT 生成服务测试

本文用于测试一个 PPT 自动生成服务。系统接收 Markdown 或 PDF，先用 DeepSeek 生成结构化大纲，再调用 gpt-image-2 生成每一页幻灯片图片，最后组装成 PPTX。

## 背景

团队希望把文章、报告、课程笔记快速转换成视觉统一的演示文稿。

## 核心流程

- 上传 Markdown 或 PDF
- 提取文本
- 生成 deck_spec.json
- 逐页生成图片
- 组装 PPTX

## 关注点

- 风格统一
- 文字清晰
- 页数合理
- 失败自动重试
- 支持 Docker 部署
```

### 3.2 PDF 测试文件

文件名：

```text
test.pdf
```

要求：

- 使用文字型 PDF
- PDF 里的文字可以复制
- 不使用扫描版 PDF

## 4. 基础接口测试

### 4.1 健康检查

```bash
curl "$BASE_URL/health"
```

预期：

```json
{"status":"ok"}
```

### 4.2 风格列表

```bash
curl -H "Authorization: Bearer $API_TOKEN" "$BASE_URL/styles"
```

预期：

- HTTP `200`
- 返回风格数组
- 包含 `clean-professional`
- 包含 `scientific-defense`

### 4.3 鉴权检查

如果配置了 `API_TOKEN`，不带 token 测试：

```bash
curl -i "$BASE_URL/styles"
```

预期：

- HTTP `401`

带正确 token：

```bash
curl -i -H "Authorization: Bearer $API_TOKEN" "$BASE_URL/styles"
```

预期：

- HTTP `200`

## 5. Markdown 生成测试

### 5.1 Markdown 指定页数，中文，清爽专业风

目的：

- 测试 Markdown 上传
- 测试 `page_count=3`
- 测试中文输出
- 测试 `clean-professional`

请求：

```bash
curl -s -X POST "$BASE_URL/jobs" \
  -H "Authorization: Bearer $API_TOKEN" \
  -F "file=@./test.md" \
  -F "style=clean-professional" \
  -F "language=zh" \
  -F "page_count=3" \
  -F "image_concurrency=2"
```

预期：

- 返回 `job_id`
- 返回 `status=queued`
- 返回 `page_count=3`
- 最终任务状态为 `completed`
- 最终生成 3 页 PPT

### 5.2 Markdown 不指定页数，英文，科研答辩风

目的：

- 测试不传 `page_count`
- 测试系统自动建议页数
- 测试英文输出
- 测试 `scientific-defense`

请求：

```bash
curl -s -X POST "$BASE_URL/jobs" \
  -H "Authorization: Bearer $API_TOKEN" \
  -F "file=@./test.md" \
  -F "style=scientific-defense" \
  -F "language=en" \
  -F "image_concurrency=2"
```

预期：

- 返回 `job_id`
- 初始响应中的 `page_count` 可以为 `null`
- 查询任务状态时，后续 `page_count` 会被系统填入
- 最终任务状态为 `completed`
- `deck_spec.json` 中 `language` 为 `en`

## 6. PDF 生成测试

### 6.1 PDF 指定页数，中文，科研答辩风

目的：

- 测试 PDF 文本抽取
- 测试 `page_count=3`
- 测试中文输出
- 测试 `scientific-defense`

请求：

```bash
curl -s -X POST "$BASE_URL/jobs" \
  -H "Authorization: Bearer $API_TOKEN" \
  -F "file=@./test.pdf" \
  -F "style=scientific-defense" \
  -F "language=zh" \
  -F "page_count=3" \
  -F "image_concurrency=2"
```

预期：

- 返回 `job_id`
- 返回 `page_count=3`
- `extracted.txt` 有有效文本
- 最终任务状态为 `completed`
- 最终生成 3 页 PPT

### 6.2 PDF 不指定页数，英文，清爽专业风

目的：

- 测试 PDF 不传 `page_count`
- 测试系统自动建议页数
- 测试英文输出
- 测试 `clean-professional`

请求：

```bash
curl -s -X POST "$BASE_URL/jobs" \
  -H "Authorization: Bearer $API_TOKEN" \
  -F "file=@./test.pdf" \
  -F "style=clean-professional" \
  -F "language=en" \
  -F "image_concurrency=2"
```

预期：

- 返回 `job_id`
- 初始响应中的 `page_count` 可以为 `null`
- 查询任务状态时，后续 `page_count` 会被系统填入
- `deck_spec.json` 中 `language` 为 `en`
- 最终任务状态为 `completed`

## 7. 查询任务状态

创建任务后，用返回的 `job_id` 查询：

```bash
curl -s -H "Authorization: Bearer $API_TOKEN" "$BASE_URL/jobs/JOB_ID"
```

正常状态流转：

```text
queued
extracting
planning
generating_images
assembling
completed
```

如果失败，状态会是：

```text
failed
```

失败时检查：

- `error_message`
- `data/jobs/{job_id}/job.log`

## 8. 下载 PPT

任务完成后下载：

```bash
curl -L -H "Authorization: Bearer $API_TOKEN" \
  "$BASE_URL/jobs/JOB_ID/download" \
  -o result.pptx
```

预期：

- 下载得到 `.pptx`
- 文件大小大于 0
- PowerPoint 可以打开
- 页数等于任务最终 `page_count`

## 9. 服务器产物检查

在服务器项目目录检查：

```bash
ls data/jobs/JOB_ID
```

应包含：

- `input.md` 或 `input.pdf`
- `extracted.txt`
- `deck_spec.json`
- `status.json`
- `job.log`
- `origin_image/`
- `speech.md`
- `output.pptx`

检查图片：

```bash
ls data/jobs/JOB_ID/origin_image
```

预期：

- `slide_01.png`
- `slide_02.png`
- 后续页按顺序递增

检查状态：

```bash
cat data/jobs/JOB_ID/status.json
```

预期：

- `status` 为 `completed`
- `completed_slides` 等于 `total_slides`
- `error_message` 为 `null`

## 10. 验收标准

本轮测试通过的最低标准：

- `/health` 可用
- `/styles` 可用
- API token 鉴权符合预期
- Markdown 指定页数中文任务完成
- Markdown 不指定页数英文任务完成
- PDF 指定页数中文任务完成
- PDF 不指定页数英文任务完成
- 每个完成任务都能下载 `.pptx`
- 服务器 `data/jobs/{job_id}` 目录产物完整

## 11. 建议执行顺序

1. 健康检查
2. 风格列表和鉴权检查
3. Markdown 指定页数测试
4. Markdown 不指定页数测试
5. PDF 指定页数测试
6. PDF 不指定页数测试
7. 下载 PPT
8. 服务器产物检查
