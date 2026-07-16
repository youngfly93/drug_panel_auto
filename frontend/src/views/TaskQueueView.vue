<template>
  <div class="task-queue">
    <div class="queue-head">
      <div>
        <h2>任务队列</h2>
        <p>按生产处理口径筛选生成任务，优先处理失败、QA 风险和未复核任务。</p>
      </div>
      <div class="head-actions">
        <el-button :icon="Refresh" :loading="loading" @click="fetchTasks">刷新</el-button>
        <el-button type="primary" @click="$router.push('/generate')">生成报告</el-button>
      </div>
    </div>

    <div class="stat-grid">
      <button
        v-for="card in statCards"
        :key="card.label"
        :class="['stat-card', card.tone, { active: card.active }]"
        type="button"
        @click="applyStatCard(card.action)"
      >
        <span>{{ card.label }}</span>
        <strong>{{ card.value }}</strong>
        <em>{{ card.detail }}</em>
      </button>
    </div>

    <section class="filter-panel">
      <div class="quick-row">
        <el-radio-group v-model="quickFilter" size="large">
          <el-radio-button label="all">全部</el-radio-button>
          <el-radio-button label="today">今日任务</el-radio-button>
          <el-radio-button label="attention">失败待处理</el-radio-button>
          <el-radio-button label="awaiting_review">待复核</el-radio-button>
          <el-radio-button label="delivered">已交付</el-radio-button>
        </el-radio-group>
        <div class="quick-meta">
          当前显示：{{ quickFilterLabel }}
        </div>
      </div>

      <div class="filter-grid">
        <el-input
          v-model="searchQuery"
          placeholder="搜索任务ID、项目类型、错误说明"
          clearable
          :prefix-icon="Search"
          @clear="applySearch"
          @keyup.enter="applySearch"
        >
          <template #append>
            <el-button @click="applySearch">搜索</el-button>
          </template>
        </el-input>

        <el-select v-model="taskTypeFilter" placeholder="任务类型" clearable>
          <el-option label="单份" value="single" />
          <el-option label="批量" value="batch" />
        </el-select>

        <el-select v-model="projectTypeFilter" placeholder="项目类型" clearable filterable>
          <el-option
            v-for="option in projectOptions"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>

        <el-select v-model="statusFilter" placeholder="任务状态" clearable :disabled="locksWorkflowFilters">
          <el-option label="运行中" value="running" />
          <el-option label="已排队" value="queued" />
          <el-option label="预检中" value="preflight" />
          <el-option label="生成中" value="generating" />
          <el-option label="质控中" value="qa" />
          <el-option label="已完成" value="completed" />
          <el-option label="部分失败" value="partial_failed" />
          <el-option label="失败" value="failed" />
          <el-option label="待执行" value="pending" />
          <el-option label="已取消" value="cancelled" />
        </el-select>

        <el-select v-model="qaStatusFilter" placeholder="QA 状态" clearable :disabled="locksWorkflowFilters">
          <el-option label="PASS" value="PASS" />
          <el-option label="WARN" value="WARN" />
          <el-option label="FAIL" value="FAIL" />
          <el-option label="SKIP" value="SKIP" />
        </el-select>

        <el-select v-model="reviewStatusFilter" placeholder="复核状态" clearable :disabled="locksWorkflowFilters">
          <el-option label="待审核" value="draft" />
          <el-option label="已审核" value="reviewed" />
          <el-option label="已交付" value="delivered" />
          <el-option label="退回修改" value="rejected" />
        </el-select>

        <el-button :icon="Close" @click="resetFilters">清空筛选</el-button>
      </div>
    </section>

    <el-table
      :data="tasks"
      stripe
      border
      v-loading="loading"
      class="task-table"
      empty-text="暂无任务"
    >
      <el-table-column label="任务" min-width="220" fixed>
        <template #default="{ row }">
          <div class="task-id-cell">
            <strong>{{ shortTaskId(row.id) }}</strong>
            <span>{{ formatTime(row.created_at) }}</span>
          </div>
        </template>
      </el-table-column>

      <el-table-column prop="task_type" label="类型" width="84">
        <template #default="{ row }">
          <el-tag :type="row.task_type === 'batch' ? 'warning' : 'primary'" size="small">
            {{ row.task_type === 'batch' ? '批量' : '单份' }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column prop="status" label="任务状态" width="105">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small">
            {{ statusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column prop="project_type" label="项目类型" min-width="150" show-overflow-tooltip>
        <template #default="{ row }">
          {{ projectLabel(row.project_type) }}
        </template>
      </el-table-column>

      <el-table-column label="生产状态" min-width="210">
        <template #default="{ row }">
          <div class="production-tags">
            <el-tag v-if="row.qa_status" :type="qaTagType(row.qa_status)" size="small">
              QA {{ row.qa_status }}
            </el-tag>
            <el-tag v-if="row.diff_status" :type="diffTagType(row)" size="small">
              Diff {{ row.diff_status }}
            </el-tag>
            <el-tag :type="reviewStatusTagType(row.review_status)" size="small">
              {{ row.review_status_label || reviewStatusLabel(row.review_status) }}
            </el-tag>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="进度" width="150">
        <template #default="{ row }">
          <div v-if="row.task_type === 'batch'" class="batch-progress-cell">
            <el-progress
              :percentage="batchProgress(row)"
              :status="row.status === 'failed' || row.status === 'partial_failed' ? 'exception' : row.status === 'completed' ? 'success' : undefined"
              :show-text="false"
            />
            <span>
              {{ row.completed_files }}/{{ row.total_files }}
              <em v-if="row.failed_files > 0">{{ row.failed_files }}失败</em>
              <em v-if="(row.cancelled_files || 0) > 0">{{ row.cancelled_files }}取消</em>
            </span>
          </div>
          <span v-else>-</span>
        </template>
      </el-table-column>

      <el-table-column label="处理提示" min-width="240" show-overflow-tooltip>
        <template #default="{ row }">
          <div v-if="attentionReasons(row).length" class="attention-cell">
            <el-icon><WarningFilled /></el-icon>
            <span>{{ attentionReasons(row).join('；') }}</span>
          </div>
          <span v-else class="muted">暂无风险</span>
        </template>
      </el-table-column>

      <el-table-column prop="duration_seconds" label="耗时" width="96">
        <template #default="{ row }">
          {{ row.duration_seconds ? row.duration_seconds.toFixed(1) + 's' : '-' }}
        </template>
      </el-table-column>

      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button
            text
            type="primary"
            size="small"
            :icon="View"
            @click="openDetail(row.id)"
          >详情</el-button>
          <el-button
            v-if="row.status === 'completed' && row.task_type === 'single'"
            text
            type="primary"
            size="small"
            :icon="Download"
            :loading="Boolean(downloadingTasks[row.id])"
            @click="downloadReport(row.id)"
          >{{ downloadingTasks[row.id] ? '下载中' : '下载' }}</el-button>
          <el-popconfirm
            v-if="isActiveTaskStatus(row.status)"
            title="确认取消当前任务？"
            @confirm="cancelTask(row.id)"
          >
            <template #reference>
              <el-button text type="danger" size="small">取消</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <div class="table-footer">
      <span>共 {{ total }} 条</span>
      <el-pagination
        v-if="total > pageSize"
        :current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="prev, pager, next"
        @current-change="handlePageChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Close,
  Download,
  Refresh,
  Search,
  View,
  WarningFilled,
} from '@element-plus/icons-vue'
import { taskApi, type TaskItem, type TaskStats } from '@/api/task'
import { reportApi } from '@/api/report'

type QuickFilter = 'all' | 'today' | 'attention' | 'awaiting_review' | 'delivered'

const router = useRouter()
const tasks = ref<TaskItem[]>([])
const stats = ref<TaskStats>({
  total: 0,
  completed: 0,
  failed: 0,
  running: 0,
  pending: 0,
  today_total: 0,
  needs_attention: 0,
  awaiting_review: 0,
  delivered: 0,
})
const loading = ref(false)
const downloadingTasks = ref<Record<string, boolean>>({})
const quickFilter = ref<QuickFilter>('all')
const searchQuery = ref('')
const appliedSearch = ref('')
const statusFilter = ref('')
const taskTypeFilter = ref('')
const projectTypeFilter = ref('')
const qaStatusFilter = ref('')
const reviewStatusFilter = ref('')
const page = ref(1)
const pageSize = 20
const total = ref(0)

const projectOptions = [
  { label: '结直肠癌301基因+MSI', value: 'crc_301_msi' },
  { label: '结直肠癌358基因+MSI', value: 'crc_358_msi' },
  { label: '肺癌329基因+PD-L1', value: 'lung_329_pdl1' },
  { label: '子宫内膜癌29基因', value: 'endometrial_29' },
  { label: '肺癌甲基化', value: 'lung_methylation' },
  { label: 'MLF基因检测', value: 'mlf_result' },
]

const quickFilterLabels: Record<QuickFilter, string> = {
  all: '全部任务',
  today: '今日创建任务',
  attention: '失败、QA 风险、Diff 阻断或退回任务',
  awaiting_review: '已完成但仍待审核的任务',
  delivered: '已标记交付的任务',
}

const quickFilterLabel = computed(() => quickFilterLabels[quickFilter.value])
const locksWorkflowFilters = computed(() => ['attention', 'awaiting_review', 'delivered'].includes(quickFilter.value))

const statCards = computed(() => [
  {
    label: '今日任务',
    value: stats.value.today_total || 0,
    detail: '当天上传/生成',
    tone: 'neutral',
    active: quickFilter.value === 'today',
    action: { quick: 'today' as QuickFilter },
  },
  {
    label: '运行中',
    value: stats.value.running || 0,
    detail: `${stats.value.pending || 0} 个待执行`,
    tone: 'working',
    active: quickFilter.value === 'all' && statusFilter.value === 'running',
    action: { quick: 'all' as QuickFilter, status: 'running' },
  },
  {
    label: '失败待处理',
    value: stats.value.needs_attention || 0,
    detail: '失败/警告/退回',
    tone: 'danger',
    active: quickFilter.value === 'attention',
    action: { quick: 'attention' as QuickFilter },
  },
  {
    label: '待复核',
    value: stats.value.awaiting_review || 0,
    detail: '完成后未审核',
    tone: 'warning',
    active: quickFilter.value === 'awaiting_review',
    action: { quick: 'awaiting_review' as QuickFilter },
  },
  {
    label: '已交付',
    value: stats.value.delivered || 0,
    detail: '生产闭环任务',
    tone: 'success',
    active: quickFilter.value === 'delivered',
    action: { quick: 'delivered' as QuickFilter },
  },
])

function statusTagType(status: string) {
  const map: Record<string, string> = {
    completed: 'success',
    partial_failed: 'danger',
    failed: 'danger',
    queued: 'info',
    preflight: 'warning',
    generating: 'warning',
    qa: 'warning',
    running: 'warning',
    pending: 'info',
    cancelled: 'info',
  }
  return map[status] || 'info'
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    completed: '已完成',
    partial_failed: '部分失败',
    failed: '失败',
    queued: '已排队',
    preflight: '预检中',
    generating: '生成中',
    qa: '质控中',
    running: '运行中',
    pending: '待执行',
    cancelled: '已取消',
  }
  return map[status] || status
}

function isActiveTaskStatus(status?: string | null) {
  return Boolean(
    status
    && ['queued', 'preflight', 'generating', 'qa', 'pending', 'running'].includes(status),
  )
}

function qaTagType(status?: string | null) {
  const map: Record<string, string> = {
    PASS: 'success',
    WARN: 'warning',
    FAIL: 'danger',
    SKIP: 'info',
  }
  return map[status || ''] || 'info'
}

function diffTagType(row: TaskItem) {
  if (row.diff_gate_passed === false) return 'danger'
  return qaTagType(row.diff_status)
}

function reviewStatusLabel(status?: string | null) {
  const map: Record<string, string> = {
    draft: '待审核',
    reviewed: '已审核',
    delivered: '已交付',
    rejected: '退回修改',
  }
  return map[status || 'draft'] || status || '待审核'
}

function reviewStatusTagType(status?: string | null) {
  const map: Record<string, string> = {
    draft: 'info',
    reviewed: 'success',
    delivered: 'primary',
    rejected: 'danger',
  }
  return map[status || 'draft'] || 'info'
}

function batchProgress(row: TaskItem) {
  if (!row.total_files) return 0
  const done = (row.completed_files || 0) + (row.failed_files || 0) + (row.cancelled_files || 0)
  return Math.min(100, Math.round((done / row.total_files) * 100))
}

function attentionReasons(row: TaskItem) {
  const reasons: string[] = []
  if (row.status === 'failed') reasons.push('生成失败')
  if (row.status === 'partial_failed') reasons.push(`${row.failed_files || 0} 个文件失败`)
  if (row.status === 'cancelled') reasons.push('任务已取消')
  if (row.qa_status === 'FAIL') reasons.push('QA 未通过')
  if (row.qa_status === 'WARN') reasons.push('QA 警告')
  if (row.diff_gate_passed === false) reasons.push('Diff 门禁阻断')
  if (row.review_status === 'rejected') reasons.push('复核退回')
  if (row.errors?.length) reasons.push(row.errors[0])
  return reasons.slice(0, 3)
}

function projectLabel(value?: string | null) {
  if (!value) return '-'
  return projectOptions.find((option) => option.value === value)?.label || value
}

function shortTaskId(value: string) {
  return value.length > 18 ? `${value.slice(0, 8)}...${value.slice(-6)}` : value
}

function formatTime(value?: string | null) {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN')
}

function todayStartIso() {
  const date = new Date()
  date.setHours(0, 0, 0, 0)
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T00:00:00`
}

function buildListParams() {
  const params: Record<string, any> = {
    page: page.value,
    page_size: pageSize,
  }
  if (appliedSearch.value.trim()) params.q = appliedSearch.value.trim()
  if (taskTypeFilter.value) params.task_type = taskTypeFilter.value
  if (projectTypeFilter.value) params.project_type = projectTypeFilter.value

  if (quickFilter.value === 'today') {
    params.created_from = todayStartIso()
  } else if (quickFilter.value === 'attention') {
    params.attention = true
  } else if (quickFilter.value === 'awaiting_review') {
    params.status = 'completed'
    params.review_status = 'draft'
  } else if (quickFilter.value === 'delivered') {
    params.review_status = 'delivered'
  }

  if (!locksWorkflowFilters.value) {
    if (statusFilter.value) params.status = statusFilter.value
    if (qaStatusFilter.value) params.qa_status = qaStatusFilter.value
    if (reviewStatusFilter.value) params.review_status = reviewStatusFilter.value
  }
  return params
}

async function fetchTasks() {
  loading.value = true
  try {
    const [taskList, taskStats] = await Promise.all([
      taskApi.list(buildListParams()),
      taskApi.getStats(),
    ])
    tasks.value = taskList.items
    total.value = taskList.total
    stats.value = taskStats
  } finally {
    loading.value = false
  }
}

function applySearch() {
  appliedSearch.value = searchQuery.value
  page.value = 1
  fetchTasks()
}

function applyStatCard(action: { quick: QuickFilter; status?: string }) {
  quickFilter.value = action.quick
  statusFilter.value = action.status || ''
  page.value = 1
  fetchTasks()
}

function resetFilters() {
  quickFilter.value = 'all'
  searchQuery.value = ''
  appliedSearch.value = ''
  statusFilter.value = ''
  taskTypeFilter.value = ''
  projectTypeFilter.value = ''
  qaStatusFilter.value = ''
  reviewStatusFilter.value = ''
  page.value = 1
  fetchTasks()
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

async function downloadReport(taskId: string) {
  downloadingTasks.value[taskId] = true
  try {
    await reportApi.download(taskId)
    ElMessage.success('报告下载完成')
  } catch (err: any) {
    ElMessage.error(err.message || '报告下载失败')
  } finally {
    downloadingTasks.value[taskId] = false
  }
}

function openDetail(taskId: string) {
  router.push(`/tasks/${taskId}`)
}

watch(
  [quickFilter, statusFilter, taskTypeFilter, projectTypeFilter, qaStatusFilter, reviewStatusFilter],
  () => {
    page.value = 1
    fetchTasks()
  },
)

onMounted(fetchTasks)
</script>

<style scoped>
.task-queue {
  display: grid;
  gap: 16px;
}

.queue-head,
.head-actions,
.quick-row,
.table-footer {
  display: flex;
  align-items: center;
}

.queue-head {
  justify-content: space-between;
  gap: 16px;
}

.queue-head h2 {
  margin: 0;
}

.queue-head p {
  margin: 6px 0 0;
  color: #667085;
  font-size: 13px;
}

.head-actions {
  gap: 8px;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(128px, 1fr));
  gap: 10px;
}

.stat-card {
  min-height: 92px;
  padding: 14px;
  border: 1px solid #d9e2ec;
  background: #fff;
  text-align: left;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 6px;
}

.stat-card span,
.stat-card em,
.quick-meta,
.muted {
  color: #667085;
  font-size: 12px;
}

.stat-card strong {
  color: #1f2937;
  font-size: 24px;
  line-height: 1;
}

.stat-card em {
  font-style: normal;
}

.stat-card.active {
  border-color: #409eff;
  box-shadow: inset 0 0 0 1px #409eff;
}

.stat-card.working strong,
.stat-card.warning strong {
  color: #b7791f;
}

.stat-card.danger strong {
  color: #c2410c;
}

.stat-card.success strong {
  color: #047857;
}

.filter-panel {
  border: 1px solid #d9e2ec;
  background: #fbfcfe;
  padding: 12px;
  display: grid;
  gap: 12px;
}

.quick-row {
  justify-content: space-between;
  gap: 12px;
}

.filter-grid {
  display: grid;
  grid-template-columns: minmax(260px, 1.5fr) repeat(5, minmax(130px, 1fr)) 110px;
  gap: 10px;
}

.task-table {
  width: 100%;
}

.task-id-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.task-id-cell strong {
  color: #1f2937;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
}

.task-id-cell span {
  color: #667085;
  font-size: 12px;
}

.production-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.batch-progress-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.batch-progress-cell span {
  color: #667085;
  font-size: 12px;
}

.batch-progress-cell em {
  color: #f56c6c;
  font-style: normal;
  margin-left: 4px;
}

.attention-cell {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #c2410c;
  font-size: 13px;
}

.table-footer {
  justify-content: space-between;
  color: #667085;
  font-size: 13px;
}

@media (max-width: 1180px) {
  .stat-grid,
  .filter-grid {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 760px) {
  .queue-head,
  .quick-row,
  .table-footer {
    align-items: stretch;
    flex-direction: column;
  }

  .stat-grid,
  .filter-grid {
    grid-template-columns: 1fr;
  }
}
</style>
