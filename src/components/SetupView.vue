<script setup lang="ts">
import { ref } from 'vue'
import headerMascot from '../assets/header-mascot.png'
import { setupRequest, type SetupCheck } from '../api/setup'

const emit = defineEmits<{ configured: [] }>()
const setupKey = ref('')
const primaryUrl = ref('')
const apiKey = ref('')
const inviteCode = ref('')
const busy = ref(false)
const message = ref('')
const checks = ref<SetupCheck[]>([])

async function submit(save: boolean) {
  if (busy.value) return
  busy.value = true
  message.value = ''
  checks.value = []
  try {
    const data = await setupRequest<{ configured?: boolean; checks: SetupCheck[] }>(save ? '' : '/test', {
      setup_key: setupKey.value,
      primary_url: primaryUrl.value.trim(),
      api_key: apiKey.value.trim(),
      invite_code: inviteCode.value.trim(),
    })
    checks.value = data.checks
    if (data.configured) {
      setupKey.value = ''
      apiKey.value = ''
      inviteCode.value = ''
      emit('configured')
    }
  } catch (cause) { message.value = cause instanceof Error ? cause.message : '配置失败，请重试' }
  finally { busy.value = false }
}
</script>

<template>
  <main class="login-page">
    <div class="login-container">
      <div class="brand"><img class="brand-mascot" :src="headerMascot" alt="" width="64" height="64" />KomgaRead</div>
      <section class="login-card">
        <p class="eyebrow">首次启动</p>
        <h1>连接 Komga</h1>
        <p class="intro">设置漫画服务地址和管理员 API 密钥，完成后即可登录。</p>
        <p class="setup-hint">初始化密钥已自动生成，请从容器启动日志中复制。</p>
        <form @submit.prevent="submit(true)" @input="checks = []; message = ''">
          <div class="field"><label for="setup-key">初始化密钥</label><input id="setup-key" v-model="setupKey" type="password" autocomplete="off" required maxlength="1024" placeholder="从启动日志复制，或使用手动设置的密钥" /></div>
          <div class="field"><label for="primary-url">Komga 公网地址</label><input id="primary-url" v-model="primaryUrl" type="url" required maxlength="2048" placeholder="https://komga.example.com" /></div>
          <p class="setup-hint">请填写容器可以访问的 Komga 公网地址。</p>
          <div class="field"><label for="komga-api-key">Komga 管理员 API 密钥</label><input id="komga-api-key" v-model="apiKey" type="password" autocomplete="off" required maxlength="4096" placeholder="填写管理员账号生成的 API 密钥" /></div>
          <p class="setup-hint">密钥只保存到后端，用于后续账号管理。它与上方的初始化密钥不同。</p>
          <div class="field"><label for="setup-invite">注册邀请码</label><input id="setup-invite" v-model="inviteCode" type="password" autocomplete="off" required maxlength="256" placeholder="设置分享给注册用户的邀请码" /></div>
          <p class="setup-hint">用户注册时必须填写此邀请码；可重复使用，区分大小写，忽略首尾空格。</p>
          <div class="setup-actions">
            <button class="text-button" type="button" :disabled="busy || !setupKey || !primaryUrl || !apiKey.trim() || !inviteCode.trim()" @click="submit(false)">测试连接</button>
            <button class="submit-button" type="submit" :disabled="busy">{{ busy ? '正在检查…' : '测试并保存' }}</button>
          </div>
          <p v-if="message" class="form-message" role="alert">{{ message }}</p>
          <ul v-if="checks.length" class="setup-checks" aria-live="polite"><li v-for="check in checks" :key="check.address">{{ check.reachable ? '✓' : '✕' }} {{ check.message }}</li></ul>
        </form>
      </section>
    </div>
  </main>
</template>
