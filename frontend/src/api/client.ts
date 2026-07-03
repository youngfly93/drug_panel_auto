import axios from 'axios'

const client = axios.create({
  baseURL: '/api/v1',
  // 上传/识别是一次同步请求内串行完成读表、类型识别、患者富集等多步，
  // 冷启动或外部富集抖动时可能接近半分钟。30s 一刀切会让报告组上传偶发
  // "timeout of 30000ms exceeded"。放宽到 90s 覆盖这些慢路径（后端富集另有
  // 硬超时+不阻断兜底，见 inspect_excel）。
  timeout: 90000,
})

// Attach JWT token from localStorage
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Handle 401 → redirect to login
client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  },
)

export default client
