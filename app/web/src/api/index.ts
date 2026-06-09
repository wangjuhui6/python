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
  // 在发送请求之前做些什么
  return config;
}, function (error) {
  // 对请求错误做些什么
  return Promise.reject(error);
});

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
