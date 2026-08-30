<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <RouterLink class="brand" to="/">
        <span class="brand-mark">远</span>
        <span>
          <strong>远行志</strong>
          <small>旅行智能助手</small>
        </span>
      </RouterLink>
      <nav aria-label="主导航">
        <RouterLink to="/">生成攻略</RouterLink>
        <RouterLink to="/knowledge">知识库</RouterLink>
        <RouterLink to="/status">运行状态</RouterLink>
      </nav>
    </header>

    <main>
      <RouterView />
    </main>

    <footer>
      攻略内容与费用均为规划建议，营业时间、天气、票价和班次请在出发前通过官方渠道确认。
    </footer>
  </div>
</template>

