import asyncio
import traceback
from typing import Callable, Coroutine, Any

_task_queue: asyncio.Queue[Callable[[], Coroutine[Any, Any, Any]]] = asyncio.Queue()

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
    asyncio.create_task(worker_loop())
