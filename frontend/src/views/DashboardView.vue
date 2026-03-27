<template>
  <div>
    <h2>工作台</h2>

    <!-- Quick stats -->
    <el-row :gutter="20" style="margin-bottom: 24px">
      <el-col :span="6">
        <el-card shadow="hover" body-style="padding: 20px">
          <el-statistic title="总任务数" :value="taskStats.total">
            <template #suffix>
              <el-tag v-if="taskStats.running > 0" type="warning" size="small" style="margin-left: 8px">
                {{ taskStats.running }} 运行中
              </el-tag>
            </template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" body-style="padding: 20px">
          <el-statistic title="已完成" :value="taskStats.completed" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" body-style="padding: 20px">
          <el-statistic title="知识库基因数" :value="kbStats.gene_knowledge?.total_rows || 0" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" body-style="padding: 20px">
          <el-statistic title="药物映射" :value="kbStats.drug_mappings?.total_rows || 0" suffix="条" />
        </el-card>
      </el-col>
    </el-row>

    <!-- Quick actions -->
    <el-row :gutter="20" style="margin-bottom: 24px">
      <el-col :span="8">
        <el-card shadow="hover">
          <template #header>生成报告</template>
          <p style="color: #606266; margin-bottom: 16px">上传 Excel 基因检测结果，自动生成标准化医疗报告</p>
          <el-button type="primary" @click="$router.push('/generate')" style="width: 100%">
            开始生成
          </el-button>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover">
          <template #header>患者信息</template>
          <p style="color: #606266; margin-bottom: 16px">管理患者基本信息，支持按样本编号快速查找和编辑</p>
          <el-button @click="$router.push('/patients')" style="width: 100%">
            管理患者
          </el-button>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover">
          <template #header>知识库</template>
          <p style="color: #606266; margin-bottom: 16px">浏览基因知识库、药物映射和免疫基因分类信息</p>
          <el-button @click="$router.push('/knowledge')" style="width: 100%">
            浏览知识库
          </el-button>
        </el-card>
      </el-col>
    </el-row>

    <!-- Recent tasks -->
    <el-card shadow="hover">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>最近任务</span>
          <el-button text type="primary" @click="$router.push('/tasks')">查看全部</el-button>
        </div>
      </template>
      <el-table :data="recentTasks" stripe size="small" v-loading="loading">
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
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="project_type" label="项目类型" />
        <el-table-column prop="duration_seconds" label="耗时" width="100">
          <template #default="{ row }">
            {{ row.duration_seconds ? row.duration_seconds.toFixed(1) + 's' : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="时间" width="180">
          <template #default="{ row }">
            {{ row.created_at ? new Date(row.created_at).toLocaleString('zh-CN') : '-' }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { taskApi, type TaskItem, type TaskStats } from '@/api/task'
import { knowledgeApi, type KBStats } from '@/api/knowledge'

const taskStats = ref<TaskStats>({ total: 0, completed: 0, failed: 0, running: 0, pending: 0 })
const kbStats = ref<Partial<KBStats>>({})
const recentTasks = ref<TaskItem[]>([])
const loading = ref(false)

function statusType(s: string) {
  return { completed: 'success', failed: 'danger', running: 'warning', pending: 'info' }[s] || 'info'
}
function statusLabel(s: string) {
  return { completed: '已完成', failed: '失败', running: '运行中', pending: '待执行', cancelled: '已取消' }[s] || s
}

onMounted(async () => {
  loading.value = true
  try {
    const [ts, kb, recent] = await Promise.allSettled([
      taskApi.getStats(),
      knowledgeApi.getStats(),
      taskApi.list({ page: 1, page_size: 5 }),
    ])
    if (ts.status === 'fulfilled') taskStats.value = ts.value
    if (kb.status === 'fulfilled') kbStats.value = kb.value
    if (recent.status === 'fulfilled') recentTasks.value = recent.value.items
  } finally {
    loading.value = false
  }
})
</script>
