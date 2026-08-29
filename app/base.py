import os
import sys

HOST = 'localhost'
PORT = 21006

def get_base_path():
  if getattr(sys, "frozen", False):
    return sys._MEIPASS
  return os.path.dirname(os.path.abspath(__file__))

def get_request_path(relative_path: str):
  return os.path.join(get_base_path(), relative_path)
