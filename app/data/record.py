from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine
from pathlib import Path
from sqlalchemy.orm import sessionmaker

# 获取项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent
# 获取数据库路径
db_path = BASE_DIR / 'sql' / 'record.db'
# 创建数据库目录
# db_path.parent.mkdir(parents=True, exist_ok=True)

# 创建数据库引擎
engine = create_engine(f'sqlite:///{db_path}', echo=True)  # echo=True 打印SQL日志

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
