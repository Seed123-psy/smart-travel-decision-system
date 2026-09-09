<script setup lang="ts">
import RequirementsView from './views/RequirementsView.vue'
</script>

<template>
  <a class="skip-link" href="#main-content">跳转到旅行需求</a>
  <header class="site-header">
    <a class="brand" href="/" aria-label="行知首页">
      <span class="brand-symbol" aria-hidden="true">行</span>
      <span>行知<span class="brand-caption">智能旅行决策</span></span>
    </a>
    <span class="environment-tag"><span aria-hidden="true"></span>本地开发版</span>
  </header>
  <RequirementsView />
  <footer class="site-footer">
    <span>行知 · 让每一次出发，都有据可依。</span>
    <span>单城旅行 / 1–7 天 / 1–10 人</span>
  </footer>
</template>
