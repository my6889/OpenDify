# OpenDify

OpenDify 是一个将 Dify API 转换为 OpenAI API 格式的代理服务器。它允许使用 OpenAI API 客户端直接与 Dify 服务进行交互。

> 🌟 本项目完全由 Cursor + Claude-3.5 自动生成，未手动编写任何代码（包括此Readme），向 AI 辅助编程的未来致敬！

## 功能特点

- 完整支持 OpenAI API 格式转换为 Dify API
- 支持流式输出（Streaming）
- 智能动态延迟控制，提供流畅的输出体验
- 支持多个模型配置
- 完整的错误处理和日志记录
- 兼容标准的 OpenAI API 客户端
- 自动获取 Dify 应用信息

## 支持的模型

支持任意 Dify 应用，系统会自动从 Dify API 获取应用名称和信息。只需在配置文件中添加应用的 API Key 即可。

## 快速开始

### 环境要求

- Python 3.9+
- pip

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置

1. 复制 `.env.example` 文件并重命名为 `.env`：
   
   ```bash
   cp .env.example .env
   ```

2. 在 Dify 平台配置应用：
   
   - 登录 Dify 平台，进入工作室
   - 点击"创建应用"，配置好需要的模型（如 Claude、Gemini 等）
   - 配置应用的提示语和其他参数
   - 发布应用
   - 进入"访问 API"页面，生成 API 密钥
   
   > **重要说明**：Dify 不支持在请求时动态传入提示词、切换模型及其他参数。所有这些配置都需要在创建应用时设置好。Dify 会根据 API 密钥来确定使用哪个应用及其对应的配置。系统会自动从 Dify API 获取应用的名称和描述信息。

3. 在 `.env` 文件中配置你的 Dify API Keys：
   
```
# Dify API Keys Configuration
# Format: Comma-separated list of API keys
DIFY_API_KEYS=app-xxxxxxxx,app-yyyyyyyy,app-zzzzzzzz

# Dify API Base URL
DIFY_API_BASE="https://your-dify-api-base-url/v1"

# Server Configuration
SERVER_HOST="0.0.0.0"
SERVER_PORT=5000
```
配置说明：
- `DIFY_API_KEYS`：以逗号分隔的 API Keys 列表，每个 Key 对应一个 Dify 应用
- 系统会自动从 Dify API 获取每个应用的名称和信息
- 无需手动配置模型名称和映射关系

### 运行服务
Bash

```
python openai_to_dify.py
```
Docker
```
docker compose up -d 
```

服务将在 `http://0.0.0.0:5000` 启动

## API 使用

### List Models

获取所有可用模型列表：

```python
import openai

openai.api_base = "http://127.0.0.1:5000/v1"
openai.api_key = "any"  # 可以使用任意值

# 获取可用模型列表
models = openai.Model.list()
print(models)

# 输出示例：
{
    "object": "list",
    "data": [
        {
            "id": "My Translation App",  # Dify 应用名称
            "object": "model",
            "created": 1704603847,
            "owned_by": "dify"
        },
        {
            "id": "Code Assistant",  # 另一个 Dify 应用名称
            "object": "model",
            "created": 1704603847,
            "owned_by": "dify"
        }
    ]
}
```

系统会自动从 Dify API 获取应用名称，并用作模型 ID。

### Chat Completions

```python
import openai

openai.api_base = "http://127.0.0.1:5000/v1"
openai.api_key = "any"  # 可以使用任意值

response = openai.ChatCompletion.create(
    model="My Translation App",  # 使用 Dify 应用的名称
    messages=[
        {"role": "user", "content": "你好"}
    ],
    stream=True
)

for chunk in response:
    print(chunk.choices[0].delta.content or "", end="")
```

## 特性

### 会话记忆功能

该代理支持自动记忆会话上下文，无需客户端进行额外处理。当启用此功能时：

- 在每个新会话的第一条回复中，会自动嵌入不可见的会话ID
- 后续的消息会自动继承会话上下文，保持对话连贯性
- 使用零宽字符编码，（大部分情况下）不会影响消息的正常显示

可以通过环境变量控制此功能：

```shell
# 在 .env 文件中设置
ENABLE_CONVERSATION_MEMORY=true  # 启用会话记忆功能
ENABLE_CONVERSATION_MEMORY=false # 禁用会话记忆功能
```

默认情况下此功能是启用的。如果您的应用场景不需要保持会话上下文，可以选择关闭此功能。

### 流式输出优化

- 智能缓冲区管理
- 动态延迟计算
- 平滑的输出体验

### 错误处理

- 完整的错误捕获和处理
- 详细的日志记录
- 友好的错误提示

### 配置灵活性

- 自动获取应用信息
- 简化的配置方式
- 动态模型名称映射

## 贡献指南

欢迎提交 Issue 和 Pull Request 来帮助改进项目。

## 许可证

[MIT License](LICENSE) 