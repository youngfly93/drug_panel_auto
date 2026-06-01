<template>
  <div class="load-test-page">
    <div class="page-head">
      <div>
        <h2>压测看板</h2>
        <div class="head-subline">
          <span>窗口 {{ windowLabel }}</span>
          <span>更新 {{ formatDate(summary?.generated_at) }}</span>
        </div>
      </div>
      <div class="head-actions">
        <el-select v-model="windowHours" class="window-select" @change="fetchSummary">
          <el-option label="近 24 小时" :value="24" />
          <el-option label="近 72 小时" :value="72" />
          <el-option label="近 7 天" :value="168" />
          <el-option label="近 30 天" :value="720" />
        </el-select>
        <el-button :icon="Refresh" :loading="loading" @click="fetchSummary">刷新</el-button>
      </div>
    </div>

    <el-alert
      v-if="error"
      class="page-alert"
      type="error"
      :closable="false"
      :title="error"
      show-icon
    />

    <section v-loading="loading && !summary" :class="['gate-section', `gate-${gateTone}`]">
      <div class="gate-main">
        <div>
          <el-tag :type="gateTagType" effect="dark">{{ gateLabel }}</el-tag>
          <h3>{{ summary?.gate.title || '压测放行判断' }}</h3>
        </div>
        <div class="gate-metrics">
          <div>
            <span>生成成功率</span>
            <strong>{{ formatPercent(summary?.totals.success_rate) }}</strong>
          </div>
          <div>
            <span>压测文件</span>
            <strong>{{ summary?.totals.units_total ?? '-' }}</strong>
          </div>
          <div>
            <span>P95 耗时</span>
            <strong>{{ formatSeconds(summary?.durations.p95_task_seconds) }}</strong>
          </div>
        </div>
      </div>
      <div class="check-grid">
        <div
          v-for="check in summary?.gate.checks || []"
          :key="check.id"
          :class="['check-item', `check-${check.status}`]"
        >
          <div>
            <strong>{{ check.label }}</strong>
            <span>{{ check.threshold }}</span>
          </div>
          <el-tag :type="checkTagType(check.status)" size="small">{{ check.value }}</el-tag>
        </div>
      </div>
    </section>

    <el-row :gutter="12" class="metric-row">
      <el-col v-for="metric in topMetrics" :key="metric.label" :xs="24" :sm="12" :lg="8" :xl="4">
        <div :class="['metric-tile', `metric-${metric.tone}`]">
          <span>{{ metric.label }}</span>
          <strong>{{ metric.value }}</strong>
          <small>{{ metric.meta }}</small>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :xs="24" :xl="14">
        <section class="dashboard-section">
          <div class="section-head">
            <div>
              <h3>项目表现</h3>
              <span>按项目类型汇总生成成功率与 QA 风险</span>
            </div>
          </div>
          <el-table :data="summary?.project_breakdown || []" size="small" stripe>
            <el-table-column prop="project_type" label="项目" min-width="150" show-overflow-tooltip />
            <el-table-column prop="tasks" label="任务" width="72" align="right" />
            <el-table-column label="文件" width="120" align="right">
              <template #default="{ row }">{{ row.units_completed }}/{{ row.units_total }}</template>
            </el-table-column>
            <el-table-column label="成功率" width="116">
              <template #default="{ row }">
                <div class="progress-cell">
                  <el-progress
                    :percentage="progressPercent(row.success_rate)"
                    :color="successColor(row.success_rate)"
                    :show-text="false"
                  />
                  <span>{{ formatPercent(row.success_rate) }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="units_failed" label="失败" width="72" align="right" />
            <el-table-column label="QA 风险" width="120" align="right">
              <template #default="{ row }">FAIL {{ row.qa_fail }} / WARN {{ row.qa_warn }}</template>
            </el-table-column>
            <el-table-column label="均耗时" width="96">
              <template #default="{ row }">{{ formatSeconds(row.avg_task_seconds) }}</template>
            </el-table-column>
          </el-table>
        </section>
      </el-col>

      <el-col :xs="24" :xl="10">
        <section class="dashboard-section">
          <div class="section-head">
            <div>
              <h3>失败与风险类型</h3>
              <span>错误原文已分类聚合</span>
            </div>
          </div>
          <el-empty v-if="!summary?.failure_reasons.length" description="暂无失败或风险记录" />
          <el-table v-else :data="summary.failure_reasons" size="small" stripe>
            <el-table-column label="级别" width="82">
              <template #default="{ row }">
                <el-tag :type="row.severity === 'error' ? 'danger' : 'warning'" size="small">
                  {{ row.severity === 'error' ? '错误' : '警告' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="reason" label="类型" min-width="150" />
            <el-table-column prop="count" label="次数" width="78" align="right" />
          </el-table>
        </section>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :xs="24" :xl="10">
        <section class="dashboard-section">
          <div class="section-head">
            <div>
              <h3>下载质量</h3>
              <span>仅统计窗口内终态下载事件</span>
            </div>
          </div>
          <div class="download-grid">
            <div>
              <span>完成</span>
              <strong>{{ summary?.downloads.summary.completed ?? '-' }}</strong>
            </div>
            <div>
              <span>慢下载</span>
              <strong>{{ summary?.downloads.summary.slow ?? '-' }}</strong>
            </div>
            <div>
              <span>失败</span>
              <strong>{{ summary?.downloads.summary.failed ?? '-' }}</strong>
            </div>
            <div>
              <span>最大耗时</span>
              <strong>{{ formatMs(summary?.downloads.summary.max_duration_ms) }}</strong>
            </div>
          </div>
          <el-table :data="summary?.downloads.recent_terminal_events || []" size="small" stripe>
            <el-table-column label="任务" width="112">
              <template #default="{ row }">
                <el-button v-if="row.task_id" text type="primary" size="small" @click="openTask(row.task_id)">
                  {{ shortId(row.task_id) }}
                </el-button>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="86">
              <template #default="{ row }">
                <el-tag :type="downloadTagType(row.event_type)" size="small">
                  {{ downloadEventText(row.event_type) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="大小" width="80">
              <template #default="{ row }">{{ formatMb(row.file_size_mb) }}</template>
            </el-table-column>
            <el-table-column label="耗时" width="86">
              <template #default="{ row }">{{ formatMs(row.duration_ms) }}</template>
            </el-table-column>
            <el-table-column label="时间" min-width="138">
              <template #default="{ row }">{{ formatDate(row.timestamp) }}</template>
            </el-table-column>
          </el-table>
        </section>
      </el-col>

      <el-col :xs="24" :xl="14">
        <section class="dashboard-section">
          <div class="section-head">
            <div>
              <h3>最近批量任务</h3>
              <span>批量压测执行明细</span>
            </div>
            <el-button text type="primary" @click="$router.push('/tasks?task_type=batch')">任务队列</el-button>
          </div>
          <el-table :data="summary?.recent_batches || []" size="small" stripe>
            <el-table-column label="任务ID" width="122">
              <template #default="{ row }">
                <el-button text type="primary" size="small" @click="openTask(row.task_id)">
                  {{ shortId(row.task_id) }}
                </el-button>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="98">
              <template #default="{ row }">
                <el-tag :type="taskStatusTagType(row.status)" size="small">
                  {{ taskStatusText(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="project_type" label="项目" min-width="150" show-overflow-tooltip />
            <el-table-column label="完成" width="84" align="right">
              <template #default="{ row }">{{ row.completed_files }}/{{ row.total_files }}</template>
            </el-table-column>
            <el-table-column prop="failed_files" label="失败" width="70" align="right" />
            <el-table-column label="未完成" width="86" align="right">
              <template #default="{ row }">{{ row.pending_files + row.running_files }}</template>
            </el-table-column>
            <el-table-column label="耗时" width="92">
              <template #default="{ row }">{{ formatSeconds(row.duration_seconds) }}</template>
            </el-table-column>
            <el-table-column label="创建时间" min-width="148">
              <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
            </el-table-column>
          </el-table>
        </section>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Refresh } from '@element-plus/icons-vue'
import { opsApi, type LoadTestSummaryPayload } from '@/api/ops'

const router = useRouter()
const loading = ref(false)
const error = ref('')
const windowHours = ref(168)
const summary = ref<LoadTestSummaryPayload | null>(null)

const windowLabel = computed(() => {
  if (windowHours.value === 24) return '近 24 小时'
  if (windowHours.value === 72) return '近 72 小时'
  if (windowHours.value === 720) return '近 30 天'
  return '近 7 天'
})

const gateTone = computed(() => summary.value?.gate.status || 'unknown')
const gateLabel = computed(() => {
  if (gateTone.value === 'pass') return '通过'
  if (gateTone.value === 'block') return '阻塞'
  if (gateTone.value === 'warning') return '需确认'
  return '待统计'
})
const gateTagType = computed(() => {
  if (gateTone.value === 'pass') return 'success'
  if (gateTone.value === 'block') return 'danger'
  return 'warning'
})

const topMetrics = computed(() => {
  const totals = summary.value?.totals
  const qa = summary.value?.qa
  const downloads = summary.value?.downloads.summary
  const durations = summary.value?.durations
  return [
    {
      label: '压测任务',
      value: totals ? `${totals.tasks_total}` : '-',
      meta: totals ? `批量 ${totals.batch_tasks} / 单份 ${totals.single_tasks}` : '-',
      tone: 'neutral',
    },
    {
      label: '生成文件',
      value: totals ? `${totals.units_completed}/${totals.units_total}` : '-',
      meta: totals ? `失败 ${totals.units_failed}，未完成 ${totals.units_pending + totals.units_running}` : '-',
      tone: (totals?.units_failed || 0) > 0 ? 'danger' : 'neutral',
    },
    {
      label: '生成成功率',
      value: formatPercent(totals?.success_rate),
      meta: `完成率 ${formatPercent(totals?.completion_rate)}`,
      tone: rateTone(totals?.success_rate),
    },
    {
      label: 'QA 风险',
      value: qa ? `FAIL ${qa.fail} / WARN ${qa.warn}` : '-',
      meta: qa ? `PASS ${qa.pass}，缺失 ${qa.missing}` : '-',
      tone: (qa?.fail || 0) > 0 ? 'danger' : (qa?.warn || 0) > 0 ? 'warning' : 'neutral',
    },
    {
      label: '耗时',
      value: formatSeconds(durations?.p95_task_seconds),
      meta: `平均 ${formatSeconds(durations?.avg_task_seconds)}`,
      tone: (durations?.p95_task_seconds || 0) > 900 ? 'warning' : 'neutral',
    },
    {
      label: '下载',
      value: downloads ? `慢 ${downloads.slow} / 失败 ${downloads.failed}` : '-',
      meta: downloads ? `完成 ${downloads.completed}，最大 ${formatMs(downloads.max_duration_ms)}` : '-',
      tone: (downloads?.failed || 0) > 0 ? 'danger' : (downloads?.slow || 0) > 0 ? 'warning' : 'neutral',
    },
  ]
})

async function fetchSummary() {
  loading.value = true
  error.value = ''
  try {
    summary.value = await opsApi.getLoadTestSummary({
      window_hours: windowHours.value,
      recent_batch_limit: 12,
    })
  } catch (err: any) {
    error.value = err?.response?.data?.message || err?.message || '压测数据加载失败'
  } finally {
    loading.value = false
  }
}

function openTask(taskId: string) {
  router.push(`/tasks/${taskId}`)
}

function formatPercent(value?: number | null) {
  return typeof value === 'number' ? `${value.toFixed(2)}%` : '-'
}

function progressPercent(value?: number | null) {
  if (typeof value !== 'number') return 0
  return Math.max(0, Math.min(100, Number(value.toFixed(2))))
}

function rateTone(value?: number | null) {
  if (typeof value !== 'number') return 'neutral'
  if (value < 95) return 'danger'
  if (value < 98) return 'warning'
  return 'neutral'
}

function successColor(value?: number | null) {
  if (typeof value !== 'number') return '#909399'
  if (value < 95) return '#c34031'
  if (value < 98) return '#b7791f'
  return '#23715b'
}

function formatSeconds(value?: number | null) {
  if (typeof value !== 'number') return '-'
  if (value < 60) return `${value.toFixed(1)}s`
  return `${(value / 60).toFixed(1)}min`
}

function formatMs(value?: number | null) {
  if (typeof value !== 'number') return '-'
  if (value < 1000) return `${value.toFixed(0)}ms`
  return `${(value / 1000).toFixed(1)}s`
}

function formatMb(value?: number | null) {
  if (typeof value !== 'number') return '-'
  if (value < 1) return `${(value * 1024).toFixed(0)}KB`
  return `${value.toFixed(1)}MB`
}

function formatDate(value?: string | null) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

function shortId(value?: string | null) {
  return value ? value.slice(0, 8) : '-'
}

function checkTagType(status: string) {
  if (status === 'pass') return 'success'
  if (status === 'block') return 'danger'
  return 'warning'
}

function taskStatusText(status: string) {
  const map: Record<string, string> = {
    pending: '等待',
    running: '运行中',
    completed: '完成',
    failed: '失败',
    partial_failed: '部分失败',
    cancelled: '已取消',
  }
  return map[status] || status
}

function taskStatusTagType(status: string) {
  if (status === 'completed') return 'success'
  if (status === 'running') return 'primary'
  if (status === 'failed' || status === 'partial_failed') return 'danger'
  if (status === 'cancelled') return 'info'
  return 'warning'
}

function downloadEventText(eventType: string) {
  if (eventType === 'report_download_completed') return '完成'
  if (eventType === 'report_download_slow') return '慢'
  if (eventType === 'report_download_failed') return '失败'
  return eventType
}

function downloadTagType(eventType: string) {
  if (eventType === 'report_download_completed') return 'success'
  if (eventType === 'report_download_failed') return 'danger'
  return 'warning'
}

onMounted(fetchSummary)
</script>

<style scoped>
.load-test-page {
  padding: 24px;
  background: #f5f7f8;
  min-height: 100%;
}

.page-head,
.gate-section,
.dashboard-section,
.metric-tile {
  background: #fff;
  border: 1px solid #dfe5eb;
  border-radius: 6px;
}

.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px;
  margin-bottom: 14px;
}

.page-head h2,
.gate-section h3,
.section-head h3 {
  margin: 0;
  color: #1f2933;
  letter-spacing: 0;
}

.page-head h2 {
  font-size: 22px;
}

.head-subline,
.section-head span,
.metric-tile span,
.metric-tile small,
.check-item span,
.gate-metrics span,
.download-grid span {
  color: #697783;
}

.head-subline {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 6px;
  font-size: 13px;
}

.head-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.window-select {
  width: 140px;
}

.page-alert {
  margin-bottom: 14px;
}

.gate-section {
  padding: 18px 20px;
  margin-bottom: 14px;
  border-left-width: 4px;
}

.gate-pass {
  border-left-color: #23715b;
}

.gate-warning {
  border-left-color: #b7791f;
}

.gate-block {
  border-left-color: #c34031;
}

.gate-main {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.gate-main h3 {
  margin-top: 10px;
  font-size: 20px;
}

.gate-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(120px, 1fr));
  gap: 10px;
  min-width: 420px;
}

.gate-metrics div,
.download-grid div {
  border: 1px solid #e6ebf0;
  border-radius: 6px;
  padding: 10px 12px;
  background: #f9fafb;
}

.gate-metrics span,
.download-grid span {
  display: block;
  font-size: 12px;
}

.gate-metrics strong,
.download-grid strong {
  display: block;
  margin-top: 4px;
  font-size: 18px;
  color: #1f2933;
}

.check-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.check-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  border: 1px solid #e6ebf0;
  border-radius: 6px;
  padding: 10px 12px;
  background: #fff;
}

.check-item strong {
  display: block;
  color: #1f2933;
}

.check-item span {
  display: block;
  margin-top: 2px;
  font-size: 12px;
}

.check-block {
  background: #fff7f5;
  border-color: #f0c4bc;
}

.check-warning {
  background: #fffaf0;
  border-color: #eed7a6;
}

.metric-row {
  margin-bottom: 16px;
}

.metric-tile {
  padding: 14px 16px;
  min-height: 104px;
  margin-bottom: 12px;
}

.metric-tile span,
.metric-tile small {
  display: block;
}

.metric-tile strong {
  display: block;
  margin: 8px 0 6px;
  font-size: 24px;
  color: #1f2933;
}

.metric-warning {
  border-color: #e3c278;
}

.metric-danger {
  border-color: #e5aaa0;
}

.dashboard-section {
  padding: 16px;
  margin-bottom: 16px;
}

.section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.section-head h3 {
  font-size: 16px;
}

.section-head span {
  display: block;
  margin-top: 4px;
  font-size: 12px;
}

.progress-cell {
  display: grid;
  grid-template-columns: minmax(56px, 1fr) 56px;
  gap: 8px;
  align-items: center;
}

.download-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}

@media (max-width: 960px) {
  .load-test-page {
    padding: 14px;
  }

  .page-head,
  .gate-main {
    flex-direction: column;
    align-items: stretch;
  }

  .head-actions {
    justify-content: flex-start;
  }

  .gate-metrics,
  .check-grid,
  .download-grid {
    grid-template-columns: 1fr;
    min-width: 0;
  }
}
</style>
