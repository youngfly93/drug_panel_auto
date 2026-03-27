<template>
  <div>
    <el-table
      v-if="data"
      :data="data.rows"
      size="small"
      stripe
      border
      max-height="400"
      style="width: 100%"
    >
      <el-table-column
        v-for="col in data.columns"
        :key="col"
        :prop="col"
        :label="col"
        min-width="120"
        show-overflow-tooltip
      />
    </el-table>
    <el-pagination
      v-if="data && data.total_rows > data.page_size"
      :current-page="page"
      :page-size="pageSize"
      :total="data.total_rows"
      layout="prev, pager, next, total"
      style="margin-top: 12px; justify-content: flex-end"
      @current-change="handlePageChange"
    />
    <el-skeleton v-if="loading" :rows="5" animated />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { excelApi, type SheetData } from '@/api/excel'

const props = defineProps<{
  uploadId: string
  sheetName: string
}>()

const data = ref<SheetData | null>(null)
const loading = ref(false)
const page = ref(1)
const pageSize = 50

async function fetchData() {
  loading.value = true
  try {
    data.value = await excelApi.getSheetData(props.uploadId, props.sheetName, page.value, pageSize)
  } finally {
    loading.value = false
  }
}

function handlePageChange(newPage: number) {
  page.value = newPage
  fetchData()
}

onMounted(fetchData)
</script>
