import json
import logging
import asyncio
from flask import Flask, request, Response, stream_with_context
import httpx
import time
from dotenv import load_dotenv
import os
import ast

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 设置 httpx 的日志级别
logging.getLogger("httpx").setLevel(logging.DEBUG)

# 加载环境变量
load_dotenv()

def parse_model_config():
    """
    从环境变量解析模型配置
    返回一个字典 {model_name: api_key}
    """
    try:
        config_str = os.getenv('MODEL_CONFIG', '{}')
        # 尝试作为Python字典解析
        try:
            return ast.literal_eval(config_str)
        except (SyntaxError, ValueError) as e:
            logger.error(f"Failed to parse MODEL_CONFIG as Python dict: {e}")
            try:
                # 尝试作为JSON解析
                return json.loads(config_str)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse MODEL_CONFIG as JSON: {e}")
                return {}
    except Exception as e:
        logger.error(f"Error parsing MODEL_CONFIG: {e}")
        return {}

# 从环境变量获取配置
MODEL_TO_API_KEY = parse_model_config()

# 根据MODEL_TO_API_KEY自动生成模型信息
AVAILABLE_MODELS = [
    {
        "id": model_id,
        "object": "model",
        "created": int(time.time()),
        "owned_by": "dify"
    }
    for model_id, api_key in MODEL_TO_API_KEY.items()
    if api_key is not None  # 只包含配置了API Key的模型
]

app = Flask(__name__)

# 从环境变量获取API基础URL
DIFY_API_BASE = os.getenv("DIFY_API_BASE", "https://mify-be.pt.xiaomi.com/api/v1")

def get_api_key(model_name):
    """根据模型名称获取对应的API密钥"""
    api_key = MODEL_TO_API_KEY.get(model_name)
    if not api_key:
        logger.warning(f"No API key found for model: {model_name}")
    return api_key

def transform_openai_to_dify(openai_request, endpoint):
    """将OpenAI格式的请求转换为Dify格式"""
    
    if endpoint == "/chat/completions":
        messages = openai_request.get("messages", [])
        stream = openai_request.get("stream", False)
        
        dify_request = {
            "inputs": {},
            "query": messages[-1]["content"] if messages else "",
            "response_mode": "streaming" if stream else "blocking",
            "conversation_id": openai_request.get("conversation_id", None),
            "user": openai_request.get("user", "default_user")
        }

        # 添加历史消息
        if len(messages) > 1:
            history = []
            for msg in messages[:-1]:  # 除了最后一条消息
                history.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
            dify_request["conversation_history"] = history

        return dify_request
    
    return None

def transform_dify_to_openai(dify_response, model="claude-3-5-sonnet-v2", stream=False):
    """将Dify格式的响应转换为OpenAI格式"""
    
    if not stream:
        return {
            "id": dify_response.get("message_id", ""),
            "object": "chat.completion",
            "created": dify_response.get("created", int(time.time())),
            "model": model,  # 使用实际使用的模型
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": dify_response.get("answer", "")
                },
                "finish_reason": "stop"
            }]
        }
    else:
        # 流式响应的转换在stream_response函数中处理
        return dify_response

def create_openai_stream_response(content, message_id, model="claude-3-5-sonnet-v2"):
    """创建OpenAI格式的流式响应"""
    return {
        "id": message_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {
                "content": content
            },
            "finish_reason": None
        }]
    }

@app.route('/v1/chat/completions', methods=['POST'])
def chat_completions():
    try:
        openai_request = request.get_json()
        logger.info(f"Received request: {json.dumps(openai_request, ensure_ascii=False)}")
        
        model = openai_request.get("model", "claude-3-5-sonnet-v2")
        logger.info(f"Using model: {model}")
        
        # 验证模型是否支持
        api_key = get_api_key(model)
        if not api_key:
            error_msg = f"Model {model} is not supported. Available models: {', '.join(MODEL_TO_API_KEY.keys())}"
            logger.error(error_msg)
            return {
                "error": {
                    "message": error_msg,
                    "type": "invalid_request_error",
                    "code": "model_not_found"
                }
            }, 404
            
        dify_request = transform_openai_to_dify(openai_request, "/chat/completions")
        logger.info(f"Transformed request: {json.dumps(dify_request, ensure_ascii=False)}")
        
        if not dify_request:
            logger.error("Failed to transform request")
            return {
                "error": {
                    "message": "Invalid request format",
                    "type": "invalid_request_error",
                }
            }, 400

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        stream = openai_request.get("stream", False)
        dify_endpoint = f"{DIFY_API_BASE}/chat-messages"
        logger.info(f"Sending request to Dify endpoint: {dify_endpoint}, stream={stream}")

        if stream:
            def generate():
                client = httpx.Client(timeout=None)
                
                def flush_chunk(chunk_data):
                    """Helper function to flush chunks immediately"""
                    return chunk_data.encode('utf-8')
                
                def calculate_delay(buffer_size):
                    """
                    根据缓冲区大小动态计算延迟
                    buffer_size: 缓冲区中剩余的字符数量
                    """
                    if buffer_size > 30:  # 缓冲区内容较多，快速输出
                        return 0.001  # 5ms延迟
                    elif buffer_size > 20:  # 中等数量，适中速度
                        return 0.002  # 10ms延迟
                    elif buffer_size > 10:  # 较少内容，稍慢速度
                        return 0.01  # 20ms延迟
                    else:  # 内容很少，使用较慢的速度
                        return 0.02  # 30ms延迟
                
                def send_char(char, message_id):
                    """Helper function to send single character"""
                    openai_chunk = {
                        "id": message_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": {
                                "content": char
                            },
                            "finish_reason": None
                        }]
                    }
                    chunk_data = f"data: {json.dumps(openai_chunk)}\n\n"
                    return flush_chunk(chunk_data)
                
                # 初始化缓冲区
                output_buffer = []
                
                try:
                    with client.stream(
                        'POST',
                        dify_endpoint,
                        json=dify_request,
                        headers={
                            **headers,
                            'Accept': 'text/event-stream',
                            'Cache-Control': 'no-cache',
                            'Connection': 'keep-alive'
                        }
                    ) as response:
                        generate.message_id = None
                        buffer = ""
                        
                        for raw_bytes in response.iter_raw():
                            if not raw_bytes:
                                continue
                                
                            try:
                                buffer += raw_bytes.decode('utf-8')
                                
                                while '\n' in buffer:
                                    line, buffer = buffer.split('\n', 1)
                                    line = line.strip()
                                    
                                    if not line or not line.startswith('data: '):
                                        continue
                                        
                                    try:
                                        json_str = line[6:]
                                        dify_chunk = json.loads(json_str)
                                        
                                        if dify_chunk.get("event") == "message" and "answer" in dify_chunk:
                                            current_answer = dify_chunk["answer"]
                                            if not current_answer:
                                                continue
                                                
                                            message_id = dify_chunk.get("message_id", "")
                                            if not generate.message_id:
                                                generate.message_id = message_id
                                            
                                            # 将当前批次的字符添加到输出缓冲区
                                            for char in current_answer:
                                                output_buffer.append((char, generate.message_id))
                                            
                                            # 根据缓冲区大小动态调整输出速度
                                            while output_buffer:
                                                char, msg_id = output_buffer.pop(0)
                                                yield send_char(char, msg_id)
                                                # 根据剩余缓冲区大小计算延迟
                                                delay = calculate_delay(len(output_buffer))
                                                time.sleep(delay)
                                            
                                            # 立即继续处理下一个请求
                                            continue
                                        
                                        elif dify_chunk.get("event") == "message_end":
                                            # 快速输出剩余内容
                                            while output_buffer:
                                                char, msg_id = output_buffer.pop(0)
                                                yield send_char(char, msg_id)
                                                time.sleep(0.001)  # 固定使用最小延迟快速输出剩余内容
                                            
                                            final_chunk = {
                                                "id": generate.message_id,
                                                "object": "chat.completion.chunk",
                                                "created": int(time.time()),
                                                "model": model,
                                                "choices": [{
                                                    "index": 0,
                                                    "delta": {},
                                                    "finish_reason": "stop"
                                                }]
                                            }
                                            yield flush_chunk(f"data: {json.dumps(final_chunk)}\n\n")
                                            yield flush_chunk("data: [DONE]\n\n")
                                        
                                    except json.JSONDecodeError as e:
                                        logger.error(f"JSON decode error: {str(e)}")
                                        continue
                                        
                            except Exception as e:
                                logger.error(f"Error processing chunk: {str(e)}")
                                continue

                finally:
                    client.close()

            return Response(
                stream_with_context(generate()),
                content_type='text/event-stream',
                headers={
                    'Cache-Control': 'no-cache, no-transform',
                    'Connection': 'keep-alive',
                    'Transfer-Encoding': 'chunked',
                    'X-Accel-Buffering': 'no',
                    'Content-Encoding': 'none'
                },
                direct_passthrough=True
            )
        else:
            async def sync_response():
                try:
                    async with httpx.AsyncClient() as client:
                        response = await client.post(
                            dify_endpoint,
                            json=dify_request,
                            headers=headers
                        )
                        
                        if response.status_code != 200:
                            error_msg = f"Dify API error: {response.text}"
                            logger.error(f"Request failed: {error_msg}")
                            return {
                                "error": {
                                    "message": error_msg,
                                    "type": "api_error",
                                    "code": response.status_code
                                }
                            }, response.status_code

                        dify_response = response.json()
                        logger.info(f"Received response from Dify: {json.dumps(dify_response, ensure_ascii=False)}")
                        openai_response = transform_dify_to_openai(dify_response, model=model)
                        return openai_response
                except httpx.RequestError as e:
                    error_msg = f"Failed to connect to Dify: {str(e)}"
                    logger.error(error_msg)
                    return {
                        "error": {
                            "message": error_msg,
                            "type": "api_error",
                            "code": "connection_error"
                        }
                    }, 503

            return asyncio.run(sync_response())

    except Exception as e:
        logger.exception("Unexpected error occurred")
        return {
            "error": {
                "message": str(e),
                "type": "internal_error",
            }
        }, 500

@app.route('/v1/models', methods=['GET'])
def list_models():
    """返回可用的模型列表"""
    logger.info("Listing available models")
    # 过滤掉没有API密钥的模型
    available_models = [
        model for model in AVAILABLE_MODELS 
        if MODEL_TO_API_KEY.get(model["id"])
    ]
    
    response = {
        "object": "list",
        "data": available_models
    }
    logger.info(f"Available models: {json.dumps(response, ensure_ascii=False)}")
    return response

if __name__ == '__main__':
    host = os.getenv("SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("SERVER_PORT", 5000))
    logger.info(f"Starting server on http://{host}:{port}")
    app.run(debug=True, host=host, port=port)
