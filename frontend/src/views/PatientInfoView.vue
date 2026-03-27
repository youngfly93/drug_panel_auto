<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px">
      <h2 style="margin: 0">患者信息管理</h2>
      <el-button type="primary" @click="showAddDialog = true">新增患者</el-button>
    </div>

    <el-table :data="patients" stripe border v-loading="loading">
      <el-table-column prop="sample_id" label="样本编号" width="180" />
      <el-table-column prop="patient_name" label="患者姓名" width="120" />
      <el-table-column prop="gender" label="性别" width="80" />
      <el-table-column prop="age" label="年龄" width="80" />
      <el-table-column prop="hospital" label="送检医院" />
      <el-table-column prop="department" label="科室" width="120" />
      <el-table-column prop="collection_date" label="采样日期" width="120" />
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button text type="primary" @click="editPatient(row)">编辑</el-button>
          <el-popconfirm title="确认删除?" @confirm="handleDelete(row.sample_id)">
            <template #reference>
              <el-button text type="danger">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- Add/Edit Dialog -->
    <el-dialog
      v-model="showAddDialog"
      :title="editingId ? '编辑患者信息' : '新增患者信息'"
      width="600px"
    >
      <el-form label-width="100px">
        <el-form-item label="样本编号" required>
          <el-input v-model="form.sample_id" :disabled="!!editingId" placeholder="样本编号" />
        </el-form-item>
        <el-form-item label="患者姓名">
          <el-input v-model="form.patient_name" placeholder="患者姓名" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="性别">
              <el-radio-group v-model="form.gender">
                <el-radio value="男">男</el-radio>
                <el-radio value="女">女</el-radio>
              </el-radio-group>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="年龄">
              <el-input v-model="form.age" placeholder="年龄" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="病理号">
          <el-input v-model="form.pathology_id" placeholder="病理号" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="送检医院">
              <el-input v-model="form.hospital" placeholder="医院" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="科室">
              <el-input v-model="form.department" placeholder="科室" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="采样日期">
              <el-date-picker v-model="form.collection_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="接收日期">
              <el-date-picker v-model="form.receive_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { clinicalApi, type PatientInfo } from '@/api/clinical'

const patients = ref<PatientInfo[]>([])
const loading = ref(false)
const showAddDialog = ref(false)
const editingId = ref<string | null>(null)

const emptyForm = (): PatientInfo => ({
  sample_id: '',
  patient_name: '',
  gender: '',
  age: '',
  pathology_id: '',
  hospital: '',
  department: '',
  collection_date: '',
  receive_date: '',
})

const form = reactive<PatientInfo>(emptyForm())

async function fetchPatients() {
  loading.value = true
  try {
    patients.value = await clinicalApi.listPatients()
  } finally {
    loading.value = false
  }
}

function editPatient(row: PatientInfo) {
  editingId.value = row.sample_id
  Object.assign(form, row)
  showAddDialog.value = true
}

async function handleSave() {
  if (!form.sample_id) {
    ElMessage.warning('样本编号不能为空')
    return
  }
  try {
    if (editingId.value) {
      await clinicalApi.updatePatient(editingId.value, form)
    } else {
      await clinicalApi.createPatient(form)
    }
    ElMessage.success('保存成功')
    showAddDialog.value = false
    editingId.value = null
    Object.assign(form, emptyForm())
    await fetchPatients()
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '保存失败')
  }
}

async function handleDelete(sampleId: string) {
  try {
    await clinicalApi.deletePatient(sampleId)
    ElMessage.success('删除成功')
    await fetchPatients()
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '删除失败')
  }
}

onMounted(fetchPatients)
</script>
