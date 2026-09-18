import axios from 'axios';

const service = axios.create({
  baseURL: '/api',
  timeout: 1000 * 60 * 60 * 24,
  headers: {
    'Content-Type': 'application/json; charset=utf-8'
  }
})

// 请求拦截
service.interceptors.request.use(function (config) {
  if (config.data instanceof FormData) {
    const headers: any = config.headers
    if (headers && typeof headers.delete === 'function') {
      headers.delete('Content-Type')
    } else if (headers) {
      delete headers['Content-Type']
    }
  }
  return config
}, function (error) {
  return Promise.reject(error)
})

// 响应拦截器
service.interceptors.response.use(function (response) {
  // 2xx 范围内的状态码都会触发该函数。
  if (response.data.code !== 200) {
    return Promise.reject(response.data.msg)
  } else {
    return response.data.data
  }
}, function (error) {
  // 超出 2xx 范围的状态码都会触发该函数。
  return Promise.reject(error);
});

export default service
