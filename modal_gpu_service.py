import os
import time
import uuid
from datetime import datetime

import modal
# import torch  # 引入 PyTorch
from fastapi import FastAPI, Request
from dotenv import load_dotenv

# 加载 .env 文件（如果存在）
try:
    load_dotenv()
except ImportError:
    print("python-dotenv not installed, skipping .env file loading.")
except FileNotFoundError:
    print(".env file not found, skipping loading.")
except Exception as e:
    print(f"Error loading .env file: {e}")

# --- 配置 ---
# 新的应用名称
APP_NAME = "gpu-compute-service"
# 新的任务状态字典名称
TASK_DICT_NAME = "gpu-compute-tasks"

# 创建任务追踪字典
task_states = modal.Dict.from_name(TASK_DICT_NAME, create_if_missing=True)

# --- 镜像定义 ---

# API网关的轻量级镜像 (移除了 boto3)
api_gateway_image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "fastapi[standard]", "python-dotenv"
)

# GPU 计算工作者的镜像 (替换了原来的 render_worker_image)
gpu_worker_image = (
    modal.Image.debian_slim(python_version="3.11")
    # 安装 PyTorch 和 FastAPI (FastAPI 用于可能的类型提示或未来扩展)
    .pip_install("torch", "fastapi[standard]", "python-dotenv")
    # .pip_install("torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu121") # 如果需要特定CUDA版本
    # 注意：Modal 通常会自动处理 CUDA 驱动。如果遇到问题，可能需要更具体的 PyTorch 安装命令或基础镜像。
    # 例如，使用 NVIDIA 官方镜像:
    # modal.Image.from_registry("nvidia/cuda:12.4.0-devel-ubuntu22.04", add_python="3.11")
    # .pip_install("torch", "fastapi[standard]", "python-dotenv")
)

# --- Modal 应用定义 ---
app = modal.App(APP_NAME)

# --- FastAPI 应用实例 ---
fastapi_app = FastAPI()

# ============= API 网关路由 =============

# FastAPI 路由 - 健康检查
@fastapi_app.get("/status")
async def health_check():
    """API 网关健康检查端点。"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

# FastAPI 路由 - 查询任务状态
@fastapi_app.get("/task_status/{task_id}")
async def get_task_status(task_id: str):
    """查询指定任务 ID 的状态。"""
    try:
        # 从 modal.Dict 获取任务状态
        if task_id in task_states:
            return {
                "success": True,
                "task_id": task_id,
                "task_data": task_states[task_id],
            }
        else:
            # 如果任务 ID 不存在
            return {
                "success": False,
                "task_id": task_id,
                "error": "Task ID not found",
            }
    except Exception as e:
        # 处理获取状态时的其他错误
        return {
            "success": False,
            "task_id": task_id,
            "error": f"Error retrieving task status: {str(e)}",
        }

# FastAPI 路由 - 提交 GPU 计算任务 (替换了 /render)
@fastapi_app.post("/submit_task")
async def submit_gpu_task(request: Request):
    """接收 GPU 计算任务请求，并将其异步分派给工作者。"""
    task_id = None # 初始化 task_id 以便在 except 块中使用
    try:
        # 解析请求体中的 JSON 数据
        request_data = await request.json()

        # 验证请求数据是否包含必要的参数 (例如: matrix_size)
        if "matrix_size" not in request_data or not isinstance(request_data["matrix_size"], int):
             raise ValueError("Missing or invalid 'matrix_size' in request data (must be an integer).")

        # 生成唯一的任务 ID
        task_id = str(uuid.uuid4())

        # 记录初始任务状态为 "received"
        task_states[task_id] = {
            "status": "received",
            "timestamp": datetime.now().isoformat(),
            "request_data": request_data,  # 存储请求数据
            "error": None,
            "result": None,
        }

        print(f"Task {task_id} received with data: {request_data}")

        # 获取 GPU 计算工作者函数的引用
        # 使用新的 App 名称和函数名称
        gpu_worker_function = modal.Function.from_name(
            APP_NAME, "gpu_compute_worker"
        )

        # 异步启动 GPU 计算任务，不等待结果
        # 将 task_id 和 request_data 传递给工作者函数
        print(f"Spawning task {task_id} for GPU worker...")
        gpu_worker_function.spawn(task_id, request_data)

        # 立即返回任务 ID 和状态，表示任务已成功提交
        return {
            "success": True,
            "task_id": task_id,
            "status": "received",
            "message": "Task submitted for processing.",
        }
    except ValueError as ve: # 处理特定的请求验证错误
        error_msg = f"Invalid request data: {str(ve)}"
        print(error_msg)
        # 如果在生成 task_id 之前出错，则不记录状态
        return {
            "success": False,
            "error": error_msg,
        }
    except Exception as e:
        # 处理提交过程中的任何其他未预期的错误
        error_msg = f"Error submitting task: {str(e)}"
        print(error_msg)
        # 如果 task_id 已生成，则更新任务状态为 "failed"
        if task_id:
            task_states[task_id] = {
                **task_states.get(task_id, {}), # 保留已有信息
                "status": "failed",
                "error": error_msg,
                "timestamp": datetime.now().isoformat(),
            }
            return {
                "success": False,
                "task_id": task_id, # 包含 task_id 以便追踪
                "error": error_msg,
            }
        else:
            # 如果 task_id 未生成，则无法追踪，仅返回错误
             return {
                "success": False,
                "error": error_msg,
            }

# ============= API 网关 Function =============
@app.function(
    image=api_gateway_image,
    cpu=0.5,  # 轻量级 CPU
    memory=1024,  # 轻量级内存
    timeout=120,  # API 请求超时时间 (秒)
    min_containers=0,  # 可以缩容到 0
    # max_containers=5, # 可以根据需要设置最大容器数
    allow_concurrent_inputs=50,  # 允许处理多个并发请求
    # keep_warm=1, # 如果希望保持一个容器热启动以减少延迟，可以取消注释
)
@modal.asgi_app()
def api_gateway_endpoint():
    """将 FastAPI 应用部署为 Modal ASGI 应用，作为 API 网关。"""
    print("API Gateway started.")
    return fastapi_app

# ============= GPU 计算工作者 Function =============
@app.function(
    image=gpu_worker_image,
    gpu="any",  # 请求任意可用的 GPU 类型 (可以是 "T4", "A10G", "A100", "H100" 等)
    cpu=2.0,     # 为 GPU 任务分配适量 CPU
    memory=8192, # 为 GPU 任务分配适量内存 (MB)
    timeout=600, # 任务执行超时时间 (10 分钟)
    # secrets=[...], # 如果需要访问外部服务（如数据库、API密钥），在这里添加Secrets
    max_containers=10, # 限制同时在此函数类型上运行的容器数量
)
def gpu_compute_worker(task_id: str, request_data: dict):
    """
    执行 GPU 矩阵计算任务。

    Args:
        task_id: 任务的唯一标识符。
        request_data: 包含任务参数的字典 (例如: {"matrix_size": 1024})。
    """
    import torch # <---- 将导入移动到这里
    print(f"GPU Worker: Starting task {task_id} with data: {request_data}")

    try:
        # 验证输入数据
        matrix_size = request_data.get("matrix_size")
        if not isinstance(matrix_size, int) or matrix_size <= 0:
            raise ValueError("'matrix_size' must be a positive integer.")

        # 更新任务状态为 "computing"
        task_states[task_id] = {
            **task_states.get(task_id, {}), # 合并现有状态
            "status": "computing",
            "timestamp": datetime.now().isoformat(),
        }
        print(f"Task {task_id}: Status updated to computing.")

        # --- GPU 计算逻辑 ---
        start_time = time.time()

        if not torch.cuda.is_available():
            error_msg = "GPU not available in this container."
            print(f"Task {task_id}: Error - {error_msg}")
            raise RuntimeError(error_msg)

        device = torch.device("cuda")
        print(f"Task {task_id}: Using device: {torch.cuda.get_device_name(device)}")

        # 创建两个随机矩阵并移动到 GPU
        print(f"Task {task_id}: Creating matrices of size {matrix_size}x{matrix_size} on GPU.")
        a = torch.randn(matrix_size, matrix_size, device=device, dtype=torch.float32)
        b = torch.randn(matrix_size, matrix_size, device=device, dtype=torch.float32)

        # 执行矩阵乘法
        print(f"Task {task_id}: Performing matrix multiplication.")
        c = torch.matmul(a, b)

        # 等待 GPU 计算完成 (用于精确计时)
        torch.cuda.synchronize()
        end_time = time.time()
        duration = end_time - start_time
        print(f"Task {task_id}: Computation finished in {duration:.4f} seconds.")

        # --- 计算完成 ---

        # (可选) 计算结果摘要，避免存储整个大矩阵
        result_checksum = c.sum().item() # 计算校验和作为简单结果
        result_summary = (
            f"Computed {matrix_size}x{matrix_size} matrix multiplication on "
            f"{torch.cuda.get_device_name(device)}. "
            f"Duration: {duration:.4f}s. Result checksum: {result_checksum:.4f}"
        )

        # 更新任务状态为 "completed"，并存储结果摘要
        task_states[task_id] = {
            **task_states.get(task_id, {}), # 合并现有状态
            "status": "completed",
            "result": result_summary,
            "duration_seconds": round(duration, 4),
            "error": None, # 明确表示没有错误
            "timestamp": datetime.now().isoformat(),
        }
        print(f"Task {task_id}: Status updated to completed. Result: {result_summary}")

    except Exception as e:
        # 处理执行过程中的任何错误
        error_msg = f"Error during task {task_id} execution: {str(e)}"
        print(error_msg)
        # 更新任务状态为 "failed" 并记录错误信息
        task_states[task_id] = {
            **task_states.get(task_id, {}), # 合并现有状态
            "status": "failed",
            "error": error_msg,
            "result": None, # 清除可能存在的旧结果
            "timestamp": datetime.now().isoformat(),
        }
        # 注意：这里不需要显式返回，因为 spawn 是异步的

# ============= 本地测试入口 =============
@app.local_entrypoint()
def main():
    """本地入口点，用于启动服务进行测试。"""
    print("Starting API Gateway locally for testing...")
    print("The service will be available via a Modal URL.")
    print("Press Ctrl+C to stop the service after testing.")
    # app.serve() # 或者使用 app.run() 取决于你的 Modal 版本和需求
    # 注意：对于 ASGI 应用，通常不需要显式调用 serve 或 run 在 local_entrypoint
    # Modal 会自动处理。保持此函数简单即可。

# 如果你想直接运行一个测试任务：
# @app.local_entrypoint()
# def test_task():
#     print("Submitting a test GPU task...")
#     # 注意：直接调用 .remote() 会阻塞，直到任务完成
#     # result = gpu_compute_worker.remote("test-task-local", {"matrix_size": 256})
#     # print(f"Test task result: {result}") # 注意：worker 函数现在不直接返回结果了

#     # 或者模拟 API 调用流程
#     submit_gpu_task.remote({"matrix_size": 128}) # 需要启动服务来接收这个调用
#     print("Test task submitted via simulated API call.")
#     print("Check status using the /task_status/{task_id} endpoint.")