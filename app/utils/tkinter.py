import tkinter as tk
from tkinter import filedialog

# 选择文件
def select_file(filetypes=None):
  root = tk.Tk()
  root.geometry("0x0")
  root.overrideredirect(True)

  root.attributes("-topmost", True)
  root.update()

  path = filedialog.askopenfilename(
    parent=root,
    filetypes=filetypes if filetypes else [("All Files", "*.*")]
  )

  root.destroy()

  return path

# 选择文件夹
def select_folder():
  root = tk.Tk()
  root.geometry("0x0")
  root.overrideredirect(True)
  root.attributes("-topmost", True)
  root.update()
  path = filedialog.askdirectory(
    parent=root,
  )
  root.destroy()
  return path

# 选择要保存的文件路径
def select_save_path(filetypes=None):
  root = tk.Tk()
  root.geometry("0x0")
  root.overrideredirect(True)
  root.attributes("-topmost", True)
  root.update()
  path = filedialog.asksaveasfilename(
    parent=root,
    filetypes=filetypes if filetypes else [("All Files", "*.*")]
  )
  root.destroy()
  return path
