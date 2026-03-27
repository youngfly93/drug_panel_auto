<template>
  <el-container class="app-layout">
    <!-- Mobile overlay -->
    <div v-if="isMobile && sidebarOpen" class="sidebar-overlay" @click="sidebarOpen = false" />

    <el-aside :width="sidebarWidth" :class="['sidebar', { 'sidebar-mobile': isMobile, 'sidebar-open': sidebarOpen }]">
      <div class="logo">
        <h2 v-if="!collapsed">Panel Report</h2>
        <h2 v-else>PR</h2>
      </div>
      <el-menu
        :default-active="activeMenu"
        :collapse="collapsed && !isMobile"
        router
        background-color="#001529"
        text-color="#ffffffa6"
        active-text-color="#ffffff"
        @select="isMobile && (sidebarOpen = false)"
      >
        <el-menu-item index="/">
          <el-icon><Monitor /></el-icon>
          <span>工作台</span>
        </el-menu-item>
        <el-menu-item index="/generate">
          <el-icon><Document /></el-icon>
          <span>生成报告</span>
        </el-menu-item>
        <el-menu-item index="/patients">
          <el-icon><User /></el-icon>
          <span>患者信息</span>
        </el-menu-item>
        <el-menu-item index="/knowledge">
          <el-icon><Reading /></el-icon>
          <span>知识库</span>
        </el-menu-item>
        <el-menu-item index="/config">
          <el-icon><Setting /></el-icon>
          <span>配置管理</span>
        </el-menu-item>
        <el-menu-item index="/tasks">
          <el-icon><List /></el-icon>
          <span>任务队列</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <div class="header-content">
          <div style="display: flex; align-items: center; gap: 8px">
            <el-button
              v-if="isMobile"
              text
              @click="sidebarOpen = !sidebarOpen"
              style="font-size: 20px; padding: 4px"
            >
              <el-icon :size="22"><Fold /></el-icon>
            </el-button>
            <el-button
              v-else
              text
              @click="collapsed = !collapsed"
              style="font-size: 18px; padding: 4px"
            >
              <el-icon :size="18"><component :is="collapsed ? Expand : Fold" /></el-icon>
            </el-button>
            <el-breadcrumb separator="/">
              <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
              <el-breadcrumb-item v-if="currentTitle">{{ currentTitle }}</el-breadcrumb-item>
            </el-breadcrumb>
          </div>
          <div class="user-info" v-if="authStore.user">
            <span class="user-name">{{ authStore.user.display_name }}</span>
            <el-button text @click="authStore.logout(); $router.push('/login')">退出</el-button>
          </div>
        </div>
      </el-header>
      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { Monitor, Document, User, Reading, Setting, List, Fold, Expand } from '@element-plus/icons-vue'

const route = useRoute()
const authStore = useAuthStore()

const collapsed = ref(false)
const sidebarOpen = ref(false)
const windowWidth = ref(window.innerWidth)

const MOBILE_BREAKPOINT = 768

const isMobile = computed(() => windowWidth.value < MOBILE_BREAKPOINT)
const sidebarWidth = computed(() => {
  if (isMobile.value) return '220px'
  return collapsed.value ? '64px' : '220px'
})

const activeMenu = computed(() => route.path)

const titleMap: Record<string, string> = {
  '/generate': '生成报告',
  '/patients': '患者信息',
  '/knowledge': '知识库',
  '/config': '配置管理',
  '/tasks': '任务队列',
}
const currentTitle = computed(() => titleMap[route.path] || '')

function onResize() {
  windowWidth.value = window.innerWidth
  if (!isMobile.value) sidebarOpen.value = false
}

onMounted(() => window.addEventListener('resize', onResize))
onUnmounted(() => window.removeEventListener('resize', onResize))
</script>

<style scoped>
.app-layout {
  height: 100vh;
}
.sidebar {
  background-color: #001529;
  overflow-y: auto;
  transition: width 0.2s;
}
.sidebar-mobile {
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  z-index: 1000;
  transform: translateX(-100%);
  transition: transform 0.25s ease;
}
.sidebar-mobile.sidebar-open {
  transform: translateX(0);
}
.sidebar-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  z-index: 999;
}
.logo {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}
.logo h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  white-space: nowrap;
}
.header {
  background: #fff;
  border-bottom: 1px solid #f0f0f0;
  display: flex;
  align-items: center;
  padding: 0 16px;
}
.header-content {
  width: 100%;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

@media (max-width: 768px) {
  .user-name {
    display: none;
  }
  .header {
    padding: 0 8px;
  }
}
</style>
