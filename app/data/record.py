# sqlite 数据库
import sys
from pathlib import Path
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        # 打包后写到 exe 同级目录，避免写入只读/临时解压目录
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent

# 获取项目根目录（开发）或 exe 所在目录（打包）
BASE_DIR = _get_base_dir()
# 获取数据库路径
db_path = BASE_DIR / 'sql' / 'record.db'
# 创建数据库目录
db_path.parent.mkdir(parents=True, exist_ok=True)

# 创建数据库引擎
engine = create_engine(f'sqlite:///{db_path.as_posix()}', echo=True)  # echo=True 打印SQL日志

# 3. 定义模型
Base = declarative_base()

class User(Base):
    __tablename__ = 'record'
    id = Column(Integer, primary_key=True, autoincrement=True)
    start_file = Column(String(255))
    end_file = Column(String(255))
    status = Column(Integer) # 0: 未完成 1: 已完成 2: 失败
    # name = Column(String(50))

# 4. 创建表
Base.metadata.create_all(engine)

# # 5. 使用数据库
Session = sessionmaker(bind=engine)
session = Session()

# # 插入测试数据
# user = User(start_file='张三', end_file='李四', status=1)
# session.add(user)
# session.commit()

# print(f"数据库文件位置: {Path(db_path).absolute()}")
