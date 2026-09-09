<script setup lang="ts">
import { ref } from 'vue'
import { usePlanning } from './composables/usePlanning'
import { providePlanning } from './composables/planningContext'
import { isTerminalTask } from './api/planning'
import DevDrawer from './components/DevDrawer.vue'

// A single planning instance (task polling, history, trip) lives here and is shared by every view.
const planning = usePlanning()
providePlanning(planning)
const { task, taskId } = planning

const drawerOpen = ref(false)
</script>

<template>
  <a class="skip-link" href="#main-content">跳到主要内容</a>
  <header class="site-header">
    <a class="brand" href="/" aria-label="行知首页">
      <span class="brand-symbol" aria-hidden="true">行</span>
      <span class="brand-name">行知<span class="brand-caption">智能旅行决策</span></span>
    </a>
    <nav class="site-nav" aria-label="主导航">
      <RouterLink to="/">首页</RouterLink>
      <RouterLink to="/plan/chat">开始规划</RouterLink>
      <RouterLink to="/flights">机票</RouterLink>
      <RouterLink to="/trips">我的行程</RouterLink>
    </nav>
    <div class="header-actions">
      <RouterLink v-if="taskId && task && !isTerminalTask(task.status)"
        class="progress-pill" to="/plan">
        <span aria-hidden="true"></span>生成中，查看进展
      </RouterLink>
      <button type="button" class="dev-toggle" :aria-expanded="drawerOpen" aria-controls="dev-drawer"
        @click="drawerOpen = !drawerOpen" title="调试面板">
        <span aria-hidden="true">⚙</span><span class="visually-hidden">调试面板</span>
      </button>
    </div>
  </header>
  <RouterView />
  <footer class="site-footer">
    <span>行知 · 让每一次出发，都有据可依。</span>
    <span>单城旅行 / 1–7 天 / 1–10 人 · 全程本地运行</span>
  </footer>
  <DevDrawer id="dev-drawer" :open="drawerOpen" @close="drawerOpen = false" />
</template>
