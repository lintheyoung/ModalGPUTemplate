import requests
import time
import argparse
import sys

def test_status(base_url):
    """测试 /status 健康检查端点"""
    status_url = f"{base_url}/status"
    print(f"[*] Testing health check endpoint: {status_url}")
    try:
        response = requests.get(status_url, timeout=10)
        response.raise_for_status() # 如果状态码不是 2xx 则抛出异常
        data = response.json()
        if data.get("status") == "ok":
            print(f"[+] Health check successful: {data}")
            return True
        else:
            print(f"[-] Health check failed: Unexpected response {data}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"[!] Error connecting to status endpoint: {e}")
        return False
    except Exception as e:
        print(f"[!] An unexpected error occurred during status check: {e}")
        return False

def submit_gpu_task(base_url, matrix_size=512):
    """向 /submit_task 提交 GPU 计算任务"""
    submit_url = f"{base_url}/submit_task"
    payload = {"matrix_size": matrix_size}
    headers = {"Content-Type": "application/json"}
    print(f"[*] Submitting task to: {submit_url} with payload: {payload}")

    try:
        response = requests.post(submit_url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        print(f"[+] Submit response: {data}")

        if data.get("success"):
            task_id = data.get("task_id")
            if task_id:
                print(f"[+] Task submitted successfully. Task ID: {task_id}")
                return task_id
            else:
                print("[-] Submission successful but no task_id returned.")
                return None
        else:
            print(f"[-] Task submission failed: {data.get('error', 'Unknown error')}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"[!] Error submitting task: {e}")
        return None
    except Exception as e:
        print(f"[!] An unexpected error occurred during task submission: {e}")
        return None

def poll_task_status(base_url, task_id, poll_interval=5, timeout=300):
    """轮询任务状态直到完成或失败"""
    status_url_template = f"{base_url}/task_status/{task_id}"
    start_time = time.time()
    print(f"[*] Polling status for Task ID: {task_id} (URL: {status_url_template})")

    while True:
        # 检查是否超时
        if time.time() - start_time > timeout:
            print(f"[!] Polling timed out after {timeout} seconds for task {task_id}.")
            return None

        try:
            response = requests.get(status_url_template, timeout=10)
            response.raise_for_status()
            data = response.json()

            if not data.get("success"):
                print(f"[-] Failed to get task status: {data.get('error', 'Unknown error')}")
                return None # 获取状态失败，停止轮询

            task_data = data.get("task_data", {})
            status = task_data.get("status")
            timestamp = task_data.get("timestamp", "N/A")

            print(f"    - Current status: {status} (at {timestamp})")

            if status == "completed":
                print(f"[+] Task {task_id} completed successfully!")
                print(f"    Result: {task_data.get('result', 'No result field')}")
                print(f"    Duration: {task_data.get('duration_seconds', 'N/A')} seconds")
                return task_data # 返回最终的任务数据
            elif status == "failed":
                print(f"[-] Task {task_id} failed.")
                print(f"    Error: {task_data.get('error', 'No error field')}")
                return task_data # 返回最终的任务数据
            elif status in ["received", "computing"]:
                # 继续轮询
                pass
            else:
                print(f"[?] Unknown status received: {status}. Stopping poll.")
                return task_data # 返回未知的任务数据

        except requests.exceptions.RequestException as e:
            print(f"[!] Error polling task status: {e}. Retrying in {poll_interval}s...")
        except Exception as e:
             print(f"[!] An unexpected error occurred during polling: {e}. Retrying in {poll_interval}s...")

        # 等待下一个轮询周期
        time.sleep(poll_interval)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test the Modal GPU service API.")
    parser.add_argument(
        "--url",
        required=True,
        help="Base URL of the deployed Modal application (e.g., https://your-modal-url.modal.run)"
    )
    parser.add_argument(
        "--size",
        type=int,
        default=256, # 使用一个较小的默认值进行测试
        help="Matrix size for the GPU computation task."
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Polling interval in seconds."
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180, # 3分钟超时
        help="Polling timeout in seconds."
    )

    args = parser.parse_args()

    print("-" * 30)
    print("Starting Modal API Test")
    print(f"Target URL: {args.url}")
    print(f"Matrix Size: {args.size}")
    print("-" * 30)

    # 1. 测试健康检查
    if not test_status(args.url):
        print("[!] Health check failed. Aborting further tests.")
        sys.exit(1)

    print("\n" + "-" * 30 + "\n")

    # 2. 提交任务
    task_id = submit_gpu_task(args.url, args.size)

    print("\n" + "-" * 30 + "\n")

    # 3. 轮询状态
    if task_id:
        final_status_data = poll_task_status(args.url, task_id, args.interval, args.timeout)
        if final_status_data:
             print("\n[*] Final Task Data:")
             # 打印最终状态的详细信息
             for key, value in final_status_data.items():
                 print(f"    {key}: {value}")
        else:
            print("[-] Polling did not complete successfully or timed out.")
    else:
        print("[-] Could not obtain Task ID, skipping status polling.")

    print("\n" + "-" * 30)
    print("Test Finished")
    print("-" * 30)