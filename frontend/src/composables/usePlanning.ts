import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ApiError } from '../api/client'
import { createPlan, deleteTrip, getHistory, getTrip, isTerminalTask } from '../api/planning'
import { monitorTask } from '../api/taskMonitor'
import { setCurrentTrip } from '../stores/currentTrip'
import type { PlanningTask, TripDetail, TripHistoryItem } from '../types/planning'
import type { TravelRequest } from '../types/travel'

const storageKey = 'xingzhi:last-task-id'
const taskIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const errorOf = (error: unknown) => error instanceof ApiError ? error
  : new ApiError({ code: 'UNEXPECTED_ERROR', message: '暂时无法读取，请重试。' })

export function usePlanning() {
  const taskId = ref<string | null>(null)
  const task = ref<PlanningTask | null>(null)
  const trip = ref<TripDetail | null>(null)
  const submitting = ref(false)
  const reading = ref(false)
  const connectionError = ref<ApiError | null>(null)
  const submissionError = ref<ApiError | null>(null)
  const uncertainSubmission = ref(false)
  const history = ref<TripHistoryItem[]>([])
  const historyLoading = ref(false)
  const historyError = ref<ApiError | null>(null)
  const hasMoreHistory = ref(false)
  const storageAvailable = ref(true)
  const busy = computed(() => submitting.value || uncertainSubmission.value
    || (taskId.value !== null && (!task.value || !isTerminalTask(task.value.status))))
  let sequence = 0
  let controller: AbortController | undefined
  let historySequence = 0
  let historyController: AbortController | undefined
  let destroyed = false
  const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api'

  function remember(id: string | null) {
    try {
      if (id) localStorage.setItem(storageKey, id)
      else localStorage.removeItem(storageKey)
    } catch { storageAvailable.value = false }
  }

  function beginRead() {
    controller?.abort()
    controller = new AbortController()
    return { number: ++sequence, signal: controller.signal }
  }

  async function refreshHistory(append = false) {
    historyController?.abort()
    historyController = new AbortController()
    const number = ++historySequence
    historyLoading.value = true
    historyError.value = null
    try {
      const result = await getHistory({ baseUrl, signal: historyController.signal, offset: append ? history.value.length : 0 })
      if (destroyed || number !== historySequence) return
      history.value = append ? [...history.value, ...result.items.filter(item => !history.value.some(old => old.trip_id === item.trip_id))] : result.items
      hasMoreHistory.value = result.has_more
    } catch (error) {
      if (!destroyed && number === historySequence) historyError.value = errorOf(error)
    } finally {
      if (!destroyed && number === historySequence) historyLoading.value = false
    }
  }

  async function readTask(id: string) {
    const request = beginRead()
    taskId.value = id
    if (task.value?.task_id !== id) task.value = null
    reading.value = true
    connectionError.value = null
    remember(id)
    try {
      const completed = await monitorTask(id, update => {
        if (request.number === sequence && !destroyed) task.value = update
      }, { baseUrl, signal: request.signal })
      if (request.number !== sequence || destroyed) return
      // Loading the persisted trip also restores the canonical input for a failed task's retry.
      const saved = await getTrip(completed.trip_id, { baseUrl, signal: request.signal })
      if (request.number !== sequence || destroyed) return
      trip.value = saved
      uncertainSubmission.value = false
      void refreshHistory()
    } catch (error) {
      if (request.number !== sequence || destroyed) return
      const failure = errorOf(error)
      connectionError.value = failure
      if (['TASK_NOT_FOUND', 'NOT_FOUND', 'VALIDATION_ERROR'].includes(failure.code)) {
        taskId.value = null
        task.value = null
        remember(null)
      }
    } finally {
      if (request.number === sequence && !destroyed) reading.value = false
    }
  }

  async function generate(requestBody: TravelRequest) {
    if (busy.value || reading.value) return
    const request = beginRead()
    submitting.value = true
    submissionError.value = null
    connectionError.value = null
    try {
      const accepted = await createPlan(requestBody, { baseUrl, signal: request.signal })
      if (request.number !== sequence || destroyed) return
      task.value = null
      trip.value = null
      taskId.value = accepted.task_id
      remember(accepted.task_id)
      submitting.value = false
      void refreshHistory()
      void readTask(accepted.task_id)
    } catch (error) {
      if (request.number !== sequence || destroyed) return
      submissionError.value = errorOf(error)
      uncertainSubmission.value = ['NETWORK_ERROR', 'REQUEST_TIMEOUT', 'INVALID_RESPONSE', 'TASK_BUSY'].includes(submissionError.value.code)
      void refreshHistory()
    } finally {
      if (!destroyed) submitting.value = false
    }
  }

  async function openTrip(id: string) {
    if (submitting.value || (busy.value && !uncertainSubmission.value)) return
    const request = beginRead()
    reading.value = true
    connectionError.value = null
    try {
      const saved = await getTrip(id, { baseUrl, signal: request.signal })
      if (request.number !== sequence || destroyed) return
      trip.value = saved
      task.value = null
      taskId.value = saved.latest_task?.task_id || null
      uncertainSubmission.value = false
      submissionError.value = null
      remember(taskId.value)
      if (taskId.value) void readTask(taskId.value)
    } catch (error) {
      if (request.number === sequence && !destroyed) connectionError.value = errorOf(error)
    } finally {
      if (request.number === sequence && !destroyed) reading.value = false
    }
  }

  async function removeTrip(id: string) {
    await deleteTrip(id, { baseUrl })
    if (trip.value?.trip_id === id) {
      trip.value = null
      task.value = null
      taskId.value = null
      remember(null)
    }
    setCurrentTrip(null)
    await refreshHistory()
  }

  async function recoverLatest() {
    // A timed-out POST can have been accepted. Inspect persisted tasks before allowing another POST.
    if (submitting.value || reading.value) return
    await refreshHistory()
    if (destroyed || historyError.value) return
    const active = history.value.find(item => !isTerminalTask(item.status))
    const latest = active || history.value[0]
    if (latest) await openTrip(latest.trip_id)
    else uncertainSubmission.value = false
  }

  onMounted(() => {
    void refreshHistory()
    try {
      const saved = localStorage.getItem(storageKey)
      if (saved && taskIdPattern.test(saved)) void readTask(saved)
      else if (saved) remember(null)
    } catch { storageAvailable.value = false }
  })
  onBeforeUnmount(() => {
    destroyed = true
    sequence += 1
    historySequence += 1
    controller?.abort()
    historyController?.abort()
  })

  return { taskId, task, trip, submitting, reading, busy, connectionError, submissionError, uncertainSubmission,
    history, historyLoading, historyError, hasMoreHistory, storageAvailable,
    generate, readTask, refreshHistory, openTrip, recoverLatest, removeTrip }
}
