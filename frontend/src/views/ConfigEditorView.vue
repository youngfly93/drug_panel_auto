<template>
  <div>
    <h2>配置管理</h2>

    <el-row :gutter="20">
      <!-- File list -->
      <el-col :span="6">
        <el-card shadow="hover">
          <template #header>配置文件</template>
          <el-menu :default-active="activeFile" @select="selectFile">
            <el-menu-item v-for="file in configFiles" :key="file.filename" :index="file.filename">
              <span>{{ file.filename }}</span>
              <el-tag size="small" type="info" style="margin-left: auto">
                {{ (file.size_bytes / 1024).toFixed(1) }}KB
              </el-tag>
            </el-menu-item>
          </el-menu>
        </el-card>
      </el-col>

      <!-- Editor -->
      <el-col :span="18">
        <el-card v-if="activeFile" shadow="hover">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center">
              <span>{{ activeFile }}</span>
              <div style="display: flex; gap: 8px">
                <el-button size="small" @click="viewHistory">历史版本</el-button>
                <el-button size="small" @click="validateContent">校验</el-button>
                <el-button size="small" type="primary" @click="saveContent">保存</el-button>
              </div>
            </div>
          </template>

          <el-input
            v-model="rawContent"
            type="textarea"
            :rows="30"
            :loading="editorLoading"
            spellcheck="false"
            style="font-family: 'Courier New', monospace; font-size: 13px"
          />

          <!-- Validation results -->
          <div v-if="validationResult" style="margin-top: 12px">
            <el-alert
              :title="validationResult.valid ? '配置校验通过' : '配置校验失败'"
              :type="validationResult.valid ? 'success' : 'error'"
              show-icon
              :closable="false"
            />
            <div v-for="(err, i) in validationResult.errors" :key="i" style="margin-top: 4px">
              <el-alert :title="err" type="error" :closable="false" size="small" />
            </div>
          </div>
        </el-card>
        <el-empty v-else description="请从左侧选择配置文件" />

        <!-- History dialog -->
        <el-dialog v-model="showHistory" title="历史版本" width="500px">
          <el-table :data="history" size="small" stripe>
            <el-table-column prop="filename" label="文件名" />
            <el-table-column prop="created_at" label="备份时间" width="180">
              <template #default="{ row }">
                {{ new Date(row.created_at).toLocaleString('zh-CN') }}
              </template>
            </el-table-column>
            <el-table-column prop="size_bytes" label="大小" width="100">
              <template #default="{ row }">
                {{ (row.size_bytes / 1024).toFixed(1) }}KB
              </template>
            </el-table-column>
          </el-table>
        </el-dialog>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { configApi, type ConfigFile, type ConfigHistory } from '@/api/config'

const configFiles = ref<ConfigFile[]>([])
const activeFile = ref('')
const rawContent = ref('')
const editorLoading = ref(false)
const validationResult = ref<{ valid: boolean; errors: string[] } | null>(null)
const showHistory = ref(false)
const history = ref<ConfigHistory[]>([])

async function fetchFiles() {
  configFiles.value = await configApi.listFiles()
}

async function selectFile(filename: string) {
  activeFile.value = filename
  editorLoading.value = true
  validationResult.value = null
  try {
    rawContent.value = await configApi.getRaw(filename)
  } finally {
    editorLoading.value = false
  }
}

async function validateContent() {
  if (!activeFile.value) return
  // Send raw YAML to backend for validation — no client-side parsing needed
  try {
    const resp = await configApi.updateRaw(activeFile.value, rawContent.value)
    // If we get here without error, check the response
    if (resp.success === false) {
      validationResult.value = { valid: false, errors: [resp.error || '校验失败'] }
    } else {
      validationResult.value = { valid: true, errors: [] }
    }
  } catch (err: any) {
    const detail = err.response?.data?.error || err.response?.data?.detail || '校验失败'
    validationResult.value = { valid: false, errors: [detail] }
  }
}

async function saveContent() {
  if (!activeFile.value) return
  try {
    const resp = await configApi.updateRaw(activeFile.value, rawContent.value)
    if (resp.success === false) {
      ElMessage.error(resp.error || '配置校验失败，未保存')
      validationResult.value = { valid: false, errors: [resp.error || '校验失败'] }
    } else {
      ElMessage.success('保存成功')
      validationResult.value = null
    }
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '保存失败')
  }
}

async function viewHistory() {
  if (!activeFile.value) return
  history.value = await configApi.getHistory(activeFile.value)
  showHistory.value = true
}

onMounted(fetchFiles)
</script>
