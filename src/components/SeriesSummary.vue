<script setup lang="ts">
import { computed, nextTick, onDeactivated, onMounted, onUnmounted, ref } from 'vue'

defineProps<{ summary: string }>()
const content = ref<HTMLElement | null>(null)
const toggle = ref<HTMLButtonElement | null>(null)
const expanded = ref(false)
const fullHeight = ref(0)
const collapsedHeight = ref(0)
const canExpand = computed(() => fullHeight.value > collapsedHeight.value + 1)
const clipStyle = computed(() => collapsedHeight.value
  ? { height: `${canExpand.value && !expanded.value ? collapsedHeight.value : fullHeight.value}px` }
  : { maxHeight: '13.2em' })
let observer: ResizeObserver | undefined
let scrollFrame = 0
async function toggleSummary() {
  cancelAnimationFrame(scrollFrame)
  const anchor = toggle.value?.getBoundingClientRect().top
  expanded.value = !expanded.value
  await nextTick()
  if (anchor === undefined) return
  const started = performance.now()
  // 同步实际高度变化补偿滚动，按钮不因展开／收起突然离开视口。
  const follow = () => {
    const top = toggle.value?.getBoundingClientRect().top
    if (top === undefined) return
    window.scrollBy({ top: top - anchor, behavior: 'instant' })
    if (performance.now() - started < 460) scrollFrame = requestAnimationFrame(follow)
    else scrollFrame = 0
  }
  scrollFrame = requestAnimationFrame(follow)
}
onMounted(() => {
  const element = content.value
  if (!element) return
  const measure = () => {
    collapsedHeight.value = parseFloat(getComputedStyle(element).lineHeight) * 8
    fullHeight.value = element.getBoundingClientRect().height
  }
  measure()
  // 观察文字本身，屏幕宽度或字体改变时重新计算；不观察动画容器以免循环。
  observer = new ResizeObserver(measure)
  observer.observe(element)
})
onDeactivated(() => cancelAnimationFrame(scrollFrame))
onUnmounted(() => { observer?.disconnect(); cancelAnimationFrame(scrollFrame) })
</script>

<template>
  <div class="series-summary" :class="{ 'is-collapsible': canExpand }">
    <div class="summary-clip" :style="clipStyle">
      <p ref="content" class="summary-text">{{ summary }}</p>
    </div>
    <button v-if="canExpand" ref="toggle" class="summary-toggle" type="button" :aria-expanded="expanded" :aria-label="expanded ? '收起简介' : '展开简介'" @click="toggleSummary">
      <svg viewBox="0 0 24 24" aria-hidden="true" :class="{ 'is-expanded': expanded }"><path d="m6 9 6 6 6-6" /></svg>
    </button>
  </div>
</template>
