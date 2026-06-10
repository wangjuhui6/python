from data.record import session, User

# 添加记录
def add_record(start_file: str, end_file: str, status: int):
  user = User(start_file=start_file, end_file=end_file, status=status)
  session.add(user)
  session.commit()
  return {
    "id": user.id,
    "start_file": user.start_file,
    "end_file": user.end_file,
    "status": user.status
  } if user else None
  
# 查询记录
def get_record(id: int):
  user = session.query(User).filter(User.id == id).first()
  return {
    "id": user.id,
    "start_file": user.start_file,
    "end_file": user.end_file,
    "status": user.status
  } if user else None

# 更新记录
def update_record(id: int, status: int):
  user = session.query(User).filter(User.id == id).first()
  user.status = status
  session.commit()
  return {
    "id": user.id,
    "start_file": user.start_file,
    "end_file": user.end_file,
    "status": user.status
  } if user else None

# 删除记录
def delete_record(id: int):
  user = session.query(User).filter(User.id == id).first()
  session.delete(user)
  session.commit()
  return user

# 查询所有记录
def get_all_record():
  users = session.query(User).all()
  return [
    {
      "id": user.id,
      "start_file": user.start_file,
      "end_file": user.end_file,
      "status": user.status
    } for user in users
  ] if users else []

# 查询未完成的记录
def get_uncompleted_record():
  users = session.query(User).filter(User.status == 0).all()
  return [
    {
      "id": user.id,
      "start_file": user.start_file,
      "end_file": user.end_file,
      "status": user.status
    } for user in users
  ] if users else []

# 查询完成的记录
def get_completed_record():
  users = session.query(User).filter(User.status == 1).all()
  return [
    {
      "id": user.id,
      "start_file": user.start_file,
      "end_file": user.end_file,
      "status": user.status
    } for user in users
  ] if users else []

# 查询记录数量
def get_record_count():
  count = session.query(User).count()
  return count

# 分页查询
def get_record_page(page: int = 1, page_size: int = 10):
  users = session.query(User).offset((page - 1) * page_size).limit(page_size).all()
  return [
    {
      "id": user.id,
      "start_file": user.start_file,
      "end_file": user.end_file,
      "status": user.status
    } for user in users
  ] if users else []