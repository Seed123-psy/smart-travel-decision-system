<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

const providerLabels = {
  llm: '模型服务',
  amap: '地图与天气',
} as const
type ProviderName = keyof typeof providerLabels
interface ProviderState {
  name: ProviderName
  label: string
  status: 'not_configured' | 'not_verified'
}

const providers = ref<ProviderState[]>([])
const loading = ref(true)
const failed = ref(false)
let requestNumber = 0
let controller: AbortController | undefined
let timeout: ReturnType<typeof setTimeout> | undefined

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function parseStatus(value: unknown): ProviderState[] {
  if (!isRecord(value) || value.live_checked !== false
    || !Array.isArray(value.providers) || value.providers.length !== 2) {
    throw new Error('Invalid service status')
  }

  const entries = new Map<ProviderName, ProviderState>()
  for (const provider of value.providers) {
    if (!isRecord(provider) || (provider.name !== 'llm' && provider.name !== 'amap')
      || entries.has(provider.name) || provider.label !== providerLabels[provider.name]
      || typeof provider.configured !== 'boolean'
      || !Array.isArray(provider.missing_fields)
      || !provider.missing_fields.every(field => typeof field === 'string')
      || (provider.configured
        ? provider.status !== 'not_verified' || provider.missing_fields.length !== 0
        : provider.status !== 'not_configured' || provider.missing_fields.length === 0)) {
      throw new Error('Invalid provider status')
    }
    entries.set(provider.name, {
      name: provider.name,
      label: providerLabels[provider.name],
      status: provider.configured ? 'not_verified' : 'not_configured',
    })
  }

  return (['llm', 'amap'] as const).map(name => entries.get(name)!)
}

async function refresh() {
  controller?.abort()
  clearTimeout(timeout)
  const currentRequest = ++requestNumber
  const currentController = new AbortController()
  controller = currentController
  const currentTimeout = setTimeout(() => currentController.abort(), 10_000)
  timeout = currentTimeout
  loading.value = true
  failed.value = false
  providers.value = []

  try {
    const baseUrl = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
    const response = await fetch(`${baseUrl}/providers/status`, {
      signal: currentController.signal,
      cache: 'no-store',
    })
    if (!response.ok) throw new Error('Service status unavailable')
    const parsed = parseStatus(await response.json())
    if (currentController.signal.aborted) throw new Error('Service status cancelled')
    if (currentRequest === requestNumber) providers.value = parsed
  } catch {
    if (currentRequest === requestNumber) failed.value = true
  } finally {
    clearTimeout(currentTimeout)
    if (currentRequest === requestNumber) {
      loading.value = false
      controller = undefined
      timeout = undefined
    }
  }
}

onMounted(refresh)
onBeforeUnmount(() => {
  requestNumber += 1
  controller?.abort()
  clearTimeout(timeout)
})
</script>

<template>
  <section class="service-card" aria-labelledby="services-heading" :aria-busy="loading">
    <div class="service-heading">
      <h2 id="services-heading">服务配置</h2>
      <button type="button" class="refresh-button" :disabled="loading" @click="refresh">
        {{ loading ? '检查中…' : failed ? '重试' : '刷新状态' }}
      </button>
    </div>
    <div class="service-status" aria-live="polite">
      <p v-if="loading" class="status-message">正在检查服务配置…</p>
      <p v-else-if="failed" class="status-message status-error">服务状态暂不可用</p>
      <ul v-else class="provider-list">
        <li v-for="provider in providers" :key="provider.name">
          <span>{{ provider.label }}</span>
          <span class="provider-status" :class="{ 'awaiting-verification': provider.status === 'not_verified' }">
            {{ provider.status === 'not_configured' ? '未配置' : '已配置' }}
          </span>
        </li>
      </ul>
    </div>
    <p class="service-description">这里显示配置状态；配置齐全不代表服务已连通，实际调用结果请查看本次协作记录。</p>
  </section>
</template>

<style scoped>
.service-card {
  padding: 22px 24px;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: var(--surface);
  font-family: var(--font-ui);
}
.service-heading {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 16px;
}
.service-heading h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 500;
  color: var(--green);
}
.refresh-button {
  min-height: 36px;
  padding: 4px 10px;
  border: 1px solid #d5dfd1;
  border-radius: 8px;
  background: #f3f5ed;
  color: var(--green);
  font-size: 12px;
}
.refresh-button:hover:enabled { background: #eaf0e3; }
.refresh-button:disabled { color: var(--muted); }
.provider-list { list-style: none; margin: 18px 0; padding: 0; }
.provider-list li {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 12px;
  font-size: 14px;
}
.provider-list li + li { margin-top: 12px; }
.provider-status {
  padding: 1px 9px;
  border: 1px solid #dce4d5;
  border-radius: 20px;
  color: #66785e;
  font-size: 12px;
}
.awaiting-verification { border-color: #e1d5b8; background: #faf6eb; color: #78643b; }
.status-message { margin: 18px 0; font-size: 13px; color: var(--muted); }
.status-error { color: #8f4426; }
.service-description { margin: 0; font-size: 12px; line-height: 1.85; color: var(--muted); }
</style>
