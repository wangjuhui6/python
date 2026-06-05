import { createRouter, createWebHashHistory } from 'vue-router'

/**
 * 首先明确这个项目要做什么
 * 1. 短期目标简单的数据处理
 *   将矢量数据转换为其他格式
 * 2. 将pbf等格式数据进行处理
 * 3. 将各种类型的数据进行分类
 */

export const routes: any[] = [
  {
    path: '/data',
    name: 'data',
    redirect: '/data/vector',
    meta: {
      title: '数据处理'
    },
    children: [
      {
        path: '/data/vector',
        name: 'vector',
        meta: {
          title: '矢量数据处理'
        },
        component: () => import('../views/data/vector.vue')
      },
      {
        path: '/data/raster',
        name: 'raster',
        meta: {
          title: '栅格数据处理'
        },
        component: () => import('../views/data/raster.vue')
      }
    ]
  },
  {
    path: '/service',
    name: 'service',
    redirect: '/service/task',
    meta: {
      title: '服务管理'
    },
    children: [
      {
        path: '/service/task',
        name: 'task',
        meta: {
          title: '任务管理'
        },
        component: () => import('../views/service/task.vue')
      }
    ]
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      redirect: routes[0].children?.[0].path as string
    },
    {
      path: '/layout',
      component: () => import('../components/Layout/index.vue'),
      children: routes,
    }
  ],
})

export default router
