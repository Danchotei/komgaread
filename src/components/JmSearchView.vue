<script setup lang="ts">
import { onActivated, onDeactivated, onMounted, onUnmounted, ref } from 'vue'

interface ResourceDetails { title: string; authors: string[]; tags: string[]; coverUrl: string | null; link?: string }
const resource = ref<ResourceDetails | null>(null)
const coverFailed = ref(false)
const jmid = ref('')
const message = ref('')
const submitting = ref(false)
let active = true
let generation = 0
function releaseResource() {
  active = false
  generation++
  resource.value = null
}
function resumePage() { active = true }
onActivated(() => { active = true })
onDeactivated(releaseResource)
onMounted(() => {
  window.addEventListener('pagehide', releaseResource)
  window.addEventListener('pageshow', resumePage)
})
onUnmounted(() => {
  releaseResource()
  window.removeEventListener('pagehide', releaseResource)
  window.removeEventListener('pageshow', resumePage)
})

function textList(value: unknown): string[] {
  const values = typeof value === 'string' ? [value] : Array.isArray(value) ? value : []
  return [...new Set(values.filter((item): item is string => typeof item === 'string').map(item => item.trim()).filter(Boolean))]
}

defineEmits<{ back: [] }>()

async function submit() {
  if (submitting.value) return
  const value = jmid.value.trim().replace(/^jm/i, '') // 去掉空格及可选的 JM 前缀
  message.value = ''
  resource.value = null
  coverFailed.value = false

  // 只允许输入 1～20 位数字
  if (!/^\d{1,20}$/.test(value)) {
    message.value = '请输入有效的数字 ID'
    return // 校验失败，不发送请求
  }

  submitting.value = true
  const current = ++generation
  try {
    const response = await fetch('/api/resource/lookup', {
      method: 'POST',
      credentials: 'same-origin', // 携带本站登录 Cookie
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jmid: value }),
    })

    const data = await response.json().catch(() => null)
    // 页面离开后到达的结果不能重新占用图片内存。
    if (!active || current !== generation) return
    if (!response.ok) throw new Error(response.status === 401 ? '请先登录' : typeof data?.detail === 'string' ? data.detail : '提交失败，请重试')
    if (!data || typeof data.title !== 'string' || (data.cover_url !== null && typeof data.cover_url !== 'string')) throw new Error('后端返回的信息格式不正确')
    resource.value = { title: data.title || '未命名漫画', authors: textList(data.author), tags: textList(data.tags), link: data.link, coverUrl: data.cover_url }
  } catch (error) {
    if (active && current === generation) message.value = error instanceof Error ? error.message : '网络连接失败'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="tab-page jm-search-page">
    <div class="search-page-actions">
      <button class="text-button" @click="$emit('back')">← 返回</button>
    </div>
    <h1 class="tab-title">JM搜索</h1>
    <form class="search-form" @submit.prevent="submit">
      <div class="search-input-row">
        <input v-model="jmid" aria-label="漫画 ID" placeholder="输入jm+数字 或 纯数字" maxlength="22" required />
        <button class="text-button" type="submit" :disabled="submitting">{{ submitting ? '提交中…' : '提交' }}</button>
      </div>
      <p v-if="message" class="form-message" role="alert">{{ message }}</p>
    </form>
    <section v-if="resource" class="series-info" aria-label="漫画详情">
      <img v-if="resource.coverUrl && !coverFailed" :key="resource.coverUrl" :src="resource.coverUrl" :alt="resource.title" @error="coverFailed = true" />
      <div v-else class="detail-cover-placeholder">暂无封面</div>
      <div class="series-description">
        <h1>{{ resource.title }}</h1>
        <dl class="series-metadata">
          <div><dt>作者</dt><dd class="metadata-tags"><template v-if="resource.authors.length"><span v-for="author in resource.authors" :key="author" class="metadata-button">{{ author }}</span></template><template v-else>暂无</template></dd></div>
          <div><dt>标签</dt><dd class="metadata-tags"><template v-if="resource.tags.length"><span v-for="tag in resource.tags" :key="tag" class="metadata-button">{{ tag }}</span></template><template v-else>暂无</template></dd></div>
          <div><dt>链接</dt><dd><a :href="resource.link" target="_blank" rel="noopener noreferrer">
      {{ resource.link }}</a></dd></div>
        </dl>
      </div>
    </section>
  </main>
</template>
