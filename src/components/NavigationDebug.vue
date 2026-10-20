<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { navigationDebugLines, traceNavigation } from '../navigationDebug'

const copied = ref(false)
let resizeObserver: ResizeObserver | undefined
let resourceObserver: PerformanceObserver | undefined
function pageEvent(event: PageTransitionEvent) { traceNavigation(event.type, { persisted: event.persisted }) }
function viewportEvent() { traceNavigation('viewport-resize') }

onMounted(() => {
  traceNavigation('app-start', {
    navigation: (performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined)?.type,
    userAgent: navigator.userAgent,
  })
  window.addEventListener('pageshow', pageEvent)
  window.addEventListener('pagehide', pageEvent)
  window.addEventListener('resize', viewportEvent)
  window.visualViewport?.addEventListener('resize', viewportEvent)
  const stage = document.querySelector('.page-stage')
  if (stage && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => traceNavigation('stage-resize'))
    resizeObserver.observe(stage)
  }
  if (typeof PerformanceObserver !== 'undefined') {
    resourceObserver = new PerformanceObserver(list => {
      for (const entry of list.getEntries()) {
        const url = new URL(entry.name, window.location.href)
        if (url.origin === window.location.origin && url.pathname.startsWith('/api/')) {
          // 只记录接口路径，不记录参数、内容、Cookie 或密钥。
          traceNavigation('api-complete', { path: url.pathname, duration: Math.round(entry.duration) })
        }
      }
    })
    resourceObserver.observe({ type: 'resource', buffered: true })
  }
})
onUnmounted(() => {
  window.removeEventListener('pageshow', pageEvent)
  window.removeEventListener('pagehide', pageEvent)
  window.removeEventListener('resize', viewportEvent)
  window.visualViewport?.removeEventListener('resize', viewportEvent)
  resizeObserver?.disconnect()
  resourceObserver?.disconnect()
})
function download() {
  const url = URL.createObjectURL(new Blob([navigationDebugLines.value.join('\n')], { type: 'text/plain' }))
  const link = document.createElement('a')
  link.href = url
  link.download = 'navigation-debug.txt'
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
async function copy() {
  try { await navigator.clipboard.writeText(navigationDebugLines.value.join('\n')); copied.value = true }
  catch { download() }
}
</script>

<template>
  <aside class="navigation-debug" aria-label="临时导航诊断">
    <div><strong>导航诊断</strong><button @click="copy">{{ copied ? '已复制' : '复制记录' }}</button><button @click="download">下载</button></div>
    <pre>{{ navigationDebugLines.slice(-4).join('\n') }}</pre>
  </aside>
</template>

<style scoped>
.navigation-debug { position: fixed; z-index: 10000; left: 6px; right: 6px; bottom: calc(70px + env(safe-area-inset-bottom, 0px)); padding: 6px; border-radius: 6px; background: #18231ef0; color: #fff; font-size: 10px; }
.navigation-debug > div { display: flex; align-items: center; gap: 10px; }
.navigation-debug button { padding: 4px 8px; border: 1px solid #98b2a2; border-radius: 4px; background: transparent; color: white; font-size: 11px; }
.navigation-debug pre { margin: 4px 0 0; max-height: 90px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
