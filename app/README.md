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