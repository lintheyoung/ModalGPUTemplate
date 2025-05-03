# Modal GPU Compute Service Template

[![Modal](https://modal.com/static/badge.svg)](https://modal.com)

这是一个使用 [Modal](https://modal.com/) 构建的异步 GPU 计算服务模板。它包含一个 FastAPI API 网关，用于接收任务请求，并将计算密集型任务（在此示例中为 GPU 上的矩阵乘法）分派给可自动伸缩的 Modal GPU 工作函数进行处理。任务状态通过 Modal 的分布式字典进行跟踪。

此模板旨在作为构建类似架构应用程序的起点，例如：

* 后台 AI 模型推理服务
* 需要 GPU 加速的科学计算 API
* 任何需要将长时间运行或资源密集型任务从主应用异步卸载的场景

## ✨ 功能特性

* **API 网关**: 基于 FastAPI，提供 RESTful 接口。
    * `/status`: 健康检查端点。
    * `/submit_task`: 异步提交 GPU 计算任务，立即返回任务 ID。
    * `/task_status/{task_id}`: 查询特定任务的当前状态和结果。
* **GPU 工作函数**: 在 Modal 云端 GPU 上执行实际计算（示例为矩阵乘法）。
    * 使用 PyTorch (`torch`) 进行 GPU 计算。
    * 可配置使用的 GPU 类型（例如 T4, A10G, A100, H100 或 'any'）。
* **异步处理**: 任务提交是非阻塞的，客户端可以通过任务 ID 轮询结果。
* **状态追踪**: 使用 `modal.Dict` 持久化存储和检索任务状态。
* **自动伸缩**: 利用 Modal 的 Serverless 特性，API 网关和 GPU 工作函数可根据负载自动扩展和缩减容器数量。
* **环境隔离**: 使用 `modal.Image` 定义清晰的 Python 环境和依赖项。
* **测试脚本**: 包含用于单任务测试 (`test_modal_gpu_service.py`) 和并发任务测试 (`test_concurrent_modal_gpu_service.py`) 的示例脚本。

## 🚀 开始使用

### 📋 先决条件

1.  **Python**: 建议使用 Python 3.10 或更高版本。
2.  **Modal**:
    * 拥有一个 [Modal 账户](https://modal.com/signup)。
    * 安装 Modal CLI: `pip install modal-client`
    * 登录 Modal: `modal setup`
3.  **Git**: 用于克隆此仓库。
4.  **(可选但推荐)** Python 虚拟环境 (如 `venv`, `conda`)。
5.  **本地测试依赖**: 如果要运行测试脚本，需要安装：
    ```bash
    pip install requests aiohttp python-dotenv
    ```
    * `requests`: 用于单任务测试脚本。
    * `aiohttp`: 用于并发测试脚本。
    * `python-dotenv`: `modal_gpu_service.py` 中使用了 `load_dotenv` 来尝试加载 `.env` 文件（即使此模板当前不需要特定环境变量，保留它可以方便后续添加）。

### 🛠️ 安装与设置

1.  **克隆仓库**:
    ```bash
    git clone <your-repository-url>
    cd <repository-directory>
    ```
2.  **(推荐)** 创建并激活虚拟环境:
    ```bash
    python -m venv venv
    source venv/bin/activate  # Linux/macOS
    # venv\Scripts\activate  # Windows
    ```
3.  **安装本地测试依赖**:
    ```bash
    pip install requests aiohttp python-dotenv
    ```
    *注意：你**不需要**在本地安装 `torch` 来运行或部署 Modal 应用本身，`torch` 仅在 Modal 云端的 `gpu_worker_image` 镜像中安装和使用。*

### ▶️ 运行 Modal 应用

你可以通过以下两种方式运行 Modal 应用：

1.  **开发/临时运行 (`modal serve`)**:
    * 此命令会启动一个临时的 Modal 应用，非常适合开发和快速测试。
    * Modal 会监控文件变化并自动重新加载应用。
    * 应用 URL 只在 `modal serve` 运行时有效，按 `Ctrl+C` 停止。
    ```bash
    modal serve modal_gpu_service.py
    ```
    Modal CLI 会输出一个 `...modal.run` 的 URL，这就是你的 API 网关地址。

2.  **部署 (`modal deploy`)**:
    * 此命令会创建一个持久化的 Modal 应用部署。
    * API 网关 URL 将保持有效，直到你手动停止部署（通过 Modal 网站或 `modal app stop` 命令）。
    * 适用于生产或需要稳定访问的场景。
    ```bash
    modal deploy modal_gpu_service.py
    ```
    部署成功后，Modal CLI 同样会输出应用的 URL。你也可以在 [Modal Dashboard](https://modal.com/apps) 查看已部署的应用。

### ✅ 测试 API

使用上一步获得的 Modal 应用 URL（`<YOUR_MODAL_APP_URL>`）和提供的测试脚本来验证 API 功能。

1.  **单任务测试**:
    * 提交一个任务并轮询其状态。
    ```bash
    python test_modal_gpu_service.py --url <YOUR_MODAL_APP_URL> --size 512
    ```
    * `--size` 参数可以指定计算的矩阵大小。

2.  **并发任务测试**:
    * 使用 `asyncio` 和 `aiohttp` 并发提交多个任务并轮询它们的状态。
    * 这有助于观察 Modal 的自动伸缩行为。
    ```bash
    python test_concurrent_modal_gpu_service.py --url <YOUR_MODAL_APP_URL> -n 20 --size 512
    ```
    * `-n` 参数指定并发任务的数量。
    * 观察脚本输出的摘要信息（成功、失败、超时、耗时统计）以及 Modal Dashboard 上的容器活动。

## 🔧 定制化

这个项目是一个模板，你可以根据自己的需求进行修改：

* **修改 GPU 任务**: 编辑 `modal_gpu_service.py` 文件中的 `gpu_compute_worker` 函数，替换其中的矩阵乘法逻辑为你自己的 GPU 计算代码。
* **调整输入参数**: 修改 `/submit_task` 端点处理函数 (`submit_gpu_task`) 以接受不同的请求数据（`request_data`），并在 `gpu_compute_worker` 中相应地解析和使用这些参数。
* **更改资源配置**: 在 `modal_gpu_service.py` 中 `@app.function` 装饰器里调整：
    * `gpu`: 选择更具体的 GPU 类型 (`"T4"`, `"A10G"`, `"A100"`, `"H100"` 等) 或保持 `"any"`。
    * `cpu`, `memory`: 根据你的任务需求调整 CPU 核心数和内存大小 (MB)。
    * `timeout`: 调整任务允许的最大执行时间 (秒)。
    * `max_containers`, `min_containers`, `keep_warm`: 控制函数的伸缩行为和冷启动性能。
* **修改镜像**: 如果你的 GPU 任务需要不同的 Python 库或系统依赖，请修改 `gpu_worker_image` 的定义（例如添加更多的 `.pip_install`, `.apt_install`, 或更换基础镜像）。
* **更改应用/字典名称**: 修改 `modal_gpu_service.py` 文件顶部的 `APP_NAME` 和 `TASK_DICT_NAME` 常量。
* **添加 Secrets**: 如果你的代码需要访问 API 密钥或其他敏感信息，请在 Modal UI 创建 Secret，并在 `@app.function` 装饰器中使用 `secrets=[modal.Secret.from_name("your-secret-name")]` 来注入它们。

## 📁 文件结构

```
.
├── modal_gpu_service.py               # 主要的 Modal 应用代码 (API 网关 + GPU Worker)
├── test_modal_gpu_service.py          # 单任务 API 测试脚本
├── test_concurrent_modal_gpu_service.py # 并发 API 测试脚本
└── README.md                          # 本文档
```