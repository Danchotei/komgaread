<script setup lang="ts">
import { ref } from 'vue'

const jmid = ref('')
const message = ref('')
const submitting = ref(false)

defineEmits<{ back: [] }>()

async function submit() {
  if (submitting.value) return
  const value = jmid.value.trim().replace(/^jm/i, '') // 去掉空格及可选的 JM 前缀
  message.value = ''

  // 只允许输入 1～20 位数字
  if (!/^\d{1,20}$/.test(value)) {
    message.value = '请输入有效的数字 ID'
    return // 校验失败，不发送请求
  }

  submitting.value = true
  try {
    const response = await fetch('/api/resource/lookup', {
      method: 'POST',
      credentials: 'same-origin', // 携带本站登录 Cookie
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jmid: value }),
    })
    // 成功响应没有正文，不调用 response.json()。
    if (!response.ok) throw new Error(response.status === 401 ? '请先登录' : '提交失败，请重试')
  } catch (error) {
    message.value = error instanceof Error ? error.message : '网络连接失败'
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
  </main>
</template>
