import { ApiError } from './client.js'
import { getTask, isTerminalTask } from './planning.js'
import type { PlanningTask } from '../types/planning.js'

function pause(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const cancelled = () => {
      clearTimeout(timer)
      signal.removeEventListener('abort', cancelled)
      reject(new ApiError({ code: 'REQUEST_CANCELLED', message: '已停止读取。' }))
    }
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', cancelled)
      resolve()
    }, milliseconds)
    signal.addEventListener('abort', cancelled, { once: true })
    if (signal.aborted) cancelled()
  })
}

export async function monitorTask(taskId: string, onTask: (task: PlanningTask) => void,
  options: { signal: AbortSignal; baseUrl?: string; intervalMs?: number }): Promise<PlanningTask> {
  while (!options.signal.aborted) {
    const task = await getTask(taskId, options)
    if (options.signal.aborted) break
    onTask(task)
    if (isTerminalTask(task.status)) return task
    // Await each request before scheduling another; slow responses never overlap.
    await pause(options.intervalMs ?? 1_000, options.signal)
  }
  throw new ApiError({ code: 'REQUEST_CANCELLED', message: '已停止读取。' })
}
