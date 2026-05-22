<template>
  <div class="reference-page">
    <div class="page-head">
      <div>
        <h2>基准报告库</h2>
        <p>按 panel 和 case 维护可自动命中的正确报告。</p>
      </div>
      <el-button :icon="Refresh" @click="fetchReferences">刷新</el-button>
    </div>

    <section class="reference-panel">
      <div class="panel-title">新增基准报告</div>
      <el-form class="upload-form" label-width="92px">
        <el-form-item label="Panel ID" required>
          <el-select v-model="form.panel_id" filterable allow-create placeholder="选择或输入 panel">
            <el-option label="crc_358_msi" value="crc_358_msi" />
            <el-option label="crc_301_msi" value="crc_301_msi" />
            <el-option label="mlf_result" value="mlf_result" />
            <el-option label="lung_methylation" value="lung_methylation" />
          </el-select>
        </el-form-item>
        <el-form-item label="Case ID" required>
          <el-input v-model="form.case_id" placeholder="通常填写样本编号" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="便于识别的名称" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.active" />
        </el-form-item>
        <el-form-item label="备注" class="notes-item">
          <el-input v-model="form.notes" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="DOCX" required class="file-item">
          <el-upload
            v-model:file-list="fileList"
            accept=".docx"
            :auto-upload="false"
            :limit="1"
            :on-change="handleFileChange"
            :on-remove="clearFile"
          >
            <el-button :icon="UploadFilled">选择正确报告</el-button>
          </el-upload>
        </el-form-item>
        <el-form-item class="submit-item">
          <el-button type="primary" :loading="uploading" @click="submitReference">
            保存基准
          </el-button>
        </el-form-item>
      </el-form>
    </section>

    <section class="reference-panel section-gap">
      <div class="table-toolbar">
        <div class="panel-title plain">基准列表</div>
        <div class="filters">
          <el-input v-model="filters.panel_id" clearable placeholder="Panel ID" />
          <el-input v-model="filters.case_id" clearable placeholder="Case ID" />
          <el-button @click="fetchReferences">筛选</el-button>
        </div>
      </div>
      <el-table :data="references" border stripe v-loading="loading">
        <el-table-column prop="panel_id" label="Panel" width="150" />
        <el-table-column prop="case_id" label="Case" width="150" />
        <el-table-column prop="name" label="名称" min-width="180" show-overflow-tooltip />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.active ? 'success' : 'info'" size="small">
              {{ row.active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="original_filename" label="文件" min-width="210" show-overflow-tooltip />
        <el-table-column label="校验值" width="120">
          <template #default="{ row }">
            <span class="mono">{{ row.checksum_sha256.slice(0, 10) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">
            {{ row.created_at ? new Date(row.created_at).toLocaleString('zh-CN') : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="downloadReference(row.id)">
              下载
            </el-button>
            <el-button
              v-if="!row.active"
              text
              type="primary"
              size="small"
              @click="activateReference(row.id)"
            >
              启用
            </el-button>
            <el-popconfirm title="确认删除该基准报告?" @confirm="deleteReference(row.id)">
              <template #reference>
                <el-button text type="danger" size="small">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { Refresh, UploadFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { referenceApi, type ReferenceReport } from '@/api/reference'

const references = ref<ReferenceReport[]>([])
const loading = ref(false)
const uploading = ref(false)
const referenceFile = ref<File | null>(null)
const fileList = ref<any[]>([])

const filters = reactive({
  panel_id: '',
  case_id: '',
})

const form = reactive({
  panel_id: 'crc_358_msi',
  case_id: '',
  name: '',
  notes: '',
  active: true,
})

async function fetchReferences() {
  loading.value = true
  try {
    const data = await referenceApi.list({
      panel_id: filters.panel_id || undefined,
      case_id: filters.case_id || undefined,
    })
    references.value = data.items
  } finally {
    loading.value = false
  }
}

function handleFileChange(file: any) {
  referenceFile.value = file.raw || null
  fileList.value = [file]
}

function clearFile() {
  referenceFile.value = null
  fileList.value = []
}

async function submitReference() {
  if (!form.panel_id || !form.case_id || !referenceFile.value) {
    ElMessage.warning('请填写 Panel ID、Case ID 并选择 DOCX')
    return
  }
  uploading.value = true
  try {
    await referenceApi.upload({
      panel_id: form.panel_id,
      case_id: form.case_id,
      name: form.name,
      notes: form.notes,
      active: form.active,
      file: referenceFile.value,
    })
    ElMessage.success('基准报告已保存')
    form.case_id = ''
    form.name = ''
    form.notes = ''
    clearFile()
    await fetchReferences()
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '基准报告保存失败')
  } finally {
    uploading.value = false
  }
}

async function activateReference(referenceId: string) {
  await referenceApi.activate(referenceId)
  ElMessage.success('基准报告已启用')
  await fetchReferences()
}

async function deleteReference(referenceId: string) {
  await referenceApi.delete(referenceId)
  ElMessage.success('基准报告已删除')
  await fetchReferences()
}

function downloadReference(referenceId: string) {
  window.open(referenceApi.getDownloadUrl(referenceId), '_blank')
}

onMounted(fetchReferences)
</script>

<style scoped>
.reference-page {
  color: #1f2933;
}

.page-head,
.table-toolbar,
.filters {
  display: flex;
  align-items: center;
}

.page-head {
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.page-head h2 {
  margin: 0 0 4px;
  font-size: 24px;
  font-weight: 650;
}

.page-head p {
  margin: 0;
  color: #667085;
}

.reference-panel {
  border: 1px solid #d9e2ec;
  background: #fff;
}

.panel-title {
  min-height: 48px;
  padding: 0 14px;
  border-bottom: 1px solid #e6edf3;
  display: flex;
  align-items: center;
  font-weight: 650;
}

.panel-title.plain {
  border-bottom: 0;
  padding-left: 0;
}

.upload-form {
  display: grid;
  grid-template-columns: repeat(4, minmax(180px, 1fr));
  gap: 0 12px;
  padding: 16px;
}

.notes-item,
.file-item,
.submit-item {
  grid-column: span 2;
}

.table-toolbar {
  justify-content: space-between;
  gap: 12px;
  padding: 0 14px;
  border-bottom: 1px solid #e6edf3;
}

.filters {
  gap: 8px;
  width: min(560px, 100%);
}

.section-gap {
  margin-top: 18px;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

@media (max-width: 980px) {
  .page-head,
  .table-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .upload-form {
    grid-template-columns: 1fr;
  }

  .notes-item,
  .file-item,
  .submit-item {
    grid-column: span 1;
  }
}
</style>
