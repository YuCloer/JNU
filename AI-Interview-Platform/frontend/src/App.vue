<template>
  <div class="app">
    <nav class="navbar">
      <div class="nav-brand">AI 求职助手</div>
      <div class="nav-links">
        <router-link to="/upload">简历解析</router-link>
        <router-link to="/match">JD匹配</router-link>
        <router-link to="/interview">模拟面试</router-link>
      </div>
    </nav>
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<script setup>
</script>
