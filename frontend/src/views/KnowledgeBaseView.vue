<template>
  <div>
    <h2>知识库</h2>

    <!-- Stats overview -->
    <el-row :gutter="16" style="margin-bottom: 20px" v-if="kbStats">
      <el-col :span="8">
        <el-card shadow="hover" body-style="padding: 16px">
          <el-statistic title="基因知识库" :value="kbStats.gene_knowledge.total_rows" suffix="条" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover" body-style="padding: 16px">
          <el-statistic title="药物映射" :value="kbStats.drug_mappings.total_rows" suffix="条" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover" body-style="padding: 16px">
          <el-statistic title="免疫基因" :value="kbStats.immune_genes.total_rows" suffix="条" />
        </el-card>
      </el-col>
    </el-row>

    <el-tabs v-model="activeTab">
      <!-- Gene Knowledge -->
      <el-tab-pane label="基因知识库" name="genes">
        <div style="margin-bottom: 12px">
          <el-input
            v-model="geneSearch"
            placeholder="搜索基因名称..."
            clearable
            style="width: 300px"
            @clear="fetchGenes"
            @keyup.enter="fetchGenes"
          >
            <template #append>
              <el-button @click="fetchGenes">搜索</el-button>
            </template>
          </el-input>
        </div>
        <el-table :data="geneData.rows" stripe border v-loading="geneLoading" max-height="500">
          <el-table-column
            v-for="col in geneData.columns"
            :key="col"
            :prop="col"
            :label="col"
            min-width="150"
            show-overflow-tooltip
          />
        </el-table>
        <el-pagination
          v-if="geneData.total > genePageSize"
          :current-page="genePage"
          :page-size="genePageSize"
          :total="geneData.total"
          layout="prev, pager, next, total"
          style="margin-top: 12px"
          @current-change="(p: number) => { genePage = p; fetchGenes() }"
        />
      </el-tab-pane>

      <!-- Drug Mappings -->
      <el-tab-pane label="药物映射" name="drugs">
        <div style="margin-bottom: 12px">
          <el-input
            v-model="drugSearch"
            placeholder="搜索基因或药物..."
            clearable
            style="width: 300px"
            @clear="fetchDrugs"
            @keyup.enter="fetchDrugs"
          >
            <template #append>
              <el-button @click="fetchDrugs">搜索</el-button>
            </template>
          </el-input>
        </div>
        <el-table :data="drugData.rows" stripe border v-loading="drugLoading" max-height="500">
          <el-table-column
            v-for="col in drugData.columns"
            :key="col"
            :prop="col"
            :label="col"
            min-width="150"
            show-overflow-tooltip
          />
        </el-table>
        <el-pagination
          v-if="drugData.total > drugPageSize"
          :current-page="drugPage"
          :page-size="drugPageSize"
          :total="drugData.total"
          layout="prev, pager, next, total"
          style="margin-top: 12px"
          @current-change="(p: number) => { drugPage = p; fetchDrugs() }"
        />
      </el-tab-pane>

      <!-- Immune Genes -->
      <el-tab-pane label="免疫基因" name="immune">
        <el-table :data="immuneData.rows" stripe border v-loading="immuneLoading" max-height="500">
          <el-table-column
            v-for="col in immuneData.columns"
            :key="col"
            :prop="col"
            :label="col"
            min-width="150"
            show-overflow-tooltip
          />
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { knowledgeApi, type PaginatedTable, type KBStats } from '@/api/knowledge'

const activeTab = ref('genes')
const kbStats = ref<KBStats | null>(null)

// Gene
const geneData = ref<PaginatedTable>({ columns: [], rows: [], total: 0, page: 1, page_size: 50 })
const geneSearch = ref('')
const genePage = ref(1)
const genePageSize = 50
const geneLoading = ref(false)

// Drug
const drugData = ref<PaginatedTable>({ columns: [], rows: [], total: 0, page: 1, page_size: 50 })
const drugSearch = ref('')
const drugPage = ref(1)
const drugPageSize = 50
const drugLoading = ref(false)

// Immune
const immuneData = ref<PaginatedTable>({ columns: [], rows: [], total: 0, page: 1, page_size: 50 })
const immuneLoading = ref(false)

async function fetchGenes() {
  geneLoading.value = true
  try {
    geneData.value = await knowledgeApi.getGenes({ search: geneSearch.value, page: genePage.value, page_size: genePageSize })
  } finally {
    geneLoading.value = false
  }
}

async function fetchDrugs() {
  drugLoading.value = true
  try {
    drugData.value = await knowledgeApi.getDrugs({ search: drugSearch.value, page: drugPage.value, page_size: drugPageSize })
  } finally {
    drugLoading.value = false
  }
}

async function fetchImmune() {
  immuneLoading.value = true
  try {
    immuneData.value = await knowledgeApi.getImmuneGenes()
  } finally {
    immuneLoading.value = false
  }
}

onMounted(async () => {
  kbStats.value = await knowledgeApi.getStats()
  await Promise.all([fetchGenes(), fetchDrugs(), fetchImmune()])
})
</script>
