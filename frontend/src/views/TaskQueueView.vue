<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px">
      <h2 style="margin: 0">任务队列</h2>
      <div style="display: flex; gap: 8px">
        <el-select v-model="statusFilter" placeholder="状态筛选" clearable style="width: 140px">
          <el-option label="全部" value="" />
          <el-option label="运行中" value="running" />
          <el-option label="已完成" value="completed" />
          <el-option label="失败" value="failed" />
          <el-option label="待执行" value="pending" />
        </el-select>
        <el-button @click="fetchTasks">刷新</el-button>
      </div>
    </div>

    <!-- Stats cards -->
    <el-row :gutter="16" style="margin-bottom: 20px">
      <el-col :span="6" v-for="(stat, label) in statCards" :key="label">
        <el-card shadow="hover" body-style="padding: 16px">
          <el-statistic :title="label" :value="stat" />
        </el-card>
      </el-col>
    </el-row>

    <!-- Task table -->
    <el-table :data="tasks" stripe border v-loading="loading">
      <el-table-column prop="id" label="任务ID" width="140" show-overflow-tooltip />
      <el-table-column prop="task_type" label="类型" width="80">
        <template #default="{ row }">
          <el-tag :type="row.task_type === 'batch' ? 'warning' : 'primary'" size="small">
            {{ row.task_type === 'batch' ? '批量' : '单份' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small">
            {{ statusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="project_type" label="项目类型" width="160" />
      <el-table-column label="进度" width="120">
        <template #default="{ row }">
          <span v-if="row.task_type === 'batch'">
            {{ row.completed_files }}/{{ row.total_files }}
            <span v-if="row.failed_files > 0" style="color: #f56c6c"> ({{ row.failed_files }}失败)</span>
          </span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="duration_seconds" label="耗时" width="100">
        <template #default="{ row }">
          {{ row.duration_seconds ? row.duration_seconds.toFixed(1) + 's' : '-' }}
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="180">
        <template #default="{ row }">
          {{ row.created_at ? new Date(row.created_at).toLocaleString('zh-CN') : '-' }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="row.status === 'completed' && row.task_type === 'single'"
            text type="primary" size="small"
            @click="downloadReport(row.id)"
          >下载</el-button>
          <el-popconfirm
            v-if="row.status === 'running' || row.status === 'pending'"
            title="确认取消?"
            @confirm="cancelTask(row.id)"
          >
            <template #reference>
              <el-button text type="danger" size="small">取消</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-if="total > pageSize"
      :current-page="page"
      :page-size="pageSize"
      :total="total"
      layout="prev, pager, next, total"
      style="margin-top: 16px; justify-content: flex-end"
      @current-change="handlePageChange"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { taskApi, type TaskItem, type TaskStats } from '@/api/task'
import { reportApi } from '@/api/report'

const tasks = ref<TaskItem[]>([])
const stats = ref<TaskStats>({ total: 0, completed: 0, failed: 0, running: 0, pending: 0 })
const loading = ref(false)
const statusFilter = ref('')
const page = ref(1)
const pageSize = 20
const total = ref(0)

const statCards = computed(() => ({
  '总任务': stats.value.total,
  '运行中': stats.value.running,
  '已完成': stats.value.completed,
  '失败': stats.value.failed,
}))

function statusTagType(status: string) {
  const map: Record<string, string> = {
    completed: 'success', failed: 'danger', running: 'warning',
    pending: 'info', cancelled: 'info',
  }
  return map[status] || 'info'
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    completed: '已完成', failed: '失败', running: '运行中',
    pending: '待执行', cancelled: '已取消',
  }
  return map[status] || status
}

async function fetchTasks() {
  loading.value = true
  try {
    const [taskList, taskStats] = await Promise.all([
      taskApi.list({ status: statusFilter.value || undefined, page: page.value, page_size: pageSize }),
      taskApi.getStats(),
    ])
    tasks.value = taskList.items
    total.value = taskList.total
    stats.value = taskStats
  } finally {
    loading.value = false
  }
}

function handlePageChange(newPage: number) {
  page.value = newPage
  fetchTasks()
}

async function cancelTask(taskId: string) {
  try {
    await taskApi.cancel(taskId)
    ElMessage.success('任务已取消')
    await fetchTasks()
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '取消失败')
  }
}

function downloadReport(taskId: string) {
  window.open(reportApi.getDownloadUrl(taskId), '_blank')
}

watch(statusFilter, () => { page.value = 1; fetchTasks() })
onMounted(fetchTasks)
</script>
