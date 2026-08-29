# ui更改
# 线去重添加数据模式 添加一个 geojson合并 与 线去重一起的方案
# 接口复制 方便后续批量添加一些数据
# 文档读取
# 图片识别
# 路由更改 两套ui
# 白膜确认
# 倾斜摄影处理

<!-- fetch("http://localhost:21006/api/gdal/lineDeduplication", {
    method: "POST",
    headers: {
        "Content-Type": "application/json"
    },
    body: JSON.stringify({
        "inputPath": "C:/Users/13934/Downloads/geojson.json",
        "outputPath": "C:/Users/13934/Downloads/test.json"
    })
})

const params = new URLSearchParams({
  page: 1,
  limit: 10,
  keyword: '测试'
});
fetch(`http://localhost:21006/api/gdal/lineDeduplication?${params}`, {
    method: "GET"
}) -->