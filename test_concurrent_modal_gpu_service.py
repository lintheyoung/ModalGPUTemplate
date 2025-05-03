import asyncio
import aiohttp
import time
import argparse
import sys
import random

async def submit_task_async(session, base_url, matrix_size, task_num):
    """异步提交单个任务并返回 Task ID"""
    submit_url = f"{base_url}/submit_task"
    payload = {"matrix_size": matrix_size}
    headers = {"Content-Type": "application/json"}
    # print(f"[Task {task_num}] Submitting...") # 可以取消注释以获取更详细的日志

    try:
        async with session.post(submit_url, json=payload, headers=headers, timeout=30) as response:
            response.raise_for_status()
            data = await response.json()
            if data.get("success"):
                task_id = data.get("task_id")
                # print(f"[Task {task_num}] Submitted. ID: {task_id}")
                return task_id
            else:
                print(f"[Task {task_num}] Submission failed: {data.get('error', 'Unknown error')}")
                return None
    except Exception as e:
        print(f"[Task {task_num}] Error during submission: {e}")
        return None

async def poll_status_async(session, base_url, task_id, task_num, poll_interval=3, timeout=300):
    """异步轮询单个任务的状态"""
    status_url_template = f"{base_url}/task_status/{task_id}"
    start_time = time.time()
    # print(f"[Task {task_num}, ID {task_id}] Start Polling...")

    while True:
        if time.time() - start_time > timeout:
            print(f"[Task {task_num}, ID {task_id}] Polling timed out after {timeout} seconds.")
            return {"task_id": task_id, "status": "timeout", "error": "Polling timeout"}

        try:
            await asyncio.sleep(random.uniform(0.5, poll_interval)) # 加入随机延迟避免同时请求
            async with session.get(status_url_template, timeout=15) as response:
                response.raise_for_status()
                data = await response.json()

                if not data.get("success"):
                    print(f"[Task {task_num}, ID {task_id}] Failed to get status: {data.get('error', 'Unknown error')}")
                    return {"task_id": task_id, "status": "poll_error", "error": data.get('error', 'Polling failed')}

                task_data = data.get("task_data", {})
                status = task_data.get("status")

                if status in ["completed", "failed"]:
                    # print(f"[Task {task_num}, ID {task_id}] Final status: {status}")
                    return {"task_id": task_id, "status": status, "data": task_data}
                elif status not in ["received", "computing"]:
                    print(f"[Task {task_num}, ID {task_id}] Unknown status: {status}")
                    return {"task_id": task_id, "status": "unknown", "data": task_data}
                # else: status is received or computing, continue polling
                # print(f"[Task {task_num}, ID {task_id}] Current status: {status}")

        except asyncio.TimeoutError:
             print(f"[Task {task_num}, ID {task_id}] Request timed out during polling. Retrying...")
        except Exception as e:
            print(f"[Task {task_num}, ID {task_id}] Error during polling: {e}. Retrying...")
            # 在重试前也等待一下
            await asyncio.sleep(poll_interval)


async def run_concurrent_tests(base_url, num_tasks, matrix_size, poll_interval, timeout):
    """运行并发测试的主函数"""
    start_total_time = time.time()
    task_ids = []
    submission_tasks = []
    results = []
    connector = aiohttp.TCPConnector(limit=num_tasks) # 限制并发连接数，防止本地端口耗尽
    async with aiohttp.ClientSession(connector=connector) as session:
        # --- 阶段 1: 并发提交所有任务 ---
        print(f"[*] Submitting {num_tasks} tasks concurrently...")
        submit_start_time = time.time()
        for i in range(num_tasks):
            # 稍微错开提交时间
            await asyncio.sleep(random.uniform(0, 0.1))
            submission_tasks.append(
                asyncio.create_task(submit_task_async(session, base_url, matrix_size, i + 1))
            )

        # 等待所有提交完成并收集 Task ID
        task_ids_results = await asyncio.gather(*submission_tasks)
        task_ids = [tid for tid in task_ids_results if tid is not None]
        submit_end_time = time.time()
        print(f"[+] Submitted {len(task_ids)} tasks successfully in {submit_end_time - submit_start_time:.2f} seconds.")
        if len(task_ids) != num_tasks:
             print(f"[!] Warning: {num_tasks - len(task_ids)} tasks failed during submission.")

        if not task_ids:
            print("[-] No tasks submitted successfully. Exiting.")
            return

        # --- 阶段 2: 并发轮询所有任务的状态 ---
        print(f"\n[*] Polling status for {len(task_ids)} tasks concurrently...")
        polling_tasks = []
        for i, task_id in enumerate(task_ids):
            polling_tasks.append(
                asyncio.create_task(poll_status_async(session, base_url, task_id, i + 1, poll_interval, timeout))
            )

        # 等待所有轮询完成
        results = await asyncio.gather(*polling_tasks)

    end_total_time = time.time()
    print(f"\n[*] All tasks finished polling. Total time: {end_total_time - start_total_time:.2f} seconds.")

    # --- 阶段 3: 统计结果 ---
    success_count = 0
    failed_count = 0
    timeout_count = 0
    other_errors = 0
    durations = []

    for result in results:
        if result and result.get("status") == "completed":
            success_count += 1
            if result.get("data") and result["data"].get("duration_seconds"):
                 durations.append(result["data"]["duration_seconds"])
        elif result and result.get("status") == "failed":
            failed_count += 1
        elif result and result.get("status") == "timeout":
             timeout_count +=1
        else:
            other_errors += 1

    print("\n--- Test Summary ---")
    print(f"Total Tasks Submitted: {num_tasks}")
    print(f"Successful Submissions: {len(task_ids)}")
    print(f"Completed Tasks: {success_count}")
    print(f"Failed Tasks: {failed_count}")
    print(f"Polling Timeouts: {timeout_count}")
    print(f"Other Errors/Unknown Status: {other_errors}")

    if durations:
        avg_duration = sum(durations) / len(durations)
        max_duration = max(durations)
        min_duration = min(durations)
        print(f"\nGPU Task Durations (for completed tasks):")
        print(f"  Average: {avg_duration:.4f}s")
        print(f"  Min: {min_duration:.4f}s")
        print(f"  Max: {max_duration:.4f}s")
    print("--------------------")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run concurrent tests on the Modal GPU service API.")
    parser.add_argument(
        "--url",
        required=True,
        help="Base URL of the deployed Modal application."
    )
    parser.add_argument(
        "-n", "--num-tasks",
        type=int,
        default=10,
        help="Number of concurrent tasks to run."
    )
    parser.add_argument(
        "--size",
        type=int,
        default=256,
        help="Matrix size for the GPU computation task."
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=3,
        help="Base polling interval in seconds."
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300, # 5分钟超时
        help="Polling timeout per task in seconds."
    )

    args = parser.parse_args()

    print("-" * 30)
    print("Starting Modal Concurrent API Test")
    print(f"Target URL: {args.url}")
    print(f"Number of Concurrent Tasks: {args.num_tasks}")
    print(f"Matrix Size: {args.size}")
    print("-" * 30)

    # 运行异步主函数
    asyncio.run(run_concurrent_tests(args.url, args.num_tasks, args.size, args.interval, args.timeout))

    print("\n" + "-" * 30)
    print("Concurrent Test Finished")
    print("-" * 30)