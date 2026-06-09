import asyncio
import os
import traceback
from typing import Callable, Coroutine, Any

_task_queue: asyncio.Queue[Callable[[], Coroutine[Any, Any, Any]]] = asyncio.Queue()
WORKER_COUNT = int(os.getenv("TASK_QUEUE_WORKERS", "4"))


async def worker_loop():
    while True:
        task_coro = await _task_queue.get()
        try:
            await task_coro()
        except Exception:
            traceback.print_exc()
        finally:
            _task_queue.task_done()


async def enqueue_task(task_coro: Callable[[], Coroutine[Any, Any, Any]]):
    await _task_queue.put(task_coro)


async def enqueue_sync_task(func: Callable[..., Any], *args, **kwargs):
    await _task_queue.put(lambda: asyncio.to_thread(func, *args, **kwargs))


async def start_queue_worker():
    for _ in range(WORKER_COUNT):
        asyncio.create_task(worker_loop())
