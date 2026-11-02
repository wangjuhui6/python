### 安装流程

```
1. 创建项目目录
mkdir myproject && cd myproject

2. 创建虚拟环境
python -m venv venv

3. 激活虚拟环境
Windows:
venv\Scripts\activate
Unix/macOS:
source venv/bin/activate

4. 安装基础依赖
pip install flask requests pandas

5. 生成依赖文件
pip freeze > requirements.txt

6. 创建 .gitignore
echo "venv/
__pycache__/
*.pyc
.env" > .gitignore

# 安装 requirements.txt 中列出的所有包
pip install -r requirements.txt
```

### 启动

python start.py

### 打包

pyinstaller start.spec

### 调试

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='start',
)

### docker PostgreSQL 数据库 PostgreSQL + PostGIS

单机启动不会再从网上拉取镜像。本机已经有 `postgis/postgis:16-3.5` 就直接用；没有的话，从离线包导入。

有网络的机器上导出一次，把 tar 拷到单机：

```
docker pull postgis/postgis:16-3.5
docker save -o postgis-16-3.5.tar postgis/postgis:16-3.5
```

离线包放在下面任一位置（打包后放 exe 旁边）：

```
app/vendor/postgis/postgis-16-3.5.tar
```

单机需要已安装并启动 Docker Desktop。数据在 `postgis-data`，换机器时连这个目录一起拷。

进入容器 docker exec -it postgis bash
进入数据库 psql -U gis -d gisdb
检查 SELECT PostGIS_Version();


# pip install llama-cpp-python 安装问题

pip install https://github.com/abetlen/llama-cpp-python/releases/download/v0.3.19/llama_cpp_python-0.3.19-cp313-cp313-win_amd64.whl

或

pip install llama-cpp-python==0.3.19 --only-binary=:all: --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu