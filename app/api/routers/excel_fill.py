import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from pydantic import BaseModel

from utils.response import ResponseModel

router = APIRouter(prefix="/excel-fill", tags=["表格填写"])

_process: subprocess.Popen | None = None


def _script_path() -> Path | None:
  here = Path(__file__).resolve()
  candidates = [
    here.parents[3] / "excel_fill" / "fill_excel.py",
  ]
  if getattr(sys, "frozen", False):
    candidates.insert(0, Path(sys.executable).resolve().parent / "excel_fill" / "fill_excel.py")
  for path in candidates:
    if path.is_file():
      return path
  return None


def _pythonw() -> str:
  executable = Path(sys.executable)
  if executable.name.lower() in {"python.exe", "pythonw.exe"}:
    pythonw = executable.with_name("pythonw.exe")
    if pythonw.is_file():
      return str(pythonw)
  return sys.executable


def _launch_command() -> tuple[list[str], str] | None:
  if getattr(sys, "frozen", False):
    return [sys.executable, "--excel-fill"], str(Path(sys.executable).resolve().parent)
  script = _script_path()
  if script is None:
    return None
  return [_pythonw(), str(script)], str(script.parent)


@router.post("/open")
def open_fill_window():
  global _process
  if _process is not None and _process.poll() is None:
    return ResponseModel(code=200, msg="填写窗口已经打开", data={"already": True})

  launch = _launch_command()
  if launch is None:
    return ResponseModel(code=201, msg="找不到填写程序", data=None)
  command, workdir = launch

  flags = 0
  if os.name == "nt":
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
  env = os.environ.copy()
  # 单文件打包再启动自己时，必须清掉上一次解压留下的环境，否则子进程起不来
  if getattr(sys, "frozen", False):
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    env.pop("_MEIPASS2", None)
  try:
    _process = subprocess.Popen(
      command,
      cwd=workdir,
      env=env,
      creationflags=flags,
      close_fds=True,
    )
  except OSError as exc:
    return ResponseModel(code=201, msg=f"打不开填写窗口：{exc}", data=None)
  return ResponseModel(code=200, msg="已打开填写窗口", data={"already": False})


class ArrayTableBody(BaseModel):
  rows: list
  path: str


def _cell_value(value):
  if value is None or isinstance(value, (str, int, float, bool)):
    return value
  return json.dumps(value, ensure_ascii=False)


@router.post("/array-table")
def array_to_table(body: ArrayTableBody):
  rows = body.rows
  if not isinstance(rows, list) or not rows:
    return ResponseModel(code=201, msg="请提供至少一组数据", data=None)
  normalized = []
  width = 0
  for index, row in enumerate(rows, start=1):
    if not isinstance(row, list):
      return ResponseModel(code=201, msg=f"第 {index} 组不是数组", data=None)
    normalized.append(row)
    width = max(width, len(row))
  if width == 0:
    return ResponseModel(code=201, msg="这些数组都是空的", data=None)

  path = Path(body.path.strip())
  if path.suffix.lower() != ".xlsx":
    path = path.with_suffix(".xlsx")
  if not path.parent.is_dir():
    return ResponseModel(code=201, msg=f"保存目录不存在：{path.parent}", data=None)

  workbook = Workbook()
  sheet = workbook.active
  sheet.title = "Sheet1"
  for row_index, row in enumerate(normalized, start=1):
    for col_index in range(width):
      value = row[col_index] if col_index < len(row) else None
      sheet.cell(row_index, col_index + 1, _cell_value(value))
    sheet.row_dimensions[row_index].height = 18
  for col_index in range(1, width + 1):
    letter = get_column_letter(col_index)
    sheet.column_dimensions[letter].width = 18

  try:
    workbook.save(path)
  except PermissionError:
    return ResponseModel(code=201, msg="文件正在被占用，请先关闭后再生成", data=None)
  except OSError as exc:
    return ResponseModel(code=201, msg=f"保存失败：{exc}", data=None)
  finally:
    workbook.close()
  return ResponseModel(
    code=200,
    msg="已生成表格",
    data={"path": str(path), "rows": len(normalized), "columns": width},
  )
