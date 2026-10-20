<script setup lang="ts">
import { ref } from 'vue'

// ref 保存会变化的数据；数据变化时，Vue 会更新对应的界面。
const username = ref('')
const password = ref('')
const showPassword = ref(false)
const message = ref('')

function handleSubmit() {
  // 目前只演示表单交互，下一步在这里调用后端登录接口。
  message.value = '表单填写完成。Komga 连接尚未配置，本次未进行登录。'
}

function clearMessage() {
  message.value = ''
}
</script>

<template>
  <main class="login-page">
    <div class="login-container">
      <a class="brand" href="./" aria-label="KomgaRead 首页">
        <span class="brand-icon" aria-hidden="true">K</span>
        KomgaRead
      </a>

      <section class="login-card" aria-labelledby="login-title">
        <p class="eyebrow">你的私人漫画书架</p>
        <h1 id="login-title">欢迎回来</h1>
        <p class="intro">使用你的 Komga 账号，继续阅读喜欢的故事。</p>

        <form @submit.prevent="handleSubmit" @input="clearMessage">
          <div class="field">
            <label for="username">账号</label>
            <input
              id="username"
              v-model.trim="username"
              name="username"
              type="text"
              autocomplete="username"
              placeholder="输入 Komga 账号"
              required
              maxlength="254"
              pattern=".*\S.*"
              title="请输入账号，不能只有空格"
            />
          </div>

          <div class="field">
            <label for="password">密码</label>
            <div class="password-field">
              <input
                id="password"
                v-model="password"
                name="password"
                :type="showPassword ? 'text' : 'password'"
                autocomplete="current-password"
                placeholder="输入密码"
                required
              />
              <button
                class="password-toggle"
                type="button"
                :aria-pressed="showPassword"
                aria-controls="password"
                @click="showPassword = !showPassword"
              >{{ showPassword ? '隐藏' : '显示' }}密码</button>
            </div>
          </div>

          <button class="submit-button" type="submit">登录</button>
          <p v-if="message" class="form-message" role="status">{{ message }}</p>
        </form>

        <p class="account-help">账号由管理员创建。如需账号或重置密码，请联系管理员。</p>
      </section>

      <p class="preview-note">界面预览 · 尚未连接 Komga</p>
    </div>
  </main>
</template>
