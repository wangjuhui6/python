from typing import Any
from pydantic import BaseModel

class ResponseModel(BaseModel):
  code: int = 200
  msg: str = "success"
  data: Any = None